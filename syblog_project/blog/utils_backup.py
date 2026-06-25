import os
import json
import base64
import tempfile
import datetime
import zipfile
import shutil
import tarfile
import subprocess
import urllib.request
import urllib.parse
import logging
from io import StringIO, BytesIO
from django.core.management import call_command
from django.contrib.auth.models import User
from blog.models import Post, Category, Tag, Series

logger = logging.getLogger(__name__)

# ── GitHub API 헬퍼 ────────────────────────────────────────────
def _github_api(method, path, token, data=None):
    url = f'https://api.github.com{path}'
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }
    req = urllib.request.Request(url, headers=headers, method=method)
    if data:
        json_data = json.dumps(data).encode('utf-8')
        req.add_header('Content-Type', 'application/json')
        req.data = json_data
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode('utf-8')
            return json.loads(res_body) if res_body else {}, response.getcode()
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        return json.loads(err_body) if err_body else {}, e.code


# ── GitHub 파일 크기 제한 분할 업로드 헬퍼 (50MB 이하) ────────────
GITHUB_MAX_BYTES = 49 * 1024 * 1024  # 49MB (안전 마진)

def _upload_large_file_to_github(token, repo, file_path_in_repo, data_bytes, commit_msg):
    if len(data_bytes) <= GITHUB_MAX_BYTES:
        b64 = base64.b64encode(data_bytes).decode('utf-8')
        res, st = _github_api('GET', f'/repos/{repo}/contents/{file_path_in_repo}', token)
        payload = {'message': commit_msg, 'content': b64}
        if st == 200:
            payload['sha'] = res.get('sha', '')
        result, status = _github_api('PUT', f'/repos/{repo}/contents/{file_path_in_repo}', token, payload)
        if status in (200, 201):
            return True, {'type': 'single', 'parts': 1, 'base_path': file_path_in_repo}
        return False, result.get('message', '업로드 실패')
    else:
        chunks = [data_bytes[i:i+GITHUB_MAX_BYTES] for i in range(0, len(data_bytes), GITHUB_MAX_BYTES)]
        for idx, chunk in enumerate(chunks):
            part_path = f'{file_path_in_repo}.part{idx:02d}'
            b64 = base64.b64encode(chunk).decode('utf-8')
            res, st = _github_api('GET', f'/repos/{repo}/contents/{part_path}', token)
            payload = {'message': f'{commit_msg} (part {idx+1}/{len(chunks)})', 'content': b64}
            if st == 200:
                payload['sha'] = res.get('sha', '')
            result, status = _github_api('PUT', f'/repos/{repo}/contents/{part_path}', token, payload)
            if status not in (200, 201):
                return False, f'파트 {idx} 업로드 실패: {result.get("message","")}'
        return True, {'type': 'multi', 'parts': len(chunks), 'base_path': file_path_in_repo}


def _download_file_from_github(token, repo, file_path_in_repo, info):
    if info.get('type', 'single') == 'single':
        res, st = _github_api('GET', f'/repos/{repo}/contents/{file_path_in_repo}', token)
        if st != 200:
            return None, f'{file_path_in_repo} 다운로드 실패'
        content_b64 = res.get('content', '').replace('\n', '')
        return base64.b64decode(content_b64), None
    else:
        parts = info.get('parts', 1)
        chunks = []
        for idx in range(parts):
            part_path = f'{file_path_in_repo}.part{idx:02d}'
            res, st = _github_api('GET', f'/repos/{repo}/contents/{part_path}', token)
            if st != 200:
                return None, f'파트 {idx} 다운로드 실패'
            content_b64 = res.get('content', '').replace('\n', '')
            chunks.append(base64.b64decode(content_b64))
        return b''.join(chunks), None


# ── 미디어 폴더 → zip bytes ─────────────────────────────────────
def _media_to_zip_bytes(media_root):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        if os.path.isdir(media_root):
            for dirpath, dirnames, filenames in os.walk(media_root):
                for filename in filenames:
                    full_path = os.path.join(dirpath, filename)
                    arcname = os.path.relpath(full_path, media_root)
                    zf.write(full_path, arcname)
    return buf.getvalue()


# ── AI 웹빌더 workspace 경로 ────────────────────────────────────
WEBDEV_WORKSPACE_PATH = '/tmp/syblog_webdev'


# ══════════════════════════════════════════════════════════════
#  venv 백업 / 복원 핵심 함수
#  전략: site-packages 폴더만 tar.gz로 묶어서 별도 백업
#        → 복원 시 새 venv 생성 후 site-packages만 덮어쓰기
#        → shebang 절대경로 문제 없음, 100% 동작 보장
# ══════════════════════════════════════════════════════════════

def _get_venv_site_packages(venv_dir):
    """venv 내 site-packages 경로 반환 (python3.x 폴더 자동 탐색)"""
    lib_dir = os.path.join(venv_dir, 'lib')
    if not os.path.isdir(lib_dir):
        return None
    for entry in os.listdir(lib_dir):
        if entry.startswith('python'):
            sp = os.path.join(lib_dir, entry, 'site-packages')
            if os.path.isdir(sp):
                return sp
    return None


def _venv_site_packages_to_tgz(venv_dir):
    """
    venv의 site-packages만 tar.gz bytes로 반환.
    없거나 비어있으면 None 반환.
    """
    sp = _get_venv_site_packages(venv_dir)
    if not sp or not os.path.isdir(sp):
        return None
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tf:
        for item in os.listdir(sp):
            full = os.path.join(sp, item)
            tf.add(full, arcname=item)
    data = buf.getvalue()
    return data if len(data) > 100 else None   # 최소 크기 체크


def _create_fresh_venv(venv_dir):
    """새 venv 생성 + pip 최신화. 성공하면 True 반환."""
    try:
        # 기존 venv 제거
        if os.path.exists(venv_dir):
            shutil.rmtree(venv_dir)
        r = subprocess.run(
            ['python3', '-m', 'venv', venv_dir],
            timeout=90, capture_output=True
        )
        if r.returncode != 0:
            logger.error(f'[venv] venv 생성 실패: {r.stderr.decode()[:200]}')
            return False
        pip = os.path.join(venv_dir, 'bin', 'pip')
        subprocess.run(
            [pip, 'install', '--upgrade', 'pip', 'setuptools', '--quiet'],
            timeout=60, capture_output=True
        )
        return True
    except Exception as e:
        logger.error(f'[venv] _create_fresh_venv 오류: {e}')
        return False


def _restore_site_packages_from_tgz(tgz_bytes, venv_dir):
    """
    tar.gz bytes → venv site-packages에 풀기.
    venv가 없으면 먼저 생성.
    완료 후 새 pip/setuptools dist-info가 없으면 재설치.
    """
    try:
        # venv 없으면 생성
        if not os.path.exists(os.path.join(venv_dir, 'bin', 'python3')):
            if not _create_fresh_venv(venv_dir):
                return False

        sp = _get_venv_site_packages(venv_dir)
        if not sp:
            logger.error(f'[venv] site-packages 경로를 찾을 수 없음: {venv_dir}')
            return False

        # site-packages 비우기 (pip/setuptools 기본 패키지 제외)
        keep = {'pip', 'setuptools', 'pkg_resources', '_distutils_hack',
                'distutils-precedence.pth', '__pycache__'}
        for item in os.listdir(sp):
            if item not in keep:
                target = os.path.join(sp, item)
                try:
                    if os.path.isdir(target):
                        shutil.rmtree(target)
                    else:
                        os.remove(target)
                except Exception:
                    pass

        # tar.gz 풀기
        with tarfile.open(fileobj=BytesIO(tgz_bytes), mode='r:gz') as tf:
            tf.extractall(sp)

        logger.info(f'[venv] site-packages 복원 완료: {sp}')
        return True
    except Exception as e:
        logger.error(f'[venv] _restore_site_packages_from_tgz 오류: {e}')
        return False


def _fallback_pip_install(venv_dir, req_file):
    """site-packages 복원 실패 시 pip install -r 로 폴백"""
    try:
        if not os.path.exists(os.path.join(venv_dir, 'bin', 'python3')):
            _create_fresh_venv(venv_dir)
        pip = os.path.join(venv_dir, 'bin', 'pip')
        r = subprocess.run(
            [pip, 'install', '-r', req_file, '--quiet'],
            timeout=300, capture_output=True
        )
        logger.info(f'[venv] pip install 폴백: returncode={r.returncode}')
        return r.returncode == 0
    except Exception as e:
        logger.error(f'[venv] 폴백 pip install 실패: {e}')
        return False


# ── AI 웹빌더 프로젝트 폴더 → zip bytes ────────────────────────
def _webdev_to_zip_bytes(workspace_path):
    """
    AI 웹빌더 전체 workspace → zip bytes.
    - 프로젝트 파일 (코드, requirements.txt 등)
    - .venv는 제외 (별도 venv_backup 채널로 저장)
    """
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        if os.path.isdir(workspace_path):
            for dirpath, dirnames, filenames in os.walk(workspace_path):
                dirnames[:] = [d for d in dirnames
                               if d not in ('__pycache__', '.git', 'node_modules', '.venv')]
                for filename in filenames:
                    full_path = os.path.join(dirpath, filename)
                    arcname = os.path.relpath(full_path, workspace_path)
                    try:
                        zf.write(full_path, arcname)
                    except (OSError, PermissionError):
                        pass
    return buf.getvalue()


def _zip_bytes_to_webdev(zip_bytes, workspace_path):
    """zip bytes → AI 웹빌더 workspace 복원 (venv 제외 파일만)"""
    if os.path.isdir(workspace_path):
        shutil.rmtree(workspace_path)
    os.makedirs(workspace_path, exist_ok=True)
    with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zf:
        zf.extractall(workspace_path)


# ── zip bytes → 미디어 폴더 복원 ────────────────────────────────
def _zip_bytes_to_media(zip_bytes, media_root):
    if os.path.isdir(media_root):
        shutil.rmtree(media_root)
    os.makedirs(media_root, exist_ok=True)
    with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zf:
        zf.extractall(media_root)


# ── venv 전체 백업 → zip bytes (프로젝트별 site-packages tar.gz 포함) ──
def _venv_all_to_zip_bytes(workspace_path):
    """
    모든 프로젝트의 .venv/site-packages를 tar.gz로 묶어
    하나의 zip으로 반환.
    구조: {project_id}/site_packages.tar.gz
          {project_id}/python_version.txt
    """
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        if not os.path.isdir(workspace_path):
            return buf.getvalue()

        for project_id in os.listdir(workspace_path):
            proj_path = os.path.join(workspace_path, project_id)
            if not os.path.isdir(proj_path):
                continue
            venv_dir = os.path.join(proj_path, '.venv')
            if not os.path.isdir(venv_dir):
                continue

            # site-packages → tar.gz
            tgz_bytes = _venv_site_packages_to_tgz(venv_dir)
            if tgz_bytes:
                zf.writestr(f'{project_id}/site_packages.tar.gz', tgz_bytes)
                logger.info(f'[venv-backup] {project_id}: site-packages {len(tgz_bytes)//1024}KB')

            # Python 버전 기록
            try:
                r = subprocess.run(
                    [os.path.join(venv_dir, 'bin', 'python3'), '--version'],
                    capture_output=True, text=True, timeout=5
                )
                zf.writestr(f'{project_id}/python_version.txt', r.stdout.strip())
            except Exception:
                zf.writestr(f'{project_id}/python_version.txt', 'python3.11')

    return buf.getvalue()



def _venv_all_to_zip_bytes_safe(workspace_path):
    """
    venv → zip bytes, 안전한 버전:
    - 각 프로젝트의 site-packages를 개별 처리
    - 큰 파일은 스킵하여 메모리/시간 절약
    - gunicorn SIGABRT 방지를 위해 단순 파일 크기 제한 적용
    """
    MAX_SINGLE_FILE_KB = 5 * 1024   # 파일 하나 5MB 이상이면 스킵
    MAX_TOTAL_KB       = 30 * 1024  # 전체 30MB 초과 시 중단

    if not os.path.isdir(workspace_path):
        return b''

    buf = io.BytesIO()
    total_bytes = 0

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        for project_id in os.listdir(workspace_path):
            proj_path = os.path.join(workspace_path, project_id)
            if not os.path.isdir(proj_path):
                continue
            venv_dir = os.path.join(proj_path, '.venv')
            if not os.path.isdir(venv_dir):
                continue

            # site-packages 경로 찾기
            sp_base = os.path.join(venv_dir, 'lib')
            if not os.path.isdir(sp_base):
                continue
            site_pkgs = None
            for py_ver in os.listdir(sp_base):
                sp = os.path.join(sp_base, py_ver, 'site-packages')
                if os.path.isdir(sp):
                    site_pkgs = sp
                    break
            if not site_pkgs:
                continue

            # site-packages → tar.gz (청크 단위, 큰 파일 스킵)
            tgz_buf = io.BytesIO()
            try:
                with __import__('gzip').open(tgz_buf, 'wb', compresslevel=1) as gz:
                    import tarfile as _tf
                    with _tf.open(fileobj=gz, mode='w|') as tar:
                        for dirpath, dirnames, filenames in os.walk(site_pkgs):
                            # __pycache__ 스킵
                            dirnames[:] = [d for d in dirnames if d != '__pycache__']
                            for fname in filenames:
                                fpath = os.path.join(dirpath, fname)
                                try:
                                    fsize = os.path.getsize(fpath)
                                    if fsize > MAX_SINGLE_FILE_KB * 1024:
                                        logger.debug(f'[venv-backup-safe] 큰 파일 스킵: {fpath} ({fsize//1024}KB)')
                                        continue
                                    arcname = os.path.relpath(fpath, site_pkgs)
                                    tar.add(fpath, arcname=arcname)
                                except Exception:
                                    pass
            except Exception as _e:
                logger.warning(f'[venv-backup-safe] {project_id} tar 생성 실패: {_e}')
                continue

            tgz_bytes = tgz_buf.getvalue()
            if not tgz_bytes:
                continue

            zf.writestr(f'{project_id}/site_packages.tar.gz', tgz_bytes)
            total_bytes += len(tgz_bytes)
            logger.info(f'[venv-backup-safe] {project_id}: {len(tgz_bytes)//1024}KB')

            # Python 버전 기록
            try:
                r = subprocess.run(
                    [os.path.join(venv_dir, 'bin', 'python3'), '--version'],
                    capture_output=True, text=True, timeout=5
                )
                zf.writestr(f'{project_id}/python_version.txt', r.stdout.strip())
            except Exception:
                zf.writestr(f'{project_id}/python_version.txt', 'python3.11')

            if total_bytes > MAX_TOTAL_KB * 1024:
                logger.warning(f'[venv-backup-safe] 총 크기 {total_bytes//1024}KB 초과 → 나머지 프로젝트 스킵')
                break

    return buf.getvalue()

def _zip_bytes_to_venv_all(venv_zip_bytes, workspace_path):
    """
    venv zip bytes → 각 프로젝트 .venv 복원.
    site-packages tar.gz를 풀어 새 venv에 심기.
    """
    if not venv_zip_bytes:
        return

    os.makedirs(workspace_path, exist_ok=True)

    with zipfile.ZipFile(BytesIO(venv_zip_bytes), 'r') as zf:
        names = zf.namelist()

        # 프로젝트 ID 추출
        project_ids = set()
        for name in names:
            parts = name.split('/')
            if len(parts) >= 2:
                project_ids.add(parts[0])

        for project_id in project_ids:
            proj_path = os.path.join(workspace_path, project_id)
            os.makedirs(proj_path, exist_ok=True)
            venv_dir = os.path.join(proj_path, '.venv')

            tgz_name = f'{project_id}/site_packages.tar.gz'
            if tgz_name not in names:
                logger.warning(f'[venv-restore] {project_id}: site_packages.tar.gz 없음')
                continue

            tgz_bytes = zf.read(tgz_name)
            logger.info(f'[venv-restore] {project_id}: venv 생성 중...')

            # 새 venv 생성 + site-packages 복원
            ok = False
            if _create_fresh_venv(venv_dir):
                ok = _restore_site_packages_from_tgz(tgz_bytes, venv_dir)

            if not ok:
                # 폴백: requirements.txt로 pip install
                logger.warning(f'[venv-restore] {project_id}: site-packages 복원 실패, pip install 폴백 시도')
                req_file = os.path.join(proj_path, 'requirements.txt')
                if os.path.isfile(req_file):
                    _fallback_pip_install(venv_dir, req_file)
            else:
                logger.info(f'[venv-restore] {project_id}: venv 복원 완료')


# ── 백업 수행 ──────────────────────────────────────────────────
def perform_backup():
    from django.conf import settings
    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_REPO', 'a50411278apeter40-svg/Syblog')
    if not token:
        return False, 'GITHUB_TOKEN 환경변수가 설정되지 않았습니다.'

    now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    errors = []

    try:
        # ① DB 덤프
        logger.info(f'[backup] DB 덤프 시작 ({now_str})')
        out = StringIO()
        call_command('dumpdata', natural_foreign=True,
                     exclude=['auth.permission', 'contenttypes', 'admin.logentry', 'sessions'],
                     stdout=out)
        backup_json = out.getvalue()
        backup_b64 = base64.b64encode(backup_json.encode('utf-8')).decode('utf-8')

        db_path = f'backups/db/syblog_db_{now_str}.json'
        res, st = _github_api('GET', f'/repos/{repo}/contents/{db_path}', token)
        payload = {'message': f'🔒 DB 백업 {now_str}', 'content': backup_b64}
        if st == 200:
            payload['sha'] = res.get('sha', '')
        result, status = _github_api('PUT', f'/repos/{repo}/contents/{db_path}', token, payload)
        if status not in (200, 201):
            return False, f'DB 백업 실패: {result.get("message","")}'
        logger.info(f'[backup] DB 덤프 완료')

        # ② 미디어 파일 zip 백업
        logger.info(f'[backup] 미디어 파일 백업 시작')
        media_root = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, '_media'))
        media_zip_bytes = _media_to_zip_bytes(media_root)

        media_path = f'backups/media/syblog_media_{now_str}.zip'
        ok, info_or_err = _upload_large_file_to_github(
            token, repo, media_path, media_zip_bytes,
            f'🖼️ 미디어 백업 {now_str}'
        )
        if not ok:
            errors.append(f'미디어 백업 경고: {info_or_err}')
        logger.info(f'[backup] 미디어 파일 백업 완료 ({len(media_zip_bytes)//1024}KB)')

        # ③ AI 웹빌더 프로젝트 파일 백업 (.venv 제외)
        logger.info(f'[backup] AI 웹빌더 파일 백업 시작')
        webdev_zip_bytes = _webdev_to_zip_bytes(WEBDEV_WORKSPACE_PATH)
        webdev_path = f'backups/webdev/syblog_webdev_{now_str}.zip'
        webdev_ok, webdev_info_or_err = _upload_large_file_to_github(
            token, repo, webdev_path, webdev_zip_bytes,
            f'🛠️ AI웹빌더 백업 {now_str}'
        )
        if not webdev_ok:
            errors.append(f'웹빌더 백업 경고: {webdev_info_or_err}')
        logger.info(f'[backup] AI 웹빌더 파일 백업 완료 ({len(webdev_zip_bytes)//1024}KB)')

        # ④ venv 백업 (site-packages tar.gz 묶음) — 청크 스트리밍 방식으로 메모리 절약
        logger.info(f'[backup] venv 백업 시작')
        venv_backup_ok = False
        venv_info_or_err = None
        venv_path = None

        try:
            venv_zip_bytes = _venv_all_to_zip_bytes_safe(WEBDEV_WORKSPACE_PATH)
            if venv_zip_bytes and len(venv_zip_bytes) > 100:
                venv_path = f'backups/venv/syblog_venv_{now_str}.zip'
                venv_backup_ok, venv_info_or_err = _upload_large_file_to_github(
                    token, repo, venv_path, venv_zip_bytes,
                    f'🐍 venv 백업 {now_str}'
                )
                if not venv_backup_ok:
                    errors.append(f'venv 백업 경고: {venv_info_or_err}')
                logger.info(f'[backup] venv 백업 완료 ({len(venv_zip_bytes)//1024}KB)')
            else:
                logger.info(f'[backup] venv 없음 - 스킵')
        except Exception as _ve:
            logger.warning(f'[backup] venv 백업 실패 (무시하고 계속): {_ve}')
            errors.append(f'venv 백업 경고: {_ve}')

        # ⑤ 메타 파일 (백업 파일끼리 쌍 기록)
        meta = {
            'timestamp': now_str,
            'db_path': db_path,
            'media_path': media_path,
            'media_info': info_or_err if ok else None,
            'media_zip_size_kb': round(len(media_zip_bytes) / 1024, 1),
            'webdev_path': webdev_path,
            'webdev_info': webdev_info_or_err if webdev_ok else None,
            'webdev_zip_size_kb': round(len(webdev_zip_bytes) / 1024, 1),
            'venv_path': venv_path if venv_backup_ok else None,
            'venv_info': venv_info_or_err if venv_backup_ok else None,
            'venv_zip_size_kb': round(len(venv_zip_bytes) / 1024, 1) if venv_zip_bytes else 0,
        }
        meta_b64 = base64.b64encode(json.dumps(meta, ensure_ascii=False).encode('utf-8')).decode('utf-8')
        meta_path = f'backups/meta/syblog_meta_{now_str}.json'
        res, st = _github_api('GET', f'/repos/{repo}/contents/{meta_path}', token)
        payload = {'message': f'📋 백업 메타 {now_str}', 'content': meta_b64}
        if st == 200:
            payload['sha'] = res.get('sha', '')
        _github_api('PUT', f'/repos/{repo}/contents/{meta_path}', token, payload)

        msg = f'DB + 미디어 + AI웹빌더 + venv 백업 완료 ({now_str})'
        if errors:
            msg += ' | 경고: ' + '; '.join(errors)
        logger.info(f'[backup] 전체 백업 완료: {msg}')
        return True, msg

    except Exception as e:
        logger.error(f'[backup] 백업 중 예외 발생: {e}', exc_info=True)
        return False, str(e)


# ── 복원 수행 ──────────────────────────────────────────────────
def perform_restore():
    from django.conf import settings
    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_REPO', 'a50411278apeter40-svg/Syblog')
    if not token:
        return False, 'GITHUB_TOKEN 환경변수가 설정되지 않았습니다.'

    try:
        # ① 최신 메타 파일 찾기
        logger.info('[restore] 메타 파일 탐색 중...')
        result, status = _github_api('GET', f'/repos/{repo}/contents/backups/meta', token)
        use_meta = status == 200 and result

        if use_meta:
            meta_files = sorted(
                [f for f in result if f['name'].endswith('.json')],
                key=lambda x: x['name'], reverse=True
            )
            if not meta_files:
                use_meta = False

        if use_meta:
            latest_meta_res = meta_files[0]
            fm, fst = _github_api('GET', f'/repos/{repo}/contents/{latest_meta_res["path"]}', token)
            if fst != 200:
                return False, '메타 파일 로드 실패'
            meta_b64 = fm.get('content', '').replace('\n', '')
            meta = json.loads(base64.b64decode(meta_b64).decode('utf-8'))

            # DB 복원
            logger.info('[restore] DB 복원 중...')
            db_fm, db_st = _github_api('GET', f'/repos/{repo}/contents/{meta["db_path"]}', token)
            if db_st != 200:
                return False, 'DB 백업 파일 로드 실패'
            db_b64 = db_fm.get('content', '').replace('\n', '')
            backup_text = base64.b64decode(db_b64).decode('utf-8')

            # 미디어 복원
            if meta.get('media_path') and meta.get('media_info'):
                logger.info('[restore] 미디어 파일 복원 중...')
                zip_bytes, media_err = _download_file_from_github(
                    token, repo, meta['media_path'], meta['media_info']
                )
                if zip_bytes:
                    media_root = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, '_media'))
                    _zip_bytes_to_media(zip_bytes, media_root)
                    logger.info('[restore] 미디어 파일 복원 완료')
                else:
                    logger.warning(f'[restore] 미디어 복원 실패: {media_err}')

            # AI 웹빌더 파일 복원
            if meta.get('webdev_path') and meta.get('webdev_info'):
                logger.info('[restore] AI 웹빌더 파일 복원 중...')
                webdev_zip_bytes, webdev_err = _download_file_from_github(
                    token, repo, meta['webdev_path'], meta['webdev_info']
                )
                if webdev_zip_bytes:
                    _zip_bytes_to_webdev(webdev_zip_bytes, WEBDEV_WORKSPACE_PATH)
                    logger.info('[restore] AI 웹빌더 파일 복원 완료')
                else:
                    logger.warning(f'[restore] 웹빌더 복원 실패: {webdev_err}')

            # venv 복원 (site-packages tar.gz 방식)
            if meta.get('venv_path') and meta.get('venv_info'):
                logger.info('[restore] venv 복원 시작 (site-packages 방식)...')
                venv_zip_bytes, venv_err = _download_file_from_github(
                    token, repo, meta['venv_path'], meta['venv_info']
                )
                if venv_zip_bytes:
                    _zip_bytes_to_venv_all(venv_zip_bytes, WEBDEV_WORKSPACE_PATH)
                    logger.info('[restore] venv 복원 완료')
                else:
                    logger.warning(f'[restore] venv 백업 없음, pip install 폴백: {venv_err}')
                    # 구버전 백업: requirements.txt로 pip install
                    _fallback_all_pip_install(WEBDEV_WORKSPACE_PATH)
            else:
                # 구버전 백업: venv 백업 없음 → requirements.txt로 pip install
                logger.info('[restore] venv 백업 없음 (구버전) → requirements.txt pip install 폴백')
                _fallback_all_pip_install(WEBDEV_WORKSPACE_PATH)

            ts = meta.get('timestamp', '알 수 없음')

        else:
            # 레거시 방식: backups/ 하위 JSON 직접 탐색
            logger.info('[restore] 레거시 방식으로 복원 시도')
            result, status = _github_api('GET', f'/repos/{repo}/contents/backups', token)
            if status != 200:
                return False, f'백업 파일 목록 로드 실패: {result.get("message","")}'
            if not result:
                return False, '백업 파일이 없습니다.'

            json_files = sorted(
                [f for f in result if f['name'].endswith('.json')],
                key=lambda x: x['name'], reverse=True
            )
            if not json_files:
                return False, '백업 JSON 파일이 없습니다.'

            latest = json_files[0]
            fm, fst = _github_api('GET', f'/repos/{repo}/contents/{latest["path"]}', token)
            if fst != 200:
                return False, '백업 파일 로드 실패'
            b64 = fm.get('content', '').replace('\n', '')
            backup_text = base64.b64decode(b64).decode('utf-8')
            ts = latest['name'].replace('syblog_db_', '').replace('.json', '')

        # DB 실제 복원 — 완전 덮어쓰기(flush → loaddata)
        logger.info('[restore] DB flush 시작...')
        import tempfile as _tempfile
        import subprocess as _sub_restore

        venv_py = '/opt/render/project/src/.venv/bin/python3'
        manage_py = os.path.join(settings.BASE_DIR, 'manage.py')

        # ① 임시 파일에 백업 JSON 저장
        with _tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                          delete=False, encoding='utf-8') as _tf:
            _tf.write(backup_text)
            tmp_fixture = _tf.name

        try:
            # ② flush — 외래키 제약 순서 문제를 피하기 위해 SQLite pragma 사용
            # django_session 은 제외 → 복원 후 로그아웃 방지
            _SKIP_TABLES = {'django_migrations', 'django_session'}
            from django.db import connection as _conn
            with _conn.cursor() as cur:
                cur.execute('PRAGMA foreign_keys = OFF')
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
                tables = [r[0] for r in cur.fetchall() if r[0] not in _SKIP_TABLES]
                for t in tables:
                    try:
                        cur.execute(f'DELETE FROM "{t}"')
                    except Exception:
                        pass
                cur.execute('PRAGMA foreign_keys = ON')
            logger.info(f'[restore] flush 완료: {len(tables)}개 테이블 (세션 테이블 유지)')

            # ③ loaddata
            r = _sub_restore.run(
                [venv_py, manage_py, 'loaddata', tmp_fixture],
                capture_output=True, text=True,
                cwd=str(settings.BASE_DIR)
            )
            if r.returncode != 0:
                logger.error(f'[restore] loaddata 실패: {r.stderr}')
                return False, f'loaddata 실패: {r.stderr[:300]}'
            logger.info(f'[restore] loaddata 성공: {r.stdout.strip()}')
        finally:
            try:
                os.remove(tmp_fixture)
            except Exception:
                pass

        logger.info(f'[restore] 복원 완료: {ts}')
        return True, f'복원 완료 (백업 시각: {ts})'

    except Exception as e:
        logger.error(f'[restore] 복원 중 예외: {e}', exc_info=True)
        return False, str(e)


def _fallback_all_pip_install(workspace_path):
    """
    구버전 백업 대응: 모든 프로젝트 requirements.txt → pip install.
    새 venv 생성 후 pip install.
    """
    if not os.path.isdir(workspace_path):
        return
    for project_id in os.listdir(workspace_path):
        proj_path = os.path.join(workspace_path, project_id)
        if not os.path.isdir(proj_path):
            continue
        req_file = os.path.join(proj_path, 'requirements.txt')
        if not os.path.isfile(req_file):
            continue
        venv_dir = os.path.join(proj_path, '.venv')
        try:
            _create_fresh_venv(venv_dir)
            _fallback_pip_install(venv_dir, req_file)
            logger.info(f'[restore-fallback] {project_id}: pip install 완료')
        except Exception as e:
            logger.error(f'[restore-fallback] {project_id}: 실패 - {e}')
