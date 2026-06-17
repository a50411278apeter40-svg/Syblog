#!/usr/bin/env python3
"""
SyBlog Keep-Alive & Auto-Backup Script
Render 무료 플랜 슬립 방지(3분) 및 매 3분마다 전체 데이터 백업
"""
import urllib.request
import urllib.error
import time
import datetime
import sys
import os

# Django 환경 설정 (자동 백업을 위해 필요)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'do_it_django_prj.settings')
import django
django.setup()
from django.core.management import call_command

SITE_URL = "https://syblog.onrender.com"
PING_INTERVAL = 180  # 3분 (초)
ENDPOINTS = [
    "/",
    "/blog/",
]

def ping(url):
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'SyBlog-KeepAlive/1.0'}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            code = resp.getcode()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{now}] ✅ {url} → HTTP {code}", flush=True)
            return True
    except urllib.error.HTTPError as e:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] ❌ {url} → HTTP {e.code}", flush=True)
    except Exception as e:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] ❌ {url} → {e}", flush=True)
    return False

def do_auto_backup():
    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] ⏳ 자동 백업 시작...", flush=True)
        call_command('auto_backup')
    except Exception as e:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] ❌ 자동 백업 실패: {e}", flush=True)

def main():
    print(f"🚀 SyBlog Keep-Alive 및 자동 백업(3분) 시작 — {SITE_URL}", flush=True)
    
    while True:
        # 백업 실행
        do_auto_backup()
        
        # 핑 보내기
        for endpoint in ENDPOINTS:
            ping(SITE_URL + endpoint)
            time.sleep(1)

        next_run = datetime.datetime.now() + datetime.timedelta(seconds=PING_INTERVAL)
        print(f"   다음 백업 및 핑: {next_run.strftime('%H:%M:%S')}", flush=True)
        time.sleep(PING_INTERVAL)

if __name__ == "__main__":
    main()
