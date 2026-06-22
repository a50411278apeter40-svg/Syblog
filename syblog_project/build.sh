#!/usr/bin/env bash
# exit on error
set -o errexit

# ── Python 패키지 설치 ──
pip install -r requirements.txt

# ── Playwright 브라우저 설치 ──
playwright install chromium
playwright install-deps chromium

# ── Django 설정 ──
python manage.py collectstatic --no-input
python manage.py migrate
# DB에 중복 등록된 Google SocialApp 정리 (MultipleObjectsReturned 방지)
python manage.py fix_socialapp
