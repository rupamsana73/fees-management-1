from django.test import TestCase
from django.urls import reverse

from students.models import Student

from .models import User


class LoginPortalTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="teacher",
            password="TeacherPass123!",
            role=User.Role.ADMIN,
        )
        self.student = User.objects.create_user(
            username="student.one",
            password="StudentPass123!",
            role=User.Role.STUDENT,
        )
        Student.objects.create(
            user=self.student,
            student_id="STU100",
            name="Student One",
            email="student.one@example.com",
            total_fee="1000.00",
        )

    def test_login_portal_shows_both_choices(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student Login")
        self.assertContains(response, "Teacher Login")
        self.assertContains(response, "Access Portal")

    def test_role_specific_login_forms_load(self):
        student_response = self.client.get(reverse("login"), {"role": "student"})
        teacher_response = self.client.get(reverse("login"), {"role": "teacher"})

        self.assertContains(student_response, "Login as Student")
        self.assertContains(teacher_response, "Login as Teacher")
        self.assertContains(student_response, "Contact your teacher/admin")
        self.assertNotContains(student_response, "Create Account")

    def test_student_login_redirects_to_password_change_when_required(self):
        self.student.must_change_password = True
        self.student.save(update_fields=["must_change_password"])

        response = self.client.post(
            reverse("login"),
            {"role": "student", "username": "student.one", "password": "StudentPass123!"},
        )

        self.assertRedirects(response, reverse("student-password-change"))

    def test_student_password_change_clears_requirement(self):
        self.student.must_change_password = True
        self.student.save(update_fields=["must_change_password"])
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("student-password-change"),
            {
                "old_password": "StudentPass123!",
                "new_password1": "NewStudentPass123!",
                "new_password2": "NewStudentPass123!",
            },
        )

        self.assertRedirects(response, reverse("student-profile"))
        self.student.refresh_from_db()
        self.assertFalse(self.student.must_change_password)

    def test_student_login_reaches_dashboard_after_password_change(self):
        response = self.client.post(
            reverse("login"),
            {"role": "student", "username": "student.one", "password": "StudentPass123!"},
        )

        self.assertRedirects(response, reverse("student-dashboard"))

    def test_teacher_login_reaches_admin_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"role": "teacher", "username": "teacher", "password": "TeacherPass123!"},
        )

        self.assertRedirects(response, reverse("admin-dashboard"))

    def test_login_role_mismatch_is_rejected(self):
        response = self.client.post(
            reverse("login"),
            {"role": "teacher", "username": "student.one", "password": "StudentPass123!"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_student_cannot_access_admin_or_management_pages(self):
        self.client.force_login(self.student)

        for route_name in ("admin-dashboard", "student-list", "payment-add", "reports"):
            response = self.client.get(reverse(route_name))
            self.assertNotEqual(response.status_code, 200)

    def test_authenticated_login_redirects_by_role(self):
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get(reverse("login")), reverse("student-dashboard"))

        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get(reverse("login")), reverse("admin-dashboard"))

    def test_authenticated_temporary_student_login_redirects_to_password_change(self):
        self.student.must_change_password = True
        self.student.save(update_fields=["must_change_password"])
        self.client.force_login(self.student)

        self.assertRedirects(self.client.get(reverse("login")), reverse("student-password-change"))

    def test_logout_returns_to_login_portal(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("logout"))

        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(self.client.get(reverse("login")), "Access Portal")
