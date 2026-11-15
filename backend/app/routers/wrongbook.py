"""错题本路由（DEPRECATED — 未注册）。

个人错题本已迁移到浏览器本地；教师不可读取。
"""
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
    """记录错题（兼容旧接口，不更新 BKT）"""
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


@router.get("/retry/{student_id}")
async def retry_questions(student_id: str, limit: int = 10):
    """错题重做：返回该学生的错题列表（按知识点去重，取最新一道）"""
    wb = get_wrongbook()
    return {"questions": wb.get_retry_questions(student_id, limit)}


@router.get("/counts/{student_id}")
async def wrong_counts(student_id: str):
    """获取该学生各知识点答错次数（学情推荐权重用）"""
    wb = get_wrongbook()
    return wb.get_wrong_count_by_student(student_id)


@router.delete("/clear/{student_id}")
async def clear_wrong(student_id: str):
    wb = get_wrongbook()
    wb.clear(student_id)
    return {"ok": True}
