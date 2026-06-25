"""기본 게시판 데이터 자동 생성 마이그레이션"""
from django.db import migrations

DEFAULT_BOARDS = [
    {'name': '자유게시판', 'slug': 'free',       'description': '자유롭게 이야기를 나눠요', 'icon': '💬', 'order': 1},
    {'name': '질문게시판', 'slug': 'qna',        'description': '모르는 것을 물어보세요',   'icon': '❓', 'order': 2},
    {'name': '정보공유',   'slug': 'info',       'description': '유용한 정보를 공유해요',   'icon': '📚', 'order': 3},
    {'name': '개발이야기', 'slug': 'dev',        'description': '개발 관련 이야기',         'icon': '💻', 'order': 4},
    {'name': '취업/커리어','slug': 'career',     'description': '취업·커리어 고민을 나눠요','icon': '🚀', 'order': 5},
]

def create_default_boards(apps, schema_editor):
    Board = apps.get_model('blog', 'Board')
    for b in DEFAULT_BOARDS:
        Board.objects.get_or_create(slug=b['slug'], defaults=b)

def delete_default_boards(apps, schema_editor):
    Board = apps.get_model('blog', 'Board')
    for b in DEFAULT_BOARDS:
        Board.objects.filter(slug=b['slug']).delete()

class Migration(migrations.Migration):
    dependencies = [
        ('blog', '0008_add_board_and_suggestion'),
    ]
    operations = [
        migrations.RunPython(create_default_boards, delete_default_boards),
    ]
