from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import logout

class BlockedUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            try:
                if request.user.profile.is_blocked:
                    logout(request)
                    messages.error(request, '관리자에 의해 차단된 계정입니다.')
                    return redirect('/')
            except:
                pass
        return self.get_response(request)
