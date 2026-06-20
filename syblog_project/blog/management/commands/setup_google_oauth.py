from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
import os


class Command(BaseCommand):
    help = 'Google OAuth SocialApp을 DB에 등록'

    def handle(self, *args, **kwargs):
        from allauth.socialaccount.models import SocialApp

        client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
        secret = os.environ.get('GOOGLE_CLIENT_SECRET', '')

        if not client_id or not secret:
            self.stdout.write(self.style.WARNING('GOOGLE_CLIENT_ID 또는 GOOGLE_CLIENT_SECRET 환경변수가 없습니다.'))
            return

        site = Site.objects.get_or_create(id=1, defaults={'domain': 'syblog.onrender.com', 'name': 'Syblog'})[0]

        app, created = SocialApp.objects.get_or_create(
            provider='google',
            defaults={
                'name': 'Google',
                'client_id': client_id,
                'secret': secret,
            }
        )

        if not created:
            app.client_id = client_id
            app.secret = secret
            app.save()

        if site not in app.sites.all():
            app.sites.add(site)

        self.stdout.write(self.style.SUCCESS(f'Google OAuth 앱 {"생성" if created else "업데이트"} 완료'))
