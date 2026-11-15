"""出题与批改路由"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.core.llm_config import LLMConfig, require_llm_config
from app.services.exam_service import get_exam
from app.services.grading_service import get_grade

router = APIRouter(prefix="/api/exam", tags=["出题批改"])


class GenerateRequest(BaseModel):
    concept: str
    qtype: str = "any"  # choice / judge / code / any
    difficulty: str = "medium"  # easy / medium / hard
    # 最近用过的切入角度（浏览器本地维护的轻量指纹），用于连续出题时轮换
    avoid_variants: Optional[List[str]] = None


class PaperRequest(BaseModel):
    concepts: Optional[List[str]] = None
    count: int = 5
    qtypes: Optional[List[str]] = None


class GradeRequest(BaseModel):
    # 个人练习是浏览器本地数据，判题时把题目快照（含 grading_plan）随请求发来；
    # 班级作业则由服务端从快照读取，不经过这个接口。
    question: dict
    answer: Optional[str] = None
    code: Optional[str] = None


@router.post("/generate")
async def generate_question(req: GenerateRequest, config: LLMConfig = Depends(require_llm_config)):
    exam = get_exam(config)
    return await exam.generate_question(req.concept, req.qtype, req.difficulty,
                                        avoid_variants=req.avoid_variants)


@router.post("/paper")
async def generate_paper(req: PaperRequest, config: LLMConfig = Depends(require_llm_config)):
    """生成一份试卷（多道题，自动从图谱选知识点）"""
    exam = get_exam(config)
    return await exam.generate_paper(req.concepts, req.count, req.qtypes)


@router.post("/grade")
async def grade_code(req: GradeRequest):
    """按题目快照中的判题方案做确定性判分，不调用 LLM、不需要 Key。"""
    if not req.question:
        raise HTTPException(status_code=400, detail="缺少题目快照 question")
    grade = get_grade()
    try:
        return grade.grade(req.question, answer=req.answer or "", code=req.code or "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"判题失败: {e}")
