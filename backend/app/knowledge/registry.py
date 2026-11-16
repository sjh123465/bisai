"""知识源注册表 — 新增知识源时只改这里 + 实现 KnowledgeSource。

当前内置：
- builtin：课程图谱 + 教材片段
- books  ：用户上传电子书

未来的 Obsidian/Notion/网页语料等，实现协议后 register_knowledge_source 即可，
Agent / 对话路由 / 前端都不需要改动。
"""
from __future__ import annotations

from typing import Callable

from app.knowledge.base import KnowledgeSource
from app.knowledge.book_source import BookKnowledgeSource
from app.knowledge.builtin_source import BuiltinKnowledgeSource
from app.core.logger import get_logger

logger = get_logger("knowledge")

BUILTIN_SOURCE_ID = "builtin"
BOOK_SOURCE_ID = "books"

_FACTORIES: dict[str, Callable[[], KnowledgeSource]] = {
    BUILTIN_SOURCE_ID: BuiltinKnowledgeSource,
    BOOK_SOURCE_ID: BookKnowledgeSource,
}
_INSTANCES: dict[str, KnowledgeSource] = {}
_DESCRIPTORS = {
    BUILTIN_SOURCE_ID: {"id": BUILTIN_SOURCE_ID, "name": "内置课程库", "kind": "builtin"},
    BOOK_SOURCE_ID: {"id": BOOK_SOURCE_ID, "name": "我的书架", "kind": "books"},
}


def register_knowledge_source(
    source_id: str,
    factory: Callable[[], KnowledgeSource],
    *,
    name: str,
    kind: str,
) -> None:
    """注册知识源插件（进程内）。"""
    if not source_id or not callable(factory):
        raise ValueError("知识源 id / factory 无效")
    _FACTORIES[source_id] = factory
    _DESCRIPTORS[source_id] = {"id": source_id, "name": name, "kind": kind}
    _INSTANCES.pop(source_id, None)
    logger.info(f"🔌 已注册知识源: {source_id} ({name})")


def get_knowledge_source(source_id: str) -> KnowledgeSource | None:
    if source_id not in _FACTORIES:
        return None
    if source_id not in _INSTANCES:
        _INSTANCES[source_id] = _FACTORIES[source_id]()
    return _INSTANCES[source_id]


def list_knowledge_sources() -> list[dict]:
    return [dict(_DESCRIPTORS[sid]) for sid in _FACTORIES]
