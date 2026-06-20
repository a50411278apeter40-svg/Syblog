
# ═══════════════════════════════════════════════════════════════════════
# ══  AI 크레딧 시스템  ══════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════

def _get_or_create_credit(user):
    """유저 크레딧 객체 가져오기 (없으면 생성, 관리자는 무제한)"""
    from blog.models import AiCredit
    credit, created = AiCredit.objects.get_or_create(
        user=user,
        defaults={
            'credits': 30,
            'is_unlimited': user.is_staff or user.is_superuser,
        }
    )
    if (user.is_staff or user.is_superuser) and not credit.is_unlimited:
        credit.is_unlimited = True
        credit.save(update_fields=['is_unlimited'])
    return credit


def _log_credit(user, action, amount, balance, note=''):
    """크레딧 변동 로그"""
    from blog.models import AiCreditLog
    AiCreditLog.objects.create(user=user, action=action, amount=amount, balance=balance, note=note)


@login_required
def ai_credit_status(request):
    credit = _get_or_create_credit(request.user)
    profile = getattr(request.user, 'profile', None)
    points = profile.points if profile else 0
    return JsonResponse({
        'credits': -1 if credit.is_unlimited else credit.credits,
        'is_unlimited': credit.is_unlimited,
        'total_used': credit.total_used,
        'points': points,
        'can_buy_normal': (points // 10) * 5,
        'can_buy_webdev': (points // 30) * 10,
    })


@login_required
@require_POST
def ai_credit_buy(request):
    """포인트로 AI 크레딧 구매"""
    try:
        body = _json_mod.loads(request.body)
        credit_type = body.get('type', 'normal')
        amount = int(body.get('amount', 1))
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    if amount < 1 or amount > 100:
        return JsonResponse({'error': '구매 수량은 1~100 사이입니다'}, status=400)

    from accounts.models import UserProfile
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return JsonResponse({'error': '프로필이 없습니다'}, status=400)

    credit = _get_or_create_credit(request.user)

    if credit_type == 'webdev':
        cost_points = 30 * amount
        gain_credits = 10 * amount
    else:
        cost_points = 10 * amount
        gain_credits = 5 * amount

    if profile.points < cost_points:
        return JsonResponse({
            'error': f'포인트가 부족합니다. 필요: {cost_points}포인트, 보유: {profile.points}포인트'
        }, status=400)

    profile.points -= cost_points
    profile.save(update_fields=['points'])
    credit.add(gain_credits)
    _log_credit(request.user, 'buy', gain_credits, credit.credits,
                note=f'{cost_points}포인트 → {gain_credits}크레딧 ({credit_type})')

    return JsonResponse({
        'ok': True,
        'credits': credit.credits,
        'points': profile.points,
        'gained': gain_credits,
        'spent_points': cost_points,
    })


import json as _json_stdlib
from django.http import StreamingHttpResponse

@login_required
def ai_chat_stream(request):
    """AI 채팅 스트리밍 (크레딧 1 차감, 관리자 무제한)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    credit = _get_or_create_credit(request.user)

    if not credit.can_use(1):
        return JsonResponse({
            'error': '크레딧이 부족합니다. 포인트로 크레딧을 구매하세요.',
            'credits': credit.credits,
            'no_credit': True,
        }, status=402)

    try:
        body = _json_mod.loads(request.body)
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    history   = body.get('history', [])
    message   = body.get('message', '').strip()
    mode      = body.get('mode', 'custom')
    text      = body.get('text', '').strip()

    if not message and not text:
        return JsonResponse({'error': '메시지를 입력하세요'}, status=400)

    if mode == 'custom':
        if history:
            ctx_parts = []
            for h in history[-10:]:
                role_label = "사용자" if h.get("role") == "user" else "AI"
                ctx_parts.append(f"[{role_label}]: {h.get('content','')[:600]}")
            context_str = "\n".join(ctx_parts)
            prompt = f"이전 대화:\n{context_str}\n\n[사용자]: {message}\n\n위 맥락을 이어받아 한국어로 자세하게 답해줘."
        else:
            prompt = message
    else:
        prompt = message or text

    system_msg = '당신은 한국어 블로그 글쓰기를 도와주는 AI 보조자입니다. 항상 한국어로 친절하게 답변하세요.'

    def stream_response():
        try:
            from g4f.client import Client as G4FClient
            client = G4FClient()
            response = client.chat.completions.create(
                model='gpt-4',
                messages=[
                    {'role': 'system', 'content': system_msg},
                    {'role': 'user', 'content': prompt}
                ],
                stream=True
            )
            full_text = ''
            for chunk in response:
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        token = delta.content
                        full_text += token
                        yield f"data: {_json_stdlib.dumps({'token': token})}\n\n"
            yield f"data: {_json_stdlib.dumps({'done': True, 'full': full_text})}\n\n"
        except Exception as e:
            try:
                from g4f.client import Client as G4FClient
                client = G4FClient()
                response = client.chat.completions.create(
                    model='gpt-4',
                    messages=[
                        {'role': 'system', 'content': system_msg},
                        {'role': 'user', 'content': prompt}
                    ]
                )
                result = response.choices[0].message.content or '응답을 받지 못했습니다.'
                yield f"data: {_json_stdlib.dumps({'token': result})}\n\n"
                yield f"data: {_json_stdlib.dumps({'done': True, 'full': result})}\n\n"
            except Exception as e2:
                yield f"data: {_json_stdlib.dumps({'error': str(e2)[:100], 'done': True})}\n\n"

    credit.use(1)
    _log_credit(request.user, 'use', -1, credit.credits if not credit.is_unlimited else -1,
                note=f'AI채팅 | {message[:50]}')

    response = StreamingHttpResponse(stream_response(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@login_required
def ai_credit_shop(request):
    """크레딧 구매 페이지"""
    credit = _get_or_create_credit(request.user)
    profile = getattr(request.user, 'profile', None)
    from blog.models import AiCreditLog
    logs = AiCreditLog.objects.filter(user=request.user).order_by('-created_at')[:20]
    return render(request, 'blog/ai_credit_shop.html', {
        'credit': credit,
        'profile': profile,
        'logs': logs,
    })


@login_required
def admin_ai_credits(request):
    """관리자 전용: 모든 유저 크레딧 관리"""
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied

    from blog.models import AiCredit, AiCreditLog
    from django.contrib.auth.models import User as AuthUser

    if request.method == 'POST':
        action = request.POST.get('action', '')
        user_id = request.POST.get('user_id')
        try:
            target_user = AuthUser.objects.get(pk=user_id)
            credit = _get_or_create_credit(target_user)

            if action == 'set':
                new_val = int(request.POST.get('value', 30))
                old = credit.credits
                credit.credits = new_val
                credit.save(update_fields=['credits'])
                _log_credit(target_user, 'admin', new_val - old, credit.credits,
                            note=f'관리자({request.user.username}) 직접 설정')
            elif action == 'add':
                amount = int(request.POST.get('value', 0))
                credit.add(amount)
                _log_credit(target_user, 'admin', amount, credit.credits,
                            note=f'관리자({request.user.username}) 지급')
            elif action == 'reset':
                old = credit.credits
                credit.credits = 30
                credit.save(update_fields=['credits'])
                _log_credit(target_user, 'reset', 30 - old, 30,
                            note=f'관리자({request.user.username}) 초기화')
            elif action == 'unlimited':
                credit.is_unlimited = not credit.is_unlimited
                credit.save(update_fields=['is_unlimited'])

            from django.contrib import messages as dj_messages
            dj_messages.success(request, f'{target_user.username} 크레딧이 수정되었습니다.')
        except Exception as e:
            from django.contrib import messages as dj_messages
            dj_messages.error(request, f'오류: {e}')
        return redirect('blog:admin_ai_credits')

    credits_qs = AiCredit.objects.select_related('user').order_by('-updated_at')
    all_users = AuthUser.objects.filter(is_active=True).order_by('username')
    credit_map = {c.user_id: c for c in credits_qs}
    user_credits = []
    for u in all_users:
        c = credit_map.get(u.pk)
        user_credits.append({'user': u, 'credit': c})

    recent_logs = AiCreditLog.objects.select_related('user').order_by('-created_at')[:50]

    return render(request, 'blog/admin_ai_credits.html', {
        'user_credits': user_credits,
        'recent_logs': recent_logs,
    })


# ═══════════════════════════════════════════════════════════════════════
# ══  AI 웹개발 베타  ════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
import subprocess, shutil
from pathlib import Path as _Path

WEBDEV_WORKSPACE = _Path('/tmp/syblog_webdev')
WEBDEV_WORKSPACE.mkdir(exist_ok=True)


def _get_project_dir(project_id):
    d = WEBDEV_WORKSPACE / str(project_id)
    d.mkdir(exist_ok=True)
    return d


@login_required
def ai_webdev(request):
    from blog.models import AiWebProject
    projects = AiWebProject.objects.filter(user=request.user).order_by('-updated_at')
    credit = _get_or_create_credit(request.user)
    return render(request, 'blog/ai_webdev.html', {
        'projects': projects,
        'credit': credit,
    })


@login_required
@require_POST
def ai_webdev_new_project(request):
    from blog.models import AiWebProject
    try:
        body = _json_mod.loads(request.body)
        name = body.get('name', '').strip()[:100]
        desc = body.get('description', '').strip()
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    if not name:
        return JsonResponse({'error': '프로젝트 이름을 입력하세요'}, status=400)

    project = AiWebProject.objects.create(user=request.user, name=name, description=desc)
    _get_project_dir(project.pk)
    return JsonResponse({'ok': True, 'id': project.pk, 'name': project.name})


@login_required
def ai_webdev_project(request, pk):
    from blog.models import AiWebProject, AiWebSession
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    sessions = AiWebSession.objects.filter(project=project).order_by('created_at')
    credit = _get_or_create_credit(request.user)
    return render(request, 'blog/ai_webdev_project.html', {
        'project': project,
        'sessions': sessions,
        'credit': credit,
        'project_dir': str(_get_project_dir(project.pk)),
    })


@login_required
@require_POST
def ai_webdev_tool(request):
    from blog.models import AiWebProject
    try:
        body = _json_mod.loads(request.body)
        project_id = body.get('project_id')
        tool = body.get('tool', '')
        args = body.get('args', {})
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    project = get_object_or_404(AiWebProject, pk=project_id, user=request.user)
    project_dir = _get_project_dir(project.pk)
    result = _run_webdev_tool(tool, args, project_dir)
    return JsonResponse({'ok': True, 'result': result})


def _run_webdev_tool(tool, args, project_dir):
    try:
        if tool == 'write_file':
            path = (project_dir / args['path'].lstrip('/')).resolve()
            if not str(path).startswith(str(project_dir)):
                return {'error': '허용되지 않은 경로'}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args.get('content', ''), encoding='utf-8')
            return {'ok': True, 'path': str(path.relative_to(project_dir))}

        elif tool == 'read_file':
            path = (project_dir / args['path'].lstrip('/')).resolve()
            if not str(path).startswith(str(project_dir)):
                return {'error': '허용되지 않은 경로'}
            if not path.exists():
                return {'error': '파일이 없습니다'}
            content = path.read_text(encoding='utf-8', errors='replace')
            return {'content': content[:50000]}

        elif tool == 'list_files':
            sub = args.get('path', '.')
            target = (project_dir / sub.lstrip('/')).resolve()
            if not str(target).startswith(str(project_dir)):
                return {'error': '허용되지 않은 경로'}
            files = []
            if target.exists():
                for p in sorted(target.iterdir()):
                    files.append({
                        'name': p.name,
                        'type': 'dir' if p.is_dir() else 'file',
                        'size': p.stat().st_size if p.is_file() else 0,
                    })
            return {'files': files}

        elif tool == 'run_command':
            cmd = args.get('command', '')
            if not cmd:
                return {'error': '명령어가 없습니다'}
            blocked = ['rm -rf /', ':(){', '>/dev/sda']
            for b in blocked:
                if b in cmd:
                    return {'error': f'차단된 명령어'}
            import os as _os
            proc = subprocess.run(
                cmd, shell=True, cwd=str(project_dir),
                capture_output=True, text=True, timeout=60,
                env={**_os.environ, 'HOME': str(project_dir), 'PATH': '/usr/local/bin:/usr/bin:/bin'}
            )
            return {
                'stdout': proc.stdout[-10000:],
                'stderr': proc.stderr[-3000:],
                'returncode': proc.returncode,
            }

        elif tool == 'web_search':
            query = args.get('query', '')
            import urllib.request, urllib.parse, html as _html, re as _re
            encoded = urllib.parse.quote(query)
            url = f'https://html.duckduckgo.com/html/?q={encoded}'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                html_text = r.read().decode('utf-8', errors='replace')
            results = []
            titles = _re.findall(r'class="result__title"[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html_text, _re.DOTALL)
            snippets = _re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html_text, _re.DOTALL)
            for i, (href, title) in enumerate(titles[:5]):
                snippet = _html.unescape(_re.sub(r'<[^>]+>', '', snippets[i])).strip() if i < len(snippets) else ''
                results.append({
                    'title': _html.unescape(_re.sub(r'<[^>]+>', '', title)).strip(),
                    'url': href,
                    'snippet': snippet,
                })
            return {'results': results}

        elif tool == 'download_file':
            url = args.get('url', '')
            filename = _Path(args.get('filename', 'downloaded_file')).name
            import urllib.request
            dest = project_dir / filename
            urllib.request.urlretrieve(url, dest)
            return {'ok': True, 'path': filename, 'size': dest.stat().st_size}

        elif tool == 'delete_file':
            path = (project_dir / args['path'].lstrip('/')).resolve()
            if not str(path).startswith(str(project_dir)):
                return {'error': '허용되지 않은 경로'}
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
            return {'ok': True}

        elif tool == 'browser':
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
                return {'error': str(e)[:200]}

        else:
            return {'error': f'알 수 없는 도구: {tool}'}

    except Exception as e:
        return {'error': str(e)[:300]}


@login_required
def ai_webdev_chat(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    credit = _get_or_create_credit(request.user)
    if not credit.can_use(1):
        return JsonResponse({
            'error': '크레딧이 부족합니다.',
            'credits': credit.credits,
            'no_credit': True,
        }, status=402)

    try:
        body = _json_mod.loads(request.body)
        project_id = body.get('project_id')
        message    = body.get('message', '').strip()
        history    = body.get('history', [])
        tool_results = body.get('tool_results', [])
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    from blog.models import AiWebProject, AiWebSession
    project = get_object_or_404(AiWebProject, pk=project_id, user=request.user)

    TOOLS_DESC = """당신은 풀스택 웹 개발 AI 에이전트입니다. 실제로 파일을 만들고 코드를 실행할 수 있습니다.

사용 가능한 도구 (도구 호출 시 아래 형식 사용):
<tool_call>{"tool":"write_file","args":{"path":"파일경로","content":"내용"}}</tool_call>
<tool_call>{"tool":"read_file","args":{"path":"파일경로"}}</tool_call>
<tool_call>{"tool":"list_files","args":{"path":"."}}</tool_call>
<tool_call>{"tool":"run_command","args":{"command":"명령어"}}</tool_call>
<tool_call>{"tool":"web_search","args":{"query":"검색어"}}</tool_call>
<tool_call>{"tool":"download_file","args":{"url":"URL","filename":"파일명"}}</tool_call>
<tool_call>{"tool":"browser","args":{"action":"screenshot","url":"URL"}}</tool_call>
<tool_call>{"tool":"delete_file","args":{"path":"파일경로"}}</tool_call>

React 스타일로 도구를 호출하고 결과를 받아 다음 단계를 진행하세요.
항상 한국어로 설명하며 실제로 작동하는 코드를 작성하세요."""

    ctx_parts = [f'[프로젝트] {project.name}: {project.description}']
    for h in history[-8:]:
        role_label = "사용자" if h.get("role") == "user" else "AI"
        ctx_parts.append(f"[{role_label}]: {h.get('content','')[:800]}")
    if tool_results:
        ctx_parts.append(f"[도구 실행 결과]: {_json_stdlib.dumps(tool_results, ensure_ascii=False)[:2000]}")
    ctx_parts.append(f"[사용자]: {message}")
    full_prompt = "\n".join(ctx_parts)

    AiWebSession.objects.create(project=project, role='user', content=message)

    def stream_response():
        try:
            from g4f.client import Client as G4FClient
            client = G4FClient()
            response = client.chat.completions.create(
                model='gpt-4',
                messages=[
                    {'role': 'system', 'content': TOOLS_DESC},
                    {'role': 'user', 'content': full_prompt}
                ],
                stream=True
            )
            full_text = ''
            for chunk in response:
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        token = delta.content
                        full_text += token
                        yield f"data: {_json_stdlib.dumps({'token': token})}\n\n"
            AiWebSession.objects.create(project=project, role='ai', content=full_text)
            yield f"data: {_json_stdlib.dumps({'done': True, 'full': full_text})}\n\n"
        except Exception as e:
            try:
                from g4f.client import Client as G4FClient
                client = G4FClient()
                response = client.chat.completions.create(
                    model='gpt-4',
                    messages=[
                        {'role': 'system', 'content': TOOLS_DESC},
                        {'role': 'user', 'content': full_prompt}
                    ]
                )
                result = response.choices[0].message.content or '응답 오류'
                AiWebSession.objects.create(project=project, role='ai', content=result)
                yield f"data: {_json_stdlib.dumps({'token': result})}\n\n"
                yield f"data: {_json_stdlib.dumps({'done': True, 'full': result})}\n\n"
            except Exception as e2:
                yield f"data: {_json_stdlib.dumps({'error': str(e2)[:100], 'done': True})}\n\n"

    credit.use(1)
    _log_credit(request.user, 'webdev', -1, credit.credits if not credit.is_unlimited else -1,
                note=f'AI웹개발|{project.name}|{message[:40]}')

    resp = StreamingHttpResponse(stream_response(), content_type='text/event-stream')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp


@login_required
def ai_webdev_files(request, pk):
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)

    def walk_dir(d, base):
        items = []
        try:
            for p in sorted(d.iterdir()):
                if p.name.startswith('.') or p.name == '__pycache__':
                    continue
                rel = str(p.relative_to(base))
                if p.is_dir():
                    items.append({'name': p.name, 'path': rel, 'type': 'dir', 'children': walk_dir(p, base)})
                else:
                    items.append({'name': p.name, 'path': rel, 'type': 'file', 'size': p.stat().st_size})
        except Exception:
            pass
        return items

    files = walk_dir(project_dir, project_dir) if project_dir.exists() else []
    return JsonResponse({'files': files})
