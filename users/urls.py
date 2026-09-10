from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("admin-dashboard/", views.admin_dashboard, name="admin-dashboard"),
    path("student-dashboard/", views.student_dashboard, name="student-dashboard"),
    path("payment-history/", views.payment_history, name="payment-history"),
    path("my-profile/", views.student_profile, name="student-profile"),
    path("my-profile/change-password/", views.student_password_change, name="student-password-change"),
    path("student-profile-missing/", views.student_profile_missing, name="student-profile-missing"),
    path("teachers/", views.teacher_list, name="teacher-list"),
    path("teachers/add/", views.teacher_add, name="teacher-add"),
    path("teachers/<int:pk>/edit/", views.teacher_edit, name="teacher-edit"),
    path("teachers/<int:pk>/reset-password/", views.teacher_password_reset, name="teacher-password-reset"),
    path("audit-log/", views.audit_log, name="audit-log"),
]
