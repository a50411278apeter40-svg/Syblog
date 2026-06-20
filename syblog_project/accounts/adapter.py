from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth import get_user_model

User = get_user_model()


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    구글 소셜 로그인 시 이메일 중복/MultipleObjectsReturned 방지
    """
    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return
        email = sociallogin.account.extra_data.get('email', '').lower().strip()
        if not email:
            return
        try:
            existing_user = User.objects.filter(email__iexact=email).first()
            if existing_user:
                sociallogin.connect(request, existing_user)
        except Exception:
            pass


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return True
