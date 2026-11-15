"""插件元数据路由 — 只读展示当前启用的出题 / 判题插件。"""
from fastapi import APIRouter

from app.plugins.registry import (
    DEFAULT_GRADER_ID,
    DEFAULT_GENERATOR_ID,
    GENERATOR_PLUGINS,
    GRADER_PLUGINS,
    list_plugins,
)

router = APIRouter(prefix="/api/plugins", tags=["插件"])


@router.get("")
async def current_plugins():
    """当前插件 + 全部已登记插件。

    前端个人学情档案用它标注「当前插件」；不涉及任何用户数据。
    """
    return {
        "generator": GENERATOR_PLUGINS.get(DEFAULT_GENERATOR_ID),
        "grader": GRADER_PLUGINS.get(DEFAULT_GRADER_ID),
        "available": list_plugins(),
    }
