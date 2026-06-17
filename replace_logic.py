import sys

with open('/app/syblog_project/blog/views.py', 'r') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if line.startswith('@staff_member_required') and lines[i+1].startswith('def backup_to_github(request):'):
        start_idx = i
        break

for i in range(start_idx, len(lines)):
    if line.startswith('# ── 카테고리 context processor'):
        pass
    if lines[i].startswith('# ── 카테고리 context processor'):
        end_idx = i
        break

with open('/app/syblog_project/blog/backup_logic.py', 'r') as f:
    new_logic = f.read()

# Strip out the first 11 lines of backup_logic.py (imports and utils)
new_lines = new_logic.split('\n')[12:]
new_logic_str = '\n'.join(new_lines) + '\n\n'

imports = """from django.core.management import call_command
from io import StringIO
import tempfile
import base64
import json

"""

lines = lines[:start_idx] + [imports + new_logic_str] + lines[end_idx:]

with open('/app/syblog_project/blog/views.py', 'w') as f:
    f.writelines(lines)
