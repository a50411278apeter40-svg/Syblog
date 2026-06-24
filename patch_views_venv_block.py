content = open('/app/syblog_project/blog/views.py').read()

OLD = """WEBDEV_WORKSPACE = _Path('/tmp/syblog_webdev')
WEBDEV_WORKSPACE.mkdir(exist_ok=True)

# 프로젝트별 환경 복원 타임스탬프 캐시 (서버 재시작 시에만 재설치)
_WEBDEV_ENV_RESTORED: set = set()

def _webdev_auto_restore_env(project_dir):
    \"\"\"
    프로젝트 디렉터리에 requirements.txt가 있으면
    서버 시작 후 첫 진입 시 자동으로 pip install -r 실행.
    이미 설치된 경우(_WEBDEV_ENV_RESTORED 캐시) 스킵.
    블로킹이지만 빠른 경우 몇 초 내 완료됨.
    \"\"\"
    import subprocess as _sp2
    req_file = project_dir / 'requirements.txt'
    cache_key = str(project_dir)
    if cache_key in _WEBDEV_ENV_RESTORED:
        return  # 이미 이 서버 프로세스에서 설치했음
    if not req_file.exists():
        _WEBDEV_ENV_RESTORED.add(cache_key)
        return
    venv_pip = '/opt/render/project/src/.venv/bin/pip'
    if not os.path.exists(venv_pip):
        venv_pip = 'pip'
    try:
        _sp2.run(
            [venv_pip, 'install', '-r', str(req_file), '--quiet'],
            timeout=120,
            capture_output=True
        )
    except Exception:
        pass
    _WEBDEV_ENV_RESTORED.add(cache_key)


def _get_project_dir(project_id):
    d = WEBDEV_WORKSPACE / str(project_id)
    d.mkdir(exist_ok=True)
    return d"""

NEW = """WEBDEV_WORKSPACE = _Path('/tmp/syblog_webdev')
WEBDEV_WORKSPACE.mkdir(exist_ok=True)

# ── 프로젝트별 독립 venv 환경 관리 ─────────────────────────────
_WEBDEV_ENV_READY: set = set()  # 이 서버 프로세스에서 준비 완료된 프로젝트


def _get_project_venv(project_dir: _Path) -> _Path:
    \"\"\"프로젝트 전용 venv 경로 반환 (없으면 자동 생성)\"\"\"
    venv_dir = project_dir / '.venv'
    if not (venv_dir / 'bin' / 'python3').exists():
        subprocess.run(
            ['python3', '-m', 'venv', str(venv_dir)],
            timeout=90, capture_output=True
        )
        pip_path = venv_dir / 'bin' / 'pip'
        if pip_path.exists():
            subprocess.run(
                [str(pip_path), 'install', '--upgrade', 'pip', 'setuptools', '--quiet'],
                timeout=60, capture_output=True
            )
    return venv_dir


def _get_venv_env(project_dir: _Path) -> dict:
    \"\"\"프로젝트 venv가 활성화된 환경변수 dict 반환 (Python 3.11 + Node 20)\"\"\"
    venv_dir = _get_project_venv(project_dir)
    venv_bin = str(venv_dir / 'bin')
    return {
        **os.environ,
        'VIRTUAL_ENV': str(venv_dir),
        'PATH': f'{venv_bin}:/usr/bin:/bin:/usr/local/bin',
        'HOME': str(project_dir),
        'PYTHONPATH': '',
        'NODE_PATH': '/usr/lib/node_modules',
    }


def _ensure_playwright():
    \"\"\"playwright가 없으면 시스템 pip으로 자동 설치 후 chromium 바이너리 설치\"\"\"
    try:
        import playwright  # noqa
        return True
    except ImportError:
        pass
    import sys
    candidates = [
        sys.executable.replace('python3', 'pip3').replace('python', 'pip'),
        '/usr/local/bin/pip3', '/usr/bin/pip3', 'pip3', 'pip',
    ]
    for pip_exe in candidates:
        try:
            r = subprocess.run(
                [pip_exe, 'install', 'playwright==1.49.1', '--quiet'],
                capture_output=True, timeout=120
            )
            if r.returncode == 0:
                subprocess.run(['playwright', 'install', 'chromium'],
                               capture_output=True, timeout=180)
                return True
        except Exception:
            continue
    return False


def _webdev_auto_restore_env(project_dir: _Path):
    \"\"\"
    프로젝트 진입 시 venv 생성 확인 + requirements.txt 있으면 자동 설치.
    서버 프로세스당 1회만 실행 (_WEBDEV_ENV_READY 캐시).
    \"\"\"
    cache_key = str(project_dir)
    if cache_key in _WEBDEV_ENV_READY:
        return
    try:
        venv_dir = _get_project_venv(project_dir)
        req_file = project_dir / 'requirements.txt'
        if req_file.exists():
            pip_path = venv_dir / 'bin' / 'pip'
            if pip_path.exists():
                subprocess.run(
                    [str(pip_path), 'install', '-r', str(req_file), '--quiet'],
                    timeout=300, capture_output=True,
                    env=_get_venv_env(project_dir)
                )
    except Exception:
        pass
    _WEBDEV_ENV_READY.add(cache_key)


def _get_project_dir(project_id) -> _Path:
    d = WEBDEV_WORKSPACE / str(project_id)
    d.mkdir(exist_ok=True)
    return d"""

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    print("OK: venv block replaced")
else:
    print("FAIL: not found")
    idx = content.find("WEBDEV_WORKSPACE = _Path")
    print(repr(content[idx:idx+300]))

open('/app/syblog_project/blog/views.py', 'w').write(content)
