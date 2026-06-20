import logging
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    allauth 0.54.x 호환 어댑터
    같은 이메일 계정 있으면 자동 연결
    """

    def authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        """에러 원인을 로그로 기록"""
        logger.error(
            f'[SocialLogin] authentication_error | provider={provider_id} | '
            f'error={error} | exception={exception} | extra={extra_context}'
        )
        super().authentication_error(request, provider_id, error=error, exception=exception, extra_context=extra_context)

    def pre_social_login(self, request, sociallogin):
        # 이미 연결된 소셜 계정이면 바로 통과
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

    def is_auto_signup_allowed(self, request, sociallogin):
        return True


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return True
