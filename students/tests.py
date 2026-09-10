from unittest.mock import patch

from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from fee_management_project import settings as project_settings
from payments.models import FeePayment
from students.forms import AddStudentForm
from students.models import Student
from students.utils import create_student_with_account, generate_unique_student_id, generate_unique_username
from users.models import User
from students.views import _send_credentials_email


class StudentCredentialGenerationTests(TestCase):
    def test_add_form_omits_manual_credentials(self):
        self.assertNotIn("username", AddStudentForm().fields)
        self.assertNotIn("password", AddStudentForm().fields)

    def test_brevo_smtp_settings_are_environment_driven(self):
        self.assertEqual(settings.EMAIL_HOST, "smtp-relay.brevo.com")
        self.assertEqual(settings.EMAIL_PORT, 587)
        self.assertEqual(project_settings.EMAIL_BACKEND, "django.core.mail.backends.smtp.EmailBackend")
        self.assertEqual(settings.DEFAULT_FROM_EMAIL, "debasiskamila2026@gmail.com")

    def test_generate_unique_student_id_uses_highest_suffix(self):
        user_one = User.objects.create_user(username="teacher1", password="pass123")
        user_two = User.objects.create_user(username="teacher2", password="pass123")
        Student.objects.create(user=user_one, student_id="STU102", name="Alpha Student", total_fee=100)
        Student.objects.create(user=user_two, student_id="STU100", name="Beta Student", total_fee=100)

        self.assertEqual(generate_unique_student_id(), "STU103")

class StudentOnboardingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="teacher",
            password="TeacherPass123!",
            role=User.Role.ADMIN,
        )
        self.client.force_login(self.admin)

    def valid_payload(self, **overrides):
        payload = {
            "name": "Asha Sen",
            "email": "asha@example.com",
            "phone": "555-0100",
            "course": "Computer Science",
            "total_fee": "1200.00",
            "admission_date": "2026-09-09",
            "status": "active",
        }
        payload.update(overrides)
        return payload

    @patch("students.views._send_credentials_email")
    def test_student_creation_creates_account_and_one_time_credentials(self, send_email):
        response = self.client.post(reverse("student-add"), self.valid_payload())

        self.assertEqual(response.status_code, 302)
        student = Student.objects.get(email="asha@example.com")
        password = self.client.session["created_student_credentials"]["password"]
        self.assertTrue(student.user.check_password(password))
        self.assertNotEqual(student.user.password, password)
        self.assertEqual(len(password), 12)
        self.assertEqual(self.client.session["created_student_credentials"]["pk"], student.pk)
        send_email.assert_called_once()

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_student_creation_sends_branded_email(self):
        response = self.client.post(reverse("student-add"), self.valid_payload())

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "FeeFlow - Your Student Account Credentials")
        self.assertIn("Password:", mail.outbox[0].body)
        self.assertEqual(len(mail.outbox[0].alternatives), 1)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_creation_email_and_saved_email_match_student_c(self):
        response = self.client.post(
            reverse("student-add"),
            self.valid_payload(email="student.c@example.com"),
        )

        self.assertEqual(response.status_code, 302)
        student = Student.objects.get(email="student.c@example.com")
        self.assertEqual(student.email, "student.c@example.com")
        self.assertEqual(mail.outbox[-1].to, [student.email])
        self.assertIn(student.student_id, mail.outbox[-1].body)
        self.assertIn(student.user.username, mail.outbox[-1].body)
        self.assertIn(
            self.client.session["created_student_credentials"]["password"].replace("&", "&amp;"),
            mail.outbox[-1].body,
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_same_credential_email_helper_accepts_one_message(self):
        student, username, password = create_student_with_account(self.valid_payload())
        request = self.client.get(reverse("student-list")).wsgi_request

        self.assertEqual(_send_credentials_email(request, student, username, password), 1)
        self.assertEqual(mail.outbox[-1].to, ["asha@example.com"])

    @patch("students.views.EmailMultiAlternatives.send", return_value=0)
    def test_zero_message_result_is_reported_as_email_failure(self, send_email):
        student, username, password = create_student_with_account(self.valid_payload())
        request = self.client.get(reverse("student-list")).wsgi_request

        with self.assertRaisesMessage(RuntimeError, "did not accept"):
            _send_credentials_email(request, student, username, password)
        send_email.assert_called_once_with(fail_silently=False)

    @patch("students.views.EmailMultiAlternatives.send", side_effect=RuntimeError("SMTP unavailable"))
    def test_email_failure_keeps_student_and_exposes_credentials_once(self, send_email):
        response = self.client.post(reverse("student-add"), self.valid_payload())

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Student.objects.filter(email="asha@example.com").exists())
        list_response = self.client.get(reverse("student-list"))
        self.assertContains(list_response, "Student created successfully, but the login credentials could not be emailed.")
        self.assertContains(list_response, "Student Created Successfully")
        self.assertNotContains(self.client.get(reverse("student-list")), "Student Created Successfully")
        send_email.assert_called_once()

    def test_duplicate_email_is_rejected_without_creating_account(self):
        user, _, _ = create_student_with_account(self.valid_payload())
        response = self.client.post(
            reverse("student-add"),
            self.valid_payload(name="Another Student"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A student with this email already exists.")
        self.assertEqual(Student.objects.filter(email="asha@example.com").count(), 1)
        self.assertEqual(User.objects.filter(email="asha@example.com").count(), 1)

    def test_username_is_generated_and_unique_from_full_name(self):
        first, _, _ = create_student_with_account(self.valid_payload())
        self.assertEqual(first.user.username, "asha.sen")
        self.assertEqual(generate_unique_username("Asha Sen"), "asha.sen2")

        response = self.client.post(
            reverse("student-add"),
            self.valid_payload(name="Asha Sen", email="asha2@example.com"),
        )

        self.assertEqual(response.status_code, 302)
        second = Student.objects.get(email="asha2@example.com")
        self.assertEqual(second.user.username, "asha.sen2")

    @patch("students.views._send_credentials_email")
    def test_resend_rotates_password_and_keeps_student_on_email_failure(self, send_email):
        send_email.side_effect = [None, RuntimeError("SMTP unavailable")]
        response = self.client.post(reverse("student-add"), self.valid_payload())
        self.assertEqual(response.status_code, 302)
        student = Student.objects.get(email="asha@example.com")
        old_password = self.client.session["created_student_credentials"]["password"]
        response = self.client.post(reverse("student-resend-credentials", args=[student.pk]))

        self.assertEqual(response.status_code, 302)
        student.user.refresh_from_db()
        new_password = self.client.session["created_student_credentials"]["password"]
        self.assertNotEqual(old_password, new_password)
        self.assertTrue(student.user.check_password(new_password))
        self.assertContains(self.client.get(reverse("student-list")), "Student created successfully")

    @patch("students.views.EmailMultiAlternatives.send", return_value=1)
    def test_resend_client_request_reaches_real_email_send(self, send_email):
        student, _, _ = create_student_with_account(self.valid_payload())

        response = self.client.post(reverse("student-resend-credentials", args=[student.pk]))

        self.assertRedirects(response, reverse("student-list"))
        send_email.assert_called_once_with(fail_silently=False)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_resend_uses_the_selected_students_email(self):
        student_a, _, _ = create_student_with_account(
            self.valid_payload(email="student.a@example.com", name="Student A")
        )
        student_b, _, _ = create_student_with_account(
            self.valid_payload(email="student.b@example.com", name="Student B")
        )

        response = self.client.post(reverse("student-resend-credentials", args=[student_b.pk]))

        self.assertRedirects(response, reverse("student-list"))
        self.assertEqual(mail.outbox[-1].to, [student_b.email])
        self.assertNotEqual(mail.outbox[-1].to, [student_a.email])

    def test_student_cannot_access_admin_student_directory(self):
        student, _, _ = create_student_with_account(self.valid_payload())
        self.client.force_login(student.user)

        response = self.client.get(reverse("student-list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("student-dashboard"))

    def test_student_login_reaches_dashboard_and_admin_payment_is_recorded(self):
        student, _, password = create_student_with_account(self.valid_payload())
        self.client.logout()

        login_response = self.client.post(
            reverse("login"),
            {"role": "student", "username": student.user.username, "password": password},
        )
        self.assertRedirects(login_response, reverse("student-password-change"))
        password_change_response = self.client.post(
            reverse("student-password-change"),
            {
                "old_password": password,
                "new_password1": "NewStudentPass123!",
                "new_password2": "NewStudentPass123!",
            },
        )
        self.assertRedirects(password_change_response, reverse("student-profile"))
        self.assertEqual(self.client.get(reverse("student-dashboard")).status_code, 200)
        self.assertRedirects(self.client.get(reverse("payment-add")), reverse("student-dashboard"))

        self.client.force_login(self.admin)
        payment_response = self.client.post(
            reverse("payment-add"),
            {"student": student.pk, "amount_paid": "250.00", "month": "September 2026", "remarks": "Initial payment"},
        )
        self.assertRedirects(payment_response, reverse("student-list"))
        self.assertEqual(FeePayment.objects.get(student=student).amount_paid, 250)
