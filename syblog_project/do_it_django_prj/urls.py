from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import custom_login, custom_signup

urlpatterns = [
    # ── 커스텀 로그인/회원가입 (allauth보다 먼저 위치해야 함) ──
    path('accounts/login/', custom_login, name='account_login'),
    path('accounts/signup/', custom_signup, name='account_signup'),

    path('blog/', include('blog.urls')),
    path('admin/', admin.site.urls),
    path('markdownx/', include('markdownx.urls')),
    # allauth 65.x URL (socialaccount, logout 등 포함)
    path('accounts/', include('allauth.urls')),
    path('user/', include('accounts.urls')),
    path('challenges/', include('challenges.urls')),
    path('mail/', include('mail_system.urls')),
    path('', include('single_pages.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
