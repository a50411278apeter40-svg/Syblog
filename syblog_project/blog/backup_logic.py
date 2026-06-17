from django.core.management import call_command
from io import StringIO
import tempfile
import os
import json
import base64
import datetime
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.admin.views.decorators import staff_member_required
from .utils import _github_api

@staff_member_required
def backup_to_github(request):
    if request.method != 'POST':
        return redirect('blog:admin_dashboard')

    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_REPO', 'a50411278apeter40-svg/Syblog')
    if not token:
        messages.error(request, '❌ GITHUB_TOKEN 환경변수가 설정되지 않았습니다.')
        return redirect('blog:admin_dashboard')

    # Django dumpdata를 이용해 모든 데이터를 JSON 문자열로 추출
    # 권한, 세션, 로그 기록 등 불필요한 모델 제외
    out = StringIO()
    call_command('dumpdata', natural_foreign=True, exclude=['auth.permission', 'contenttypes', 'admin.logentry', 'sessions'], stdout=out)
    backup_json = out.getvalue()
    
    backup_b64 = base64.b64encode(backup_json.encode('utf-8')).decode('utf-8')

    now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = f'backups/syblog_backup_{now_str}.json'

    # GitHub에 파일 업로드
    commit_msg = f'🔒 전체 데이터 자동 백업 {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
    result, status = _github_api('PUT', f'/repos/{repo}/contents/{file_path}', token, {
        'message': commit_msg,
        'content': backup_b64,
    })

    if status in (200, 201):
        messages.success(request, f'✅ GitHub 전체 백업 완료! (모든 데이터 저장됨) → {file_path}')
    else:
        messages.error(request, f'❌ 백업 실패: {result.get("message", "알 수 없는 오류")}')

    return redirect('blog:admin_dashboard')

@staff_member_required
def restore_from_github(request):
    if request.method != 'POST':
        return redirect('blog:admin_dashboard')

    token = os.environ.get('GITHUB_TOKEN', '')
    repo = os.environ.get('GITHUB_REPO', 'a50411278apeter40-svg/Syblog')
    if not token:
        messages.error(request, '❌ GITHUB_TOKEN 환경변수가 설정되지 않았습니다.')
        return redirect('blog:admin_dashboard')

    # 최신 백업 파일 목록 가져오기
    result, status = _github_api('GET', f'/repos/{repo}/contents/backups', token)
    if status != 200:
        messages.error(request, f'❌ 백업 파일 목록 로드 실패: {result.get("message", "")}')
        return redirect('blog:admin_dashboard')

    if not result:
        messages.error(request, '❌ 백업 파일이 없습니다.')
        return redirect('blog:admin_dashboard')

    # 가장 최신 파일 선택
    backup_files = sorted([f for f in result if f['name'].endswith('.json')], key=lambda x: x['name'], reverse=True)
    if not backup_files:
        messages.error(request, '❌ 백업 JSON 파일이 없습니다.')
        return redirect('blog:admin_dashboard')

    latest = backup_files[0]
    file_result, file_status = _github_api('GET', f'/repos/{repo}/contents/{latest["path"]}', token)
    if file_status != 200:
        messages.error(request, '❌ 백업 파일 로드 실패')
        return redirect('blog:admin_dashboard')

    content_b64 = file_result.get('content', '').replace('\n', '')
    
    # 일부 구형 백업 파일은 직접 딕셔너리로 저장했을 수 있으므로 호환성을 확인
    backup_text = base64.b64decode(content_b64).decode('utf-8')
    try:
        backup_data = json.loads(backup_text)
        if isinstance(backup_data, dict):
            messages.error(request, '❌ 선택된 백업 파일이 구버전(일부 데이터만 저장) 양식입니다. "전부 다 저장"된 새 백업 파일만 덮어쓰기 복원이 가능합니다.')
            return redirect('blog:admin_dashboard')
    except Exception:
        messages.error(request, '❌ 백업 파일 파싱 오류')
        return redirect('blog:admin_dashboard')

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(backup_text)
            f_name = f.name
        
        # 완전히 덮어쓰기 위해 기존 데이터를 모두 삭제
        from django.contrib.auth.models import User
        from blog.models import Post, Category, Tag, Series
        
        # User를 삭제하면 UserProfile, ChallengeScore, Mail, Comment, SocialAccount 등이 CASCADE로 함께 지워집니다.
        # Session은 ForeignKey가 없어서 지워지지 않으므로, 복원 직후 로그인 상태가 그대로 유지됩니다!
        User.objects.all().delete()
        Post.objects.all().delete()
        Category.objects.all().delete()
        Tag.objects.all().delete()
        Series.objects.all().delete()
        
        # 새 데이터(전체) 로드
        call_command('loaddata', f_name)
        os.remove(f_name)
        
        messages.success(request, f'✅ 완벽 복원 완료! 기존 데이터가 완전히 지워지고 {latest["name"]} 파일의 모든 정보로 덮어씌워졌습니다.')
    except Exception as e:
        messages.error(request, f'❌ 복원 중 오류 발생: {str(e)}')
    
    return redirect('blog:admin_dashboard')
