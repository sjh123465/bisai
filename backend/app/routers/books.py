"""我的书架路由 — 上传、列表、状态、删除、重建索引。"""
import hashlib
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.security import get_current_user
from app.knowledge.registry import list_knowledge_sources
from app.services.book_service import (
    BookDuplicateError,
    BookNotFoundError,
    BookPermissionError,
    BookTooLargeError,
    BookValidationError,
    get_book_service,
)

router = APIRouter(prefix="/api/books", tags=["我的书架"])

_SPOOL_CHUNK = 1024 * 1024  # 1MB：上传分块落盘，避免大文件整体读进内存


async def _spool_upload(
    file: UploadFile,
    books_dir: Path,
    max_bytes: int,
    limit_mb: int,
) -> tuple[Path, int, str]:
    """把上传流分块写入书架临时目录，返回 (临时路径, 字节数, sha256)。"""
    upload_dir = Path(books_dir) / ".uploads"
    await run_in_threadpool(upload_dir.mkdir, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="upload-", suffix=".part", dir=str(upload_dir))
    path = Path(name)
    sha = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await file.read(_SPOOL_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise BookTooLargeError(f"文件超过 {limit_mb}MB 上限")
                sha.update(chunk)
                await run_in_threadpool(out.write, chunk)
        if total == 0:
            raise BookValidationError("文件为空")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path, total, sha.hexdigest()


def _raise_http(e: Exception):
    if isinstance(e, BookNotFoundError):
        raise HTTPException(status_code=404, detail=str(e)) from e
    if isinstance(e, BookPermissionError):
        raise HTTPException(status_code=403, detail=str(e)) from e
    if isinstance(e, BookDuplicateError):
        raise HTTPException(status_code=409, detail=str(e)) from e
    if isinstance(e, BookTooLargeError):
        raise HTTPException(status_code=413, detail=str(e)) from e
    if isinstance(e, BookValidationError):
        raise HTTPException(status_code=400, detail=str(e)) from e
    raise e


@router.get("")
async def list_books(user: dict = Depends(get_current_user)):
    svc = get_book_service()
    cfg = get_settings()
    return {
        "books": svc.list_books(user["username"]),
        "supported_formats": svc.supported_formats(),
        "max_mb": cfg.book_max_mb,
        "ocr": {
            "mode": cfg.book_ocr_mode,
            "max_pages": int(cfg.book_ocr_max_pages),
        },
        "sources": list_knowledge_sources(),
    }


@router.get("/sources")
async def available_sources(user: dict = Depends(get_current_user)):
    return {"sources": list_knowledge_sources()}


@router.post("")
async def upload_book(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    svc = get_book_service()
    cfg = get_settings()
    max_bytes = int(cfg.book_max_mb) * 1024 * 1024
    temp_path: Path | None = None
    try:
        known_size = getattr(file, "size", None)
        if known_size and int(known_size) > max_bytes:
            raise BookTooLargeError(f"文件超过 {cfg.book_max_mb}MB 上限")
        temp_path, size, sha = await _spool_upload(file, svc.books_dir, max_bytes, int(cfg.book_max_mb))
        record = svc.create_book(user["username"], file.filename or "book.txt", temp_path, size, sha)
        temp_path = None  # 已移动到书籍目录
    except Exception as e:
        _raise_http(e)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
    background.add_task(svc.ingest, record["id"])
    return {"book": record}


@router.get("/{book_id}")
async def get_book(book_id: str, user: dict = Depends(get_current_user)):
    try:
        return {"book": get_book_service().get_book(user["username"], book_id)}
    except Exception as e:
        _raise_http(e)


@router.delete("/{book_id}")
async def delete_book(book_id: str, user: dict = Depends(get_current_user)):
    try:
        get_book_service().delete_book(user["username"], book_id)
    except Exception as e:
        _raise_http(e)
    return {"ok": True}


@router.post("/{book_id}/reindex")
async def reindex_book(
    book_id: str,
    background: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    svc = get_book_service()
    try:
        book = svc.get_book(user["username"], book_id)
        if book.get("status") not in ("ready", "needs_reindex", "failed"):
            raise BookValidationError("书籍正在处理中，请稍后再试")
    except Exception as e:
        _raise_http(e)
    background.add_task(svc.reindex_book, user["username"], book_id)
    return {"book": book}
