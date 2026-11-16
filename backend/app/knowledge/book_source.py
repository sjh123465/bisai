"""用户书架知识源 — 按用户隔离的电子书向量库。"""
from __future__ import annotations

from typing import Optional

from app.knowledge.base import KnowledgeChunk, KnowledgeResult
from app.services.book_service import get_book_service


class BookKnowledgeSource:
    id = "books"
    name = "我的书架"
    kind = "books"

    def __init__(self):
        self.books = get_book_service()

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        config=None,
        user_id: Optional[str] = None,
        book_ids: Optional[list[str]] = None,
    ) -> KnowledgeResult:
        if not user_id or not book_ids:
            return KnowledgeResult()
        rows = await self.books.query(user_id, book_ids, query, top_k=top_k)
        chunks = []
        for row in rows:
            meta = row.get("metadata") or {}
            chunks.append(KnowledgeChunk(
                text=row.get("text", ""),
                score=float(row.get("score", 0.0)),
                source_type="book",
                source_name=str(meta.get("title") or "我的书架"),
                metadata=meta,
                chunk_id=str(row.get("id") or ""),
            ))
        return KnowledgeResult(chunks=chunks)
