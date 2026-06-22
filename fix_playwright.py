content = open('/app/syblog_project/blog/views.py').read()

old_browser = '''        elif tool == 'browser':
            action = args.get('action', 'screenshot')
            url = args.get('url', '')
            selector = args.get('selector', '')
            text_input = args.get('text', '')
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    if url:
                        page.goto(url, timeout=15000)
                    if action == 'screenshot':
                        ss_path = str(project_dir / '_screenshot.png')
                        page.screenshot(path=ss_path)
                        browser.close()
                        return {'ok': True, 'screenshot': '_screenshot.png'}
                    elif action == 'get_text':
                        content = page.locator(selector).inner_text() if selector else page.content()
                        browser.close()
                        return {'content': content[:5000]}
                    elif action == 'click':
                        page.click(selector)
                        browser.close()
                        return {'ok': True}
                    elif action == 'type':
                        page.fill(selector, text_input)
                        browser.close()
                        return {'ok': True}
                    else:
                        browser.close()
                        return {'error': '알 수 없는 액션'}
            except ImportError:
                return {'error': 'playwright 미설치'}
            except Exception as e:
                return {'error': str(e)[:200]}'''

new_browser = '''        elif tool == 'browser':
            action = args.get('action', 'screenshot')
            url = args.get('url', '')
            selector = args.get('selector', '')
            text_input = args.get('text', '')
            wait_ms = int(args.get('wait', 1000))
            try:
                from playwright.sync_api import sync_playwright as _sync_pw
                with _sync_pw() as pw:
                    browser = pw.chromium.launch(
                        headless=True,
                        args=['--no-sandbox', '--disable-setuid-sandbox',
                              '--disable-dev-shm-usage', '--disable-gpu']
                    )
                    ctx = browser.new_context(
                        viewport={'width': 1280, 'height': 800},
                        user_agent='Mozilla/5.0 (compatible; SyblogBot/1.0)',
                        ignore_https_errors=True,
                    )
                    page = ctx.new_page()
                    try:
                        if url:
                            page.goto(url, timeout=20000, wait_until='domcontentloaded')
                            if wait_ms > 0:
                                page.wait_for_timeout(min(wait_ms, 3000))
                        if action == 'screenshot':
                            ss_path = str(project_dir / '_screenshot.png')
                            page.screenshot(path=ss_path, full_page=False)
                            return {'ok': True, 'screenshot': '_screenshot.png',
                                    'title': page.title(), 'current_url': page.url}
                        elif action == 'get_text':
                            if selector:
                                try:
                                    txt = page.locator(selector).first.inner_text(timeout=5000)
                                except Exception:
                                    txt = ''
                            else:
                                txt = page.inner_text('body') if page.locator('body').count() else page.content()
                            return {'content': txt[:8000], 'title': page.title()}
                        elif action == 'get_html':
                            html = page.content()
                            return {'html': html[:10000], 'title': page.title()}
                        elif action == 'click':
                            page.locator(selector).first.click(timeout=5000)
                            page.wait_for_timeout(500)
                            return {'ok': True, 'current_url': page.url}
                        elif action == 'type':
                            page.locator(selector).first.fill(text_input, timeout=5000)
                            return {'ok': True}
                        elif action == 'evaluate':
                            js_code = args.get('js', 'document.title')
                            result_js = page.evaluate(js_code)
                            return {'result': str(result_js)[:2000]}
                        else:
                            return {'error': f'알 수 없는 액션: {action}'}
                    finally:
                        browser.close()
            except ImportError:
                return {'error': 'playwright 미설치. 터미널에서: pip install playwright && playwright install chromium'}
            except Exception as e:
                return {'error': f'browser 오류: {str(e)[:300]}'}'''

if old_browser in content:
    content = content.replace(old_browser, new_browser, 1)
    open('/app/syblog_project/blog/views.py', 'w').write(content)
    print("✅ Playwright 브라우저 도구 개선 완료")
else:
    print("❌ 패턴 불일치")
    idx = content.find("elif tool == 'browser':")
    print(f"browser tool 위치: {idx}")
    print(repr(content[idx:idx+300]))
