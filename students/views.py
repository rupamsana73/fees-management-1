from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Prefetch, Sum, Value
from django.db.models.functions import Coalesce
from decimal import Decimal
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
import logging

from users.models import User
from users.audit import record_audit
from users.models import AuditLog
from payments.models import Notification
from payments.notifications import NoPendingFeeError, ReminderCooldownError, send_fee_reminder

from .decorators import admin_required
from .forms import AddStudentForm, StudentForm
from .models import Student
from .utils import create_student_with_account, generate_temporary_password


logger = logging.getLogger(__name__)


def _send_credentials_email(request, student, username, password):
    context = {
        "student_name": student.name,
        "student_id": student.student_id,
        "username": username,
        "temporary_password": password,
        "login_url": request.build_absolute_uri("/login/"),
        "client_name": "Debasis Kamila",
    }
    html_content = render_to_string("emails/student_credentials.html", context)
    text_content = render_to_string("emails/student_credentials.txt", context)
    email = EmailMultiAlternatives(
        "FeeFlow - Your Student Account Credentials",
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        [student.email],
    )
    email.attach_alternative(html_content, "text/html")
    sent_count = email.send(fail_silently=False)
    if sent_count != 1:
        raise RuntimeError("The email backend did not accept the credential email.")
    logger.info(
        "Student credential email accepted by the email backend: student_id=%s recipient=%s",
        student.student_id,
        student.email,
    )
    return sent_count


@login_required
@admin_required
def student_list(request):
    students = student_balance_queryset()
    credentials = request.session.pop("created_student_credentials", None)
    return render(
        request,
        "students/student_list.html",
        {
            "students": students,
            "add_form": AddStudentForm(),
            "created_student_credentials": credentials,
            "show_credential_modal": bool(credentials),
        },
    )


def student_balance_queryset():
    return Student.objects.select_related("user").annotate(
        paid_total=Coalesce(
            Sum("payments__amount_paid"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).annotate(
        pending_total=ExpressionWrapper(
            F("total_fee") - F("paid_total"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).order_by("name")


def _student_created_message(request):
    credentials = request.session.pop("created_student_credentials", None)
    if credentials:
        request.session["student_created_credentials"] = credentials
        return credentials
    return None


@login_required
@admin_required
def pending_fees(request):
    reminder_history = Notification.objects.filter(
        notification_type=Notification.NotificationType.FEE_REMINDER
    ).order_by("-sent_at")
    students = student_balance_queryset().filter(pending_total__gt=0).order_by("-pending_total").prefetch_related(
        Prefetch("notifications", queryset=reminder_history, to_attr="reminder_history")
    )
    for student in students:
        student.last_reminder = student.reminder_history[0] if student.reminder_history else None
    return render(request, "students/pending_fees.html", {"students": students})


@login_required
@admin_required
@require_POST
def student_send_fee_reminder(request, pk):
    student = get_object_or_404(Student.objects.select_related("user"), pk=pk)
    try:
        notification = send_fee_reminder(student, force=request.POST.get("override") == "1")
    except NoPendingFeeError:
        messages.info(request, "This student has no pending fee, so no reminder was sent.")
    except ReminderCooldownError:
        messages.warning(
            request,
            "A reminder was already sent within the cooldown period. Use resend to override the cooldown.",
        )
    else:
        if notification.status == Notification.Status.SENT:
            record_audit(request, AuditLog.Action.REMINDER_SENT, target=student, description="Fee reminder sent")
            messages.success(request, "Fee reminder sent successfully.")
        else:
            messages.error(request, "Fee reminder could not be sent. The failure was recorded for retry.")
    return redirect("pending-fees")


@login_required
@admin_required
def student_add(request):
    form = AddStudentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        payload = {
            "name": form.cleaned_data["name"],
            "email": form.cleaned_data["email"],
            "phone": form.cleaned_data.get("phone", ""),
            "course": form.cleaned_data.get("course", ""),
            "total_fee": form.cleaned_data["total_fee"],
            "admission_date": form.cleaned_data.get("admission_date"),
            "status": form.cleaned_data.get("status", Student.Status.ACTIVE),
        }
        created_credentials = None

        try:
            with transaction.atomic():
                student, username, password = create_student_with_account(payload)
                created_credentials = {
                    "pk": student.pk,
                    "student_id": student.student_id,
                    "username": username,
                    "password": password,
                    "email": student.email,
                }
        except Exception:
            messages.error(request, "Student creation failed. Please review the details and try again.")
            students = student_balance_queryset()
            return render(
                request,
                "students/student_list.html",
                {"students": students, "add_form": form, "open_add_modal": True},
            )

        record_audit(request, AuditLog.Action.STUDENT_CREATED, target=student, description="Student record created")

        try:
            logger.info(
                "Calling credential email helper for create: student_id=%s recipient=%s",
                student.student_id,
                student.email,
            )
            send_count = _send_credentials_email(request, student, username, password)
            logger.info(
                "Credential email helper completed for create: send_count=%s recipient=%s",
                send_count,
                student.email,
            )
            messages.success(request, "Student created successfully.")
        except Exception:
            logger.exception(
                "Student creation email failed: student_pk=%s student_id=%s recipient=%s action=create",
                student.pk,
                student.student_id,
                student.email,
            )
            request.session["created_student_credentials"] = created_credentials
            messages.warning(
                request,
                "Student created successfully, but the login credentials could not be emailed. Please copy/download the credentials and send them manually.",
            )
            return redirect("student-list")

        request.session["created_student_credentials"] = created_credentials
        return redirect("student-list")

    students = student_balance_queryset()
    if request.method == "POST" and form.errors:
        return render(
            request,
            "students/student_list.html",
            {"students": students, "add_form": form, "open_add_modal": True},
        )
    return render(
        request,
        "students/student_list.html",
        {"students": students, "add_form": form, "open_add_modal": True},
    )


@login_required
@admin_required
@require_POST
def student_resend_credentials(request, pk):
    logger.info(
        "Student credential resend request received: method=%s authenticated_username=%s student_pk=%s",
        request.method,
        request.user.get_username(),
        pk,
    )
    student = get_object_or_404(Student.objects.select_related("user"), pk=pk)
    logger.info(
        "Student credential resend target loaded: student_id=%s recipient=%s",
        student.student_id,
        student.email,
    )
    password = generate_temporary_password(student.name, student.student_id)

    with transaction.atomic():
        student.user.must_change_password = True
        student.user.set_password(password)
        student.user.save(update_fields=["password", "must_change_password"])

    credentials = {
        "pk": student.pk,
        "student_id": student.student_id,
        "username": student.user.username,
        "password": password,
        "email": student.email,
    }
    try:
        logger.info(
            "Calling credential email helper for resend: student_id=%s recipient=%s",
            student.student_id,
            student.email,
        )
        send_count = _send_credentials_email(request, student, student.user.username, password)
        logger.info(
            "Credential email helper completed for resend: send_count=%s recipient=%s",
            send_count,
            student.email,
        )
    except Exception:
        logger.exception(
            "Student credential resend failed: student_pk=%s student_id=%s recipient=%s action=resend",
            student.pk,
            student.student_id,
            student.email,
        )
        request.session["created_student_credentials"] = credentials
        messages.warning(
            request,
            "Email delivery failed. The new password was saved; please check the Brevo SMTP configuration and retry.",
        )
    else:
        request.session["created_student_credentials"] = credentials
        messages.success(request, "A new temporary password was emailed successfully.")

    record_audit(request, AuditLog.Action.CREDENTIALS_RESENT, target=student, description="Student credentials resend requested")

    return redirect("student-list")


@login_required
@admin_required
def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk)
    old_status = student.status
    form = StudentForm(request.POST or None, instance=student)
    if request.method == "POST" and form.is_valid():
        form.save()
        record_audit(request, AuditLog.Action.STUDENT_UPDATED, target=student, description="Student record updated")
        if old_status != student.status:
            record_audit(request, AuditLog.Action.STUDENT_STATUS_CHANGED, target=student, description="Student status changed")
        messages.success(request, "Student updated successfully.")
        return redirect("student-list")

    return render(request, "students/student_form.html", {"form": form, "title": "Edit Student"})


@login_required
@admin_required
@require_POST
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    student.user.delete()
    messages.success(request, "Student deleted successfully.")
    return redirect("student-list")
