from datetime import date
from decimal import Decimal

from django.db import models

from students.models import Student


class FeePayment(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(auto_now_add=True)
    month = models.CharField(max_length=50)
    payment_method = models.CharField(max_length=50, blank=True, default="Cash")
    transaction_id = models.CharField(max_length=120, blank=True, default="")
    remarks = models.CharField(max_length=255, blank=True)
    receipt_number = models.CharField(max_length=50, unique=True, blank=True, db_index=True)

    def __str__(self):
        return f"{self.student.name} - {self.month} - {self.amount_paid}"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = self.generate_receipt_number()
        super().save(*args, **kwargs)

    @classmethod
    def generate_receipt_number(cls):
        year = date.today().year
        prefix = f"FF-{year}-"
        latest = (
            cls.objects.filter(receipt_number__startswith=prefix)
            .order_by("-receipt_number")
            .values_list("receipt_number", flat=True)
            .first()
        )
        next_number = 1
        if latest:
            try:
                next_number = int(latest.split("-")[-1]) + 1
            except ValueError:
                next_number = 1
        return f"{prefix}{next_number:06d}"

    @property
    def total_fee(self):
        return self.student.total_fee

    @property
    def previous_paid(self):
        return (
            self.student.payments.filter(
                models.Q(payment_date__lt=self.payment_date)
                | (models.Q(payment_date=self.payment_date) & models.Q(pk__lt=self.pk))
            ).aggregate(total=models.Sum("amount_paid"))["total"]
            or Decimal("0.00")
        )

    @property
    def total_paid_after_payment(self):
        return self.previous_paid + self.amount_paid

    @property
    def remaining_balance(self):
        return max(self.total_fee - self.total_paid_after_payment, Decimal("0.00"))

    @property
    def payment_status(self):
        if self.total_paid_after_payment >= self.total_fee:
            return "PAID"
        if self.total_paid_after_payment > Decimal("0.00"):
            return "PARTIAL"
        return "PENDING"

    @property
    def formatted_amount(self):
        return f"₹{self.amount_paid:,.2f}"


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        PAYMENT_CONFIRMATION = "PAYMENT_CONFIRMATION", "Payment Confirmation"
        FEE_REMINDER = "FEE_REMINDER", "Fee Reminder"

    class Status(models.TextChoices):
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=30, choices=NotificationType.choices)
    recipient_email = models.EmailField()
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    related_payment = models.ForeignKey(
        FeePayment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    error_message = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ("-sent_at", "-pk")

    def __str__(self):
        return f"{self.get_notification_type_display()} - {self.student.student_id} - {self.status}"
