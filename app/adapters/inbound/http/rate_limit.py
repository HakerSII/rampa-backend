"""Fixed-window rate limiting (in-memory, per process): per API key (Open API, F5) and per user / IP on AI and
login endpoints (F43)."""
import math
import time
from collections.abc import Callable

from starlette.responses import JSONResponse

from app.domain.errors import RateLimited

API_PREFIX = "/api/v1"


class FixedWindowRateLimiter:
    def __init__(self, limit: int, window_s: float = 60.0, now: Callable[[], float] = time.monotonic,
                 max_keys: int = 10_000):
        self.limit = limit  # 0 = unlimited
        self.window_s = window_s
        self.now = now
        self.max_keys = max_keys
        self._windows: dict[str, tuple[float, int]] = {}  # key -> (window start, count)

    def hit(self, key: str) -> None:
        if self.limit <= 0:
            return
        now = self.now()
        if len(self._windows) >= self.max_keys:  # forget expired windows (no unbounded growth)
            self._windows = {k: w for k, w in self._windows.items() if now - w[0] < self.window_s}
        start, count = self._windows.get(key, (now, 0))
        if now - start >= self.window_s:
            start, count = now, 0
        if count >= self.limit:
            retry = max(1, math.ceil(self.window_s - (now - start)))
            raise RateLimited(f"rate limit {self.limit}/min exceeded", retry_after=retry)
        self._windows[key] = (start, count + 1)


def client_ip(scope, trusted_hops: int = 0) -> str:
    """Socket address; behind `trusted_hops` proxies (Render: 1) the address the nearest trusted proxy appended to
    X-Forwarded-For (counted from the right). The client-controlled left part is never trusted."""
    if trusted_hops > 0:
        raw = dict(scope.get("headers") or []).get(b"x-forwarded-for", b"").decode()
        hops = [h.strip() for h in raw.split(",") if h.strip()]
        if len(hops) >= trusted_hops:
            return hops[-trusted_hops]
    client = scope.get("client")
    return client[0] if client else "unknown"


class RequestRateLimitMiddleware:
    """F43: /api/v1/ai/* → per user (token, else IP) + per IP; POST /api/v1/auth/* (not logout) → per IP."""

    def __init__(self, app, *, ai_per_user: int, ai_per_ip: int, auth_per_ip: int, trusted_hops: int = 0):
        self.app = app
        self.ai_user = FixedWindowRateLimiter(ai_per_user)
        self.ai_ip = FixedWindowRateLimiter(ai_per_ip)
        self.auth_ip = FixedWindowRateLimiter(auth_per_ip)
        self.trusted_hops = trusted_hops

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path, method = scope["path"], scope["method"]
        try:
            if path.startswith(f"{API_PREFIX}/ai/"):
                ip = client_ip(scope, self.trusted_hops)
                token = dict(scope.get("headers") or []).get(b"authorization", b"").decode()
                self.ai_ip.hit(ip)
                self.ai_user.hit(f"t:{token}" if token else f"ip:{ip}")
            elif (path.startswith(f"{API_PREFIX}/auth/") and method == "POST"
                  and path != f"{API_PREFIX}/auth/logout"):
                self.auth_ip.hit(client_ip(scope, self.trusted_hops))
        except RateLimited as e:
            body = {"error": {"code": "RATE_LIMITED", "message": e.message}}
            return await JSONResponse(body, status_code=429, headers={"Retry-After": str(e.retry_after)})(
                scope, receive, send)
        return await self.app(scope, receive, send)
