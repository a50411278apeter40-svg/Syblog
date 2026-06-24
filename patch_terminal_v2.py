content = open('/app/syblog_project/blog/views.py').read()

OLD = """    blocked = ['rm -rf /', ':(){', '>/dev/sda', 'shutdown', 'reboot']
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
                    _cd_err = f'cd: {target}: No such directory\\n'
                    yield f"data: {_json_stdlib.dumps({'line': _cd_err})}\\n\\n"
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

            # pip install 성공 시 requirements.txt 자동 갱신
            is_pip_install = bool(_re.search(r'\\bpip\\b.*\\binstall\\b', cmd_fixed))
            if is_pip_install and proc.returncode == 0:
                try:
                    import subprocess as _sp2
                    freeze_result = _sp2.run(
                        [venv_pip, 'freeze'],
                        capture_output=True, text=True, env=env
                    )
                    if freeze_result.returncode == 0:
                        req_path = project_dir / 'requirements.txt'
                        req_path.write_text(freeze_result.stdout, encoding='utf-8')
                        _save_msg = _json_stdlib.dumps({'line': '\\n[자동저장] requirements.txt 업데이트됨\\n'})
                        yield f"data: {_save_msg}\\n\\n"
                except Exception:
                    pass

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
    return resp"""

NEW = """    blocked = ['rm -rf /', ':(){', 'shutdown', 'reboot']
    for b in blocked:
        if b in cmd:
            return JsonResponse({'error': '차단된 명령어입니다'}, status=400)

    # 프로젝트 독립 venv 환경 (Python 3.11 + Node 20)
    proj_venv = _get_project_venv(project_dir)
    venv_bin  = str(proj_venv / 'bin')
    venv_pip  = f'{venv_bin}/pip'
    venv_py   = f'{venv_bin}/python3'

    def fix_cmd(c):
        if venv_bin in c:
            return c
        c = _re.sub(r'(?<![/\\w])pip3?\\s+install', f'{venv_pip} install', c)
        c = _re.sub(r'(?<![/\\w])pip3?(?!\\s*install)\\b', venv_pip, c)
        c = _re.sub(r'(?<![/\\w])python3?\\b', venv_py, c)
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
            env = _get_venv_env(project_dir)

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
                    _cd_err = f'cd: {target}: No such directory\\n'
                    yield f"data: {_json_stdlib.dumps({'line': _cd_err})}\\n\\n"
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

            # pip install 성공 시 requirements.txt 자동 갱신
            is_pip_install = bool(_re.search(r'\\bpip\\b.*\\binstall\\b', cmd_fixed))
            if is_pip_install and proc.returncode == 0:
                try:
                    freeze_result = subprocess.run(
                        [venv_pip, 'freeze'],
                        capture_output=True, text=True, env=env
                    )
                    if freeze_result.returncode == 0:
                        (project_dir / 'requirements.txt').write_text(
                            freeze_result.stdout, encoding='utf-8')
                        _save_msg = _json_stdlib.dumps({'line': '\\n[자동저장] requirements.txt 업데이트됨\\n'})
                        yield f"data: {_save_msg}\\n\\n"
                except Exception:
                    pass

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
    return resp"""

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    print("OK: terminal venv replaced")
else:
    print("FAIL: terminal not found")
    idx = content.find("venv_base = '/opt/render")
    print(f"venv_base at char {idx}")
    print(repr(content[idx-100:idx+200]))

open('/app/syblog_project/blog/views.py', 'w').write(content)
