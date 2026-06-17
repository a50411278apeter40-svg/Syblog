from django.core.management.base import BaseCommand
from blog.utils_backup import perform_backup

class Command(BaseCommand):
    help = 'Automatically backup all data to GitHub'

    def handle(self, *args, **options):
        success, msg = perform_backup()
        if success:
            self.stdout.write(self.style.SUCCESS(f'✅ 백업 성공: {msg}'))
        else:
            self.stdout.write(self.style.ERROR(f'❌ 백업 실패: {msg}'))
