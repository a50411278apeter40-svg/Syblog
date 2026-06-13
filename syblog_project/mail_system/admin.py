from django.contrib import admin
from .models import Mail

@admin.register(Mail)
class MailAdmin(admin.ModelAdmin):
    list_display = ['sender', 'recipient', 'subject', 'sent_at', 'is_read']
    list_filter = ['is_read']
