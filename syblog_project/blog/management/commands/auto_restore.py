from django.core.management.base import BaseCommand
from blog.utils_backup import perform_restore

class Command(BaseCommand):
    help = 'Automatically restore all data from GitHub'

    def handle(self, *args, **options):
        success, msg = perform_restore()
        if success:
            self.stdout.write(self.style.SUCCESS(f'✅ 복원 성공: {msg}'))
        else:
            self.stdout.write(self.style.ERROR(f'❌ 복원 실패: {msg}'))
