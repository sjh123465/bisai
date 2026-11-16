"""知识源插件契约。

内置课程、用户书架都是 KnowledgeSource；后续接入 Obsidian / Notion / 网页语料时，
只需要实现同一协议并在 registry 注册，无需改动 Agent 与对话链路。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class KnowledgeChunk:
    text: str
    score: float = 0.0
    source_type: str = "builtin"       # builtin | book | future...
    source_name: str = "内置课程"
    metadata: dict = field(default_factory=dict)
    chunk_id: str = ""


@dataclass
class KnowledgeResult:
    chunks: list[KnowledgeChunk] = field(default_factory=list)
    graph_nodes: list[dict] = field(default_factory=list)
    graph_upstream: dict = field(default_factory=dict)
    graph_downstream: dict = field(default_factory=dict)


class KnowledgeSource(Protocol):
    id: str
    name: str
    kind: str

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        config=None,
        user_id: Optional[str] = None,
        book_ids: Optional[list[str]] = None,
    ) -> KnowledgeResult:
        ...
