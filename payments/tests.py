from decimal import Decimal
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.test import override_settings
from django.utils import timezone
from django.urls import reverse

from payments.models import FeePayment, Notification
from payments.notifications import send_fee_reminder
from students.models import Student
from students.utils import create_student_with_account
from users.models import User
from users.models import AuditLog


class PaymentReceiptTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="teacher",
            password="TeacherPass123!",
            role=User.Role.ADMIN,
        )
        self.student, _, self.password = create_student_with_account(
            {
                "name": "Alice Student",
                "email": "alice@example.com",
                "course": "Computer Science",
                "total_fee": "1200.00",
                "phone": "9876543210",
                "admission_date": "2026-09-10",
                "status": "active",
            }
        )
        self.payment = FeePayment.objects.create(
            student=self.student,
            amount_paid=Decimal("300.00"),
            month="September 2026",
            remarks="Initial payment",
        )

    def test_admin_can_view_receipt(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("payment-receipt", args=[self.payment.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PAYMENT RECEIPT")
        self.assertContains(response, self.student.name)

    def test_payment_form_rejects_nonpositive_amounts(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("payment-add"),
            {
                "student": self.student.pk,
                "amount_paid": "-10.00",
                "month": "September 2026",
                "payment_method": "Cash",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(FeePayment.objects.filter(amount_paid=Decimal("-10.00")).exists())

    def test_payment_form_rejects_duplicate_transaction_ids(self):
        FeePayment.objects.create(
            student=self.student,
            amount_paid=Decimal("100.00"),
            month="August 2026",
            transaction_id="TXN-DUPLICATE",
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("payment-add"),
            {
                "student": self.student.pk,
                "amount_paid": "50.00",
                "month": "September 2026",
                "payment_method": "UPI",
                "transaction_id": "TXN-DUPLICATE",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(FeePayment.objects.filter(transaction_id="TXN-DUPLICATE").count(), 1)

    def test_database_allows_blank_and_rejects_duplicate_transaction_ids(self):
        FeePayment.objects.create(
            student=self.student,
            amount_paid=Decimal("25.00"),
            month="October 2026",
        )
        FeePayment.objects.create(
            student=self.student,
            amount_paid=Decimal("30.00"),
            month="November 2026",
        )
        FeePayment.objects.create(
            student=self.student,
            amount_paid=Decimal("40.00"),
            month="December 2026",
            transaction_id="TXN-UNIQUE",
        )

        with self.assertRaises(IntegrityError):
            FeePayment.objects.create(
                student=self.student,
                amount_paid=Decimal("50.00"),
                month="January 2027",
                transaction_id="TXN-UNIQUE",
            )

    @patch("payments.views.FeePaymentForm.save", side_effect=IntegrityError)
    def test_database_duplicate_is_returned_as_form_error(self, save_mock):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("payment-add"),
            {
                "student": self.student.pk,
                "amount_paid": "50.00",
                "month": "September 2026",
                "payment_method": "UPI",
                "transaction_id": "TXN-RACE",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This transaction ID has already been recorded.")
        save_mock.assert_called_once()

    def test_student_can_view_own_receipt(self):
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("payment-receipt", args=[self.payment.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student.student_id)

    def test_student_cannot_view_another_student_receipt(self):
        other_student, _, _ = create_student_with_account(
            {
                "name": "Bob Learner",
                "email": "bob@example.com",
                "course": "Physics",
                "total_fee": "800.00",
                "phone": "1234567890",
                "admission_date": "2026-09-11",
                "status": "active",
            }
        )
        other_payment = FeePayment.objects.create(
            student=other_student,
            amount_paid=Decimal("200.00"),
            month="September 2026",
            remarks="Other payment",
        )

        self.client.force_login(self.student.user)
        response = self.client.get(reverse("payment-receipt", args=[other_payment.pk]))

        self.assertIn(response.status_code, (302, 403, 404))

    def test_unauthenticated_user_cannot_access_receipt(self):
        response = self.client.get(reverse("payment-receipt", args=[self.payment.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_receipt_contains_expected_payment_information(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("payment-receipt", args=[self.payment.pk]))

        self.assertContains(response, "FeeFlow")
        self.assertContains(response, self.student.name)
        self.assertContains(response, self.student.student_id)
        self.assertContains(response, self.student.course)
        self.assertContains(response, self.student.email)
        self.assertContains(response, str(self.payment.amount_paid))
        self.assertContains(response, self.payment.month)
        self.assertContains(response, "Initial payment")

    def test_receipt_number_is_generated_and_stable_after_edit(self):
        self.client.force_login(self.admin)
        first_response = self.client.get(reverse("payment-receipt", args=[self.payment.pk]))
        first_number = self.payment.receipt_number

        self.assertTrue(first_number)
        self.assertIn(first_number, first_response.content.decode())

        self.payment.amount_paid = Decimal("450.00")
        self.payment.save(update_fields=["amount_paid"])

        second_response = self.client.get(reverse("payment-receipt", args=[self.payment.pk]))
        self.assertIn(first_number, second_response.content.decode())
        self.assertEqual(self.payment.receipt_number, first_number)

    def test_receipt_pdf_response_has_correct_content_type(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("payment-receipt-pdf", args=[self.payment.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content)
        self.assertIn("FeeFlow_Receipt_", response["Content-Disposition"])
        self.assertIn(self.payment.receipt_number, response["Content-Disposition"])

    def test_admin_receipt_link_is_available_on_student_history_page(self):
        self.student.user.must_change_password = False
        self.student.user.save(update_fields=["must_change_password"])
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("payment-history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("payment-receipt", args=[self.payment.pk]))


class AdvancedReportsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="teacher2",
            password="TeacherPass123!",
            role=User.Role.ADMIN,
        )
        self.student_user = User.objects.create_user(
            username="studentreport",
            password="StudentPass123!",
            role=User.Role.STUDENT,
        )
        self.student = Student.objects.create(
            user=self.student_user,
            student_id="STU200",
            name="Charlie Report",
            email="charlie@example.com",
            phone="9998887777",
            course="Computer Science",
            total_fee=Decimal("1500.00"),
            admission_date="2026-09-01",
            status=Student.Status.ACTIVE,
        )
        self.payment = FeePayment.objects.create(
            student=self.student,
            amount_paid=Decimal("600.00"),
            payment_date="2026-09-05",
            month="September 2026",
            payment_method="UPI",
            transaction_id="TXN-1001",
            remarks="Initial payment",
        )

    def test_reports_page_requires_admin(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, 200)

    def test_reports_page_displays_summary_cards_and_filters(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports"))

        self.assertContains(response, "Total Students")
        self.assertContains(response, "Total Fees")
        self.assertContains(response, "Total Collected")
        self.assertContains(response, "Total Pending")
        self.assertContains(response, "Date From")
        self.assertContains(response, "Date To")
        self.assertContains(response, "Payment Status")
        self.assertContains(response, "Student")
        self.assertContains(response, "Course")
        self.assertContains(response, "Payment Method")
        self.assertContains(response, "Student-wise Fee Report")
        self.assertContains(response, "Payment-wise Report")

    def test_reports_filters_update_report_values(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("reports"),
            {
                "student": str(self.student.pk),
                "course": "Computer Science",
                "payment_method": "UPI",
            },
        )

        self.assertContains(response, "Charlie Report")
        self.assertContains(response, "TXN-1001")
        self.assertContains(response, "UPI")
        self.assertContains(response, "Computer Science")

    def test_csv_export_contains_filtered_payment_data(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("reports-csv"),
            {"student": self.student.pk, "course": "Computer Science", "payment_method": "UPI"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment; filename=\"FeeFlow_Report.csv\"", response["Content-Disposition"])
        self.assertIn("Receipt Number,Payment Date,Student Name", response.content.decode("utf-8"))
        self.assertIn("Charlie Report", response.content.decode("utf-8"))
        self.assertIn("TXN-1001", response.content.decode("utf-8"))

    def test_excel_export_contains_report_sheets(self):
        from openpyxl import load_workbook

        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports-excel"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        workbook = load_workbook(filename=BytesIO(response.content), read_only=True)
        self.assertEqual(
            workbook.sheetnames,
            ["Summary", "Student Fee Report", "Payment Report", "Course Analytics", "Payment Method Analytics"],
        )
        self.assertEqual(workbook["Payment Report"]["A2"].value, self.payment.receipt_number)

    def test_pdf_export_returns_report_pdf(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports-pdf"), {"course": "Computer Science"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment; filename=\"FeeFlow_Report.pdf\"", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_print_view_contains_filters_and_filtered_tables(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("reports-print"),
            {"student": self.student.pk, "course": "Computer Science", "payment_method": "UPI"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "FeeFlow")
        self.assertContains(response, "Computer Science")
        self.assertContains(response, "Charlie Report")
        self.assertContains(response, "TXN-1001")

    def test_students_and_unauthenticated_users_cannot_export_reports(self):
        for route_name in ("reports-csv", "reports-excel", "reports-pdf", "reports-print"):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/", response.url)

            self.client.force_login(self.student_user)
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 302)
            self.assertIn("student-dashboard", response.url)
            self.client.logout()

    def test_combined_filters_and_empty_filtered_results(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("reports-csv"),
            {
                "date_from": "2099-01-01",
                "date_to": "2099-12-31",
                "student": self.student.pk,
                "course": "Computer Science",
                "payment_status": "PAID",
                "payment_method": "UPI",
            },
        )

        content = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Receipt Number,Payment Date,Student Name", content)
        self.assertNotIn("Charlie Report", content)
        self.assertNotIn("TXN-1001", content)


class NotificationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="notification-admin",
            password="TeacherPass123!",
            role=User.Role.ADMIN,
        )
        self.student_user = User.objects.create_user(
            username="notification-student",
            password="StudentPass123!",
            role=User.Role.STUDENT,
        )
        self.student = Student.objects.create(
            user=self.student_user,
            student_id="STU300",
            name="Reminder Student",
            email="reminder@example.com",
            course="Physics",
            total_fee=Decimal("1000.00"),
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_payment_confirmation_email_contains_payment_details(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("payment-add"),
            {
                "student": self.student.pk,
                "amount_paid": "250.00",
                "month": "September 2026",
                "payment_method": "UPI",
                "transaction_id": "PAY-300",
                "remarks": "Tuition",
            },
        )

        self.assertEqual(response.status_code, 302)
        notification = Notification.objects.filter(
            notification_type=Notification.NotificationType.PAYMENT_CONFIRMATION,
        ).get()
        self.assertEqual(notification.status, Notification.Status.SENT)
        self.assertEqual(notification.recipient_email, self.student.email)
        self.assertEqual(notification.related_payment.amount_paid, Decimal("250.00"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.student.student_id, mail.outbox[0].body)
        self.assertIn(notification.related_payment.receipt_number, mail.outbox[0].body)
        self.assertIn("250.00", mail.outbox[0].body)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.PAYMENT_CREATED).exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_payment_email_failure_does_not_rollback_payment(self):
        self.client.force_login(self.admin)
        with patch("payments.notifications.EmailMultiAlternatives.send", side_effect=RuntimeError("SMTP unavailable")):
            response = self.client.post(
                reverse("payment-add"),
                {
                    "student": self.student.pk,
                    "amount_paid": "200.00",
                    "month": "September 2026",
                    "payment_method": "Cash",
                    "transaction_id": "PAY-FAIL",
                    "remarks": "Failure test",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(FeePayment.objects.filter(transaction_id="PAY-FAIL").exists())
        notification = Notification.objects.get(notification_type=Notification.NotificationType.PAYMENT_CONFIRMATION)
        self.assertEqual(notification.status, Notification.Status.FAILED)
        self.assertNotIn("SMTP unavailable", notification.error_message)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", FEE_REMINDER_COOLDOWN_DAYS=7)
    def test_pending_student_receives_reminder_and_cooldown_blocks_repeat(self):
        self.student._paid_total = Decimal("0.00")
        notification = send_fee_reminder(self.student)

        self.assertEqual(notification.status, Notification.Status.SENT)
        self.assertEqual(notification.recipient_email, self.student.email)
        self.assertEqual(notification.notification_type, Notification.NotificationType.FEE_REMINDER)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("1000.00", mail.outbox[0].body)
        self.assertIn("Reminder Student", mail.outbox[0].body)

        self.client.force_login(self.admin)
        response = self.client.post(reverse("student-send-fee-reminder", args=[self.student.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(notification_type=Notification.NotificationType.FEE_REMINDER).count(), 1)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_zero_pending_fee_does_not_send_reminder(self):
        FeePayment.objects.create(
            student=self.student,
            amount_paid=Decimal("1000.00"),
            month="September 2026",
            payment_method="Cash",
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("student-send-fee-reminder", args=[self.student.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Notification.objects.filter(notification_type=Notification.NotificationType.FEE_REMINDER).exists())
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_manual_override_sends_again_and_command_continues_after_failure(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("student-send-fee-reminder", args=[self.student.pk]))
        self.client.post(
            reverse("student-send-fee-reminder", args=[self.student.pk]),
            {"override": "1"},
        )
        self.assertEqual(Notification.objects.filter(notification_type=Notification.NotificationType.FEE_REMINDER).count(), 2)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.REMINDER_SENT).exists())

        Notification.objects.filter(
            notification_type=Notification.NotificationType.FEE_REMINDER
        ).update(sent_at=timezone.now() - timedelta(days=8))

        with patch("payments.notifications.EmailMultiAlternatives.send", side_effect=RuntimeError("SMTP unavailable")):
            call_command("send_fee_reminders")
        self.assertEqual(Notification.objects.filter(status=Notification.Status.FAILED).count(), 1)

    def test_students_cannot_send_reminders_or_view_notification_history(self):
        self.client.force_login(self.student_user)

        reminder_response = self.client.post(reverse("student-send-fee-reminder", args=[self.student.pk]))
        history_response = self.client.get(reverse("notification-history"))

        self.assertEqual(reminder_response.status_code, 302)
        self.assertEqual(history_response.status_code, 302)
        self.assertEqual(reminder_response.url, reverse("student-dashboard"))
        self.assertEqual(history_response.url, reverse("student-dashboard"))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_admin_can_filter_notification_history(self):
        self.client.force_login(self.admin)
        send_fee_reminder(self.student)

        response = self.client.get(
            reverse("notification-history"),
            {"student": self.student.pk, "notification_type": Notification.NotificationType.FEE_REMINDER},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student.student_id)
        self.assertContains(response, self.student.email)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_admin_can_retry_failed_reminder(self):
        with patch("payments.notifications.EmailMultiAlternatives.send", side_effect=RuntimeError("SMTP unavailable")):
            failed = send_fee_reminder(self.student)

        self.assertEqual(failed.status, Notification.Status.FAILED)
        self.client.force_login(self.admin)
        response = self.client.post(reverse("notification-retry", args=[failed.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(notification_type=Notification.NotificationType.FEE_REMINDER).count(), 2)
        self.assertEqual(Notification.objects.order_by("-pk").first().status, Notification.Status.SENT)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.NOTIFICATION_RETRIED).exists())
