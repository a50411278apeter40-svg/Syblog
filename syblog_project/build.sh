#!/usr/bin/env bash
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
python manage.py shell << 'PYEOF'
from django.contrib.auth.models import User
from accounts.models import UserProfile
if not User.objects.filter(username='admin').exists():
    u = User.objects.create_superuser('admin', 'admin@syblog.com', '1234aiai')
    UserProfile.objects.get_or_create(user=u)
    print('admin 계정 생성 완료')
else:
    u = User.objects.get(username='admin')
    u.set_password('1234aiai')
    u.save()
    UserProfile.objects.get_or_create(user=u)
    print('admin 계정 확인 완료')
PYEOF
