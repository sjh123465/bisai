"""路由层 — 按功能模块拆分"""
from app.routers import chat, knowledge, code, bkt, teacher

routers_list = [
    chat.router,
    knowledge.router,
    code.router,
    bkt.router,
    teacher.router,
]
