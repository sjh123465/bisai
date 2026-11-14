"""CodeMentor 主入口 — FastAPI 应用"""
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.logger import get_logger
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
        logger.error(f"知识库初始化失败（可能是 Embedding API 未配置）: {e}")
        logger.warning("⚠️ 图谱可能为空，如需种子数据请先在 .env 填入 LLM_API_KEY")

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

# 注册路由
for r in routers_list:
    app.include_router(r)

# 静态文件（前端）
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="frontend")


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
    return {"status": "ok"}


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
