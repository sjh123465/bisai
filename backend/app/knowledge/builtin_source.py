"""内置课程知识源 — 现有 GraphRAG（86 节点图谱 + 14 篇教材片段）。"""
from __future__ import annotations

from typing import Optional

from app.knowledge.base import KnowledgeChunk, KnowledgeResult
from app.services.graphrag_service import get_graphrag


class BuiltinKnowledgeSource:
    id = "builtin"
    name = "内置课程库"
    kind = "builtin"

    def __init__(self):
        self.graphrag = get_graphrag()

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        config=None,
        user_id: Optional[str] = None,
        book_ids: Optional[list[str]] = None,
    ) -> KnowledgeResult:
        data = await self.graphrag.retrieve(query, vector_top_k=top_k, config=config)
        chunks = []
        for item in data.get("vector_chunks", []):
            meta = item.get("metadata") or {}
            chunks.append(KnowledgeChunk(
                text=item.get("text", ""),
                score=1.0 - float(item.get("distance", 1.0)),
                source_type="builtin",
                source_name=str(meta.get("source") or "内置课程"),
                metadata=meta,
                chunk_id=str(item.get("id") or ""),
            ))
        return KnowledgeResult(
            chunks=chunks,
            graph_nodes=data.get("graph_nodes", []),
            graph_upstream=data.get("graph_upstream", {}),
            graph_downstream=data.get("graph_downstream", {}),
        )
