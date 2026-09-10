from datetime import date
from decimal import Decimal

from django.db.models import Sum

from payments.models import FeePayment


def admin_context(request):
    if not request.user.is_authenticated or getattr(request.user, "role", None) != "admin":
        return {}
    today = date.today()
    collected = (
        FeePayment.objects.filter(payment_date__year=today.year, payment_date__month=today.month)
        .aggregate(total=Sum("amount_paid"))["total"]
        or Decimal("0.00")
    )
    return {"this_month_collection": collected}