"""
백업/복원 로직 - DB(JSON) + 미디어 파일(base64) 통합 백업
"""
from django.core.management import call_command
from io import StringIO
import tempfile, os, json, base64, datetime
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.admin.views.decorators import staff_member_required
from .utils import _github_api

MEDIA_ROOT = None  # 동적으로 settings에서 가져옴

def _get_media_root():
    from django.conf import settings
    return getattr(settings, 'MEDIA_ROOT', None)

def _collect_media_files():
    """_media/ 하위 모든 파일을 {상대경로: base64} dict로 반환"""
    media_root = _get_media_root()
    if not media_root or not os.path.isdir(media_root):
        return {}
    files = {}
    for dirpath, _, filenames in os.walk(media_root):
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, media_root)
            try:
                with open(full_path, 'rb') as f:
                    files[rel_path] = base64.b64encode(f.read()).decode('utf-8')
            except Exception:
                pass
    return files

def _restore_media_files(media_dict):
    """base64 dict를 _media/ 에 복원"""
    media_root = _get_media_root()
    if not media_root:
        return 0
    count = 0
    for rel_path, b64_data in media_dict.items():
        dest = os.path.join(media_root, rel_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        try:
            with open(dest, 'wb') as f:
                f.write(base64.b64decode(b64_data))
            count += 1
        except Exception:
            pass
    return count


@staff_member_required
def backup_to_github(request):
    if request.method != 'POST':
        return redirect('blog:admin_dashboard')

    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_BACKUP_REPO', 'a50411278apeter40-svg/syblog-data-backup')
    if not token:
        messages.error(request, '❌ GITHUB_TOKEN 환경변수가 설정되지 않았습니다.')
        return redirect('blog:admin_dashboard')

    # 1) DB 덤프
    out = StringIO()
    call_command('dumpdata', natural_foreign=True,
                 exclude=['auth.permission', 'contenttypes', 'admin.logentry', 'sessions'],
                 stdout=out)
    db_json = out.getvalue()

    # 2) 미디어 파일 수집
    media_files = _collect_media_files()

    # 3) 통합 패키지 생성
    package = {
        'version': 2,
        'created_at': datetime.datetime.now().isoformat(),
        'db': db_json,
        'media': media_files,
    }
    package_json = json.dumps(package, ensure_ascii=False)
    package_b64 = base64.b64encode(package_json.encode('utf-8')).decode('utf-8')

    now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = f'backups/syblog_full_{now_str}.json'

    commit_msg = f'💾 전체 백업 (DB+미디어) {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}'
    result, status = _github_api('PUT', f'/repos/{repo}/contents/{file_path}', token, {
        'message': commit_msg,
        'content': package_b64,
    })

    if status in (200, 201):
        media_count = len(media_files)
        messages.success(request, f'✅ 전체 백업 완료! DB + 미디어 {media_count}개 파일 → {file_path}')
    else:
        messages.error(request, f'❌ 백업 실패: {result.get("message", "알 수 없는 오류")}')

    return redirect('blog:admin_dashboard')


@staff_member_required
def restore_from_github(request):
    if request.method != 'POST':
        return redirect('blog:admin_dashboard')

    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_BACKUP_REPO', 'a50411278apeter40-svg/syblog-data-backup')
    if not token:
        messages.error(request, '❌ GITHUB_TOKEN 환경변수가 설정되지 않았습니다.')
        return redirect('blog:admin_dashboard')

    # 최신 백업 파일 목록
    result, status = _github_api('GET', f'/repos/{repo}/contents/backups', token)
    if status != 200:
        messages.error(request, f'❌ 백업 파일 목록 로드 실패: {result.get("message", "")}')
        return redirect('blog:admin_dashboard')

    if not result:
        messages.error(request, '❌ 백업 파일이 없습니다.')
        return redirect('blog:admin_dashboard')

    backup_files = sorted(
        [f for f in result if f['name'].endswith('.json')],
        key=lambda x: x['name'], reverse=True
    )
    if not backup_files:
        messages.error(request, '❌ 백업 JSON 파일이 없습니다.')
        return redirect('blog:admin_dashboard')

    latest = backup_files[0]
    file_result, file_status = _github_api('GET', f'/repos/{repo}/contents/{latest["path"]}', token)
    if file_status != 200:
        messages.error(request, '❌ 백업 파일 로드 실패')
        return redirect('blog:admin_dashboard')

    content_b64 = file_result.get('content', '').replace('\n', '')
    backup_text = base64.b64decode(content_b64).decode('utf-8')

    try:
        package = json.loads(backup_text)
    except Exception:
        messages.error(request, '❌ 백업 파일 파싱 오류')
        return redirect('blog:admin_dashboard')

    # version 2 (통합 패키지) vs 구버전 호환
    if isinstance(package, dict) and package.get('version') == 2:
        db_json = package.get('db', '[]')
        media_dict = package.get('media', {})
    elif isinstance(package, list):
        # 구버전: 순수 dumpdata 리스트
        db_json = backup_text
        media_dict = {}
    else:
        messages.error(request, '❌ 지원하지 않는 백업 포맷입니다.')
        return redirect('blog:admin_dashboard')

    try:
        # DB 완전 교체
        from django.contrib.auth.models import User
        from blog.models import Post, Category, Tag, Series

        User.objects.all().delete()
        Post.objects.all().delete()
        Category.objects.all().delete()
        Tag.objects.all().delete()
        Series.objects.all().delete()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(db_json)
            f_name = f.name

        call_command('loaddata', f_name)
        os.remove(f_name)

        # 미디어 파일 복원
        media_count = _restore_media_files(media_dict)

        messages.success(
            request,
            f'✅ 복원 완료! ({latest["name"]}) — DB 전체 + 미디어 {media_count}개 파일 복원됨'
        )
    except Exception as e:
        messages.error(request, f'❌ 복원 중 오류 발생: {str(e)}')

    return redirect('blog:admin_dashboard')
