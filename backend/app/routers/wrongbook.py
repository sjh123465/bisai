"""错题本路由"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Any
from app.services.wrongbook_service import get_wrongbook

router = APIRouter(prefix="/api/wrongbook", tags=["错题本"])


class WrongItem(BaseModel):
    student_id: str
    concept_id: str
    question: dict
    student_answer: str


@router.post("/add")
async def add_wrong(item: WrongItem):
    wb = get_wrongbook()
    wb.add(item.student_id, item.concept_id, item.question, item.student_answer)
    return {"ok": True}


@router.get("/list/{student_id}")
async def list_wrong(student_id: str, concept_id: Optional[str] = None):
    wb = get_wrongbook()
    return wb.list(student_id, concept_id)


@router.delete("/clear/{student_id}")
async def clear_wrong(student_id: str):
    wb = get_wrongbook()
    wb.clear(student_id)
    return {"ok": True}
