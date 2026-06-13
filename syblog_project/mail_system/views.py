from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from accounts.models import UserProfile
from .models import Mail
from .forms import ComposeMailForm


@login_required
def inbox(request):
    mails = Mail.objects.filter(
        recipient=request.user,
        is_deleted_by_recipient=False
    ).select_related('sender').order_by('-sent_at')
    paginator = Paginator(mails, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'mail_system/inbox.html', {'mails': page, 'tab': 'inbox'})


@login_required
def sent_box(request):
    mails = Mail.objects.filter(
        sender=request.user,
        is_deleted_by_sender=False
    ).select_related('recipient').order_by('-sent_at')
    paginator = Paginator(mails, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'mail_system/inbox.html', {'mails': page, 'tab': 'sent'})


@login_required
def mail_detail(request, pk):
    mail = get_object_or_404(Mail, pk=pk)
    if mail.recipient != request.user and mail.sender != request.user:
        messages.error(request, '권한이 없습니다.')
        return redirect('mail_system:inbox')
    if mail.recipient == request.user and not mail.is_read:
        mail.is_read = True
        mail.save()
    # 돌아갈 탭 결정
    back_tab = 'sent' if mail.sender == request.user and mail.recipient != request.user else 'inbox'
    return render(request, 'mail_system/detail.html', {'mail': mail, 'back_tab': back_tab})


@login_required
def compose(request, recipient_username=None):
    initial = {}
    if recipient_username:
        try:
            User.objects.get(username=recipient_username)
            initial['recipient_username'] = recipient_username
        except User.DoesNotExist:
            pass

    if request.method == 'POST':
        form = ComposeMailForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['recipient_username'].strip()
            try:
                recipient = User.objects.get(username=username)
                # 자기 자신에게 보내기 차단
                if recipient == request.user:
                    form.add_error('recipient_username', '자기 자신에게는 메일을 보낼 수 없습니다.')
                else:
                    # 차단된 유저 체크
                    try:
                        rprofile = recipient.profile
                        if rprofile.is_blocked:
                            form.add_error('recipient_username', '차단된 사용자에게는 메일을 보낼 수 없습니다.')
                            return render(request, 'mail_system/compose.html', {'form': form})
                    except Exception:
                        pass
                    Mail.objects.create(
                        sender=request.user,
                        recipient=recipient,
                        subject=form.cleaned_data['subject'],
                        body=form.cleaned_data['body'],
                    )
                    messages.success(request, f'✉️ {recipient.username}에게 메일을 보냈습니다!')
                    return redirect('mail_system:inbox')
            except User.DoesNotExist:
                form.add_error('recipient_username', '존재하지 않는 사용자입니다.')
    else:
        form = ComposeMailForm(initial=initial)
    return render(request, 'mail_system/compose.html', {'form': form})


@login_required
@require_POST
def delete_mail(request, pk):
    mail = get_object_or_404(Mail, pk=pk)
    if mail.sender == request.user:
        mail.is_deleted_by_sender = True
        mail.save()
        messages.success(request, '메일이 삭제되었습니다.')
        return redirect('mail_system:sent')
    elif mail.recipient == request.user:
        mail.is_deleted_by_recipient = True
        mail.save()
        messages.success(request, '메일이 삭제되었습니다.')
        return redirect('mail_system:inbox')
    else:
        messages.error(request, '권한이 없습니다.')
        return redirect('mail_system:inbox')


@login_required
def search_users(request):
    """사용자명 자동완성 API"""
    q = request.GET.get('q', '').strip()
    if len(q) < 1:
        return JsonResponse({'users': []})
    users = User.objects.filter(
        username__icontains=q,
        is_active=True
    ).exclude(
        pk=request.user.pk
    ).exclude(
        profile__is_blocked=True
    ).values('username', 'id')[:10]
    result = []
    for u in users:
        result.append({'username': u['username']})
    return JsonResponse({'users': result})
