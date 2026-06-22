import re

content = open('/app/syblog_project/blog/views.py').read()

# Find exact markers
start_idx = content.find('def ai_webdev_terminal_stream(request, pk):')
end_idx = content.find('@login_required\ndef ai_webdev_file_read(request, pk):')

if start_idx == -1 or end_idx == -1:
    print(f"마커 못 찾음. start={start_idx}, end={end_idx}")
    exit(1)

# 앞쪽 데코레이터 포함 (login_required  \n 포함)
# start_idx 앞에서 @login_required 찾기
prefix_search = content.rfind('@login_required', 0, start_idx)
func_start = prefix_search  # 데코레이터부터

old_section = content[func_start:end_idx]
print(f"교체할 구간: {func_start}~{end_idx}, 길이={len(old_section)}")
print("=== 기존 함수 첫 3줄 ===")
for line in old_section.splitlines()[:3]:
    print(repr(line))

new_func = '''@login_required
def ai_webdev_terminal_stream(request, pk):
    """터미널 명령어 실시간 스트리밍 (venv 자동교정 + cd 세션유지)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    from blog.models import AiWebProject
    import os as _os
    import re as _re

    project = get_object_or_404(AiWebProject, pk=pk, user=request.user)
    project_dir = _get_project_dir(project.pk)

    try:
        body = _json_mod.loads(request.body)
        cmd = body.get('command', '').strip()
        cwd_rel = body.get('cwd', '.').strip()
    except Exception:
        return JsonResponse({'error': '잘못된 요청'}, status=400)

    if not cmd:
        return JsonResponse({'error': '명령어를 입력하세요'}, status=400)

    blocked = ['rm -rf /', ':(){', '>/dev/sda', 'shutdown', 'reboot']
    for b in blocked:
        if b in cmd:
            return JsonResponse({'error': '차단된 명령어입니다'}, status=400)

    # venv 경로
    venv_base = '/opt/render/project/src/.venv'
    venv_bin  = f'{venv_base}/bin'
    venv_pip  = f'{venv_bin}/pip'
    venv_py   = f'{venv_bin}/python3'

    def fix_cmd(c):
        if venv_bin in c:
            return c
        c = _re.sub(r'\\bpip3?\\s+install\\b', f'{venv_pip} install', c)
        c = _re.sub(r'\\bpip3?\\b', venv_pip, c)
        c = _re.sub(r'\\bpython3?\\b', venv_py, c)
        return c

    cmd_fixed = fix_cmd(cmd)

    # CWD 계산
    try:
        cwd_path = project_dir if (not cwd_rel or cwd_rel == '.') else (project_dir / cwd_rel).resolve()
        if not str(cwd_path).startswith(str(project_dir)):
            cwd_path = project_dir
    except Exception:
        cwd_path = project_dir

    def stream_cmd():
        try:
            env = {
                **_os.environ,
                'HOME': str(project_dir),
                'PATH': f'{venv_bin}:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin',
                'VIRTUAL_ENV': venv_base,
            }

            # cd 명령 처리
            cd_match = _re.match(r'^cd\\s*(.*)', cmd.strip())
            if cd_match:
                target = cd_match.group(1).strip()
                if not target or target == '~':
                    new_dir = project_dir
                elif target == '..':
                    new_dir = cwd_path.parent
                else:
                    new_dir = (cwd_path / target).resolve()
                if str(new_dir).startswith(str(project_dir)) and new_dir.is_dir():
                    try:
                        rel = str(new_dir.relative_to(project_dir))
                    except ValueError:
                        rel = '.'
                    yield f"data: {_json_stdlib.dumps({'done': True, 'returncode': 0, 'new_cwd': rel})}\\n\\n"
                else:
                    yield f"data: {_json_stdlib.dumps({'line': f'cd: {target}: No such directory\\n'})}\\n\\n"
                    yield f"data: {_json_stdlib.dumps({'done': True, 'returncode': 1})}\\n\\n"
                return

            proc = subprocess.Popen(
                cmd_fixed, shell=True,
                cwd=str(cwd_path),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env, bufsize=1
            )
            for line in iter(proc.stdout.readline, ''):
                yield f"data: {_json_stdlib.dumps({'line': line})}\\n\\n"
            proc.wait()
            try:
                rel_cwd = str(cwd_path.relative_to(project_dir))
            except ValueError:
                rel_cwd = '.'
            yield f"data: {_json_stdlib.dumps({'done': True, 'returncode': proc.returncode, 'cwd': rel_cwd})}\\n\\n"
        except Exception as e:
            yield f"data: {_json_stdlib.dumps({'error': str(e), 'done': True})}\\n\\n"

    resp = StreamingHttpResponse(stream_cmd(), content_type='text/event-stream')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp


'''

new_content = content[:func_start] + new_func + content[end_idx:]
open('/app/syblog_project/blog/views.py', 'w').write(new_content)
print("✅ 함수 교체 완료")

# 검증
result = open('/app/syblog_project/blog/views.py').read()
idx = result.find('def ai_webdev_terminal_stream')
print("=== 새 함수 첫 8줄 ===")
for line in result[idx:idx+600].splitlines()[:8]:
    print(repr(line))
