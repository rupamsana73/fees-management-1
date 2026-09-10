from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce

from payments.models import Notification
from payments.notifications import ReminderCooldownError, send_fee_reminder
from students.models import Student
from users.audit import record_audit
from users.models import AuditLog


class Command(BaseCommand):
    help = "Send fee reminders to students with pending balances."

    def handle(self, *args, **options):
        students = Student.objects.annotate(
            paid_total=Coalesce(
                Sum("payments__amount_paid"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        ).filter(total_fee__gt=0, paid_total__lt=F("total_fee")).order_by("pk")
        sent = skipped = failed = 0

        for student in students.iterator():
            student._paid_total = student.paid_total
            try:
                notification = send_fee_reminder(student)
            except ReminderCooldownError:
                skipped += 1
                self.stdout.write(f"Skipped {student.student_id}: cooldown active")
                continue
            except Exception:
                failed += 1
                self.stdout.write(self.style.ERROR(f"Failed {student.student_id}: unexpected reminder error"))
                continue

            if notification.status == Notification.Status.SENT:
                sent += 1
                record_audit(None, AuditLog.Action.REMINDER_SENT, target=student, description="Automated fee reminder sent")
                self.stdout.write(f"Sent reminder to {student.student_id}")
            else:
                failed += 1
                self.stdout.write(self.style.ERROR(f"Failed {student.student_id}: delivery failed"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Fee reminders complete: sent={sent}, skipped={skipped}, failed={failed}"
            )
        )
