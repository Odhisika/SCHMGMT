from django.shortcuts import redirect


class TemporaryPasswordMiddleware:
    """Limit temporary-password accounts to the password-change page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.must_change_password:
            path = request.path_info.rstrip("/")
            if not path.endswith("/change_password") and not path.endswith("/logout"):
                return redirect("change_password")
        return self.get_response(request)
