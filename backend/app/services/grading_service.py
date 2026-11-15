"""判题服务 — 基于出题阶段冻结的 grading_plan 做确定性判分。

不再在判题时调用 LLM：这样班级作业无需服务端 Key，评分可复现，
也不会出现同一份代码因模型波动得到不同分数的问题。
"""
from app.core.logger import get_logger
from app.plugins.base import GradingContext, Question
from app.plugins.registry import DEFAULT_GRADER_ID, get_grader
from app.services.ast_service import analyze_code, features_to_text

logger = get_logger("grade")


class GradingService:
    def __init__(self, grader_id: str = DEFAULT_GRADER_ID):
        self.grader_id = grader_id
        self.grader = get_grader(grader_id)

    def grade(self, question: Question | dict, answer: str = "", code: str = "") -> dict:
        if isinstance(question, dict):
            question = Question.model_validate(question)
        result = self.grader.grade(GradingContext(question=question, answer=answer or "", code=code or ""))
        payload = result.model_dump()
        payload["grader_id"] = self.grader.id
        payload["grader_version"] = self.grader.version

        # 兼容旧版前端/接口的 review 字段；新前端可直接使用顶层 GradeResult
        sandbox = result.details.get("sandbox")
        ast = result.details.get("ast") or {}
        ast_text = ""
        if question.type == "code":
            try:
                ast_text = features_to_text(analyze_code(code or answer or ""))
            except Exception:
                ast_text = ""
        correctness = "通过" if result.passed else ("待复核" if result.needs_human_review else "不通过")
        review = {
            "correctness": correctness,
            "correctness_score": round(result.score),
            "style_score": result.details.get("style_score"),
            "complexity_analysis": (
                f"{ast.get('estimated_complexity', '')}：{ast.get('complexity_reason', '')}".strip("：")
                if ast else ""
            ),
            "bugs": [c.note for c in result.criteria if c.score < 0.999 and c.note][:6],
            "suggestions": [],
            "encouragement": "继续保持，尝试补充边界用例验证自己的思路。" if result.passed else "先定位未通过的判题规则，再逐项修正。",
        }
        payload.update({
            "sandbox_track": sandbox,
            "ast_track": ast,
            "ast_text": ast_text,
            "review": review,
        })
        return payload

    # 旧接口兼容：没有题目快照时无法按方案判分，返回明确错误。
    def grade_code(self, code: str, test_cases: list = None, concept_id: str = None) -> dict:
        raise ValueError("判题需要题目快照（question），请使用新版 /api/exam/grade 请求体")


def get_grade(grader_id: str = DEFAULT_GRADER_ID) -> GradingService:
    return GradingService(grader_id)
