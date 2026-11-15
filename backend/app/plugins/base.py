"""出题 / 判题插件的数据契约。

设计原则：
- 插件只做纯计算，返回标准化模型；不直接写数据库、不更新 BKT/错题本。
- 判题器必须能在不调用 LLM 的情况下执行；LLM 只在“出题时生成判题方案”阶段参与。
- 题目快照里保存 grading_plan，之后按方案做确定性判分，保证可复现。
"""
from typing import Any, ClassVar, Literal, Optional, Protocol

from pydantic import BaseModel, Field


class TestCase(BaseModel):
    __test__: ClassVar[bool] = False   # 避免 pytest 把数据模型当作测试类收集

    input: str = ""
    expected: str = ""


class GradingCriterion(BaseModel):
    """一条可执行的判题规则。

    kind 当前支持：
      answer / tests_pass / no_infinite_loop / max_loop_depth /
      has_recursion / required_keywords / forbidden_keywords / pep8 / manual
    """
    id: str
    description: str = ""
    weight: float = 1.0
    kind: str = "manual"
    params: dict[str, Any] = Field(default_factory=dict)
    auto: bool = True


class GradingPlan(BaseModel):
    version: int = 1
    method: str = "objective"          # objective / test_cases / hybrid / rubric
    answer_key: Any = None
    accepted_answers: list[str] = Field(default_factory=list)
    pass_threshold: float = 0.6        # 0-1；总得分 >= threshold*100 即通过
    criteria: list[GradingCriterion] = Field(default_factory=list)
    feedback_template: str = ""
    notes: str = ""


class Question(BaseModel):
    """内部完整题目，含答案、解析与判题方案；绝不能原样下发给作业学生。"""
    id: str = ""
    type: Literal["choice", "judge", "code", "blank", "short"] = "choice"
    concept: str = ""
    concept_id: str = ""
    concept_ids: list[str] = Field(default_factory=list)
    question: str = ""
    options: list[str] = Field(default_factory=list)
    answer: Any = None
    explanation: str = ""
    hint: str = ""
    test_cases: list[TestCase] = Field(default_factory=list)
    function_name: str = ""
    input_desc: str = ""
    output_desc: str = ""
    complexity: str = ""
    difficulty: str = "medium"
    grading_plan: GradingPlan = Field(default_factory=GradingPlan)
    generator_id: str = "llm_default"
    generator_version: str = "1"

    def to_public(self) -> "PublicQuestion":
        """学生作业视图：不含答案、解析、判题方案；测试用例保留输入和可见样例。"""
        return PublicQuestion(
            id=self.id,
            type=self.type,
            concept=self.concept,
            concept_ids=self.concept_ids or ([self.concept_id] if self.concept_id else []),
            question=self.question,
            options=self.options,
            hint=self.hint,
            test_cases=self.test_cases,
            function_name=self.function_name,
            input_desc=self.input_desc,
            output_desc=self.output_desc,
            difficulty=self.difficulty,
        )


class PublicQuestion(BaseModel):
    """学生可见题目（作业场景）"""
    id: str = ""
    type: Literal["choice", "judge", "code", "blank", "short"] = "choice"
    concept: str = ""
    concept_ids: list[str] = Field(default_factory=list)
    question: str = ""
    options: list[str] = Field(default_factory=list)
    hint: str = ""
    test_cases: list[TestCase] = Field(default_factory=list)
    function_name: str = ""
    input_desc: str = ""
    output_desc: str = ""
    difficulty: str = "medium"


class GradeCriterionResult(BaseModel):
    id: str
    description: str = ""
    weight: float = 1.0
    score: float = 0.0          # 0-1
    note: str = ""


class GradeResult(BaseModel):
    correct: bool = False
    score: float = 0.0          # 0-100
    passed: bool = False
    criteria: list[GradeCriterionResult] = Field(default_factory=list)
    feedback: str = ""
    needs_human_review: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class GenerationContext(BaseModel):
    concept: str = ""
    concept_id: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    qtype: str = "any"
    difficulty: str = "medium"
    profile: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class GradingContext(BaseModel):
    question: Question
    answer: str = ""
    code: str = ""


class QuestionGenerator(Protocol):
    """预留出题插件接口。当前默认实现位于 ExamService 内部。"""
    id: str
    version: str
    name: str

    async def generate(self, ctx: GenerationContext) -> list[Question]:
        ...


class GradingStrategy(Protocol):
    """预留判题插件接口。当前默认实现为 plan_based。"""
    id: str
    version: str
    name: str

    def grade(self, ctx: GradingContext) -> GradeResult:
        ...
