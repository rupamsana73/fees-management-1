from functools import wraps

from django.shortcuts import redirect

from users.models import User


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if request.user.role not in {User.Role.ADMIN, User.Role.TEACHER}:
            return redirect("student-dashboard")
        return view_func(request, *args, **kwargs)

    return wrapped_view


def admin_only(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if request.user.role != User.Role.ADMIN:
            return redirect("admin-dashboard" if request.user.is_authenticated else "login")
        return view_func(request, *args, **kwargs)

    return wrapped_view
