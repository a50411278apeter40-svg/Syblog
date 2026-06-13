from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q
from .models import Mail
from .forms import ComposeMailForm

@login_required
def inbox(request):
    mails = Mail.objects.filter(
        recipient=request.user,
        is_deleted_by_recipient=False
    ).order_by('-sent_at')
    return render(request, 'mail_system/inbox.html', {'mails': mails})

@login_required
def sent_box(request):
    mails = Mail.objects.filter(
        sender=request.user,
        is_deleted_by_sender=False
    ).order_by('-sent_at')
    return render(request, 'mail_system/sent.html', {'mails': mails})

@login_required
def mail_detail(request, pk):
    mail = get_object_or_404(Mail, pk=pk)
    if mail.recipient != request.user and mail.sender != request.user:
        messages.error(request, '권한이 없습니다.')
        return redirect('mail_system:inbox')
    if mail.recipient == request.user and not mail.is_read:
        mail.is_read = True
        mail.save()
    return render(request, 'mail_system/detail.html', {'mail': mail})

@login_required
def compose(request, recipient_username=None):
    initial = {}
    if recipient_username:
        try:
            recipient = User.objects.get(username=recipient_username)
            initial['recipient'] = recipient.username
        except:
            pass
    
    if request.method == 'POST':
        form = ComposeMailForm(request.POST)
        if form.is_valid():
            try:
                recipient = User.objects.get(username=form.cleaned_data['recipient_username'])
                mail = Mail.objects.create(
                    sender=request.user,
                    recipient=recipient,
                    subject=form.cleaned_data['subject'],
                    body=form.cleaned_data['body'],
                )
                messages.success(request, f'{recipient.username}에게 메일을 보냈습니다!')
                return redirect('mail_system:inbox')
            except User.DoesNotExist:
                form.add_error('recipient_username', '존재하지 않는 사용자입니다.')
    else:
        form = ComposeMailForm(initial=initial)
    return render(request, 'mail_system/compose.html', {'form': form})

@login_required
def delete_mail(request, pk):
    mail = get_object_or_404(Mail, pk=pk)
    if mail.sender == request.user:
        mail.is_deleted_by_sender = True
        mail.save()
    elif mail.recipient == request.user:
        mail.is_deleted_by_recipient = True
        mail.save()
    messages.success(request, '메일이 삭제되었습니다.')
    return redirect('mail_system:inbox')
