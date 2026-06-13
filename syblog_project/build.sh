#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate

python manage.py shell << 'PYEOF'
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from accounts.models import UserProfile

# 관리자 계정
if not User.objects.filter(username='admin').exists():
    u = User.objects.create_superuser('admin', 'admin@syblog.com', '1234aiai')
    UserProfile.objects.get_or_create(user=u)
    print('✅ admin 계정 생성')
else:
    u = User.objects.get(username='admin')
    u.set_password('1234aiai')
    u.save()
    UserProfile.objects.get_or_create(user=u)
    print('✅ admin 계정 확인')

# Site 도메인 syblog.onrender.com 으로 설정
site, _ = Site.objects.get_or_create(id=1)
site.domain = 'syblog.onrender.com'
site.name = 'SyBlog'
site.save()
print(f'✅ Site 설정: {site.domain}')

# Google SocialApp 등록 (환경변수에서 읽기)
import os
google_client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
google_client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '')

if google_client_id and google_client_secret:
    from allauth.socialaccount.models import SocialApp
    app, created = SocialApp.objects.get_or_create(provider='google')
    app.name = 'Google'
    app.client_id = google_client_id
    app.secret = google_client_secret
    app.save()
    if site not in app.sites.all():
        app.sites.add(site)
    print(f'✅ Google OAuth 앱 {"생성" if created else "업데이트"}')
else:
    print('⚠️  GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET 환경변수 미설정 — Google 로그인 비활성')
PYEOF
