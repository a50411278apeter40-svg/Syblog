import os
import json
import base64
import tempfile
import datetime
import zipfile
import shutil
import urllib.request
import urllib.parse
from io import StringIO, BytesIO
from django.core.management import call_command
from django.contrib.auth.models import User
from blog.models import Post, Category, Tag, Series

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
    """
    data_bytes가 크면 여러 청크로 분할해 업로드.
    청크가 1개면 단일 파일, 여러 개면 file_path.part00, .part01 ... 형태로 저장.
    반환값: (success, info_dict_or_msg)
    info_dict = {'type': 'single'|'multi', 'parts': int, 'base_path': str}
    """
    if len(data_bytes) <= GITHUB_MAX_BYTES:
        # 단일 파일 업로드
        b64 = base64.b64encode(data_bytes).decode('utf-8')
        # 기존 sha 확인
        res, st = _github_api('GET', f'/repos/{repo}/contents/{file_path_in_repo}', token)
        payload = {'message': commit_msg, 'content': b64}
        if st == 200:
            payload['sha'] = res.get('sha', '')
        result, status = _github_api('PUT', f'/repos/{repo}/contents/{file_path_in_repo}', token, payload)
        if status in (200, 201):
            return True, {'type': 'single', 'parts': 1, 'base_path': file_path_in_repo}
        return False, result.get('message', '업로드 실패')
    else:
        # 분할 업로드
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
    """upload_large_file의 반대 — 분할 파일이면 합쳐서 bytes 반환"""
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


# ── zip bytes → 미디어 폴더 복원 ────────────────────────────────
def _zip_bytes_to_media(zip_bytes, media_root):
    # 기존 미디어 폴더 삭제 후 재생성
    if os.path.isdir(media_root):
        shutil.rmtree(media_root)
    os.makedirs(media_root, exist_ok=True)
    with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zf:
        zf.extractall(media_root)


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

        # ② 미디어 파일 zip 백업
        media_root = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, '_media'))
        media_zip_bytes = _media_to_zip_bytes(media_root)

        media_path = f'backups/media/syblog_media_{now_str}.zip'
        ok, info_or_err = _upload_large_file_to_github(
            token, repo, media_path, media_zip_bytes,
            f'🖼️ 미디어 백업 {now_str}'
        )
        if not ok:
            errors.append(f'미디어 백업 경고: {info_or_err}')

        # ③ 메타 파일 (어떤 백업 파일끼리 쌍인지 기록)
        meta = {
            'timestamp': now_str,
            'db_path': db_path,
            'media_path': media_path,
            'media_info': info_or_err if ok else None,
            'media_zip_size_kb': round(len(media_zip_bytes) / 1024, 1),
        }
        meta_b64 = base64.b64encode(json.dumps(meta, ensure_ascii=False).encode('utf-8')).decode('utf-8')
        meta_path = f'backups/meta/syblog_meta_{now_str}.json'
        res, st = _github_api('GET', f'/repos/{repo}/contents/{meta_path}', token)
        payload = {'message': f'📋 백업 메타 {now_str}', 'content': meta_b64}
        if st == 200:
            payload['sha'] = res.get('sha', '')
        _github_api('PUT', f'/repos/{repo}/contents/{meta_path}', token, payload)

        msg = f'DB + 미디어 백업 완료 ({now_str})'
        if errors:
            msg += ' | 경고: ' + '; '.join(errors)
        return True, msg

    except Exception as e:
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
            # 메타 방식: DB + 미디어 쌍으로 복원
            latest_meta_res = meta_files[0]
            fm, fst = _github_api('GET', f'/repos/{repo}/contents/{latest_meta_res["path"]}', token)
            if fst != 200:
                return False, '메타 파일 로드 실패'
            meta_b64 = fm.get('content', '').replace('\n', '')
            meta = json.loads(base64.b64decode(meta_b64).decode('utf-8'))

            # DB 복원
            db_fm, db_st = _github_api('GET', f'/repos/{repo}/contents/{meta["db_path"]}', token)
            if db_st != 200:
                return False, 'DB 백업 파일 로드 실패'
            db_b64 = db_fm.get('content', '').replace('\n', '')
            backup_text = base64.b64decode(db_b64).decode('utf-8')

            # 미디어 복원
            media_err = None
            if meta.get('media_path') and meta.get('media_info'):
                zip_bytes, media_err = _download_file_from_github(
                    token, repo, meta['media_path'], meta['media_info']
                )
                if zip_bytes:
                    media_root = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, '_media'))
                    _zip_bytes_to_media(zip_bytes, media_root)

            ts = meta.get('timestamp', '알 수 없음')

        else:
            # 레거시 방식: backups/ 하위 JSON 직접 탐색
            result, status = _github_api('GET', f'/repos/{repo}/contents/backups', token)
            if status != 200:
                return False, f'백업 파일 목록 로드 실패: {result.get("message","")}'
            if not result:
                return False, '백업 파일이 없습니다.'
            backup_files = sorted(
                [f for f in result if f['name'].endswith('.json')],
                key=lambda x: x['name'], reverse=True
            )
            if not backup_files:
                return False, '백업 JSON 파일이 없습니다.'
            latest = backup_files[0]
            file_result, file_status = _github_api('GET', f'/repos/{repo}/contents/{latest["path"]}', token)
            if file_status != 200:
                return False, '백업 파일 로드 실패'
            content_b64 = file_result.get('content', '').replace('\n', '')
            backup_text = base64.b64decode(content_b64).decode('utf-8')
            ts = latest['name']
            media_err = '(레거시 백업 — 미디어 파일 없음)'

        # DB 로드
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(backup_text)
            f_name = f.name

        User.objects.all().delete()
        Post.objects.all().delete()
        Category.objects.all().delete()
        Tag.objects.all().delete()
        Series.objects.all().delete()

        call_command('loaddata', f_name)
        os.remove(f_name)

        msg = f'복원 완료 ({ts})'
        if media_err:
            msg += f' | 미디어: {media_err}'
        return True, msg

    except Exception as e:
        return False, str(e)
