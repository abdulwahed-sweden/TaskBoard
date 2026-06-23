"""A small fixed-window rate limiter built on Django's cache framework.

No extra dependency. NOTE: with the default per-process LocMemCache each gunicorn
worker keeps its own counters, so for production deploy a shared cache backend
(Redis/Memcached) to make limits global across workers.
"""

from django.core.cache import cache


def client_ip(request):
    """Best-effort client IP. Uses REMOTE_ADDR; behind a proxy, configure the
    proxy to set a trusted header and read it here instead."""
    return request.META.get("REMOTE_ADDR") or "unknown"


def too_many(key, limit, window_seconds):
    """Register one hit against ``key`` and return True if ``limit`` is exceeded
    within ``window_seconds`` (fixed window). The first ``limit`` calls return
    False; the next returns True until the window expires."""
    current = cache.get(key)
    if current is None:
        cache.set(key, 1, timeout=window_seconds)
        return False
    if current >= limit:
        return True
    try:
        cache.incr(key)
    except ValueError:  # entry expired between get and incr
        cache.set(key, 1, timeout=window_seconds)
    return False
