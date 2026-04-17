from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone

from .models import UserProfile


class LastSeenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated:
            cache_key = f"last_seen_update:{request.user.id}"
            if not cache.get(cache_key):
                UserProfile.objects.filter(user=request.user).update(last_seen=timezone.now())
                cache.set(cache_key, True, timeout=60)

        return response


class RateLimitMiddleware:
    LIMITED_PATHS = {
        "/": 8,
        "/register": 5,
        "/addpost": 12,
        "/post/": 18,
        "/chat/send": 25,
        "/chat/group/": 25,
        "/post/": 18,
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" or request.path in {"/", "/register", "/chat/send", "/addpost"} or request.path.startswith("/post/") or request.path.startswith("/chat/group/"):
            limit = self._limit_for_path(request.path)
            if limit and self._is_limited(request, limit):
                return HttpResponse("Too many requests. Please slow down.", status=429)

        return self.get_response(request)

    def _limit_for_path(self, path):
        for prefix, limit in self.LIMITED_PATHS.items():
            if path.startswith(prefix):
                return limit
        return None

    def _is_limited(self, request, limit):
        identity = request.user.id if request.user.is_authenticated else request.META.get("REMOTE_ADDR", "anonymous")
        cache_key = f"ratelimit:{identity}:{request.path}:{request.method}"
        count = cache.get(cache_key, 0) + 1
        cache.set(cache_key, count, timeout=60)
        return count > limit
