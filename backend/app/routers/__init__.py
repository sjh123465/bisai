"""路由层 — 按功能模块拆分"""
from app.routers import chat, knowledge, code, classroom, exam, multimodal, auth, metrics_router, settings, plugins, analysis

# 注意：个人 BKT/错题本已迁移到浏览器本地（frontend/js/core/localStore.js），
# 旧的 teacher.py 基于服务端 BKT 的接口不再注册；教师能力统一走 classroom 路由。
routers_list = [
    chat.router,
    knowledge.router,
    code.router,
    classroom.router,
    exam.router,
    multimodal.router,
    auth.router,
    metrics_router.router,
    settings.router,
    plugins.router,
    analysis.router,
]
