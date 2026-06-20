"""
배포 시 Google SocialApp DB 레코드를 자동으로 생성/정리합니다.

- 환경변수 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET 이 설정된 경우:
  DB 레코드가 없으면 자동 생성, 중복이면 1개만 남기고 삭제합니다.
- 환경변수가 없는 경우:
  settings.py 의 APP 키를 통해 allauth 가 직접 처리하므로 아무것도 하지 않습니다.
"""
import os
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Ensure exactly one Google SocialApp entry exists in DB'

    def handle(self, *args, **options):
        try:
            from allauth.socialaccount.models import SocialApp
            from django.contrib.sites.models import Site

            client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
            client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '')

            google_apps = SocialApp.objects.filter(provider='google')
            count = google_apps.count()

            # 환경변수가 없으면 settings APP 키로 처리되므로 DB 레코드 불필요
            if not client_id:
                if count > 1:
                    # 중복 제거
                    google_apps.delete()
                    self.stdout.write(self.style.SUCCESS(
                        f'Deleted {count} duplicate Google SocialApp entries. '
                        'Settings-based APP config will be used.'
                    ))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        'GOOGLE_CLIENT_ID not set — using settings-based APP config.'
                    ))
                return

            if count == 0:
                # 새로 생성
                site = Site.objects.get_or_create(
                    id=1,
                    defaults={'domain': 'syblog.onrender.com', 'name': 'Syblog'}
                )[0]
                app = SocialApp.objects.create(
                    provider='google',
                    name='Google',
                    client_id=client_id,
                    secret=client_secret,
                )
                app.sites.add(site)
                self.stdout.write(self.style.SUCCESS(
                    f'Created Google SocialApp (client_id={client_id[:8]}...) and linked to site id=1.'
                ))
            elif count == 1:
                # 기존 레코드 값 업데이트
                app = google_apps.first()
                app.client_id = client_id
                app.secret = client_secret
                app.save()
                # site 연결 확인
                site = Site.objects.get_or_create(
                    id=1,
                    defaults={'domain': 'syblog.onrender.com', 'name': 'Syblog'}
                )[0]
                app.sites.add(site)
                self.stdout.write(self.style.SUCCESS(
                    f'Updated existing Google SocialApp (id={app.pk}) with env credentials.'
                ))
            else:
                # 중복 → 전부 삭제 후 재생성
                google_apps.delete()
                site = Site.objects.get_or_create(
                    id=1,
                    defaults={'domain': 'syblog.onrender.com', 'name': 'Syblog'}
                )[0]
                app = SocialApp.objects.create(
                    provider='google',
                    name='Google',
                    client_id=client_id,
                    secret=client_secret,
                )
                app.sites.add(site)
                self.stdout.write(self.style.SUCCESS(
                    f'Replaced {count} duplicate entries with a single Google SocialApp.'
                ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'fix_socialapp error: {e}'))
