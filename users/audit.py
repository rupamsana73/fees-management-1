from .models import AuditLog


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record_audit(request, action, *, target=None, target_type="", target_id="", description=""):
    if target is not None:
        target_type = target_type or target.__class__.__name__
        target_id = target_id or getattr(target, "pk", "")
    user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
    return AuditLog.objects.create(
        user=user,
        action=action,
        target_type=target_type,
        target_id=str(target_id or ""),
        description=description[:255],
        ip_address=get_client_ip(request) if request else None,
    )
