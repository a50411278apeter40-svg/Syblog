content = open('/app/syblog_project/blog/views.py').read()

OLD = """def _get_pw_page(pk, viewport_w=1280, viewport_h=800):
    \"\"\"프로젝트별 Playwright 페이지를 영구 유지/재사용한다.\"\"\"
    import threading
    try:
        from playwright.sync_api import sync_playwright as _sync_pw
    except ImportError:
        # 자동 설치 시도
        import subprocess, sys
        venv_pip = '/opt/render/project/src/.venv/bin/pip'
        pip_cmd = venv_pip if __import__('os').path.exists(venv_pip) else sys.executable.replace('python', 'pip').replace('python3', 'pip3')
        subprocess.run([pip_cmd, 'install', 'playwright==1.49.1'], check=False)
        venv_pw = '/opt/render/project/src/.venv/bin/playwright'
        pw_cmd = venv_pw if __import__('os').path.exists(venv_pw) else 'playwright'
        subprocess.run([pw_cmd, 'install', 'chromium'], check=False)
        from playwright.sync_api import sync_playwright as _sync_pw
    sess = _pw_sessions.get(pk)
    # 살아있는 세션 재사용
    if sess:
        try:
            _ = sess['page'].url   # 살아있는지 ping
            return sess['page'], sess
        except Exception:
            try: sess['browser'].close()
            except Exception: pass
            try: sess['pw'].__exit__(None, None, None)
            except Exception: pass
            _pw_sessions.pop(pk, None)
    # 새 세션 시작
    pw_ctx = _sync_pw()
    pw = pw_ctx.__enter__()
    browser = pw.chromium.launch(
        headless=True,
        args=['--no-sandbox','--disable-setuid-sandbox',
              '--disable-dev-shm-usage','--disable-gpu',
              '--disable-extensions']
    )
    ctx = browser.new_context(
        viewport={'width': viewport_w, 'height': viewport_h},
        user_agent='Mozilla/5.0 (compatible; SyblogBot/1.0)',
        ignore_https_errors=True,
    )
    page = ctx.new_page()
    sess = {'pw_ctx': pw_ctx, 'pw': pw, 'browser': browser, 'ctx': ctx, 'page': page}
    _pw_sessions[pk] = sess
    return page, sess"""

NEW = """def _get_pw_page(pk, viewport_w=1280, viewport_h=800):
    \"\"\"프로젝트별 Playwright 페이지를 영구 유지/재사용한다.\"\"\"
    if not _ensure_playwright():
        raise ImportError('playwright 설치 실패')
    try:
        from playwright.sync_api import sync_playwright as _sync_pw
    except ImportError as e:
        raise ImportError(f'playwright import 실패: {e}')

    sess = _pw_sessions.get(pk)
    if sess:
        try:
            _ = sess['page'].url
            return sess['page'], sess
        except Exception:
            try: sess['browser'].close()
            except Exception: pass
            try: sess['pw'].__exit__(None, None, None)
            except Exception: pass
            _pw_sessions.pop(pk, None)

    pw_ctx = _sync_pw()
    pw = pw_ctx.__enter__()
    browser = pw.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox', '--disable-setuid-sandbox',
            '--disable-dev-shm-usage', '--disable-gpu',
            '--disable-extensions', '--single-process',
        ]
    )
    ctx = browser.new_context(
        viewport={'width': viewport_w, 'height': viewport_h},
        user_agent='Mozilla/5.0 (compatible; SyblogBot/1.0)',
        ignore_https_errors=True,
    )
    page = ctx.new_page()
    sess = {'pw_ctx': pw_ctx, 'pw': pw, 'browser': browser, 'ctx': ctx, 'page': page}
    _pw_sessions[pk] = sess
    return page, sess"""

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    print("OK: _get_pw_page replaced")
else:
    print("FAIL: not found")
    idx = content.find("def _get_pw_page")
    print(repr(content[idx:idx+300]))

open('/app/syblog_project/blog/views.py', 'w').write(content)
