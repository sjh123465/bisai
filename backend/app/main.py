"""CodeMentor 主入口 — FastAPI 应用"""
import os
import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.metrics import metrics
from app.core.ratelimit import RateLimitMiddleware
from app.routers import routers_list

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化知识图谱 + 向量库"""
    cfg = get_settings()
    os.makedirs(cfg.data_dir, exist_ok=True)

    # 延迟导入避免循环
    try:
        from app.core.seed_knowledge import init_knowledge_base
        await init_knowledge_base()
    except Exception as e:
        logger.error(f"知识库初始化失败（请检查 ChromaDB / 数据目录 / 依赖安装）: {e}")
        logger.warning("⚠️ 知识库可能为空；个人练习与班级作业仍可使用，图谱/向量功能会受限")

    yield
    logger.info("👋 CodeMentor 关闭")


app = FastAPI(
    title="CodeMentor — Agent + GraphRAG 助学平台",
    description="懂代码、知图谱、能动手的 AI 导师",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS（前端开发跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# L4 安全层：限流 + 监控（顺序：CORS 最外层 → 限流 → 监控）
app.add_middleware(RateLimitMiddleware)
from app.core.metrics import MetricsMiddleware
app.add_middleware(MetricsMiddleware)

# 注册路由
for r in routers_list:
    app.include_router(r)

# 静态文件（前端）
# 本地运行: backend/app/../../frontend == 仓库根/frontend
# Docker:   /app/app/../frontend      == /app/frontend
_here = os.path.dirname(os.path.abspath(__file__))
_frontend_candidates = [
    os.path.abspath(os.path.join(_here, "..", "..", "frontend")),
    os.path.abspath(os.path.join(_here, "..", "frontend")),
    os.path.abspath(os.path.join(os.getcwd(), "frontend")),
]
frontend_dir = next((p for p in _frontend_candidates if os.path.isdir(p)), None)
if frontend_dir:
    app.mount("/static", StaticFiles(directory=frontend_dir), name="frontend")
else:
    logger.warning("⚠️ 未找到 frontend 目录，/static 前端将不可用")


@app.middleware("http")
async def no_cache_static(request, call_next):
    """静态资源走协商缓存：改了 js/css 立刻生效，未改动时仍返回 304

    避免浏览器缓存旧版 ES Module 导致「改了代码但页面还是旧行为 / 报函数未定义」。
    """
    resp = await call_next(request)
    if request.url.path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/")
async def root():
    return {
        "name": "CodeMentor",
        "version": "1.0.0",
        "docs": "/docs",
        "frontend": "/static/index.html",
    }


@app.get("/health")
async def health():
    """健康检查（含运行指标摘要，无需鉴权，供探活）"""
    snap = metrics.snapshot()
    return {
        "status": "ok",
        "uptime_seconds": snap["uptime_seconds"],
        "total_requests": snap["total_requests"],
        "error_rate": snap["error_rate"],
    }


if __name__ == "__main__":
    import uvicorn
    cfg = get_settings()
    uvicorn.run(
        "app.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=False,
        log_level="info",
    )
