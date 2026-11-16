"""我的书架 — 用户上传电子书的解析、切片、向量化与检索。

隔离策略：
- 每个用户一个 Chroma collection：user_books_<sha1(username)[:12]>；
- 同一 collection 内用 book_id 元数据过滤，删除/检索都带 book_id；
- 原始文件与切片结果保存在 data/books/<user_key>/<book_id>/，索引 data/books/index.json；
- 书籍只对上传者可见，接口层每次校验 owner。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import chromadb

from app.core.config import get_settings
from app.core.logger import get_logger
from app.services.book_parser import (
    SUPPORTED_EXTENSIONS,
    BookParseError,
    chunk_blocks,
    parse_book,
)
from app.services.embedding_service import embed_local, embedding_signature

logger = get_logger("books")

BOOK_INDEX_VERSION = "book-v1"
INDEX_FILE = "index.json"
MAX_CHUNKS_PER_BOOK = 5000


class BookError(Exception):
    """业务错误基类。"""


class BookValidationError(BookError):
    pass


class BookTooLargeError(BookError):
    pass


class BookDuplicateError(BookError):
    def __init__(self, existing: dict):
        super().__init__(f"这本书已经上传过了：{existing.get('title', '')}")
        self.existing = existing


class BookNotFoundError(BookError):
    pass


class BookPermissionError(BookError):
    pass


class BookService:
    def __init__(self):
        self.cfg = get_settings()
        self.books_dir = Path(self.cfg.books_dir)
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.books_dir / INDEX_FILE
        self._lock = threading.RLock()
        self._ingesting: set[str] = set()
        self._books: dict[str, dict] = self._load_index()
        self.client = chromadb.PersistentClient(path=self.cfg.chroma_dir)

    # ---------------- 索引持久化 ----------------
    def _load_index(self) -> dict[str, dict]:
        if not self.index_path.exists():
            return {}
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            books = data.get("books") if isinstance(data, dict) else {}
            return {k: v for k, v in (books or {}).items() if isinstance(v, dict)}
        except Exception as e:
            logger.error(f"书架索引读取失败: {e}")
            return {}

    def _save_index_locked(self):
        data = {"version": 1, "books": self._books}
        tmp = self.index_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.index_path)

    def _update_record(self, book_id: str, **fields):
        with self._lock:
            rec = self._books.get(book_id)
            if not rec:
                return None
            rec.update(fields)
            rec["updated_at"] = _now()
            self._save_index_locked()
            return dict(rec)

    # ---------------- 用户与路径 ----------------
    @staticmethod
    def user_key(user: str) -> str:
        return hashlib.sha1(str(user or "").lower().encode("utf-8")).hexdigest()[:12]

    def collection_name(self, user: str) -> str:
        return f"user_books_{self.user_key(user)}"

    def _book_dir(self, record: dict) -> Path:
        return self.books_dir / self.user_key(record["user"]) / record["id"]

    def _original_path(self, record: dict) -> Path:
        return self._book_dir(record) / f"original{record['format']}"

    def _chunks_path(self, record: dict) -> Path:
        return self._book_dir(record) / "chunks.json"

    # ---------------- 列表 / 查询记录 ----------------
    @staticmethod
    def _public(record: dict) -> dict:
        keys = (
            "id", "title", "filename", "format", "size", "status", "progress",
            "chunk_count", "error", "created_at", "updated_at",
        )
        out = {k: record.get(k) for k in keys}
        out["format"] = str(record.get("format") or "").lstrip(".").upper()
        return out

    def list_books(self, user: str) -> list[dict]:
        with self._lock:
            rows = [dict(r) for r in self._books.values() if r.get("user") == user]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return [self._public(r) for r in rows]

    def get_book(self, user: str, book_id: str) -> dict:
        with self._lock:
            rec = self._books.get(book_id)
        if not rec:
            raise BookNotFoundError("书籍不存在")
        if rec.get("user") != user:
            raise BookPermissionError("无权访问这本书")
        return self._public(rec)

    def ready_titles(self, user: str, book_ids: list[str] | None = None) -> list[str]:
        ids = set(book_ids or [])
        with self._lock:
            rows = [dict(r) for r in self._books.values()
                    if r.get("user") == user and r.get("status") == "ready"
                    and (not ids or r.get("id") in ids)]
        rows.sort(key=lambda r: r.get("created_at", ""))
        return [r.get("title", "") for r in rows if r.get("title")]

    @staticmethod
    def supported_formats() -> list[str]:
        return sorted({label for label in SUPPORTED_EXTENSIONS.values()})

    # ---------------- 上传 ----------------
    def create_book(self, user: str, filename: str, data: bytes) -> dict:
        if not user:
            raise BookPermissionError("请先登录后再上传书籍")
        max_bytes = int(self.cfg.book_max_mb) * 1024 * 1024
        if not data:
            raise BookValidationError("文件为空")
        if len(data) > max_bytes:
            raise BookTooLargeError(f"文件超过 {self.cfg.book_max_mb}MB 上限")

        safe_name = os.path.basename(str(filename or "")).replace("\x00", "").strip()[:160]
        if not safe_name:
            safe_name = "book.txt"
        ext = Path(safe_name).suffix.lower()
        if ext == ".doc":
            raise BookValidationError("暂不支持旧版 .doc，请在 Word 中另存为 .docx 后上传")
        if ext not in SUPPORTED_EXTENSIONS:
            raise BookValidationError(
                f"暂不支持 {ext or '该'} 格式，支持: " + "、".join(SUPPORTED_EXTENSIONS)
            )

        sha = hashlib.sha256(data).hexdigest()
        with self._lock:
            for rec in self._books.values():
                if rec.get("user") == user and rec.get("sha256") == sha and rec.get("status") != "failed":
                    raise BookDuplicateError(self._public(rec))

        book_id = uuid.uuid4().hex[:16]
        title = Path(safe_name).stem.strip() or safe_name
        now = _now()
        record = {
            "id": book_id,
            "user": user,
            "title": title,
            "filename": safe_name,
            "format": ext,
            "size": len(data),
            "sha256": sha,
            "status": "pending",
            "progress": 0,
            "chunk_count": 0,
            "error": "",
            "created_at": now,
            "updated_at": now,
        }
        book_dir = self.books_dir / self.user_key(user) / book_id
        book_dir.mkdir(parents=True, exist_ok=True)
        (book_dir / f"original{ext}").write_bytes(data)

        with self._lock:
            self._books[book_id] = record
            self._save_index_locked()
        logger.info(f"📚 新书上传: {user} / {title} ({len(data)/1024/1024:.1f}MB, {ext})")
        return self._public(record)

    # ---------------- 解析 / 入库 ----------------
    async def ingest(self, book_id: str):
        with self._lock:
            rec = self._books.get(book_id)
            if not rec:
                logger.warning(f"入库失败，书籍不存在: {book_id}")
                return
            if book_id in self._ingesting:
                logger.info(f"书籍已在入库中，跳过重复任务: {book_id}")
                return
            self._ingesting.add(book_id)
            record = dict(rec)

        try:
            self._update_record(book_id, status="parsing", progress=5, error="")
            parsed = await asyncio.to_thread(
                parse_book, self._original_path(record), record["format"], record.get("title", "")
            )
            chunks = chunk_blocks(
                parsed.blocks,
                chunk_size=int(self.cfg.book_chunk_size),
                overlap=int(self.cfg.book_chunk_overlap),
                max_chunks=MAX_CHUNKS_PER_BOOK,
            )
            if not chunks:
                raise BookParseError("没有可用的文字片段")

            payload = {
                "version": 1,
                "title": parsed.title or record.get("title", ""),
                "format": parsed.format,
                "chunks": [asdict(c) for c in chunks],
            }
            chunks_path = self._chunks_path(record)
            chunks_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = chunks_path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, chunks_path)

            self._update_record(
                book_id,
                title=payload["title"] or record.get("title", ""),
                chunk_count=len(chunks),
                status="embedding",
                progress=20,
            )
            collection = self._ensure_collection(record["user"])
            try:
                await asyncio.to_thread(collection.delete, where={"book_id": book_id})
            except Exception:
                pass

            batch_size = max(1, int(self.cfg.book_embed_batch))
            total = len(chunks)
            for start in range(0, total, batch_size):
                batch = chunks[start:start + batch_size]
                texts = [c.text for c in batch]
                metas = [{
                    "book_id": book_id,
                    "title": payload["title"] or record.get("title", ""),
                    "user": record["user"],
                    "chapter": c.chapter or "",
                    "page": int(c.page or 0),
                    "kind": c.kind or "text",
                    "chunk_index": int(c.index),
                    "source": payload["title"] or record.get("title", ""),
                } for c in batch]
                ids = [f"{book_id}:{c.index}" for c in batch]
                vecs = await asyncio.to_thread(embed_local, texts, is_query=False)
                await asyncio.to_thread(
                    collection.add,
                    ids=ids,
                    documents=texts,
                    metadatas=metas,
                    embeddings=vecs,
                )
                progress = 20 + int(75 * min(total, start + len(batch)) / max(total, 1))
                self._update_record(book_id, progress=progress)

            self._update_record(book_id, status="ready", progress=100, error="")
            logger.info(f"✅ 书籍入库完成: {record['user']} / {payload['title']} ({total} 片)")
        except Exception as e:
            message = str(e) if isinstance(e, BookParseError) else f"解析/入库失败: {e}"
            logger.error(f"❌ 书籍入库失败 {book_id}: {message}")
            self._update_record(book_id, status="failed", progress=0, error=message[:500])
        finally:
            with self._lock:
                self._ingesting.discard(book_id)

    # ---------------- Chroma collection ----------------
    def _ensure_collection(self, user: str):
        name = self.collection_name(user)
        model_name, dim = embedding_signature()
        meta = {
            "hnsw:space": "cosine",
            "embedding_model": model_name,
            "embedding_dim": dim,
            "index_version": BOOK_INDEX_VERSION,
        }
        try:
            collection = self.client.get_or_create_collection(name=name, metadata=meta)
        except Exception as e:
            logger.warning(f"书籍向量库打开失败，重建: {e}")
            try:
                self.client.delete_collection(name)
            except Exception:
                pass
            return self.client.get_or_create_collection(name=name, metadata=meta)

        old = collection.metadata or {}
        old_model = str(old.get("embedding_model", ""))
        old_version = str(old.get("index_version", ""))
        try:
            old_dim = int(old.get("embedding_dim") or 0)
        except (TypeError, ValueError):
            old_dim = 0
        if old_model != model_name or old_dim != dim or old_version != BOOK_INDEX_VERSION:
            logger.warning(
                f"书籍向量库标识不匹配（{old_model or '旧索引'} {old_dim or '?'} 维 / "
                f"{old_version or '旧版本'}），清空并标记旧书待重建"
            )
            self.client.delete_collection(name)
            collection = self.client.get_or_create_collection(name=name, metadata=meta)
            with self._lock:
                for rec in self._books.values():
                    if rec.get("user") == user and rec.get("status") == "ready":
                        rec["status"] = "needs_reindex"
                        rec["progress"] = 0
                        rec["updated_at"] = _now()
                self._save_index_locked()
        return collection

    # ---------------- 检索 ----------------
    async def query(
        self,
        user: str,
        book_ids: list[str],
        query_text: str,
        top_k: int = 5,
    ) -> list[dict]:
        if not user or not book_ids:
            return []
        ids = list(dict.fromkeys(str(b) for b in book_ids if b))
        with self._lock:
            ready = {
                rec["id"] for rec in self._books.values()
                if rec.get("user") == user and rec.get("status") == "ready" and rec.get("id") in ids
            }
        ids = [b for b in ids if b in ready]
        if not ids:
            return []

        collection = self._ensure_collection(user)
        if collection.count() == 0:
            return []
        where = {"book_id": ids[0]} if len(ids) == 1 else {"book_id": {"$in": ids}}
        q_vecs = await asyncio.to_thread(embed_local, [query_text], is_query=True)
        try:
            result = await asyncio.to_thread(
                collection.query,
                query_embeddings=q_vecs,
                n_results=max(1, min(int(top_k), collection.count())),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.warning(f"书籍检索失败: {e}")
            return []

        out = []
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        ids_out = (result.get("ids") or [[]])[0]
        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) and metas[i] else {}
            dist = float(dists[i]) if i < len(dists) else 1.0
            out.append({
                "id": ids_out[i] if i < len(ids_out) else "",
                "text": doc or "",
                "metadata": meta,
                "distance": dist,
                "score": 1.0 - dist,
                "source_type": "book",
                "source_name": meta.get("title", "我的书架"),
            })
        return out

    # ---------------- 删除 / 重建 ----------------
    def delete_book(self, user: str, book_id: str) -> None:
        with self._lock:
            rec = self._books.get(book_id)
        if not rec:
            raise BookNotFoundError("书籍不存在")
        if rec.get("user") != user:
            raise BookPermissionError("无权删除这本书")

        try:
            collection = self._ensure_collection(user)
            collection.delete(where={"book_id": book_id})
        except Exception as e:
            logger.warning(f"删除书籍向量失败（继续删除文件）: {e}")
        try:
            shutil.rmtree(self._book_dir(rec), ignore_errors=True)
        except Exception:
            pass
        with self._lock:
            self._books.pop(book_id, None)
            self._save_index_locked()
        logger.info(f"🗑️ 已删除书籍: {user} / {rec.get('title')}")

    async def reindex_book(self, user: str, book_id: str) -> dict:
        with self._lock:
            rec = self._books.get(book_id)
        if not rec:
            raise BookNotFoundError("书籍不存在")
        if rec.get("user") != user:
            raise BookPermissionError("无权重建这本书")
        if rec.get("status") not in ("ready", "needs_reindex", "failed"):
            raise BookValidationError("书籍正在处理中，请稍后再试")
        with self._lock:
            if book_id in self._ingesting:
                raise BookValidationError("书籍正在处理中，请稍后再试")
            self._books[book_id]["status"] = "pending"
            self._books[book_id]["progress"] = 0
            self._books[book_id]["error"] = ""
            self._save_index_locked()
        await self.ingest(book_id)
        return self.get_book(user, book_id)


_book_service: BookService | None = None


def get_book_service() -> BookService:
    global _book_service
    if _book_service is None:
        _book_service = BookService()
    return _book_service


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
