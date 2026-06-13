from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from .models import UserProfile, LEVEL_THRESHOLDS
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
    return render(request, 'accounts/profile.html', {
        'profile_user': user,
        'profile': profile,
        'posts': posts,
        'series_list': series_list,
        'level_thresholds': LEVEL_THRESHOLDS,
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
