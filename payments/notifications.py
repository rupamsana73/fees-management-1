import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import FeePayment, Notification


logger = logging.getLogger(__name__)


class ReminderCooldownError(Exception):
    def __init__(self, notification):
        self.notification = notification
        super().__init__("A fee reminder was already sent during the cooldown period.")


class NoPendingFeeError(Exception):
    pass


def _safe_error_message(error):
    return f"{type(error).__name__}: email delivery failed"


def _send_notification(*, student, notification_type, subject, context, related_payment=None):
    notification = Notification.objects.create(
        student=student,
        notification_type=notification_type,
        recipient_email=student.email,
        status=Notification.Status.FAILED,
        related_payment=related_payment,
    )
    try:
        text_content = render_to_string(context["text_template"], context)
        html_content = render_to_string(context["html_template"], context)
        email = EmailMultiAlternatives(
            subject,
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [student.email],
        )
        email.attach_alternative(html_content, "text/html")
        sent_count = email.send(fail_silently=False)
        if sent_count != 1:
            raise RuntimeError("Email backend did not accept the message.")
    except Exception as error:
        notification.error_message = _safe_error_message(error)
        notification.save(update_fields=["error_message"])
        logger.warning(
            "FeeFlow notification failed: type=%s student_id=%s error_type=%s",
            notification_type,
            student.student_id,
            type(error).__name__,
        )
        return notification

    notification.status = Notification.Status.SENT
    notification.error_message = ""
    notification.save(update_fields=["status", "error_message"])
    logger.info(
        "FeeFlow notification sent: type=%s student_id=%s",
        notification_type,
        student.student_id,
    )
    return notification


def send_payment_confirmation(payment):
    student = payment.student
    context = {
        "student_name": student.name,
        "student_id": student.student_id,
        "payment_amount": payment.amount_paid,
        "payment_date": payment.payment_date,
        "payment_method": payment.payment_method or "Cash",
        "receipt_number": payment.receipt_number,
        "total_fee": student.total_fee,
        "total_paid": payment.total_paid_after_payment,
        "pending_amount": payment.remaining_balance,
        "client_name": "Debasis Kamila",
        "text_template": "emails/payment_confirmation.txt",
        "html_template": "emails/payment_confirmation.html",
    }
    return _send_notification(
        student=student,
        notification_type=Notification.NotificationType.PAYMENT_CONFIRMATION,
        subject="FeeFlow - Payment Confirmation",
        context=context,
        related_payment=payment,
    )


def send_fee_reminder(student, *, force=False):
    pending_amount = max(student.pending, Decimal("0.00"))
    if pending_amount <= Decimal("0.00"):
        raise NoPendingFeeError("Student has no pending fee.")

    cooldown_start = timezone.now() - timedelta(days=settings.FEE_REMINDER_COOLDOWN_DAYS)
    latest_sent = student.notifications.filter(
        notification_type=Notification.NotificationType.FEE_REMINDER,
        status=Notification.Status.SENT,
        sent_at__gte=cooldown_start,
    ).first()
    if latest_sent and not force:
        raise ReminderCooldownError(latest_sent)

    context = {
        "student_name": student.name,
        "student_id": student.student_id,
        "total_fee": student.total_fee,
        "amount_paid": student.paid,
        "pending_amount": pending_amount,
        "client_name": "Debasis Kamila",
        "text_template": "emails/fee_reminder.txt",
        "html_template": "emails/fee_reminder.html",
    }
    return _send_notification(
        student=student,
        notification_type=Notification.NotificationType.FEE_REMINDER,
        subject="FeeFlow - Fee Payment Reminder",
        context=context,
    )
