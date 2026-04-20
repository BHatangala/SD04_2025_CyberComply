from django.conf import settings


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' "
            "https://cdn.jsdelivr.net "
            "https://cdnjs.cloudflare.com "
            "https://unpkg.com "
            "https://cdn.tailwindcss.com "
            "https://accounts.google.com "
            "https://apis.google.com; "
            "style-src 'self' 'unsafe-inline' "
            "https://cdnjs.cloudflare.com "
            "https://fonts.googleapis.com; "
            "img-src 'self' data: blob:; "
            "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com data:; "
            "connect-src 'self' "
            "http://127.0.0.1:8000 "
            "http://127.0.0.1:5000 "
            "http://127.0.0.1:5500 "
            "http://localhost:8000 "
            "http://localhost:5000 "
            "http://localhost:5500 "
            "https://www.googleapis.com "
            "https://graph.microsoft.com "
            "https://login.microsoftonline.com "
            "https://accounts.google.com "
            "https://apis.google.com "
            "ws://127.0.0.1:5500 "
            "ws://localhost:5500; "
            "frame-src 'self' https://accounts.google.com; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'self'; "
            "form-action 'self';"
        )

        response["Content-Security-Policy"] = csp
        return response