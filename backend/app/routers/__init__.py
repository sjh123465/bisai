"""路由层 — 按功能模块拆分"""
from app.routers import chat, knowledge, code, bkt, teacher, exam, multimodal, wrongbook, auth, metrics_router

routers_list = [
    chat.router,
    knowledge.router,
    code.router,
    bkt.router,
    teacher.router,
    exam.router,
    multimodal.router,
    wrongbook.router,
    auth.router,
    metrics_router.router,
]
