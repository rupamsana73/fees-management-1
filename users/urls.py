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
]
