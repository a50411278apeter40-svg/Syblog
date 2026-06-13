from .models import Mail

def unread_mail_count(request):
    if request.user.is_authenticated:
        count = Mail.objects.filter(recipient=request.user, is_read=False, is_deleted_by_recipient=False).count()
        return {'unread_mail_count': count}
    return {'unread_mail_count': 0}
