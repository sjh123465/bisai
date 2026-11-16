"""知识源插件层。"""
from app.knowledge.base import KnowledgeChunk, KnowledgeResult, KnowledgeSource
from app.knowledge.registry import (
    BOOK_SOURCE_ID,
    BUILTIN_SOURCE_ID,
    get_knowledge_source,
    list_knowledge_sources,
    register_knowledge_source,
)
from app.knowledge.router import KnowledgeRouter, get_knowledge_router

__all__ = [
    "KnowledgeChunk",
    "KnowledgeResult",
    "KnowledgeSource",
    "KnowledgeRouter",
    "get_knowledge_router",
    "get_knowledge_source",
    "list_knowledge_sources",
    "register_knowledge_source",
    "BUILTIN_SOURCE_ID",
    "BOOK_SOURCE_ID",
]
