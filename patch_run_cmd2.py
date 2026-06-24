content = open('/app/syblog_project/blog/views.py').read()

OLD = """        elif tool == 'run_command':
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
            }"""

NEW = """        elif tool == 'run_command':
            cmd = args.get('command', '')
            if not cmd:
                return {'error': '명령어가 없습니다'}
            blocked = ['rm -rf /', ':(){', 'shutdown', 'reboot']
            for b in blocked:
                if b in cmd:
                    return {'error': '차단된 명령어'}
            import re as _re_rc
            # 프로젝트 독립 venv 환경 (Python 3.11 + Node 20)
            env = _get_venv_env(project_dir)
            venv_bin = str(_get_project_venv(project_dir) / 'bin')
            cmd_fixed = cmd
            if venv_bin not in cmd_fixed:
                cmd_fixed = _re_rc.sub(r'(?<![/\\w])pip3?\\s+install',
                                       f'{venv_bin}/pip install', cmd_fixed)
                cmd_fixed = _re_rc.sub(r'(?<![/\\w])pip3?(?!\\s*install)\\b',
                                       f'{venv_bin}/pip', cmd_fixed)
                cmd_fixed = _re_rc.sub(r'(?<![/\\w])python3?\\b',
                                       f'{venv_bin}/python3', cmd_fixed)
            proc = subprocess.run(
                cmd_fixed, shell=True, cwd=str(project_dir),
                capture_output=True, text=True, timeout=120,
                env=env
            )
            # pip install 성공시 requirements.txt 자동 갱신
            if _re_rc.search(r'\\bpip\\b.*\\binstall\\b', cmd_fixed) and proc.returncode == 0:
                try:
                    pip_exe = f'{venv_bin}/pip'
                    freeze = subprocess.run(
                        [pip_exe, 'freeze'], capture_output=True, text=True, env=env)
                    if freeze.returncode == 0:
                        (project_dir / 'requirements.txt').write_text(
                            freeze.stdout, encoding='utf-8')
                except Exception:
                    pass
            return {
                'stdout': proc.stdout[-10000:],
                'stderr': proc.stderr[-3000:],
                'returncode': proc.returncode,
            }"""

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    print("OK: run_command venv 교체")
else:
    print("FAIL: not found")
    idx = content.find("elif tool == 'run_command'")
    print(repr(content[idx:idx+400]))

open('/app/syblog_project/blog/views.py', 'w').write(content)
