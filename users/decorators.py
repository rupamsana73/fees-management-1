from functools import wraps

from django.shortcuts import redirect

from .models import User


def student_required(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != User.Role.STUDENT:
            return redirect("admin-dashboard")
        if request.user.must_change_password and request.resolver_match.url_name != "student-password-change":
            return redirect("student-password-change")
        return view_func(request, *args, **kwargs)

    return wrapped_view