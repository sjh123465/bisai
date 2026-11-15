"""默认判题器：严格按照出题阶段冻结的 grading_plan 做确定性判分。

判题过程不调用 LLM，因此：
- 不依赖任何服务端 API Key；
- 同一份提交在任意时间、任意老师机器上得到同一个结果；
- 适合教师统一作业与可复现的班级统计。
"""
import re
from typing import Any

from app.core.logger import get_logger
from app.plugins.base import (
    GradeCriterionResult,
    GradeResult,
    GradingContext,
    GradingCriterion,
    GradingPlan,
    Question,
)
from app.services.ast_service import analyze_code
from app.services.sandbox_service import run_test_cases

logger = get_logger("grader.plan_based")

GRADER_ID = "plan_based"
GRADER_VERSION = "1"
GRADER_NAME = "判题方案确定性判分"


# ---------------- 答案归一化 ----------------

def _norm(value: Any) -> str:
    return re.sub(r"\s+", "", str(value if value is not None else "")).lower()


def _letter(value: Any) -> str:
    m = re.match(r"^\s*([A-Ha-h])(?:[.、:：)\s]|$)", str(value or ""))
    return m.group(1).upper() if m else ""


# 选项前缀必须带分隔符（A. / A、/ A: / A)），避免把 "B tree" 这类正文当成前缀裁掉。
_OPTION_PREFIX_RE = re.compile(r"^\s*([A-Ha-h])\s*[.、:：)]\s*")


def _option_index(value: Any, options: list[str]) -> int | None:
    """把答案解析成选项下标，兼容字母、完整文本、去前缀文本与 1-based 序号。"""
    if not options or value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value - 1 if 1 <= value <= len(options) else None

    text = str(value).strip()
    if not text:
        return None

    # 纯字母答案，例如 "B"
    if re.fullmatch(r"[A-Ha-h]", text):
        idx = ord(text.upper()) - ord("A")
        return idx if 0 <= idx < len(options) else None

    # 带前缀的选项文本，例如 "B. O(n log n)"
    m = _OPTION_PREFIX_RE.match(text)
    if m:
        idx = ord(m.group(1).upper()) - ord("A")
        if 0 <= idx < len(options):
            return idx

    # 完整选项文本 / 去掉前缀后的文本
    norm_text = _norm(text)
    stripped_text = _norm(_OPTION_PREFIX_RE.sub("", text))
    for i, opt in enumerate(options):
        opt_str = str(opt or "")
        norm_opt = _norm(opt_str)
        stripped_opt = _norm(_OPTION_PREFIX_RE.sub("", opt_str))
        if norm_text == norm_opt:
            return i
        if stripped_text and stripped_text == stripped_opt:
            return i

    # 纯数字答案按 1-based 序号处理（放在文本匹配之后，避免误伤 "2" 这种选项文本）。
    if re.fullmatch(r"\d+", text):
        idx = int(text)
        if 1 <= idx <= len(options):
            return idx - 1
    return None


_TRUE_WORDS = {"true", "1", "正确", "对", "是", "√", "yes", "t"}
_FALSE_WORDS = {"false", "0", "错误", "错", "否", "×", "no", "f"}


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _norm(value)
    if text in _TRUE_WORDS:
        return True
    if text in _FALSE_WORDS:
        return False
    return None


def _answer_matches(selected: Any, expected: Any, accepted: list[str], options: list[str] | None = None) -> bool:
    """兼容字母、完整选项文本、选项下标与判断题布尔值。"""
    if isinstance(expected, bool) or expected in (True, False):
        sel_bool = _as_bool(selected)
        if sel_bool is not None:
            return sel_bool is expected

    candidates = [expected, *accepted]

    # 核心兜底：无论选项是否有 A/B 前缀，都按「选项位置」比较一次。
    # 生成题目的选项并不保证带前缀，而 answer_key 通常只是字母。
    if options:
        sel_idx = _option_index(selected, options)
        if sel_idx is not None:
            for cand in candidates:
                if _option_index(cand, options) == sel_idx:
                    return True

    sel_text = _norm(selected)
    sel_letter = _letter(selected)
    for cand in candidates:
        if cand is None:
            continue
        if sel_text == _norm(cand):
            return True
        cand_letter = _letter(cand)
        if sel_letter and cand_letter and sel_letter == cand_letter:
            return True
        if _as_bool(cand) is not None and _as_bool(selected) is not None:
            if _as_bool(cand) is _as_bool(selected):
                return True
    return False


# ---------------- 默认判题方案 ----------------

def build_default_plan(question: Question) -> GradingPlan:
    """LLM 没有给出可用方案时的安全兜底：仍然完全确定性。"""
    if question.type in ("choice", "judge"):
        accepted: list[str] = []
        if isinstance(question.answer, bool):
            accepted = ["正确" if question.answer else "错误", "true" if question.answer else "false"]
        elif question.answer is not None:
            accepted = [str(question.answer)]
            letter = _letter(question.answer)
            if letter:
                for opt in question.options:
                    if _letter(opt) == letter:
                        accepted.append(opt)
        return GradingPlan(
            method="objective",
            answer_key=question.answer,
            accepted_answers=accepted,
            pass_threshold=0.6,
            criteria=[GradingCriterion(
                id="correctness", description="答案是否匹配标准答案", weight=1.0,
                kind="answer", params={}, auto=True,
            )],
        )

    criteria: list[GradingCriterion] = []
    if question.test_cases:
        criteria.append(GradingCriterion(
            id="tests_pass", description="通过测试用例的比例", weight=0.8,
            kind="tests_pass", auto=True,
        ))
    criteria.extend([
        GradingCriterion(id="no_infinite_loop", description="未检测到明显死循环", weight=0.1, kind="no_infinite_loop", auto=True),
        GradingCriterion(id="pep8", description="基础代码风格", weight=0.1, kind="pep8", auto=True),
    ])
    return GradingPlan(
        method="test_cases" if question.test_cases else "hybrid",
        answer_key=None,
        pass_threshold=0.6,
        criteria=criteria,
    )


# ---------------- 轻量风格检查 ----------------

def _style_issue_count(code: str) -> tuple[int, list[str]]:
    try:
        import io
        import contextlib
        import pycodestyle
        out = io.StringIO()
        checker = pycodestyle.Checker(lines=code.splitlines(keepends=True))
        with contextlib.redirect_stdout(out):
            checker.check_all()
        lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
        return len(lines), lines[:5]
    except Exception:
        issues = []
        for i, line in enumerate(code.splitlines(), 1):
            if len(line) > 79:
                issues.append(f"第 {i} 行超过 79 字符")
            if "\t" in line:
                issues.append(f"第 {i} 行使用 Tab 缩进")
            if line != line.rstrip():
                issues.append(f"第 {i} 行存在行尾空白")
        return len(issues), issues[:5]


def _eval_code_criterion(c: GradingCriterion, code: str, ast_feats, test_result: dict | None) -> tuple[float, str]:
    kind = (c.kind or "").lower()
    params = c.params or {}

    if kind == "tests_pass":
        if not test_result or not test_result.get("total"):
            if test_result and test_result.get("error"):
                return 0.0, f"测试运行失败：{test_result['error'][:100]}"
            return 0.0, "未提供测试用例"
        total = max(1, int(test_result.get("total") or 0))
        passed = int(test_result.get("passed") or 0)
        return passed / total, f"通过 {passed}/{total} 个测试用例"

    if kind == "no_infinite_loop":
        bad = bool(ast_feats.possible_infinite_loop)
        return (0.0 if bad else 1.0), (ast_feats.infinite_loop_hint or "未检测到明显死循环")

    if kind == "max_loop_depth":
        max_depth = int(params.get("max", 2))
        depth = int(ast_feats.max_loop_depth or 0)
        return (1.0 if depth <= max_depth else 0.0), f"最大循环嵌套 {depth} 层（要求 ≤ {max_depth}）"

    if kind == "has_recursion":
        expected = bool(params.get("expected", True))
        return (1.0 if ast_feats.has_recursion == expected else 0.0), (
            f"递归检测：{'有' if ast_feats.has_recursion else '无'}"
        )

    if kind in ("required_keywords", "forbidden_keywords"):
        keywords = params.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = [str(keywords)]
        if kind == "required_keywords":
            if not keywords:
                return 1.0, "未配置关键词要求"
            hit = sum(1 for k in keywords if str(k).lower() in code.lower())
            missing = [str(k) for k in keywords if str(k).lower() not in code.lower()]
            return hit / len(keywords), ("关键词全部命中" if not missing else f"缺少关键词：{', '.join(missing[:5])}")
        bad = [str(k) for k in keywords if str(k).lower() in code.lower()]
        return (0.0 if bad else 1.0), ("未使用禁用关键词" if not bad else f"使用了禁用关键词：{', '.join(bad[:5])}")

    if kind == "pep8":
        count, samples = _style_issue_count(code)
        # 1 个问题轻微扣分，5 个以上视为风格未达标
        score = max(0.0, 1.0 - min(count, 5) / 5.0)
        return score, ("基础风格检查通过" if count == 0 else f"发现 {count} 处风格问题；" + "；".join(samples[:2]))

    if kind == "manual":
        return 0.0, "该项需要教师人工复核"

    return 1.0, "未知规则，默认通过"


class PlanBasedGrader:
    id = GRADER_ID
    version = GRADER_VERSION
    name = GRADER_NAME

    def grade(self, ctx: GradingContext) -> GradeResult:
        q = ctx.question
        plan = q.grading_plan or build_default_plan(q)
        if not plan.criteria:
            plan = build_default_plan(q)

        if q.type in ("choice", "judge"):
            return self._grade_objective(q, plan, ctx.answer)
        if q.type == "code":
            return self._grade_code(q, plan, ctx.code or ctx.answer)
        return self._grade_text(q, plan, ctx.answer)

    # ---------- 客观题 ----------
    def _grade_objective(self, q: Question, plan: GradingPlan, answer: Any) -> GradeResult:
        correct = _answer_matches(
            answer,
            plan.answer_key if plan.answer_key is not None else q.answer,
            plan.accepted_answers,
            q.options,
        )
        score = 100.0 if correct else 0.0
        criterion = GradeCriterionResult(
            id="correctness",
            description="答案是否匹配标准答案",
            weight=1.0,
            score=1.0 if correct else 0.0,
            note="回答正确" if correct else "回答错误",
        )
        return GradeResult(
            correct=correct,
            score=score,
            passed=correct,
            criteria=[criterion],
            feedback="回答正确" if correct else "回答错误，建议回顾相关知识点后重试。",
            details={"selected": str(answer), "answer_key": plan.answer_key},
        )

    # ---------- 编程题 ----------
    def _grade_code(self, q: Question, plan: GradingPlan, code: str) -> GradeResult:
        code = code or ""
        ast_feats = analyze_code(code)
        test_result = None
        if q.test_cases:
            test_result = run_test_cases(
                code,
                [{"input": tc.input, "expected": tc.expected} for tc in q.test_cases],
            )

        auto_criteria = [c for c in plan.criteria if c.auto and (c.kind or "").lower() != "manual"]
        manual_criteria = [c for c in plan.criteria if not c.auto or (c.kind or "").lower() == "manual"]
        if not auto_criteria:
            plan = build_default_plan(q)
            auto_criteria = [c for c in plan.criteria if c.auto]

        results: list[GradeCriterionResult] = []
        total_weight = 0.0
        weighted = 0.0
        notes: list[str] = []
        for c in auto_criteria:
            try:
                ratio, note = _eval_code_criterion(c, code, ast_feats, test_result)
            except Exception as e:
                logger.warning(f"判题规则 {c.id} 执行失败: {e}")
                ratio, note = 0.0, f"规则执行失败：{e}"
            ratio = max(0.0, min(1.0, ratio))
            weight = max(0.0, float(c.weight or 0))
            results.append(GradeCriterionResult(
                id=c.id, description=c.description, weight=weight, score=ratio, note=note,
            ))
            if weight > 0:
                weighted += ratio * weight
                total_weight += weight
            if ratio < 0.999 and note:
                notes.append(note)

        for c in manual_criteria:
            results.append(GradeCriterionResult(
                id=c.id, description=c.description, weight=float(c.weight or 0),
                score=0.0, note="需要教师人工复核",
            ))

        raw_score = (weighted / total_weight * 100.0) if total_weight > 0 else 0.0
        score = round(max(0.0, min(100.0, raw_score)), 1)
        threshold = max(0.0, min(1.0, float(plan.pass_threshold or 0.6))) * 100
        passed = score >= threshold
        needs_human = bool(manual_criteria)
        if not code.strip():
            passed = False
            score = 0.0

        style_scores = [r.score for r in results if r.id == "pep8"]
        bugs = notes[:5]
        suggestions = []
        if ast_feats.possible_infinite_loop:
            suggestions.append("检查 while 循环的退出条件，避免死循环")
        if ast_feats.has_nested_loop:
            suggestions.append("注意嵌套循环带来的时间复杂度增长")
        if style_scores and style_scores[0] < 0.8:
            suggestions.append("根据 PEP8 建议调整缩进、行宽和空格")
        if not suggestions:
            suggestions.append("继续保持，并尝试补充边界用例验证自己的代码")

        feedback = plan.feedback_template.strip() if plan.feedback_template else ""
        if not feedback:
            feedback = (
                f"通过率 {test_result.get('passed', 0)}/{test_result.get('total', 0)}，"
                f"综合得分 {score}/100。" if test_result else f"综合得分 {score}/100。"
            )
            if notes:
                feedback += " " + "；".join(notes[:3])

        return GradeResult(
            correct=bool(passed and not needs_human),
            score=score,
            passed=bool(passed),
            criteria=results,
            feedback=feedback,
            needs_human_review=needs_human,
            details={
                "sandbox": test_result,
                "ast": ast_feats.__dict__,
                "style_score": round(style_scores[0] * 100, 1) if style_scores else None,
                "manual_review": needs_human,
            },
        )

    # ---------- 主观题（预留） ----------
    def _grade_text(self, q: Question, plan: GradingPlan, answer: str) -> GradeResult:
        criteria = plan.criteria or [GradingCriterion(id="manual", description="主观题需人工或后续 LLM 插件复核", kind="manual", auto=False)]
        results = []
        total_weight = 0.0
        weighted = 0.0
        for c in criteria:
            ratio, note = _eval_code_criterion(c, answer or "", analyze_code(""), None)
            weight = max(0.0, float(c.weight or 0))
            results.append(GradeCriterionResult(id=c.id, description=c.description, weight=weight, score=ratio, note=note))
            if c.auto:
                weighted += ratio * weight
                total_weight += weight
        score = round(weighted / total_weight * 100, 1) if total_weight else 0.0
        needs_human = any(not c.auto for c in criteria)
        result = GradeResult(
            correct=False, score=score, passed=False, criteria=results,
            feedback="主观题自动判分能力有限，已标记为待教师复核。" if needs_human else f"综合得分 {score}/100。",
            needs_human_review=needs_human,
        )
        return result
