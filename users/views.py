from datetime import date
from decimal import Decimal

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.paginator import Paginator
from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from payments.models import FeePayment
from students.models import Student

from .audit import record_audit
from students.decorators import admin_only

from .decorators import student_required
from .forms import AdminPasswordResetForm, LoginForm, TeacherCreateForm, TeacherUpdateForm
from .models import AuditLog, User


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
                record_audit(request, AuditLog.Action.LOGIN_FAILURE, description="Role-mismatched login rejected")
                logout(request)
                error = "Invalid username or password."
            elif selected_role == "teacher" and user.role not in {User.Role.ADMIN, User.Role.TEACHER}:
                record_audit(request, AuditLog.Action.LOGIN_FAILURE, description="Role-mismatched login rejected")
                logout(request)
                error = "Invalid username or password."
            else:
                record_audit(request, AuditLog.Action.LOGIN_SUCCESS, target=user, description="User logged in")
                return redirect_for_role(user)
        else:
            record_audit(request, AuditLog.Action.LOGIN_FAILURE, description="Login credentials rejected")
        error = "Invalid username or password."

    return render(
        request,
        "users/login.html",
        {"form": form, "error": error, "mode": selected_role},
    )


def logout_view(request):
    if request.user.is_authenticated:
        record_audit(request, AuditLog.Action.LOGOUT, target=request.user, description="User logged out")
    logout(request)
    return redirect("login")


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return redirect_for_role(request.user)


@login_required
def admin_dashboard(request):
    if request.user.role not in {User.Role.ADMIN, User.Role.TEACHER}:
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
        record_audit(request, AuditLog.Action.PASSWORD_CHANGED, target=user, description="Student password changed")
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
    if user.role in {User.Role.ADMIN, User.Role.TEACHER}:
        return redirect("admin-dashboard")
    if user.must_change_password:
        return redirect("student-password-change")
    return redirect("student-dashboard")


@login_required
@admin_only
def teacher_list(request):
    staff_users = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.TEACHER]).order_by("username")
    return render(request, "users/teacher_list.html", {"staff_users": staff_users})


@login_required
@admin_only
def teacher_add(request):
    form = TeacherCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        teacher = form.save()
        record_audit(request, AuditLog.Action.TEACHER_CREATED, target=teacher, description="Teacher account created")
        return redirect("teacher-list")
    return render(request, "users/teacher_form.html", {"form": form, "title": "Add Teacher"})


@login_required
@admin_only
def teacher_edit(request, pk):
    teacher = get_object_or_404(User, pk=pk)
    if teacher.role not in {User.Role.ADMIN, User.Role.TEACHER}:
        return redirect("teacher-list")
    old_role = teacher.role
    old_active = teacher.is_active
    form = TeacherUpdateForm(request.POST or None, instance=teacher)
    if request.method == "POST" and form.is_valid():
        teacher = form.save()
        record_audit(request, AuditLog.Action.TEACHER_UPDATED, target=teacher, description="Staff account updated")
        if old_role != teacher.role or old_active != teacher.is_active:
            record_audit(request, AuditLog.Action.TEACHER_STATUS_CHANGED, target=teacher, description="Staff role or active status changed")
        return redirect("teacher-list")
    return render(request, "users/teacher_form.html", {"form": form, "title": "Edit Staff Account", "teacher": teacher})


@login_required
@admin_only
def teacher_password_reset(request, pk):
    teacher = get_object_or_404(User, pk=pk)
    if teacher.role not in {User.Role.ADMIN, User.Role.TEACHER}:
        return redirect("teacher-list")
    form = AdminPasswordResetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        teacher.set_password(form.cleaned_data["new_password1"])
        teacher.must_change_password = False
        teacher.save(update_fields=["password", "must_change_password"])
        record_audit(request, AuditLog.Action.PASSWORD_CHANGED, target=teacher, description="Staff password reset by admin")
        return redirect("teacher-list")
    return render(request, "users/teacher_password_reset.html", {"form": form, "teacher": teacher})


@login_required
@admin_only
def audit_log(request):
    logs = AuditLog.objects.select_related("user")
    selected_user = request.GET.get("user", "")
    selected_action = request.GET.get("action", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    if selected_user:
        logs = logs.filter(user_id=selected_user)
    if selected_action:
        logs = logs.filter(action=selected_action)
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)
    page = Paginator(logs, 25).get_page(request.GET.get("page"))
    return render(request, "users/audit_log.html", {
        "page_obj": page,
        "staff_users": User.objects.filter(role__in=[User.Role.ADMIN, User.Role.TEACHER]).order_by("username"),
        "audit_actions": AuditLog.Action.choices,
        "selected_user": selected_user,
        "selected_action": selected_action,
        "date_from": date_from,
        "date_to": date_to,
    })
