content = open('/app/syblog_project/blog/utils_backup.py').read()

OLD_AUTO = """def _auto_install_requirements(workspace_path):
    \"\"\"
    복원된 webdev workspace 내 각 프로젝트 폴더의
    requirements.txt를 찾아 자동으로 pip install -r 실행.
    실패해도 전체 복원을 막지 않음.
    \"\"\"
    import subprocess as _sp
    venv_pip = '/opt/render/project/src/.venv/bin/pip'
    fallback_pip = 'pip'
    pip_cmd = venv_pip if os.path.exists(venv_pip) else fallback_pip

    if not os.path.isdir(workspace_path):
        return

    for project_id_dir in os.listdir(workspace_path):
        req_file = os.path.join(workspace_path, project_id_dir, 'requirements.txt')
        if os.path.isfile(req_file):
            try:
                _sp.run(
                    [pip_cmd, 'install', '-r', req_file, '--quiet'],
                    timeout=120,
                    capture_output=True
                )
            except Exception:
                pass  # 실패해도 무시 - 복원 자체는 성공"""

NEW_AUTO = """def _create_project_venv(project_dir):
    \"\"\"프로젝트 전용 venv 생성 및 pip 업그레이드\"\"\"
    import subprocess as _sp
    venv_dir = os.path.join(project_dir, '.venv')
    if not os.path.exists(os.path.join(venv_dir, 'bin', 'python3')):
        _sp.run(['python3', '-m', 'venv', venv_dir],
                timeout=60, capture_output=True)
        pip_path = os.path.join(venv_dir, 'bin', 'pip')
        if os.path.exists(pip_path):
            _sp.run([pip_path, 'install', '--upgrade', 'pip', '--quiet'],
                    timeout=60, capture_output=True)
    return venv_dir


def _auto_install_requirements(workspace_path):
    \"\"\"
    복원된 webdev workspace 내 각 프로젝트 폴더의
    requirements.txt를 찾아 프로젝트 전용 venv에 자동 pip install.
    실패해도 전체 복원을 막지 않음.
    \"\"\"
    import subprocess as _sp

    if not os.path.isdir(workspace_path):
        return

    for project_id_dir in os.listdir(workspace_path):
        proj_path = os.path.join(workspace_path, project_id_dir)
        if not os.path.isdir(proj_path):
            continue
        req_file = os.path.join(proj_path, 'requirements.txt')
        if not os.path.isfile(req_file):
            continue
        try:
            venv_dir = _create_project_venv(proj_path)
            pip_path = os.path.join(venv_dir, 'bin', 'pip')
            if os.path.exists(pip_path):
                _sp.run(
                    [pip_path, 'install', '-r', req_file, '--quiet'],
                    timeout=180, capture_output=True
                )
        except Exception:
            pass  # 실패해도 무시 - 복원 자체는 성공"""

if OLD_AUTO in content:
    content = content.replace(OLD_AUTO, NEW_AUTO, 1)
    print("OK: _auto_install_requirements 교체")
else:
    print("FAIL: not found")
    idx = content.find("_auto_install_requirements")
    print(repr(content[idx:idx+300]))

open('/app/syblog_project/blog/utils_backup.py', 'w').write(content)
