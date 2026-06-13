#!/usr/bin/env bash
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
# 관리자 계정 생성 (없으면)
python manage.py shell -c "
from django.contrib.auth.models import User
from accounts.models import UserProfile
if not User.objects.filter(username='admin').exists():
    u = User.objects.create_superuser('admin', 'admin@syblog.com', '1234aiai')
    UserProfile.objects.get_or_create(user=u)
    print('관리자 계정 생성됨')
else:
    print('관리자 계정 이미 존재')
"
