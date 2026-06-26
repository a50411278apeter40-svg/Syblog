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
    if not info:
        info = {}
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

# ══════════════════════════════════════════════════════════════
#  perform_backup / perform_restore  —  완전 재설계 버전
#  모든 데이터 누락 없이 백업/복원
#
#  백업 구성:
#    backups/meta/syblog_meta_{ts}.json  ← 메타 (파일 경로 기록)
#    backups/db/syblog_db_{ts}.json      ← dumpdata (sessions 포함 전체)
#    backups/sessions/syblog_sessions_{ts}.json ← django_session SQL 직접 덤프
#    backups/media/syblog_media_{ts}.zip ← 미디어 파일
#    backups/webdev/syblog_webdev_{ts}.zip ← AI 웹빌더 파일
#    backups/venv/syblog_venv_{ts}.zip   ← venv (선택)
#
#  복원 전략:
#    1. DB flush (django_session, django_migrations 제외)
#    2. loaddata --ignorenonexistent
#    3. sessions 별도 복원 (SQL INSERT) → 로그아웃 방지
#    4. 미디어 복원
#    5. 웹빌더 파일 복원
# ══════════════════════════════════════════════════════════════

def perform_backup():
    from django.conf import settings
    from django.db import connection as _dj_conn
    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_REPO', 'a50411278apeter40-svg/Syblog')
    if not token:
        return False, 'GITHUB_TOKEN 환경변수가 설정되지 않았습니다.'

    now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    errors = []
    meta = {'timestamp': now_str}

    try:
        # ① DB 전체 덤프 (dumpdata — contenttypes/auth.permission 제외는 loaddata 호환성)
        logger.info(f'[backup] DB 전체 덤프 시작 ({now_str})')
        out = StringIO()
        call_command(
            'dumpdata',
            natural_primary=True,
            natural_foreign=True,
            exclude=['contenttypes', 'auth.permission', 'django_migrations'],
            stdout=out,
        )
        backup_json = out.getvalue()
        db_path = f'backups/db/syblog_db_{now_str}.json'
        db_bytes = backup_json.encode('utf-8')
        ok_db, info_db = _upload_large_file_to_github(
            token, repo, db_path, db_bytes, f'🗄️ DB 전체 백업 {now_str}'
        )
        if not ok_db:
            return False, f'DB 백업 실패: {info_db}'
        meta['db_path'] = db_path
        meta['db_info'] = info_db
        meta['db_size_kb'] = round(len(db_bytes) / 1024, 1)
        logger.info(f'[backup] DB 덤프 완료 ({meta["db_size_kb"]}KB)')

        # ② django_session 테이블 직접 SQL 덤프 (로그인 세션 완전 보존)
        logger.info(f'[backup] sessions 직접 덤프 시작')
        try:
            with _dj_conn.cursor() as cur:
                cur.execute('SELECT session_key, session_data, expire_date FROM django_session')
                rows = cur.fetchall()
            sessions_data = [
                {'session_key': r[0], 'session_data': r[1],
                 'expire_date': r[2].isoformat() if hasattr(r[2], 'isoformat') else str(r[2])}
                for r in rows
            ]
            sessions_json = json.dumps(sessions_data, ensure_ascii=False).encode('utf-8')
            sess_path = f'backups/sessions/syblog_sessions_{now_str}.json'
            ok_sess, info_sess = _upload_large_file_to_github(
                token, repo, sess_path, sessions_json, f'🔐 세션 백업 {now_str}'
            )
            if ok_sess:
                meta['sessions_path'] = sess_path
                meta['sessions_info'] = info_sess
                meta['sessions_count'] = len(sessions_data)
            else:
                errors.append(f'세션 백업 경고: {info_sess}')
            logger.info(f'[backup] sessions 덤프 완료 ({len(sessions_data)}개)')
        except Exception as _se:
            logger.warning(f'[backup] sessions 덤프 실패 (무시): {_se}')
            errors.append(f'세션 백업 경고: {_se}')

        # ③ 미디어 파일 zip 백업
        logger.info(f'[backup] 미디어 파일 백업 시작')
        media_root = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, '_media'))
        media_zip_bytes = _media_to_zip_bytes(media_root)
        media_path = f'backups/media/syblog_media_{now_str}.zip'
        ok_media, info_media = _upload_large_file_to_github(
            token, repo, media_path, media_zip_bytes, f'🖼️ 미디어 백업 {now_str}'
        )
        if not ok_media:
            errors.append(f'미디어 백업 경고: {info_media}')
        meta['media_path'] = media_path
        meta['media_info'] = info_media if ok_media else None
        meta['media_size_kb'] = round(len(media_zip_bytes) / 1024, 1)
        logger.info(f'[backup] 미디어 완료 ({meta["media_size_kb"]}KB)')

        # ④ AI 웹빌더 프로젝트 파일 백업 (.venv 제외)
        logger.info(f'[backup] AI 웹빌더 파일 백업 시작')
        webdev_zip_bytes = _webdev_to_zip_bytes(WEBDEV_WORKSPACE_PATH)
        webdev_path = f'backups/webdev/syblog_webdev_{now_str}.zip'
        ok_webdev, info_webdev = _upload_large_file_to_github(
            token, repo, webdev_path, webdev_zip_bytes, f'🛠️ AI웹빌더 백업 {now_str}'
        )
        if not ok_webdev:
            errors.append(f'웹빌더 백업 경고: {info_webdev}')
        meta['webdev_path'] = webdev_path
        meta['webdev_info'] = info_webdev if ok_webdev else None
        meta['webdev_size_kb'] = round(len(webdev_zip_bytes) / 1024, 1)
        logger.info(f'[backup] AI 웹빌더 완료 ({meta["webdev_size_kb"]}KB)')

        # ⑤ venv 백업 (메모리 초과 방지를 위해 safe 버전 사용)
        logger.info(f'[backup] venv 백업 시작')
        venv_zip_bytes = None
        try:
            venv_zip_bytes = _venv_all_to_zip_bytes_safe(WEBDEV_WORKSPACE_PATH)
            if venv_zip_bytes and len(venv_zip_bytes) > 100:
                venv_path = f'backups/venv/syblog_venv_{now_str}.zip'
                ok_venv, info_venv = _upload_large_file_to_github(
                    token, repo, venv_path, venv_zip_bytes, f'🐍 venv 백업 {now_str}'
                )
                if ok_venv:
                    meta['venv_path'] = venv_path
                    meta['venv_info'] = info_venv
                    meta['venv_size_kb'] = round(len(venv_zip_bytes) / 1024, 1)
                else:
                    errors.append(f'venv 백업 경고: {info_venv}')
                logger.info(f'[backup] venv 완료 ({meta.get("venv_size_kb", 0)}KB)')
            else:
                logger.info('[backup] venv 없음 — 스킵')
        except Exception as _ve:
            logger.warning(f'[backup] venv 백업 실패 (무시): {_ve}')
            errors.append(f'venv 백업 경고: {_ve}')

        # ⑥ 메타 파일 저장
        meta_b64 = base64.b64encode(json.dumps(meta, ensure_ascii=False).encode('utf-8')).decode('utf-8')
        meta_path = f'backups/meta/syblog_meta_{now_str}.json'
        res, st = _github_api('GET', f'/repos/{repo}/contents/{meta_path}', token)
        payload = {'message': f'📋 백업 메타 {now_str}', 'content': meta_b64}
        if st == 200:
            payload['sha'] = res.get('sha', '')
        _github_api('PUT', f'/repos/{repo}/contents/{meta_path}', token, payload)

        db_kb = meta.get('db_size_kb', 0)
        media_kb = meta.get('media_size_kb', 0)
        webdev_kb = meta.get('webdev_size_kb', 0)
        venv_kb = meta.get('venv_size_kb', 0)
        msg = (f'전체 백업 완료 ({now_str}) | '
               f'DB:{db_kb}KB 미디어:{media_kb}KB 웹빌더:{webdev_kb}KB venv:{venv_kb}KB')
        if errors:
            msg += ' | 경고: ' + '; '.join(str(e) for e in errors)
        logger.info(f'[backup] {msg}')
        return True, msg

    except Exception as e:
        logger.error(f'[backup] 예외: {e}', exc_info=True)
        return False, str(e)


# ── 복원 수행 ──────────────────────────────────────────────────
def perform_restore():
    from django.conf import settings
    from django.db import connection as _dj_conn
    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_REPO', 'a50411278apeter40-svg/Syblog')
    if not token:
        return False, 'GITHUB_TOKEN 환경변수가 설정되지 않았습니다.'

    try:
        # ① 최신 메타 파일 로드
        logger.info('[restore] 메타 파일 탐색 중...')
        result, status = _github_api('GET', f'/repos/{repo}/contents/backups/meta', token)
        if status != 200 or not result:
            return False, f'백업 메타 목록 로드 실패 (status={status})'

        meta_files = sorted(
            [f for f in result if isinstance(f, dict) and f.get('name', '').endswith('.json')],
            key=lambda x: x['name'], reverse=True
        )
        if not meta_files:
            return False, '메타 파일이 없습니다. 먼저 백업을 실행하세요.'

        fm, fst = _github_api('GET', f'/repos/{repo}/contents/{meta_files[0]["path"]}', token)
        if fst != 200:
            return False, '메타 파일 로드 실패'
        meta_b64 = fm.get('content', '').replace('\n', '')
        meta = json.loads(base64.b64decode(meta_b64).decode('utf-8'))
        ts = meta.get('timestamp', '알 수 없음')
        logger.info(f'[restore] 메타 로드 완료: {ts}')

        # ② DB 파일 다운로드
        logger.info('[restore] DB 백업 파일 다운로드 중...')
        if not meta.get('db_path'):
            return False, 'DB 백업 경로 정보가 없습니다.'

        db_bytes, db_err = _download_file_from_github(
            token, repo, meta['db_path'], meta.get('db_info')
        )
        if not db_bytes:
            return False, f'DB 파일 다운로드 실패: {db_err}'
        backup_text = db_bytes.decode('utf-8')
        logger.info(f'[restore] DB 파일 다운로드 완료 ({len(db_bytes)//1024}KB)')

        # ③ sessions 백업 다운로드 (있으면)
        sessions_data = None
        if meta.get('sessions_path') and meta.get('sessions_info'):
            logger.info('[restore] sessions 백업 다운로드 중...')
            sess_bytes, sess_err = _download_file_from_github(
                token, repo, meta['sessions_path'], meta.get('sessions_info')
            )
            if sess_bytes:
                sessions_data = json.loads(sess_bytes.decode('utf-8'))
                logger.info(f'[restore] sessions {len(sessions_data)}개 로드 완료')
            else:
                logger.warning(f'[restore] sessions 다운로드 실패: {sess_err}')

        # ④ DB flush (django_session, django_migrations 제외) + loaddata
        logger.info('[restore] DB 복원 시작...')
        import tempfile as _tempfile
        import subprocess as _sub_restore

        venv_py = '/opt/render/project/src/.venv/bin/python3'
        manage_py = os.path.join(settings.BASE_DIR, 'manage.py')

        with _tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                          delete=False, encoding='utf-8') as _tf:
            _tf.write(backup_text)
            tmp_fixture = _tf.name

        try:
            # flush: sessions, migrations 제외하고 전부 삭제 (완전 덮어쓰기)
            _SKIP = {'django_migrations', 'django_session'}
            with _dj_conn.cursor() as cur:
                cur.execute('PRAGMA foreign_keys = OFF')
                cur.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = [r[0] for r in cur.fetchall() if r[0] not in _SKIP]
                for t in tables:
                    try:
                        cur.execute(f'DELETE FROM "{t}"')
                    except Exception:
                        pass
                cur.execute('PRAGMA foreign_keys = ON')
            logger.info(f'[restore] flush 완료 ({len(tables)}개 테이블, 세션 보존)')

            # loaddata
            r = _sub_restore.run(
                [venv_py, manage_py, 'loaddata', '--ignorenonexistent', tmp_fixture],
                capture_output=True, text=True, cwd=str(settings.BASE_DIR)
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

        # ⑤ sessions 복원 (SQL INSERT — 로그아웃 방지)
        if sessions_data:
            logger.info(f'[restore] sessions {len(sessions_data)}개 복원 중...')
            try:
                with _dj_conn.cursor() as cur:
                    # 기존 세션 삭제 후 백업 세션 삽입
                    cur.execute('DELETE FROM django_session')
                    for s in sessions_data:
                        cur.execute(
                            'INSERT OR REPLACE INTO django_session '
                            '(session_key, session_data, expire_date) VALUES (?,?,?)',
                            (s['session_key'], s['session_data'], s['expire_date'])
                        )
                logger.info(f'[restore] sessions 복원 완료')
            except Exception as _se:
                logger.warning(f'[restore] sessions 복원 실패 (무시): {_se}')
        else:
            logger.info('[restore] sessions 백업 없음 — 현재 세션 유지')

        # ⑥ 미디어 파일 복원
        if meta.get('media_path'):
            logger.info('[restore] 미디어 파일 복원 중...')
            media_bytes, media_err = _download_file_from_github(
                token, repo, meta['media_path'], meta.get('media_info')
            )
            if media_bytes:
                media_root = getattr(settings, 'MEDIA_ROOT',
                                     os.path.join(settings.BASE_DIR, '_media'))
                _zip_bytes_to_media(media_bytes, media_root)
                logger.info('[restore] 미디어 복원 완료')
            else:
                logger.warning(f'[restore] 미디어 복원 실패: {media_err}')

        # ⑦ AI 웹빌더 파일 복원
        if meta.get('webdev_path'):
            logger.info('[restore] AI 웹빌더 파일 복원 중...')
            webdev_bytes, webdev_err = _download_file_from_github(
                token, repo, meta['webdev_path'], meta.get('webdev_info')
            )
            if webdev_bytes:
                _zip_bytes_to_webdev(webdev_bytes, WEBDEV_WORKSPACE_PATH)
                logger.info('[restore] AI 웹빌더 복원 완료')
            else:
                logger.warning(f'[restore] 웹빌더 복원 실패: {webdev_err}')

        # ⑧ venv 복원
        if meta.get('venv_path') and meta.get('venv_info'):
            logger.info('[restore] venv 복원 중...')
            venv_bytes, venv_err = _download_file_from_github(
                token, repo, meta['venv_path'], meta.get('venv_info')
            )
            if venv_bytes:
                _zip_bytes_to_venv_all(venv_bytes, WEBDEV_WORKSPACE_PATH)
                logger.info('[restore] venv 복원 완료')
            else:
                logger.warning(f'[restore] venv 복원 실패, pip install 폴백: {venv_err}')
                _fallback_all_pip_install(WEBDEV_WORKSPACE_PATH)
        else:
            logger.info('[restore] venv 백업 없음 → pip install 폴백')
            _fallback_all_pip_install(WEBDEV_WORKSPACE_PATH)

        logger.info(f'[restore] 전체 복원 완료: {ts}')
        return True, f'전체 복원 완료 (백업 시각: {ts})'

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
