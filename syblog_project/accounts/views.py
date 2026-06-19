from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from .models import UserProfile, LEVEL_THRESHOLDS, BADGE_IDS, BADGE_LIST
from .forms import UserUpdateForm, ProfileUpdateForm

@login_required
def profile_view(request, username=None):
    if username:
        user = get_object_or_404(User, username=username)
    else:
        user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    from blog.models import Post, Series
    posts = Post.objects.filter(author=user).order_by('-created_at')[:5]
    series_list = Series.objects.filter(author=user)
    earned_badge_ids = profile.get_badges()
    earned_badges = [BADGE_IDS[bid] for bid in earned_badge_ids if bid in BADGE_IDS]
    return render(request, 'accounts/profile.html', {
        'profile_user': user,
        'profile': profile,
        'posts': posts,
        'series_list': series_list,
        'level_thresholds': LEVEL_THRESHOLDS,
        'earned_badges': earned_badges,
        'earned_badge_ids': earned_badge_ids,
    })

@login_required
def profile_edit(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, '프로필이 업데이트되었습니다!')
            return redirect('accounts:profile')
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=profile)
    return render(request, 'accounts/profile_edit.html', {
        'user_form': user_form,
        'profile_form': profile_form,
    })

@staff_member_required
def admin_user_list(request):
    users = User.objects.filter(is_superuser=False).select_related('profile').order_by('-date_joined')
    return render(request, 'accounts/admin_user_list.html', {'users': users})

@staff_member_required
def toggle_block_user(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    if target_user.is_superuser:
        messages.error(request, '관리자 계정은 차단할 수 없습니다.')
        return redirect('accounts:admin_user_list')
    profile, _ = UserProfile.objects.get_or_create(user=target_user)
    profile.is_blocked = not profile.is_blocked
    profile.save()
    action = '차단' if profile.is_blocked else '차단 해제'
    messages.success(request, f'{target_user.username} 을(를) {action}했습니다.')
    return redirect('accounts:admin_user_list')

def leaderboard(request):
    profiles = UserProfile.objects.filter(
        user__is_active=True,
        is_blocked=False
    ).select_related('user').order_by('-points')[:50]
    return render(request, 'accounts/leaderboard.html', {
        'profiles': profiles,
        'level_thresholds': LEVEL_THRESHOLDS,
    })

@staff_member_required
def admin_badge_manage(request):
    """관리자 - 배지 관리 페이지 (유저별 배지 부여/회수)"""
    from .models import UserBadge
    users = User.objects.filter(is_superuser=False).select_related('profile').order_by('username')

    # 검색
    q = request.GET.get('q', '').strip()
    if q:
        users = users.filter(username__icontains=q)

    user_data = []
    for u in users:
        profile, _ = UserProfile.objects.get_or_create(user=u)
        earned = set(profile.get_badges())
        user_data.append({
            'user': u,
            'profile': profile,
            'earned_count': len(earned),
            'earned_ids': list(earned),
        })

    return render(request, 'accounts/admin_badge_manage.html', {
        'user_data': user_data,
        'badge_list': BADGE_LIST,
        'badge_ids': BADGE_IDS,
        'q': q,
    })


@staff_member_required
def admin_badge_award(request):
    """배지 부여 / 회수 AJAX"""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST only'})
    import json as _json
    body = _json.loads(request.body)
    user_id = body.get('user_id')
    badge_id = body.get('badge_id')
    action = body.get('action')  # 'award' or 'revoke'

    target_user = get_object_or_404(User, pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    from .models import UserBadge
    if action == 'award':
        result = profile.award_badge(badge_id)
        if result:
            return JsonResponse({'ok': True, 'action': 'awarded', 'badge': badge_id})
        return JsonResponse({'ok': True, 'action': 'already_exists'})
    elif action == 'revoke':
        deleted, _ = UserBadge.objects.filter(profile=profile, badge_id=badge_id).delete()
        return JsonResponse({'ok': True, 'action': 'revoked', 'deleted': deleted})
    elif action == 'award_all':
        count = 0
        for b in BADGE_LIST:
            if profile.award_badge(b['id']):
                count += 1
        return JsonResponse({'ok': True, 'action': 'award_all', 'count': count})
    elif action == 'revoke_all':
        deleted, _ = UserBadge.objects.filter(profile=profile).delete()
        return JsonResponse({'ok': True, 'action': 'revoke_all', 'deleted': deleted})

    return JsonResponse({'ok': False, 'error': 'unknown action'})



# ── 커스텀 로그인 / 회원가입 뷰 (allauth 우회) ──────────────────────
from django.contrib.auth import authenticate, login as auth_login
from allauth.account.forms import SignupForm as AllauthSignupForm


def custom_login(request):
    """allauth URL보다 먼저 잡히는 커스텀 로그인 뷰"""
    next_url = request.GET.get('next', '') or request.POST.get('next', '/blog/')
    error = None

    if request.method == 'POST':
        username = request.POST.get('login', '').strip()
        password = request.POST.get('password', '')
        remember = request.POST.get('remember', False)

        user = authenticate(request, username=username, password=password)
        if user is not None:
            if hasattr(user, 'profile') and user.profile.is_blocked:
                error = '차단된 계정입니다. 관리자에게 문의하세요.'
            else:
                auth_login(request, user,
                           backend='allauth.account.auth_backends.AuthenticationBackend')
                if not remember:
                    request.session.set_expiry(0)
                return redirect(next_url or '/blog/')
        else:
            error = '아이디 또는 비밀번호가 올바르지 않습니다.'

    return render(request, 'account/login.html', {
        'next': next_url,
        'error': error,
    })


def custom_signup(request):
    """allauth URL보다 먼저 잡히는 커스텀 회원가입 뷰"""
    errors = {}

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        # 유효성 검사
        if not username:
            errors['username'] = '아이디를 입력하세요.'
        elif User.objects.filter(username=username).exists():
            errors['username'] = '이미 사용 중인 아이디입니다.'
        elif len(username) < 3:
            errors['username'] = '아이디는 3자 이상이어야 합니다.'

        if not password1:
            errors['password1'] = '비밀번호를 입력하세요.'
        elif len(password1) < 8:
            errors['password1'] = '비밀번호는 8자 이상이어야 합니다.'
        elif password1.isdigit():
            errors['password1'] = '비밀번호는 숫자로만 구성될 수 없습니다.'

        if password1 != password2:
            errors['password2'] = '비밀번호가 일치하지 않습니다.'

        if not errors:
            user = User.objects.create_user(username=username, email=email, password=password1)
            UserProfile.objects.get_or_create(user=user)
            user_auth = authenticate(request, username=username, password=password1)
            if user_auth:
                auth_login(request, user_auth,
                           backend='allauth.account.auth_backends.AuthenticationBackend')
            messages.success(request, f'🎉 {username}님, 환영합니다!')
            return redirect('/blog/')

    return render(request, 'account/signup.html', {
        'errors': errors,
        'posted': request.POST if request.method == 'POST' else {},
    })
