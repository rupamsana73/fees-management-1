from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum

from .utils import generate_unique_student_id


class Student(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING = "pending", "Pending"
        INACTIVE = "inactive", "Inactive"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    student_id = models.CharField(max_length=50, unique=True, blank=True)
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    course = models.CharField(max_length=255, blank=True)
    total_fee = models.DecimalField(max_digits=12, decimal_places=2)
    admission_date = models.DateField(default=date.today, blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    def __str__(self):
        return f"{self.name} ({self.student_id})"

    def save(self, *args, **kwargs):
        if not self.student_id:
            self.student_id = generate_unique_student_id()
        super().save(*args, **kwargs)

    @property
    def paid(self):
        if not hasattr(self, "_paid_total"):
            self._paid_total = self.payments.aggregate(total=Sum("amount_paid"))["total"]
        return self._paid_total or Decimal("0.00")

    @property
    def pending(self):
        return self.total_fee - self.paid
