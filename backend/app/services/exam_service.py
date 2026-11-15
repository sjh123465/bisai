"""AI 智能出题服务 — 出题 + 判题方案。

流程：
1. LLM 生成题目，并在同一个响应里生成一份 grading_plan；
2. 服务端规范化题目与判题方案（缺失/非法时用确定性默认方案兜底）；
3. 之后判分只依赖快照中的 grading_plan，不再调用 LLM。

这样既满足“LLM 先针对题目生成判题方案”，又保证无服务端 Key 时班级作业
仍然可以随时、可复现地判分。
"""
import asyncio
import json
import random
import re
import uuid
from typing import Optional

from pydantic import ValidationError

from app.core.llm_config import LLMConfig
from app.core.logger import get_logger
from app.plugins.base import GradingPlan, Question
from app.plugins.graders.plan_based import build_default_plan
from app.plugins.registry import DEFAULT_GENERATOR_ID
from app.services.graph_service import get_graph
from app.services.llm_service import LLMService

logger = get_logger("exam")

GENERATOR_VERSION = "1"

# 同一知识点重复出题时，随机挑两个角度，避免每次都落在同一个“经典例题”上。
VARIATION_ANGLES = [
    "概念辨析：区分相近或易混淆的概念",
    "代码输出：给出一小段代码，判断运行结果",
    "复杂度分析：分析时间/空间复杂度或最坏情况",
    "边界条件：空输入、单元素、重复元素等特殊输入",
    "实际应用：把知识点放进一个具体场景",
    "易错陷阱：用常见误解作为干扰项",
    "对比区分：比较两种做法或两个知识点的差异",
    "执行过程：考察算法/数据结构某一步的中间状态",
]

QUESTION_PROMPT = """你是资深计算机出题专家。请严格按照给定知识点和前置知识生成一道题目，并同时生成一份**可执行的判题方案**。

知识点：{concept}
知识点说明：{concept_desc}
前置知识点：{prerequisites}
题型与难度要求：{qtype_hint}
本次建议切入角度：{variation}
{avoid_text}

输出必须是严格 JSON（不要任何多余文字、不要 markdown 代码块），字段如下：

选择题：
{{"type":"choice","question":"题干",
  "options":["A. ...","B. ...","C. ...","D. ..."],
  "answer":"B","explanation":"为什么选B",
  "grading_plan":{{"version":1,"method":"objective","answer_key":"B",
    "accepted_answers":["B","B. ..."],"pass_threshold":0.6,
    "criteria":[{{"id":"correctness","description":"答案是否匹配标准答案",
      "weight":1.0,"kind":"answer","params":{{}},"auto":true}}]}}}}

判断题：
{{"type":"judge","question":"题干","answer":true,"explanation":"...",
  "grading_plan":{{"version":1,"method":"objective","answer_key":true,
    "accepted_answers":["正确","true"],"pass_threshold":0.6,
    "criteria":[{{"id":"correctness","description":"答案是否匹配标准答案",
      "weight":1.0,"kind":"answer","params":{{}},"auto":true}}]}}}}

编程题（仅当题型要求为编程题时）：
{{"type":"code","question":"题目描述","function_name":"solve",
  "input_desc":"输入格式说明","output_desc":"输出格式说明",
  "test_cases":[{{"input":"1 2 3","expected":"[1, 2, 3]"}},
                {{"input":"3 1 2","expected":"[1, 2, 3]"}}],
  "hint":"解题思路提示","complexity":"预期复杂度",
  "grading_plan":{{"version":1,"method":"test_cases","answer_key":null,
    "accepted_answers":[],"pass_threshold":0.6,
    "criteria":[
      {{"id":"tests_pass","description":"通过测试用例的比例",
        "weight":0.8,"kind":"tests_pass","params":{{}},"auto":true}},
      {{"id":"no_infinite_loop","description":"未检测到明显死循环",
        "weight":0.1,"kind":"no_infinite_loop","params":{{}},"auto":true}},
      {{"id":"pep8","description":"基础代码风格",
        "weight":0.1,"kind":"pep8","params":{{}},"auto":true}}
    ]}}}}

判题方案约束：
1. grading_plan 必须可被确定性执行，不能依赖 LLM 二次判断；
2. 可用 kind：answer、tests_pass、no_infinite_loop、max_loop_depth、has_recursion、
   required_keywords、forbidden_keywords、pep8、manual；
3. 编程题应包含 tests_pass 规则，并给测试用例覆盖边界；
4. 选择题的 accepted_answers 要同时覆盖选项字母和完整选项文本；
5. 题目难度必须严格符合上方的难度要求；
6. 请优先从「本次建议切入角度」中选择一个最贴合题型的角度命题，不要每次都使用最常见的例题问法；
7. 同一知识点重复出题时，题干、选项与考查角度必须有明显差异，禁止照搬常见例题。
"""


class ExamService:
    def __init__(self, config: LLMConfig):
        self.llm = LLMService(config)
        self.graph = get_graph()

    async def generate_question(self, concept: str, qtype: str = "any", difficulty: str = "medium",
                                avoid_variants: Optional[list[str]] = None):
        """生成一道题，并附带判题方案。

        avoid_variants 是前端最近用过的切入角度（轻量指纹，不是完整题干）。
        用它做轮换，既避免同一知识点反复出“经典例题”，又不会让 Prompt 随历史增长。
        """
        node = None
        matches = self.graph.search_nodes(concept, top_k=1)
        if matches:
            node = matches[0]
        concept_name = (node or {}).get("name", concept)
        concept_desc = (node or {}).get("description", "")
        prereq_ids = self.graph.get_upstream(node["id"]) if node else []
        prereq_names = [p.get("name", p["id"]) for p in prereq_ids[:4]] or ["无"]

        qtype_hint = {
            "choice": "请生成选择题",
            "judge": "请生成判断题",
            "code": "请生成编程题（带测试用例）",
        }.get(qtype, "请在选择题/判断题/编程题中任选一种最合适的题型")

        difficulty_hint = {
            "easy": "简单：考察概念记忆与基本用法，编程题只需实现最直接的逻辑",
            "medium": "中等：考察原理理解与常见陷阱，编程题需要处理一般情况",
            "hard": "困难：考察边界条件、复杂度权衡与易错细节，编程题必须覆盖边界用例",
        }.get(difficulty, "中等：考察原理理解与常见陷阱")

        # 只传最近用过的角度标签；优先从没用过的角度里随机挑两个。
        recent_keys = {
            str(item).split("：", 1)[0].strip()
            for item in (avoid_variants or [])
            if str(item).strip()
        }
        candidates = [
            angle for angle in VARIATION_ANGLES
            if angle.split("：", 1)[0] not in recent_keys
        ]
        if len(candidates) < 2:
            candidates = VARIATION_ANGLES
        angles = random.sample(candidates, k=2)
        angle_keys = [angle.split("：", 1)[0] for angle in angles]
        avoid_text = ""
        if recent_keys:
            avoid_text = "最近已经使用过这些切入角度，请尽量避开：" + "、".join(sorted(recent_keys))

        prompt = QUESTION_PROMPT.format(
            concept=concept_name,
            concept_desc=concept_desc or "无",
            prerequisites="、".join(prereq_names),
            qtype_hint=f"{qtype_hint}（难度：{difficulty_hint}）",
            variation="、".join(angles),
            avoid_text=avoid_text,
        )

        messages = [
            {"role": "system", "content": "你是严格的 JSON 生成器，只输出合法 JSON，不要 markdown 代码块，不要解释。"},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        # JSON 出题对格式要求高；高温采样偶尔会返回不合法结构，失败时重试一次。
        for attempt in range(2):
            try:
                resp = await self.llm.chat(messages, temperature=1.0)
                raw_text = resp["choices"][0]["message"]["content"]
                raw = _extract_json(raw_text)
                question = _normalize_question(
                    raw, concept_name, node["id"] if node else concept, difficulty
                )
                logger.info(
                    f"📝 出题: {concept_name} / {question.type} / "
                    f"plan={question.grading_plan.method} / 角度={angle_keys}"
                )
                result = question.model_dump()
                # 把本次使用的角度指纹返回给前端轮换；不参与判分，也不含答案以外的额外信息。
                result["variation"] = angle_keys
                return result
            except Exception as e:
                last_error = e
                logger.warning(f"出题失败（第 {attempt + 1} 次）: {e}")
        logger.error(f"出题失败: {last_error}")
        return {"error": f"出题失败: {last_error}"}

    async def generate_paper(
        self,
        concepts: list[str] = None,
        count: int = 5,
        qtypes: list[str] = None,
        difficulty: str = "medium",
    ) -> dict:
        """生成一份试卷（多道题）。"""
        if not concepts:
            all_nodes = self.graph.all_nodes()
            candidates = [n for n in all_nodes if n.get("category") in ("algorithm", "structure")]
            random.shuffle(candidates)
            concepts = [n["id"] for n in candidates[:count]]

        # 尊重调用方传入的题型列表：不足时循环补齐，而不是整段丢弃
        if not qtypes:
            default_types = ["choice", "choice", "judge", "code", "code", "choice", "judge", "code"]
            qtypes = (default_types * ((count // len(default_types)) + 1))[:count]
        elif len(qtypes) < count:
            if not qtypes:
                qtypes = ["any"]
            qtypes = (qtypes * ((count // len(qtypes)) + 1))[:count]

        sem = asyncio.Semaphore(3)

        async def _bounded(concept, qtype):
            async with sem:
                return await self.generate_question(concept, qtype, difficulty)

        tasks = [_bounded(c, t) for c, t in zip(concepts[:count], qtypes[:count])]
        questions = await asyncio.gather(*tasks)
        valid = [q for q in questions if q and "error" not in q]
        logger.info(f"📄 试卷生成: 成功 {len(valid)}/{count} 题")
        return {
            "total": count,
            "generated": len(valid),
            "questions": valid,
            "concepts": concepts[:count],
            "generator": f"{DEFAULT_GENERATOR_ID}@{GENERATOR_VERSION}",
        }


# ---------------- JSON / 题目规范化 ----------------

def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取第一个 JSON 对象，兼容 ```json 包裹与前后说明文字。"""
    text = (text or "").strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        try:
            obj = json.loads(fence.group(1).strip())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    if start < 0:
        raise ValueError("LLM 未返回合法 JSON")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败: {e}")
    if not isinstance(obj, dict):
        raise ValueError("LLM 返回的 JSON 不是对象")
    return obj


_TYPE_MAP = {
    "choice": "choice", "multiple_choice": "choice", "mcq": "choice",
    "judge": "judge", "true_false": "judge", "boolean": "judge",
    "code": "code", "programming": "code", "coding": "code",
    "blank": "blank", "fill_blank": "blank",
    "short": "short", "short_answer": "short",
}


def _normalize_question(raw: dict, concept_name: str, concept_id: str, difficulty: str) -> Question:
    data = dict(raw or {})
    qtype = _TYPE_MAP.get(str(data.get("type", "")).lower(), "choice")
    data["type"] = qtype
    data["question"] = str(data.get("question") or data.get("stem") or "").strip()
    if not data["question"]:
        raise ValueError("LLM 返回的题目缺少题干")

    data["id"] = data.get("id") or f"q_{uuid.uuid4().hex[:12]}"
    data["concept"] = data.get("concept") or concept_name
    data["concept_id"] = data.get("concept_id") or concept_id
    if not data.get("concept_ids"):
        data["concept_ids"] = [data["concept_id"]] if data["concept_id"] else []
    data["difficulty"] = difficulty or data.get("difficulty") or "medium"
    data["generator_id"] = DEFAULT_GENERATOR_ID
    data["generator_version"] = GENERATOR_VERSION

    options = data.get("options") or []
    if not isinstance(options, list):
        options = [str(options)]
    data["options"] = [str(o) for o in options]

    test_cases = data.get("test_cases") or []
    normalized_cases = []
    if isinstance(test_cases, list):
        for tc in test_cases:
            if isinstance(tc, dict):
                normalized_cases.append({
                    "input": str(tc.get("input", "")),
                    "expected": str(tc.get("expected", "")),
                })
    data["test_cases"] = normalized_cases

    # 解析 LLM 生成的判题方案；失败则由默认方案兜底。
    # 注意：先把原始 grading_plan 从 data 中移除，避免非法方案阻塞题目校验。
    plan = None
    plan_raw = data.pop("grading_plan", None)
    if isinstance(plan_raw, dict):
        try:
            plan = GradingPlan.model_validate(plan_raw)
        except ValidationError as e:
            logger.warning(f"LLM 判题方案不合法，使用默认方案: {e}")

    try:
        question = Question.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"题目结构不合法: {e}")

    if plan is None or not plan.criteria:
        plan = build_default_plan(question)
    question.grading_plan = plan
    return question


def get_exam(config: LLMConfig) -> ExamService:
    return ExamService(config)
