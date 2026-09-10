from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("users.urls")),
    path("students/", include("students.urls")),
    path("payments/", include("payments.urls")),
]

handler404 = "fee_management_project.views.error_404"
handler403 = "fee_management_project.views.error_403"
handler500 = "fee_management_project.views.error_500"
