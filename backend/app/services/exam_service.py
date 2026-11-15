"""AI 智能出题服务 — 遍历图谱前置关系生成题目
支持题型：选择题 / 判断题 / 编程题（带测试用例）
设计：先查图谱拿知识点 + 前置节点 → 把上下文喂给 LLM → 严格 JSON 输出
"""
import json
import re
from typing import Optional
from app.services.llm_service import get_llm
from app.services.graph_service import get_graph
from app.core.logger import get_logger

logger = get_logger("exam")


QUESTION_PROMPT = """你是资深计算机出题专家。请严格按照给定知识点和前置知识生成一道题目。

知识点：{concept}
知识点说明：{concept_desc}
前置知识点：{prerequisites}
题型要求：{qtype_hint}

输出必须是严格 JSON（不要任何多余文字、不要 markdown 代码块），字段如下：

选择题：
{{"type":"choice","question":"题干","options":["A. ...","B. ...","C. ...","D. ..."],"answer":"B","explanation":"为什么选B"}}

判断题：
{{"type":"judge","question":"题干","answer":true,"explanation":"..."}}

编程题（仅当题型要求为编程题时）：
{{"type":"code","question":"题目描述","function_name":"solve","input_desc":"输入格式说明","output_desc":"输出格式说明","test_cases":[{{"input":"1 2 3","expected":"[1, 2, 3]"}},{{"input":"3 1 2","expected":"[1, 2, 3]"}}],"hint":"解题思路提示","complexity":"预期复杂度"}}

约束：
1. 题目必须考察「{concept}」，难度严格符合上方题型要求中标注的难度
2. 编程题的 test_cases 用例要覆盖边界情况
3. explanation/hint 用中文，简洁
"""


class ExamService:
    def __init__(self):
        self.llm = get_llm()
        self.graph = get_graph()

    async def generate_question(self, concept: str, qtype: str = "any", difficulty: str = "medium"):
        """
        生成一道题
        concept: 知识点 ID 或名称
        qtype: choice / judge / code / any
        difficulty: easy / medium / hard
        """
        # 1. 查图谱拿节点 + 前置知识
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

        prompt = QUESTION_PROMPT.format(
            concept=concept_name,
            concept_desc=concept_desc or "无",
            prerequisites="、".join(prereq_names),
            qtype_hint=f"{qtype_hint}（难度：{difficulty_hint}）",
        )

        messages = [
            {"role": "system", "content": "你是严格的 JSON 生成器，只输出合法 JSON，不要 markdown 代码块，不要解释。"},
            {"role": "user", "content": prompt},
        ]
        try:
            resp = await self.llm.chat(messages, temperature=0.8)
            raw = resp["choices"][0]["message"]["content"]
            # 提取 JSON（兼容 ```json ... ``` 包裹）
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                return {"error": "LLM 未返回合法 JSON", "raw": raw[:200]}
            question = json.loads(m.group(0))
            question["concept"] = concept_name
            question["concept_id"] = node["id"] if node else concept
            logger.info(f"📝 出题: {concept_name} / {question.get('type')}")
            return question
        except Exception as e:
            logger.error(f"出题失败: {e}")
            return {"error": f"出题失败: {e}"}

    async def generate_paper(self, concepts: list[str] = None, count: int = 5,
                              qtypes: list[str] = None) -> dict:
        """
        生成一份试卷（多道题）
        concepts: 知识点列表；为空则自动从图谱选取
        count: 题目数量
        qtypes: 题型分布列表，如 ["choice","choice","judge","code","code"]；为空则混合
        """
        import asyncio

        # 1. 确定知识点列表
        if not concepts:
            # 从图谱自动选取（优先 algorithm/structure 类）
            all_nodes = self.graph.all_nodes()
            candidates = [n for n in all_nodes if n.get("category") in ("algorithm", "structure")]
            # 按类别均匀选取
            import random
            random.shuffle(candidates)
            concepts = [n["id"] for n in candidates[:count]]

        # 2. 确定题型分布
        if not qtypes or len(qtypes) < count:
            default_types = ["choice", "choice", "judge", "code", "code", "choice", "judge", "code"]
            qtypes = (default_types * ((count // len(default_types)) + 1))[:count]

        # 3. 并行出题（并发限制 3，避免 LLM 限流）
        async def _gen_one(concept, qtype):
            return await self.generate_question(concept, qtype)

        sem = asyncio.Semaphore(3)
        async def _bounded(concept, qtype):
            async with sem:
                return await _gen_one(concept, qtype)

        tasks = [_bounded(c, t) for c, t in zip(concepts[:count], qtypes[:count])]
        questions = await asyncio.gather(*tasks)

        # 4. 过滤失败的题目
        valid = [q for q in questions if q and "error" not in q]
        logger.info(f"📄 试卷生成: 成功 {len(valid)}/{count} 题")
        return {
            "total": count,
            "generated": len(valid),
            "questions": valid,
            "concepts": concepts[:count],
        }


_exam = None

def get_exam() -> ExamService:
    global _exam
    if _exam is None:
        _exam = ExamService()
    return _exam
