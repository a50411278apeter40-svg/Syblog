"""
Django management command: keepalive
10분마다 자신의 사이트에 핑을 보내 Render 슬립 방지
"""
import threading
import time
import urllib.request
import urllib.error
import datetime
from django.core.management.base import BaseCommand


SITE_URL = "https://syblog.onrender.com"
INTERVAL = 600  # 10분


def ping_loop():
    """백그라운드 스레드 — 10분마다 사이트 핑"""
    time.sleep(30)  # 서버 완전 기동 후 시작
    while True:
        for path in ["/", "/blog/"]:
            try:
                req = urllib.request.Request(
                    SITE_URL + path,
                    headers={"User-Agent": "SyBlog-KeepAlive/1.0"},
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    now = datetime.datetime.now().strftime("%H:%M:%S")
                    print(f"[keepalive {now}] ✅ {path} → HTTP {resp.getcode()}", flush=True)
            except Exception as e:
                print(f"[keepalive] ⚠ {path} → {e}", flush=True)
            time.sleep(2)
        time.sleep(INTERVAL)


class Command(BaseCommand):
    help = "Start keep-alive ping thread (run once on startup)"

    def handle(self, *args, **kwargs):
        self.stdout.write("🚀 keep-alive 스레드 시작 (10분 간격)")
        t = threading.Thread(target=ping_loop, daemon=True)
        t.start()
        # 스레드가 데몬이라 프로세스가 살아있는 동안 계속 실행됨
        while True:
            time.sleep(3600)
