from django.contrib import admin

from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "student_id", "course", "total_fee")
    search_fields = ("name", "student_id", "user__username")
