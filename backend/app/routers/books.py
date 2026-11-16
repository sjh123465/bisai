"""我的书架路由 — 上传、列表、状态、删除、重建索引。"""
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

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
    return {
        "books": svc.list_books(user["username"]),
        "supported_formats": svc.supported_formats(),
        "max_mb": get_settings().book_max_mb,
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
    max_bytes = int(get_settings().book_max_mb) * 1024 * 1024
    try:
        known_size = getattr(file, "size", None)
        if known_size and int(known_size) > max_bytes:
            raise BookTooLargeError(f"文件超过 {get_settings().book_max_mb}MB 上限")
        data = await file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise BookTooLargeError(f"文件超过 {get_settings().book_max_mb}MB 上限")
        record = svc.create_book(user["username"], file.filename or "book.txt", data)
    except Exception as e:
        _raise_http(e)
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
