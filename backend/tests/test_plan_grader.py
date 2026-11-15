"""判题方案 + 确定性判分测试（不依赖 LLM / API Key）"""
from app.plugins.base import (
    GradeResult,
    GradingContext,
    GradingCriterion,
    GradingPlan,
    Question,
    TestCase,
)
from app.plugins.graders.plan_based import PlanBasedGrader, build_default_plan


def _choice_question():
    return Question(
        id="q_choice",
        type="choice",
        concept="快速排序",
        concept_id="quick_sort",
        question="平均时间复杂度？",
        options=["A. O(n²)", "B. O(n log n)"],
        answer="B",
        explanation="平均 O(n log n)",
        grading_plan=GradingPlan(
            method="objective",
            answer_key="B",
            accepted_answers=["B", "B. O(n log n)"],
            criteria=[GradingCriterion(id="correctness", kind="answer", weight=1.0)],
        ),
    )


def _code_question():
    return Question(
        id="q_code",
        type="code",
        concept="数组",
        concept_id="array",
        question="输入 n，输出 2n",
        test_cases=[TestCase(input="3", expected="6"), TestCase(input="10", expected="20")],
        grading_plan=GradingPlan(
            method="test_cases",
            criteria=[
                GradingCriterion(id="tests_pass", kind="tests_pass", weight=0.8),
                GradingCriterion(id="no_infinite_loop", kind="no_infinite_loop", weight=0.1),
                GradingCriterion(id="pep8", kind="pep8", weight=0.1),
            ],
        ),
    )


def test_choice_accepts_full_option_text():
    result = PlanBasedGrader().grade(
        GradingContext(question=_choice_question(), answer="B. O(n log n)")
    )
    assert isinstance(result, GradeResult)
    assert result.correct is True
    assert result.score == 100.0


def test_choice_wrong_answer():
    result = PlanBasedGrader().grade(
        GradingContext(question=_choice_question(), answer="A. O(n²)")
    )
    assert result.correct is False
    assert result.score == 0.0


def _unprefixed_choice_question():
    """LLM 偶尔不按 A./B. 格式返回选项；此时仍应按选项位置正确判分。"""
    return Question(
        id="q_unprefixed",
        type="choice",
        concept="快速排序",
        concept_id="quick_sort",
        question="平均时间复杂度？",
        options=["O(n²)", "O(n log n)", "O(n)", "O(1)"],
        answer="B",
        grading_plan=GradingPlan(
            method="objective",
            answer_key="B",
            accepted_answers=["B"],
            criteria=[GradingCriterion(id="correctness", kind="answer", weight=1.0)],
        ),
    )


def test_choice_accepts_unprefixed_option_text_by_position():
    result = PlanBasedGrader().grade(
        GradingContext(question=_unprefixed_choice_question(), answer="O(n log n)")
    )
    assert result.correct is True
    assert result.score == 100.0


def test_choice_accepts_letter_with_unprefixed_options():
    result = PlanBasedGrader().grade(
        GradingContext(question=_unprefixed_choice_question(), answer="B")
    )
    assert result.correct is True


def test_choice_rejects_wrong_unprefixed_option():
    result = PlanBasedGrader().grade(
        GradingContext(question=_unprefixed_choice_question(), answer="O(n²)")
    )
    assert result.correct is False


def test_choice_accepts_numeric_index():
    result = PlanBasedGrader().grade(
        GradingContext(question=_unprefixed_choice_question(), answer="2")
    )
    assert result.correct is True
    result = PlanBasedGrader().grade(
        GradingContext(question=_unprefixed_choice_question(), answer="1")
    )
    assert result.correct is False


def test_code_test_cases_deterministic():
    result = PlanBasedGrader().grade(
        GradingContext(question=_code_question(), code="n = int(input())\nprint(n * 2)\n")
    )
    assert result.correct is True
    assert result.score >= 60.0
    assert result.details["sandbox"]["passed"] == 2


def test_code_infinite_loop_penalized():
    result = PlanBasedGrader().grade(
        GradingContext(question=_code_question(), code="while True:\n    pass\n")
    )
    assert result.correct is False
    assert any("死循环" in c.note for c in result.criteria if c.note)


def test_default_plan_is_derived_from_question():
    q = Question(type="choice", question="1+1?", options=["A. 1", "B. 2"], answer="B")
    plan = build_default_plan(q)
    assert plan.method == "objective"
    assert plan.answer_key == "B"
    assert plan.criteria


def test_public_question_hides_answer_and_plan():
    public = _choice_question().to_public()
    data = public.model_dump()
    assert "answer" not in data
    assert "explanation" not in data
    assert "grading_plan" not in data
    assert data["question"]
