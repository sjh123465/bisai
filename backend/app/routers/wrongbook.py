"""错题本路由"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.services.wrongbook_service import get_wrongbook

router = APIRouter(prefix="/api/wrongbook", tags=["错题本"])


class WrongItem(BaseModel):
    student_id: str
    concept_id: str
    question: dict
    student_answer: str


class ResultRecord(BaseModel):
    """统一答题记录：答对只更 BKT，答错进错题本 + BKT"""
    student_id: str
    concept_id: str
    question: dict
    student_answer: str
    correct: bool


@router.post("/add")
async def add_wrong(item: WrongItem):
    """记录错题（兼容旧接口，自动联动 BKT 降掌握度）"""
    wb = get_wrongbook()
    wb.add(item.student_id, item.concept_id, item.question, item.student_answer)
    return {"ok": True}


@router.post("/record")
async def record_result(r: ResultRecord):
    """统一记录答题结果（推荐）：
    - correct=True  → BKT 掌握度 +0.15
    - correct=False → 加入错题本 + BKT 掌握度 -0.10
    """
    wb = get_wrongbook()
    wb.record_result(r.student_id, r.concept_id, r.question, r.student_answer, r.correct)
    return {"ok": True, "bkt_updated": True}


@router.get("/list/{student_id}")
async def list_wrong(student_id: str, concept_id: Optional[str] = None):
    wb = get_wrongbook()
    return wb.list(student_id, concept_id)


@router.delete("/clear/{student_id}")
async def clear_wrong(student_id: str):
    wb = get_wrongbook()
    wb.clear(student_id)
    return {"ok": True}
