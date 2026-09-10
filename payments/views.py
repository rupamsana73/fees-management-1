from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render

from students.decorators import admin_required
from students.models import Student

from .forms import FeePaymentForm
from .models import FeePayment


@login_required
@admin_required
def payment_add(request):
    form = FeePaymentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Payment added successfully.")
        return redirect("student-list")

    students = Student.objects.annotate(
        paid_total=Coalesce(
            Sum("payments__amount_paid"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )
    for student in students:
        student.pending_total = student.total_fee - student.paid_total
    return render(request, "payments/payment_form.html", {"form": form, "students": students})


@login_required
@admin_required
def reports(request):
    monthly_rows = (
        FeePayment.objects.values("payment_date__year", "payment_date__month")
        .annotate(total=Sum("amount_paid"))
        .order_by("payment_date__year", "payment_date__month")
    )
    monthly_collections = [
        {
            "label": date(row["payment_date__year"], row["payment_date__month"], 1).strftime("%B %Y"),
            "total": row["total"] or Decimal("0.00"),
        }
        for row in monthly_rows
    ]
    students = Student.objects.annotate(
        paid_total=Coalesce(
            Sum("payments__amount_paid"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )
    collected = students.aggregate(total=Sum("paid_total"))["total"] or Decimal("0.00")
    total_fees = students.aggregate(total=Sum("total_fee"))["total"] or Decimal("0.00")
    return render(
        request,
        "payments/reports.html",
        {
            "monthly_collections": monthly_collections,
            "report_collected": collected,
            "report_pending": total_fees - collected,
        },
    )
