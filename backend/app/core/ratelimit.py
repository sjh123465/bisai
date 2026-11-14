"""限流中间件 — 滑动窗口计数（内存版，单实例足够）

- 默认每 IP 每分钟 60 次，可经 RATE_LIMIT_PER_MIN 配置
- 豁免: /health、/、/static、/docs、/openapi.json
"""
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings

EXEMPT_PREFIXES = ("/static", "/docs", "/openapi.json", "/assets")
EXEMPT_PATHS = {"/", "/health", "/favicon.ico"}


class RateLimiter:
    """独立类，便于单测"""

    def __init__(self, limit_per_min: int):
        self.limit = limit_per_min
        self._buckets: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, int]:
        """返回 (是否放行, 剩余额度)。窗口 60s 滑动。"""
        now = time.time()
        dq = self._buckets[key]
        while dq and dq[0] <= now - 60:
            dq.popleft()
        if len(dq) >= self.limit:
            return False, 0
        dq.append(now)
        return True, self.limit - len(dq)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.limiter = RateLimiter(get_settings().rate_limit_per_min)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in EXEMPT_PATHS or any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        ok, remaining = self.limiter.check(client_ip)
        if not ok:
            return JSONResponse(
                {"detail": "请求过于频繁，请稍后再试（限流: 每分钟 "
                           f"{get_settings().rate_limit_per_min} 次）"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
