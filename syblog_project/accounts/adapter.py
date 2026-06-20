import logging
import requests
from io import BytesIO
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

        # 이미 아바타가 있으면 덮어쓰기 (항상 구글 프사 최신 유지)
        resp = requests.get(picture_url, timeout=10)
        if resp.status_code == 200:
            ext = 'jpg'
            filename = f'google_{user.pk}.{ext}'
            profile.avatar.save(filename, ContentFile(resp.content), save=True)
            logger.info(f'[SocialLogin] 구글 프사 저장 완료: {user.username}')
    except Exception as e:
        logger.error(f'[SocialLogin] 구글 프사 저장 실패: {e}')


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    allauth 0.54.x 호환 어댑터
    같은 이메일 계정 있으면 자동 연결 + 구글 프사 자동 적용
    """

    def authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        """에러 원인을 로그로 기록"""
        logger.error(
            f'[SocialLogin] authentication_error | provider={provider_id} | '
            f'error={error} | exception={exception} | extra={extra_context}'
        )
        super().authentication_error(request, provider_id, error=error, exception=exception, extra_context=extra_context)

    def pre_social_login(self, request, sociallogin):
        # 이미 연결된 소셜 계정이면 바로 통과 (프사는 save_user에서 처리)
        if sociallogin.is_existing:
            return

        # Google에서 받아온 이메일
        email = ''
        if sociallogin.account.extra_data:
            email = sociallogin.account.extra_data.get('email', '') or ''
        email = email.lower().strip()

        logger.info(f'[SocialLogin] pre_social_login | email={email}')

        if not email:
            return

        # 같은 이메일의 기존 유저가 있으면 소셜 계정을 연결
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

    def populate_user(self, request, sociallogin, data):
        """기존 유저가 구글로 로그인할 때도 프사 최신화"""
        user = super().populate_user(request, sociallogin, data)
        return user


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return True
