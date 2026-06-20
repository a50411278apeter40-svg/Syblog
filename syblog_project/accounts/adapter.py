import logging
import requests
from django.core.files.base import ContentFile
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


def _apply_google_avatar(user, extra_data):
    """구글 프로필 사진을 유저 아바타로 저장"""
    try:
        picture_url = extra_data.get('picture', '')
        if not picture_url:
            return
        profile = getattr(user, 'profile', None)
        if profile is None:
            return
        resp = requests.get(picture_url, timeout=10)
        if resp.status_code == 200:
            filename = f'google_{user.pk}.jpg'
            profile.avatar.save(filename, ContentFile(resp.content), save=True)
            logger.info(f'[SocialLogin] 구글 프사 저장 완료: {user.username}')
    except Exception as e:
        logger.error(f'[SocialLogin] 구글 프사 저장 실패: {e}')


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    allauth 65.x 호환 어댑터
    - 같은 이메일 기존 유저가 있으면 소셜 계정 자동 연결
    - 구글 프사 자동 적용
    """

    def authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        logger.error(
            f'[SocialLogin] authentication_error | provider={provider_id} | '
            f'error={error} | exception={exception} | extra={extra_context}'
        )
        super().authentication_error(
            request, provider_id,
            error=error, exception=exception, extra_context=extra_context
        )

    def pre_social_login(self, request, sociallogin):
        """이미 존재하는 이메일이면 기존 계정에 연결"""
        if sociallogin.is_existing:
            return

        email = ''
        if sociallogin.account.extra_data:
            email = sociallogin.account.extra_data.get('email', '') or ''
        email = email.lower().strip()

        logger.info(f'[SocialLogin] pre_social_login | email={email}')

        if not email:
            return

        try:
            existing_user = User.objects.filter(email__iexact=email).first()
            if existing_user:
                sociallogin.connect(request, existing_user)
        except Exception as e:
            logger.error(f'[SocialLogin] connect error: {e}')

    def save_user(self, request, sociallogin, form=None):
        """신규 유저 저장 후 구글 프사 적용"""
        user = super().save_user(request, sociallogin, form)
        extra_data = sociallogin.account.extra_data or {}
        _apply_google_avatar(user, extra_data)
        return user

    def is_auto_signup_allowed(self, request, sociallogin):
        return True


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return True
