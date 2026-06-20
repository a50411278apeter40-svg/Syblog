from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth import get_user_model

User = get_user_model()


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    구글 소셜 로그인 핵심 수정:
    1. pre_social_login: 같은 이메일 계정 있으면 자동 연결
    2. is_auto_signup_allowed: 이메일 중복이어도 자동 signup 허용 (연결로 처리)
    """

    def pre_social_login(self, request, sociallogin):
        # 이미 연결된 소셜 계정이면 바로 통과
        if sociallogin.is_existing:
            return

        email = (
            sociallogin.account.extra_data.get('email', '') or ''
        ).lower().strip()

        if not email:
            return

        # 같은 이메일의 기존 유저가 있으면 소셜 계정을 연결해버림
        try:
            existing_user = User.objects.filter(email__iexact=email).first()
            if existing_user:
                sociallogin.connect(request, existing_user)
        except Exception:
            pass

    def is_auto_signup_allowed(self, request, sociallogin):
        """
        이메일 중복 체크를 우회 — pre_social_login에서 이미 연결 처리했으므로
        항상 auto_signup 허용
        """
        return True


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return True
