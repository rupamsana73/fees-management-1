from django.contrib import admin

from .models import FeePayment


@admin.register(FeePayment)
class FeePaymentAdmin(admin.ModelAdmin):
    list_display = ("student", "amount_paid", "payment_date", "month")
    list_filter = ("payment_date", "month")
    search_fields = ("student__name", "student__student_id")
