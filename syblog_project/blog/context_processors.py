from django.utils import timezone
from django.db.models import Q


def active_notices(request):
    try:
        from .models import Notice
        now = timezone.now()
        notices = Notice.objects.filter(is_active=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).order_by('-created_at')
        return {'active_notices': notices}
    except Exception:
        return {'active_notices': []}
