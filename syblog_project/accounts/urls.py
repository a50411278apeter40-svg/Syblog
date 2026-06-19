from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/<str:username>/', views.profile_view, name='user_profile'),
    path('admin/users/', views.admin_user_list, name='admin_user_list'),
    path('admin/users/<int:user_id>/toggle-block/', views.toggle_block_user, name='toggle_block'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('admin/badges/', views.admin_badge_manage, name='admin_badge_manage'),
    path('admin/badges/award/', views.admin_badge_award, name='admin_badge_award'),
    # ── NEW ──
    path('follow/<str:username>/', views.follow_toggle_view, name='follow_toggle'),
]
