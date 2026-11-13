from django.shortcuts import redirect


class NoCachePrivateMiddleware:
    """Stop browsers from caching authenticated pages and the auth screens.

    Without this, pressing Back after signing in restores the cached login
    page, and pressing Forward after signing out restores the cached
    dashboard/portal even though the session has already been destroyed.
    """

    AUTH_PATHS = ("/login", "/logout")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        path = request.path_info.rstrip("/")
        user = getattr(request, "user", None)
        is_auth_screen = path.endswith(self.AUTH_PATHS)

        if (user is not None and user.is_authenticated) or is_auth_screen:
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"

        return response


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
