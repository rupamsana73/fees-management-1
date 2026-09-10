from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    must_change_password = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.is_staff or self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_full_name() or self.username


class AuditLog(models.Model):
    class Action(models.TextChoices):
        LOGIN_SUCCESS = "LOGIN_SUCCESS", "Login success"
        LOGIN_FAILURE = "LOGIN_FAILURE", "Login failure"
        LOGOUT = "LOGOUT", "Logout"
        STUDENT_CREATED = "STUDENT_CREATED", "Student created"
        STUDENT_UPDATED = "STUDENT_UPDATED", "Student updated"
        STUDENT_STATUS_CHANGED = "STUDENT_STATUS_CHANGED", "Student status changed"
        CREDENTIALS_RESENT = "CREDENTIALS_RESENT", "Credentials resent"
        PAYMENT_CREATED = "PAYMENT_CREATED", "Payment created"
        REMINDER_SENT = "REMINDER_SENT", "Reminder sent"
        NOTIFICATION_RETRIED = "NOTIFICATION_RETRIED", "Notification retried"
        TEACHER_CREATED = "TEACHER_CREATED", "Teacher created"
        TEACHER_UPDATED = "TEACHER_UPDATED", "Teacher updated"
        TEACHER_STATUS_CHANGED = "TEACHER_STATUS_CHANGED", "Teacher status changed"
        PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password changed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=40, choices=Action.choices, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    target_type = models.CharField(max_length=80, blank=True, default="")
    target_id = models.CharField(max_length=80, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ("-timestamp", "-pk")
        indexes = [
            models.Index(fields=("user", "-timestamp")),
            models.Index(fields=("action", "-timestamp")),
        ]

    def __str__(self):
        return f"{self.action} at {self.timestamp:%Y-%m-%d %H:%M}"
