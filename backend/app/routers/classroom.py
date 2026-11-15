"""班级 / 统一作业 / 班级看板路由。

- 教师：多班级、生成并发布统一作业、查看作业提交统计、生成班级报告；
- 学生：加入班级、查看待完成作业、提交一次、查看自己的作业结果；
- 所有个人日常练习数据都在浏览器本地，这里完全不读取。
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.llm_config import LLMConfig, require_llm_config
from app.core.logger import get_logger
from app.core.security import get_current_user, require_role
from app.services.classroom_service import ClassroomError, get_classroom
from app.services.exam_service import get_exam
from app.services.llm_service import LLMService

logger = get_logger("classroom.api")
router = APIRouter(prefix="/api", tags=["班级作业"])


class CreateClassRequest(BaseModel):
    name: str


class JoinClassRequest(BaseModel):
    join_code: str


class AssignmentGenerateRequest(BaseModel):
    title: str
    class_ids: list[str]
    concepts: Optional[list[str]] = None
    count: int = Field(5, ge=1, le=20)
    qtypes: Optional[list[str]] = None
    difficulty: str = "medium"
    due_at: Optional[str] = None
    scenario: str = "default"


class SubmitRequest(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)


class RetryRequest(BaseModel):
    question_id: str
    answer: str = ""
    code: str = ""


class OverrideRequest(BaseModel):
    score: float
    feedback: str = ""


def _raise(e: ClassroomError):
    raise HTTPException(status_code=e.status_code, detail=str(e))


# ---------------- 班级 ----------------

@router.post("/classes")
async def create_class(req: CreateClassRequest, user: dict = Depends(require_role("teacher"))):
    try:
        return get_classroom().create_class(user["username"], req.name)
    except ClassroomError as e:
        _raise(e)
    except Exception as e:
        logger.error(f"创建班级失败: {e}")
        raise HTTPException(
            status_code=500,
            detail="创建班级失败：请检查后端 data 目录是否可写，以及 classroom.json 是否损坏",
        )


@router.get("/classes")
async def list_classes(user: dict = Depends(get_current_user)):
    store = get_classroom()
    if user.get("role") == "teacher":
        return {"classes": store.list_classes_for_teacher(user["username"])}
    return {"classes": store.list_classes_for_student(user["username"])}


@router.post("/classes/join")
async def join_class(req: JoinClassRequest, user: dict = Depends(require_role("student"))):
    try:
        return get_classroom().join_class(req.join_code, user["username"])
    except ClassroomError as e:
        _raise(e)


@router.get("/classes/{class_id}")
async def get_class(class_id: str, user: dict = Depends(get_current_user)):
    try:
        return get_classroom().get_class(class_id, user)
    except ClassroomError as e:
        _raise(e)


# ---------------- 教师端 ----------------

@router.post("/teacher/assignments")
async def create_assignment(
    req: AssignmentGenerateRequest,
    user: dict = Depends(require_role("teacher")),
    config: LLMConfig = Depends(require_llm_config),
):
    """教师用自己的 Key 生成统一作业快照并发布；之后判分不再需要 Key。"""
    if not req.class_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个班级")
    difficulty = (req.difficulty or "medium").lower()
    if difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(status_code=400, detail="难度仅支持 easy/medium/hard")

    try:
        exam = get_exam(config)
        generated = await exam.generate_paper(req.concepts, req.count, req.qtypes, difficulty)
    except Exception as e:
        logger.error(f"作业生成失败: {e}")
        raise HTTPException(status_code=400, detail=f"作业生成失败: {e}")

    questions = generated.get("questions") or []
    if not questions:
        raise HTTPException(status_code=400, detail="AI 未生成有效题目，请稍后重试")

    try:
        assignment = get_classroom().create_assignment(
            teacher_id=user["username"],
            title=req.title,
            class_ids=req.class_ids,
            questions=questions,
            due_at=req.due_at,
            scenario=req.scenario,
            generator=generated.get("generator", "llm_default@1"),
            grader="plan_based@1",
        )
    except ClassroomError as e:
        _raise(e)
    return {
        "assignment": assignment,
        "generated": len(questions),
        "requested": req.count,
        "notice": (
            "作业已按统一题目快照发布。判分使用冻结的判题方案，不需要服务端 Key。"
        ),
    }


@router.get("/teacher/assignments")
async def list_teacher_assignments(
    class_id: Optional[str] = None,
    user: dict = Depends(require_role("teacher")),
):
    try:
        storage = get_classroom()
        if class_id:
            cls = storage._get_class(class_id)
            if cls.teacher_id != user["username"]:
                raise ClassroomError("无权查看该班级", 403)
        return {"assignments": storage.list_assignments_for_teacher(user["username"], class_id)}
    except ClassroomError as e:
        _raise(e)


@router.get("/teacher/assignments/{assignment_id}")
async def get_teacher_assignment(assignment_id: str, user: dict = Depends(require_role("teacher"))):
    try:
        return get_classroom().get_assignment_for_teacher(assignment_id, user["username"])
    except ClassroomError as e:
        _raise(e)


@router.post("/teacher/assignments/{assignment_id}/close")
async def close_assignment(assignment_id: str, user: dict = Depends(require_role("teacher"))):
    try:
        return get_classroom().close_assignment(assignment_id, user["username"])
    except ClassroomError as e:
        _raise(e)


@router.get("/teacher/classes/{class_id}/dashboard")
async def class_dashboard(class_id: str, user: dict = Depends(require_role("teacher"))):
    try:
        return get_classroom().class_stats(class_id, user["username"])
    except ClassroomError as e:
        _raise(e)


@router.post("/teacher/assignments/{assignment_id}/submissions/{student_id}/override")
async def override_submission(
    assignment_id: str,
    student_id: str,
    req: OverrideRequest,
    user: dict = Depends(require_role("teacher")),
):
    try:
        return get_classroom().override_submission(
            assignment_id, student_id, user["username"], req.score, req.feedback
        )
    except ClassroomError as e:
        _raise(e)


@router.get("/teacher/classes/{class_id}/report")
async def class_report(
    class_id: str,
    user: dict = Depends(require_role("teacher")),
    config: LLMConfig = Depends(require_llm_config),
):
    """基于作业数据生成班级报告；不读取任何学生日常练习。"""
    store = get_classroom()
    try:
        stats = store.class_stats(class_id, user["username"])
        prompt_data = store.report_prompt_data(class_id, user["username"])
    except ClassroomError as e:
        _raise(e)

    messages = [
        {"role": "system", "content": "你是资深教育数据分析专家。只基于提供的作业数据写简洁的中文班级学情报告，突出共性问题与教学建议，不要编造数据。"},
        {"role": "user", "content": prompt_data},
    ]
    try:
        resp = await LLMService(config).chat(messages, temperature=0.3)
        report = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"报告生成失败: {e}")
    return {"report": report or "AI 未返回有效报告。", "dashboard": stats}


# ---------------- 学生端 ----------------

@router.get("/assignments/mine")
async def my_assignments(user: dict = Depends(require_role("student"))):
    return {"assignments": get_classroom().list_assignments_for_student(user["username"])}


@router.get("/assignments/{assignment_id}")
async def get_assignment(assignment_id: str, user: dict = Depends(require_role("student"))):
    try:
        return get_classroom().get_assignment_for_student(assignment_id, user["username"])
    except ClassroomError as e:
        _raise(e)


@router.post("/assignments/{assignment_id}/submit")
async def submit_assignment(
    assignment_id: str,
    req: SubmitRequest,
    user: dict = Depends(require_role("student")),
):
    """提交后由服务端按冻结的判题方案确定性判分；不更新服务端个人学情。"""
    try:
        return get_classroom().submit_assignment(assignment_id, user["username"], req.answers)
    except ClassroomError as e:
        _raise(e)
    except Exception as e:
        logger.error(f"作业判分失败: {e}")
        raise HTTPException(status_code=400, detail=f"判分失败: {e}")


@router.post("/assignments/{assignment_id}/retry")
async def retry_assignment_question(
    assignment_id: str,
    req: RetryRequest,
    user: dict = Depends(require_role("student")),
):
    """已提交作业后的错题重做：服务端用完整快照判分，不返回答案。"""
    try:
        return get_classroom().retry_assignment_question(
            assignment_id, user["username"], req.question_id, req.answer, req.code,
        )
    except ClassroomError as e:
        _raise(e)
    except Exception as e:
        logger.error(f"错题重做判分失败: {e}")
        raise HTTPException(status_code=400, detail=f"判分失败: {e}")
