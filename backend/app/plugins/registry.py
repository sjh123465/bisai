"""静态插件注册表 — 只登记服务端内置插件，不接受用户上传代码。"""
from typing import Any

DEFAULT_GENERATOR_ID = "llm_default"
DEFAULT_GRADER_ID = "plan_based"

# 面向未来插件化的元数据。当前默认出题逻辑仍由 ExamService 承载，
# 后续实现新的 QuestionGenerator 时在这里登记即可。
GENERATOR_PLUGINS: dict[str, dict[str, Any]] = {
    DEFAULT_GENERATOR_ID: {
        "id": DEFAULT_GENERATOR_ID,
        "name": "LLM 标准出题 + 判题方案",
        "version": "1",
        "description": "调用用户自己的 LLM 生成题目，同时冻结一份可执行判题方案。",
        "requires_llm": True,
    },
}

GRADER_PLUGINS: dict[str, dict[str, Any]] = {
    DEFAULT_GRADER_ID: {
        "id": DEFAULT_GRADER_ID,
        "name": "判题方案确定性判分",
        "version": "1",
        "description": "仅依据题目快照中的 grading_plan 判分，不调用 LLM。",
        "requires_llm": False,
    },
}


def get_grader(plugin_id: str = DEFAULT_GRADER_ID):
    if plugin_id == DEFAULT_GRADER_ID:
        # 延迟导入，避免 plugins/__init__ 与具体实现循环依赖
        from app.plugins.graders.plan_based import PlanBasedGrader
        return PlanBasedGrader()
    raise KeyError(f"未注册的判题插件: {plugin_id}")


def get_generator(plugin_id: str = DEFAULT_GENERATOR_ID):
    # 当前默认生成器由 ExamService 直接实现；保留入口供后续替换。
    if plugin_id == DEFAULT_GENERATOR_ID:
        return None
    raise KeyError(f"未注册的出题插件: {plugin_id}")


def list_plugins() -> dict[str, list[dict[str, Any]]]:
    return {
        "generators": list(GENERATOR_PLUGINS.values()),
        "graders": list(GRADER_PLUGINS.values()),
        "default_generator": DEFAULT_GENERATOR_ID,
        "default_grader": DEFAULT_GRADER_ID,
    }
