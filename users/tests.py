from django.test import TestCase
from django.urls import reverse

from students.models import Student

from .models import AuditLog, User


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


class StaffManagementAndAuditTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin-owner",
            password="AdminPass123!",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="teacher-one",
            password="TeacherPass123!",
            role=User.Role.TEACHER,
        )
        self.student = User.objects.create_user(
            username="student-two",
            password="StudentPass123!",
            role=User.Role.STUDENT,
        )
        Student.objects.create(
            user=self.student,
            student_id="STU500",
            name="Student Two",
            email="student.two@example.com",
            total_fee="1000.00",
        )

    def test_admin_can_manage_staff_but_teacher_and_student_cannot(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("teacher-list")).status_code, 200)

        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("teacher-list")).status_code, 302)
        self.assertEqual(self.client.get(reverse("audit-log")).status_code, 302)

        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("teacher-list")).status_code, 302)
        self.assertEqual(self.client.get(reverse("audit-log")).status_code, 302)

    def test_admin_can_create_edit_and_reset_teacher_without_exposing_password(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("teacher-add"),
            {
                "username": "teacher-new",
                "first_name": "New",
                "last_name": "Teacher",
                "email": "teacher.new@example.com",
                "is_active": "on",
                "password1": "NewTeacherPass123!",
                "password2": "NewTeacherPass123!",
            },
        )
        self.assertRedirects(response, reverse("teacher-list"))
        teacher = User.objects.get(username="teacher-new")
        self.assertEqual(teacher.role, User.Role.TEACHER)
        self.assertTrue(teacher.check_password("NewTeacherPass123!"))
        self.assertFalse(AuditLog.objects.filter(description__icontains="NewTeacherPass123").exists())

        response = self.client.post(
            reverse("teacher-edit", args=[teacher.pk]),
            {"username": "teacher-new", "first_name": "Updated", "last_name": "Teacher", "email": "teacher.new@example.com", "role": "teacher", "is_active": ""},
        )
        self.assertRedirects(response, reverse("teacher-list"))
        teacher.refresh_from_db()
        self.assertFalse(teacher.is_active)

        response = self.client.post(
            reverse("teacher-password-reset", args=[teacher.pk]),
            {"new_password1": "ResetTeacherPass123!", "new_password2": "ResetTeacherPass123!"},
        )
        self.assertRedirects(response, reverse("teacher-list"))
        teacher.refresh_from_db()
        self.assertTrue(teacher.check_password("ResetTeacherPass123!"))
        self.assertFalse(AuditLog.objects.filter(description__icontains="ResetTeacherPass123").exists())

    def test_teacher_can_use_operational_staff_pages(self):
        self.client.force_login(self.teacher)
        for route_name in ("admin-dashboard", "student-list", "payment-add", "pending-fees", "reports", "notification-history"):
            self.assertNotEqual(self.client.get(reverse(route_name)).status_code, 403)

    def test_login_and_logout_create_audit_events(self):
        response = self.client.post(
            reverse("login"),
            {"role": "teacher", "username": self.teacher.username, "password": "TeacherPass123!"},
        )
        self.assertRedirects(response, reverse("admin-dashboard"))
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.LOGIN_SUCCESS, user=self.teacher).exists())

        self.client.get(reverse("logout"))
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.LOGOUT, user=self.teacher).exists())

    def test_audit_log_is_paginated_and_contains_no_passwords(self):
        AuditLog.objects.bulk_create(
            [AuditLog(user=self.admin, action=AuditLog.Action.LOGIN_SUCCESS, description="Safe event") for _ in range(30)]
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("audit-log"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Page 1 of 2")
        self.assertNotContains(response, "AdminPass123")
        self.assertNotContains(response, "TeacherPass123")

    def test_student_status_change_is_audited(self):
        self.client.force_login(self.admin)
        student_profile = self.student.student_profile
        response = self.client.post(
            reverse("student-edit", args=[student_profile.pk]),
            {
                "name": student_profile.name,
                "email": student_profile.email,
                "phone": "",
                "course": student_profile.course,
                "total_fee": "1000.00",
                "admission_date": "2026-09-10",
                "status": "inactive",
            },
        )
        self.assertRedirects(response, reverse("student-list"))
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.STUDENT_STATUS_CHANGED).exists())
