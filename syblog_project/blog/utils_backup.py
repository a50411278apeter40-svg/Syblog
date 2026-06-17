import os
import json
import base64
import tempfile
import datetime
import urllib.request
import urllib.parse
from io import StringIO
from django.core.management import call_command
from django.contrib.auth.models import User
from blog.models import Post, Category, Tag, Series

def _github_api(method, path, token, data=None):
    """GitHub API 호출 헬퍼"""
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

def perform_backup():
    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_REPO', 'a50411278apeter40-svg/Syblog')
    if not token:
        return False, 'GITHUB_TOKEN 환경변수가 설정되지 않았습니다.'

    try:
        out = StringIO()
        call_command('dumpdata', natural_foreign=True, exclude=['auth.permission', 'contenttypes', 'admin.logentry', 'sessions'], stdout=out)
        backup_json = out.getvalue()
        
        backup_b64 = base64.b64encode(backup_json.encode('utf-8')).decode('utf-8')

        now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path = f'backups/syblog_backup_{now_str}.json'

        commit_msg = f'🔒 전체 데이터 자동 백업 {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        result, status = _github_api('PUT', f'/repos/{repo}/contents/{file_path}', token, {
            'message': commit_msg,
            'content': backup_b64,
        })

        if status in (200, 201):
            return True, file_path
        else:
            return False, result.get("message", "알 수 없는 오류")
    except Exception as e:
        return False, str(e)


def perform_restore():
    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_REPO', 'a50411278apeter40-svg/Syblog')
    if not token:
        return False, 'GITHUB_TOKEN 환경변수가 설정되지 않았습니다.'

    try:
        result, status = _github_api('GET', f'/repos/{repo}/contents/backups', token)
        if status != 200:
            return False, f'백업 파일 목록 로드 실패: {result.get("message", "")}'

        if not result:
            return False, '백업 파일이 없습니다.'

        backup_files = sorted([f for f in result if f['name'].endswith('.json')], key=lambda x: x['name'], reverse=True)
        if not backup_files:
            return False, '백업 JSON 파일이 없습니다.'

        latest = backup_files[0]
        file_result, file_status = _github_api('GET', f'/repos/{repo}/contents/{latest["path"]}', token)
        if file_status != 200:
            return False, '백업 파일 로드 실패'

        content_b64 = file_result.get('content', '').replace('\n', '')
        backup_text = base64.b64decode(content_b64).decode('utf-8')
        
        try:
            backup_data = json.loads(backup_text)
            if isinstance(backup_data, dict):
                return False, '선택된 백업 파일이 구버전(일부 데이터만 저장) 양식입니다. "전부 다 저장"된 새 백업 파일만 덮어쓰기 복원이 가능합니다.'
        except Exception:
            return False, '백업 파일 파싱 오류'

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
        
        return True, latest["name"]
    except Exception as e:
        return False, str(e)
