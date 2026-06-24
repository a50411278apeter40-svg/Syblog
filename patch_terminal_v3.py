content = open('/app/syblog_project/blog/views.py').read()

# 정확한 위치 찾아서 교체
idx_start = content.find("venv_base = '/opt/render/project/src/.venv'")
idx_end = content.find("resp['X-Accel-Buffering'] = 'no'\n    return resp", idx_start)
idx_end += len("resp['X-Accel-Buffering'] = 'no'\n    return resp")

old_block = content[idx_start:idx_end]
print(f"OLD: {len(old_block)} chars")

NEW_BLOCK = """proj_venv = _get_project_venv(project_dir)
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

content = content[:idx_start] + NEW_BLOCK + content[idx_end:]
open('/app/syblog_project/blog/views.py', 'w').write(content)
print("OK: terminal replaced by slice")
