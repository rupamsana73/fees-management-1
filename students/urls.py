from django.urls import path

from . import views

urlpatterns = [
    path("", views.student_list, name="student-list"),
    path("pending/", views.pending_fees, name="pending-fees"),
    path("<int:pk>/send-reminder/", views.student_send_fee_reminder, name="student-send-fee-reminder"),
    path("add/", views.student_add, name="student-add"),
    path("<int:pk>/resend-credentials/", views.student_resend_credentials, name="student-resend-credentials"),
    path("<int:pk>/edit/", views.student_edit, name="student-edit"),
    path("<int:pk>/delete/", views.student_delete, name="student-delete"),
]
