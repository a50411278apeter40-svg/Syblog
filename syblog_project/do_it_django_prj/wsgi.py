import os
import threading
import time
import urllib.request
import urllib.error
import datetime

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'do_it_django_prj.settings')

application = get_wsgi_application()

# ── Keep-Alive 백그라운드 스레드 ──────────────────────────────────
SITE_URL = "https://syblog.onrender.com"
PING_INTERVAL = 600  # 10분 (초)


def _keepalive():
    """Render 슬립 방지: 10분마다 자기 사이트에 GET 요청"""
    time.sleep(60)  # 서버 완전 기동 대기
    while True:
        for path in ["/", "/blog/"]:
            try:
                req = urllib.request.Request(
                    SITE_URL + path,
                    headers={"User-Agent": "SyBlog-KeepAlive/1.0"},
                )
                with urllib.request.urlopen(req, timeout=25) as resp:
                    now = datetime.datetime.now().strftime("%H:%M:%S")
                    print(
                        f"[keepalive {now}] ✅ {path} → HTTP {resp.getcode()}",
                        flush=True,
                    )
            except Exception as exc:
                print(f"[keepalive] ⚠  {path} → {exc}", flush=True)
            time.sleep(3)
        time.sleep(PING_INTERVAL)


_t = threading.Thread(target=_keepalive, daemon=True, name="keepalive")
_t.start()
# ─────────────────────────────────────────────────────────────────
