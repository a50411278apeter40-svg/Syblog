#!/usr/bin/env bash
# exit on error
set -o errexit

python manage.py collectstatic --no-input
python manage.py migrate
# DB에 중복 등록된 Google SocialApp 정리 (MultipleObjectsReturned 방지)
python manage.py fix_socialapp
