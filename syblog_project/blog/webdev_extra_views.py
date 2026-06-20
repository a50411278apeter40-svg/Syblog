"""
AI 웹개발 - 배포 + 미리보기 + 파일서빙 뷰
이 파일은 views.py 끝에 append됩니다.
"""

# ── 원클릭 배포 (Vercel CLI 자동 실행) ─────────────────────────────────────
@login_required
@require_POST
def ai_webdev_deploy(request, pk):
    """
    원클릭 배포: Vercel CLI로 자동 배포 (무료 도메인)
    - vercel CLI 없으면 자동 설치
    - 결과 URL을 DB에 저장
    """
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)

    import os as _os

    def do_deploy():
        # 1. vercel cli 설치 확인 (npx vercel 로 실행)
        node_check = subprocess.run('which node', shell=True, capture_output=True, text=True)
        if node_check.returncode != 0:
            # Node 없으면 netlify drop 방식 (정적파일 zip 업로드)
            yield f"data: {_json_stdlib.dumps({'log': '⚠️ Node.js 없음 → 정적 배포 모드로 전환'})}\n\n"
            result = _deploy_static_netlify(project_dir, project.name)
            yield f"data: {_json_stdlib.dumps({'log': result.get('log',''), 'url': result.get('url',''), 'done': True})}\n\n"
            return

        # 2. package.json 없으면 정적 html 배포
        has_pkg = (project_dir / 'package.json').exists()
        has_index = (project_dir / 'index.html').exists() or (project_dir / 'public' / 'index.html').exists()

        yield f"data: {_json_stdlib.dumps({'log': f'🚀 배포 시작... (프로젝트: {project.name})'})}\n\n"

        # vercel.json 자동 생성
        import json as _j
        if not (project_dir / 'vercel.json').exists():
            if has_pkg:
                vcfg = {"version": 2}
            else:
                vcfg = {"version": 2, "builds": [{"src": "**/*", "use": "@vercel/static"}]}
            (project_dir / 'vercel.json').write_text(_j.dumps(vcfg))
            yield f"data: {_json_stdlib.dumps({'log': '📄 vercel.json 자동 생성'})}\n\n"

        # npx vercel --prod --yes
        yield f"data: {_json_stdlib.dumps({'log': '📦 Vercel CLI 실행 중...'})}\n\n"
        env = {**_os.environ, 'HOME': str(project_dir), 'PATH': '/usr/local/bin:/usr/bin:/bin'}
        proc = subprocess.run(
            'npx vercel --prod --yes --token dummy 2>&1 || true',
            shell=True, cwd=str(project_dir),
            capture_output=True, text=True, timeout=120, env=env
        )
        output = proc.stdout + proc.stderr

        # URL 파싱
        import re as _re
        urls = _re.findall(r'https://[^\s"]+\.vercel\.app[^\s"]*', output)
        deploy_url = urls[0] if urls else ''

        if not deploy_url:
            # fallback: Netlify 정적 배포
            yield f"data: {_json_stdlib.dumps({'log': '⚠️ Vercel 인증 필요 → Netlify 정적 배포로 전환'})}\n\n"
            result = _deploy_static_netlify(project_dir, project.name)
            deploy_url = result.get('url', '')
            for log_line in result.get('logs', []):
                yield f"data: {_json_stdlib.dumps({'log': log_line})}\n\n"
        else:
            yield f"data: {_json_stdlib.dumps({'log': f'✅ 배포 완료!'})}\n\n"

        # DB 저장
        if deploy_url:
            project.deploy_url = deploy_url
            project.status = 'deployed'
            project.save(update_fields=['deploy_url', 'status'])

        yield f"data: {_json_stdlib.dumps({'log': f'🌐 배포 URL: {deploy_url}', 'url': deploy_url, 'done': True})}\n\n"

    resp = StreamingHttpResponse(do_deploy(), content_type='text/event-stream')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp


def _deploy_static_netlify(project_dir, project_name):
    """
    Netlify Drop API로 정적 배포 (API키 불필요 - netlify drop은 공개 API)
    zip으로 묶어서 POST 업로드
    """
    import zipfile, io, urllib.request, urllib.error
    import json as _j

    logs = []
    logs.append('📦 파일 압축 중...')

    # zip 생성 (메모리)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fpath in project_dir.rglob('*'):
            if fpath.is_file() and not any(p in str(fpath) for p in ['node_modules', '.git', '__pycache__', '.venv']):
                arcname = str(fpath.relative_to(project_dir))
                zf.write(fpath, arcname)
    zip_data = buf.getvalue()
    logs.append(f'✅ 압축 완료 ({len(zip_data)//1024}KB)')

    # index.html 없으면 기본 생성
    has_index = (project_dir / 'index.html').exists()
    if not has_index:
        # zip에 index.html 추가
        buf2 = io.BytesIO()
        with zipfile.ZipFile(buf2, 'w', zipfile.ZIP_DEFLATED) as zf2:
            with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as src:
                for item in src.infolist():
                    zf2.writestr(item, src.read(item.filename))
            zf2.writestr('index.html', f'<html><head><title>{project_name}</title></head><body><h1>{project_name}</h1><p>AI가 만든 프로젝트입니다.</p></body></html>')
        zip_data = buf2.getvalue()
        logs.append('📄 index.html 자동 생성')

    logs.append('🚀 Netlify에 업로드 중...')
    try:
        req = urllib.request.Request(
            'https://api.netlify.com/api/v1/sites',
            data=zip_data,
            headers={
                'Content-Type': 'application/zip',
                'User-Agent': 'Syblog-AI-Webdev/1.0',
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = _j.loads(r.read())
        url = data.get('ssl_url') or data.get('url', '')
        logs.append(f'✅ Netlify 배포 성공!')
        return {'url': url, 'logs': logs}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:200]
        logs.append(f'❌ Netlify 오류: {e.code} - {err_body}')
        # surpress error - just return no URL
        return {'url': '', 'logs': logs, 'error': str(e)}
    except Exception as e:
        logs.append(f'❌ 배포 오류: {str(e)[:100]}')
        return {'url': '', 'logs': logs, 'error': str(e)}


# ── 프로젝트 내장 미리보기 (iframe으로 서빙) ───────────────────────────────
@login_required
def ai_webdev_preview(request, pk):
    """
    프로젝트 파일을 Django에서 직접 서빙 → iframe으로 미리보기
    path GET 파라미터로 특정 파일 지정 (기본: index.html)
    """
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)

    file_path = request.GET.get('path', 'index.html').lstrip('/')
    target = (project_dir / file_path).resolve()

    if not str(target).startswith(str(project_dir)):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('허용되지 않은 경로')

    if not target.exists():
        # index.html 없으면 파일 목록 표시
        files = []
        if project_dir.exists():
            for p in sorted(project_dir.rglob('*')):
                if p.is_file() and 'node_modules' not in str(p):
                    files.append(str(p.relative_to(project_dir)))
        html = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><title>{project.name} - 파일 목록</title>
<style>body{{font-family:sans-serif;padding:20px;background:#f5f5f5;}}
a{{display:block;padding:6px;color:#6c63ff;text-decoration:none;}}
a:hover{{background:#eef;}}h2{{color:#333;}}</style></head>
<body><h2>📁 {project.name}</h2>
<p>index.html이 없습니다. 파일 목록:</p>
{''.join(f'<a href="?path={f}">{f}</a>' for f in files) or '<p>파일이 없습니다.</p>'}
</body></html>"""
        return HttpResponse(html, content_type='text/html; charset=utf-8')

    # MIME 타입 결정
    import mimetypes
    mime, _ = mimetypes.guess_type(str(target))
    if not mime:
        mime = 'text/plain'

    # HTML 파일은 base 경로 주입 (상대경로 자원 처리)
    if mime == 'text/html':
        content = target.read_text(encoding='utf-8', errors='replace')
        # 상대 경로 → 프리뷰 경로로 rewrite
        base_tag = f'<base href="/blog/ai-webdev/{pk}/preview/">'
        if '<head>' in content:
            content = content.replace('<head>', f'<head>{base_tag}', 1)
        elif '<html>' in content:
            content = content.replace('<html>', f'<html><head>{base_tag}</head>', 1)
        return HttpResponse(content, content_type='text/html; charset=utf-8')

    # CSS / JS / 이미지 등
    return HttpResponse(target.read_bytes(), content_type=mime)


# ── 미리보기용 정적파일 서빙 (base href 없이 직접) ─────────────────────────
@login_required
def ai_webdev_static(request, pk, filepath):
    """프로젝트 내 정적파일 서빙 (CSS, JS, 이미지 등)"""
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)

    target = (project_dir / filepath.lstrip('/')).resolve()
    if not str(target).startswith(str(project_dir)) or not target.exists():
        from django.http import Http404
        raise Http404

    import mimetypes
    mime, _ = mimetypes.guess_type(str(target))
    return HttpResponse(target.read_bytes(), content_type=mime or 'application/octet-stream')


# ── 터미널 스트리밍 실행 ─────────────────────────────────────────────────────
@login_required  
def ai_webdev_terminal_stream(request, pk):
    """터미널 명령어를 실시간 스트리밍으로 실행"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    from blog.models import AiWebProject
    import os as _os

    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)

    try:
        body = _json_mod.loads(request.body)
        cmd = body.get('command', '').strip()
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    if not cmd:
        return JsonResponse({'error': '명령어를 입력하세요'}, status=400)

    blocked = ['rm -rf /', ':(){', '>/dev/sda', 'shutdown', 'reboot']
    for b in blocked:
        if b in cmd:
            return JsonResponse({'error': f'차단된 명령어입니다'}, status=400)

    def stream_cmd():
        try:
            env = {**_os.environ, 'HOME': str(project_dir), 'PATH': '/usr/local/bin:/usr/bin:/bin:/usr/local/sbin'}
            proc = subprocess.Popen(
                cmd, shell=True, cwd=str(project_dir),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env,
                bufsize=1
            )
            for line in iter(proc.stdout.readline, ''):
                yield f"data: {_json_stdlib.dumps({'line': line})}\n\n"
            proc.wait()
            yield f"data: {_json_stdlib.dumps({'done': True, 'returncode': proc.returncode})}\n\n"
        except Exception as e:
            yield f"data: {_json_stdlib.dumps({'error': str(e), 'done': True})}\n\n"

    resp = StreamingHttpResponse(stream_cmd(), content_type='text/event-stream')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp


# ── 프로젝트 파일 읽기/저장 API (에디터용) ──────────────────────────────────
@login_required
def ai_webdev_file_read(request, pk):
    """특정 파일 내용 반환"""
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)
    path = request.GET.get('path', '').lstrip('/')
    if not path:
        return JsonResponse({'error': '경로 필요'}, status=400)
    target = (project_dir / path).resolve()
    if not str(target).startswith(str(project_dir)):
        return JsonResponse({'error': '허용되지 않은 경로'}, status=403)
    if not target.exists():
        return JsonResponse({'error': '파일 없음'}, status=404)
    content = target.read_text(encoding='utf-8', errors='replace')
    return JsonResponse({'content': content, 'path': path})


@login_required
@require_POST
def ai_webdev_file_write(request, pk):
    """파일 저장"""
    from blog.models import AiWebProject
    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)
    try:
        body = _json_mod.loads(request.body)
        path = body.get('path', '').lstrip('/')
        content = body.get('content', '')
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)
    if not path:
        return JsonResponse({'error': '경로 필요'}, status=400)
    target = (project_dir / path).resolve()
    if not str(target).startswith(str(project_dir)):
        return JsonResponse({'error': '허용되지 않은 경로'}, status=403)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')
    return JsonResponse({'ok': True, 'path': path})
