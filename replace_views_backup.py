import sys
import re

with open('/app/syblog_project/blog/views.py', 'r') as f:
    content = f.read()

# Define the new backup logic for views using utils_backup
new_backup_logic = """
from .utils_backup import perform_backup, perform_restore

@staff_member_required
def backup_to_github(request):
    if request.method != 'POST':
        return redirect('blog:admin_dashboard')
    
    success, msg = perform_backup()
    if success:
        messages.success(request, f'✅ GitHub 전체 백업 완료! (모든 데이터 저장됨) → {msg}')
    else:
        messages.error(request, f'❌ 백업 실패: {msg}')
    return redirect('blog:admin_dashboard')

@staff_member_required
def restore_from_github(request):
    if request.method != 'POST':
        return redirect('blog:admin_dashboard')
        
    success, msg = perform_restore()
    if success:
        messages.success(request, f'✅ 완벽 복원 완료! 기존 데이터가 완전히 지워지고 {msg} 파일의 모든 정보로 덮어씌워졌습니다.')
    else:
        messages.error(request, f'❌ 복원 실패: {msg}')
    return redirect('blog:admin_dashboard')
"""

# We need to replace everything from @staff_member_required def backup_to_github
# up to the start of # ── 카테고리 context processor (전역) ──

start_pattern = r"@staff_member_required\ndef backup_to_github\(request\):"
end_pattern = r"# ── 카테고리 context processor \(전역\) ──"

parts = re.split(f"({start_pattern}.*?)({end_pattern})", content, flags=re.DOTALL)

if len(parts) >= 4:
    new_content = parts[0] + new_backup_logic + "\n" + parts[3] + parts[4]
    with open('/app/syblog_project/blog/views.py', 'w') as f:
        f.write(new_content)
    print("Replaced successfully")
else:
    print("Could not find patterns")
