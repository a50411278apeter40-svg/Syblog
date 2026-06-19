"""
Django admin Sites 테이블에 중복 등록된 Google 소셜 앱을 정리합니다.
settings.py의 SOCIALACCOUNT_PROVIDERS에 APP이 정의되어 있으면
DB 레코드는 필요 없으므로 전부 삭제합니다.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Remove duplicate SocialApp entries for Google from DB'

    def handle(self, *args, **options):
        try:
            from allauth.socialaccount.models import SocialApp
            google_apps = SocialApp.objects.filter(provider='google')
            count = google_apps.count()
            if count == 0:
                self.stdout.write(self.style.SUCCESS('No Google SocialApp in DB — nothing to do.'))
                return
            if count == 1:
                self.stdout.write(self.style.WARNING(f'1 Google SocialApp found in DB (id={google_apps.first().pk}). Keeping it.'))
                return
            # 중복 있으면 전부 삭제 (settings.APP이 우선 사용됨)
            google_apps.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Deleted {count} duplicate Google SocialApp entries from DB. '
                'Settings-based config will be used.'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
