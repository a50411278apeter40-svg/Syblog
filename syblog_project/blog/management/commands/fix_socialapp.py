"""
배포 시 Google / Microsoft SocialApp DB 레코드를 자동으로 생성/정리합니다.
"""
import os
from django.core.management.base import BaseCommand


def _ensure_social_app(provider, name, client_id, client_secret, site):
    from allauth.socialaccount.models import SocialApp
    apps = SocialApp.objects.filter(provider=provider)
    count = apps.count()
    if count == 0:
        app = SocialApp.objects.create(
            provider=provider, name=name,
            client_id=client_id, secret=client_secret,
        )
        app.sites.add(site)
        return f'Created {name} SocialApp'
    elif count == 1:
        app = apps.first()
        app.client_id = client_id
        app.secret = client_secret
        app.save()
        app.sites.add(site)
        return f'Updated {name} SocialApp'
    else:
        apps.delete()
        app = SocialApp.objects.create(
            provider=provider, name=name,
            client_id=client_id, secret=client_secret,
        )
        app.sites.add(site)
        return f'Replaced {count} duplicate {name} SocialApp entries'


class Command(BaseCommand):
    help = 'Ensure Google and Microsoft SocialApp entries exist in DB'

    def handle(self, *args, **options):
        try:
            from allauth.socialaccount.models import SocialApp
            from django.contrib.sites.models import Site

            site, _ = Site.objects.get_or_create(
                id=1,
                defaults={'domain': 'syblog.onrender.com', 'name': 'Syblog'}
            )

            # Google
            google_id = os.environ.get('GOOGLE_CLIENT_ID', '')
            google_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '')
            if google_id:
                msg = _ensure_social_app('google', 'Google', google_id, google_secret, site)
                self.stdout.write(self.style.SUCCESS(f'[Google] {msg}'))
            else:
                self.stdout.write(self.style.WARNING('[Google] GOOGLE_CLIENT_ID not set — using settings APP config.'))

            # Microsoft
            ms_id = os.environ.get('MICROSOFT_CLIENT_ID', '')
            ms_secret = os.environ.get('MICROSOFT_CLIENT_SECRET', '')
            if ms_id:
                msg = _ensure_social_app('microsoft', 'Microsoft', ms_id, ms_secret, site)
                self.stdout.write(self.style.SUCCESS(f'[Microsoft] {msg}'))
            else:
                self.stdout.write(self.style.WARNING('[Microsoft] MICROSOFT_CLIENT_ID not set — using settings APP config.'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'fix_socialapp error: {e}'))
