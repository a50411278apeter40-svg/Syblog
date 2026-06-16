#!/usr/bin/env python3
"""
SyBlog Keep-Alive Script
Render 무료 플랜 슬립 방지 — 3분마다 사이트에 핑을 보냅니다.
"""
import urllib.request
import urllib.error
import time
import datetime
import sys

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

def main():
    print(f"🚀 SyBlog Keep-Alive 시작 — {SITE_URL}", flush=True)
    print(f"   핑 간격: {PING_INTERVAL // 60}분", flush=True)

    while True:
        for endpoint in ENDPOINTS:
            ping(SITE_URL + endpoint)
            time.sleep(1)

        next_ping = datetime.datetime.now() + datetime.timedelta(seconds=PING_INTERVAL)
        print(f"   다음 핑: {next_ping.strftime('%H:%M:%S')}", flush=True)
        time.sleep(PING_INTERVAL)

if __name__ == "__main__":
    main()
