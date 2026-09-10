from functools import wraps

from django.shortcuts import redirect

from users.models import User


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if request.user.role != User.Role.ADMIN:
            return redirect("student-dashboard")
        return view_func(request, *args, **kwargs)

    return wrapped_view
