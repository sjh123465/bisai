"""轻量监控 — 请求计数 / 错误率 / 延迟统计（内存版）

暴露 GET /api/metrics（teacher 权限）供驾驶舱展示。
"""
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class Metrics:
    def __init__(self):
        self.started_at = time.time()
        self.total = 0
        self.errors = 0
        self.by_path: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "errors": 0, "total_ms": 0.0, "max_ms": 0.0}
        )

    def record(self, method: str, path: str, status: int, ms: float):
        self.total += 1
        if status >= 400:
            self.errors += 1
        key = f"{method} {path}"
        s = self.by_path[key]
        s["count"] += 1
        if status >= 400:
            s["errors"] += 1
        s["total_ms"] += ms
        s["max_ms"] = max(s["max_ms"], ms)

    def snapshot(self) -> dict:
        uptime = time.time() - self.started_at
        paths = []
        for key, s in sorted(self.by_path.items(), key=lambda kv: -kv[1]["count"])[:50]:
            paths.append({
                "endpoint": key,
                "count": s["count"],
                "errors": s["errors"],
                "avg_ms": round(s["total_ms"] / s["count"], 1),
                "max_ms": round(s["max_ms"], 1),
            })
        return {
            "uptime_seconds": round(uptime, 1),
            "total_requests": self.total,
            "total_errors": self.errors,
            "error_rate": round(self.errors / self.total, 4) if self.total else 0.0,
            "qpm": round(self.total / (uptime / 60), 1) if uptime > 0 else 0.0,
            "endpoints": paths,
        }


metrics = Metrics()


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            metrics.record(request.method, request.url.path, status, (time.time() - start) * 1000)
        return response
