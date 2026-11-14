"""监控路由 — 运行指标（teacher 权限）"""
from fastapi import APIRouter, Depends

from app.core.metrics import metrics
from app.core.security import require_role

router = APIRouter(prefix="/api", tags=["监控"])


@router.get("/metrics")
async def get_metrics(user: dict = Depends(require_role("teacher"))):
    return metrics.snapshot()
