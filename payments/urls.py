from django.urls import path

from . import views

urlpatterns = [
    path("add/", views.payment_add, name="payment-add"),
    path("reports/", views.reports, name="reports"),
]
