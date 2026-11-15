"""出题与批改路由"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from app.services.exam_service import get_exam
from app.services.grading_service import get_grade

router = APIRouter(prefix="/api/exam", tags=["出题批改"])


class GenerateRequest(BaseModel):
    concept: str
    qtype: str = "any"  # choice / judge / code / any
    difficulty: str = "medium"  # easy / medium / hard


class PaperRequest(BaseModel):
    concepts: Optional[List[str]] = None
    count: int = 5
    qtypes: Optional[List[str]] = None


class TestCase(BaseModel):
    input: str = ""
    expected: str


class GradeRequest(BaseModel):
    code: str
    test_cases: Optional[List[TestCase]] = None
    concept_id: Optional[str] = None
    question: Optional[dict] = None


@router.post("/generate")
async def generate_question(req: GenerateRequest):
    exam = get_exam()
    return await exam.generate_question(req.concept, req.qtype, req.difficulty)


@router.post("/paper")
async def generate_paper(req: PaperRequest):
    """生成一份试卷（多道题，自动从图谱选知识点）"""
    exam = get_exam()
    return await exam.generate_paper(req.concepts, req.count, req.qtypes)


@router.post("/grade")
async def grade_code(req: GradeRequest):
    grade = get_grade()
    cases = [{"input": t.input, "expected": t.expected} for t in (req.test_cases or [])]
    result = await grade.grade_code(req.code, cases or None, req.concept_id)
    return result
