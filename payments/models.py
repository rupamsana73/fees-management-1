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
    remarks = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.student.name} - {self.month} - {self.amount_paid}"
