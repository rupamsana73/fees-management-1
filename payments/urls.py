from django.urls import path

from . import views

urlpatterns = [
    path("add/", views.payment_add, name="payment-add"),
    path("reports/", views.reports, name="reports"),
    path("reports/export/csv/", views.reports_csv, name="reports-csv"),
    path("reports/export/excel/", views.reports_excel, name="reports-excel"),
    path("reports/export/pdf/", views.reports_pdf, name="reports-pdf"),
    path("reports/print/", views.reports_print, name="reports-print"),
    path("<int:payment_id>/receipt/", views.payment_receipt, name="payment-receipt"),
    path("<int:payment_id>/receipt/pdf/", views.payment_receipt_pdf, name="payment-receipt-pdf"),
]
