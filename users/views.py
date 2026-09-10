from datetime import date
from decimal import Decimal

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render

from payments.models import FeePayment
from students.models import Student

from .decorators import student_required
from .forms import LoginForm
from .models import User


def login_view(request):
    if request.user.is_authenticated:
        return redirect_for_role(request.user)

    selected_role = request.POST.get("role") or request.GET.get("role")
    if selected_role not in {"student", "teacher"}:
        return render(request, "users/login.html", {"mode": "portal"})

    form = LoginForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )
        if user is not None:
            login(request, user)
            if selected_role == "student" and user.role != User.Role.STUDENT:
                logout(request)
                error = "Invalid username or password."
            elif selected_role == "teacher" and user.role != User.Role.ADMIN:
                logout(request)
                error = "Invalid username or password."
            else:
                return redirect_for_role(user)
        error = "Invalid username or password."

    return render(
        request,
        "users/login.html",
        {"form": form, "error": error, "mode": selected_role},
    )


def logout_view(request):
    logout(request)
    return redirect("login")


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return redirect_for_role(request.user)


@login_required
def admin_dashboard(request):
    if request.user.role != User.Role.ADMIN:
        return redirect("student-dashboard")

    students = Student.objects.annotate(
        paid_total=Coalesce(
            Sum("payments__amount_paid"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )
    total_students = students.count()
    total_collected = students.aggregate(total=Sum("paid_total"))["total"] or Decimal("0.00")
    total_fee = students.aggregate(total=Sum("total_fee"))["total"] or Decimal("0.00")
    total_pending = total_fee - total_collected
    today = date.today()
    this_month_collection = (
        FeePayment.objects.filter(payment_date__year=today.year, payment_date__month=today.month)
        .aggregate(total=Sum("amount_paid"))["total"]
        or Decimal("0.00")
    )

    monthly_rows = (
        FeePayment.objects.values("payment_date__year", "payment_date__month")
        .annotate(total=Sum("amount_paid"))
        .order_by("payment_date__year", "payment_date__month")
    )
    month_labels = []
    month_values = []
    for row in monthly_rows:
        month = date(row["payment_date__year"], row["payment_date__month"], 1)
        month_labels.append(month.strftime("%b %Y"))
        month_values.append(str(row["total"] or Decimal("0.00")))

    recent_payments = FeePayment.objects.select_related("student").order_by(
        "-payment_date", "-id"
    )[:5]
    return render(
        request,
        "users/admin_dashboard.html",
        {
            "total_students": total_students,
            "total_collected": total_collected,
            "total_pending": total_pending,
            "this_month_collection": this_month_collection,
            "month_labels": month_labels,
            "month_values": month_values,
            "recent_payments": recent_payments,
        },
    )


@login_required
@student_required
def student_dashboard(request):
    student = get_student_or_redirect(request)
    if student is None:
        return redirect("student-profile-missing")
    paid = student.paid
    pending = student.pending
    progress = min((paid / student.total_fee * 100) if student.total_fee else Decimal("0"), Decimal("100"))
    return render(
        request,
        "users/student_dashboard.html",
        {"student": student, "paid": paid, "pending": pending, "progress": progress},
    )


@login_required
@student_required
def payment_history(request):
    student = get_student_or_redirect(request)
    if student is None:
        return redirect("student-profile-missing")
    payments = student.payments.order_by("-payment_date", "-id")
    return render(request, "users/payment_history.html", {"student": student, "payments": payments})


@login_required
@student_required
def student_profile(request):
    student = get_student_or_redirect(request)
    if student is None:
        return redirect("student-profile-missing")
    return render(request, "users/student_profile.html", {"student": student})


@login_required
@student_required
def student_password_change(request):
    student = get_student_or_redirect(request)
    if student is None:
        return redirect("student-profile-missing")
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])
        update_session_auth_hash(request, user)
        return redirect("student-profile")
    return render(request, "users/student_profile.html", {"student": student, "form": form})


@login_required
@student_required
def student_profile_missing(request):
    return render(request, "users/student_profile_missing.html")


def get_student_or_redirect(request):
    try:
        return Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return None


def redirect_for_role(user):
    if user.role == User.Role.ADMIN:
        return redirect("admin-dashboard")
    if user.must_change_password:
        return redirect("student-password-change")
    return redirect("student-dashboard")
