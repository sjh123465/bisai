"""双轨批改服务 — 沙箱测试轨 + AST 分析轨 → LLM 结构化评语
坚决不让大模型算复杂度，只让大模型解释由测试用例 + AST 特征体现出的问题
"""
import json
import re
from app.services.sandbox_service import run_test_cases
from app.services.ast_service import analyze_code, features_to_text
from app.services.llm_service import get_llm
from app.core.logger import get_logger

logger = get_logger("grade")


GRADING_PROMPT = """你是资深软件架构师 + 教学顾问。下面是学生提交的代码，以及两条批改轨的结果。请给出结构化评语。

【学生代码】
```python
{code}
```

【沙箱轨 - 测试用例执行结果】
通过率: {passed}/{total}
{test_details}

【AST 轨 - 静态代码特征】
{ast_features}

请严格输出 JSON（不要 markdown 代码块，不要多余文字）：
{{
  "correctness": "通过/部分通过/不通过",
  "correctness_score": 0-100,
  "style_score": 0-100,
  "complexity_analysis": "基于AST特征的复杂度分析（例如：嵌套循环深度N，存在递归...）",
  "bugs": ["问题1","问题2"],
  "suggestions": ["建议1","建议2"],
  "encouragement": "一句鼓励性反馈"
}}

注意：复杂度分析必须基于上面的 AST 特征，不要凭空猜测。
"""


class GradingService:
    def __init__(self):
        self.llm = get_llm()

    async def grade_code(self, code: str, test_cases: list = None, concept_id: str = None):
        """
        双轨批改：
        1. 沙箱轨：跑测试用例 → 通过率
        2. AST 轨：静态分析 → 特征
        3. LLM：解释 + 结构化评分
        """
        # AST 轨（始终执行）
        ast_feats = analyze_code(code)
        ast_text = features_to_text(ast_feats)

        # 沙箱轨（有测试用例才跑）
        test_result = None
        if test_cases:
            test_result = run_test_cases(code, test_cases)

        # 组装提示词
        if test_result:
            passed = test_result["passed"]
            total = test_result["total"]
            details_lines = []
            for d in test_result.get("details", []):
                mark = "✅" if d["passed"] else "❌"
                details_lines.append(f"{mark} 用例{d['case']}: 输入={d['input']!r} 期望={d['expected']!r} 实际={d['actual']!r}" + (f" 错误={d['error'][:80]}" if d.get('error') else ""))
            test_details = "\n".join(details_lines)
        else:
            passed, total = 0, 0
            test_details = "（未提供测试用例，未执行沙箱轨）"

        prompt = GRADING_PROMPT.format(
            code=code,
            passed=passed,
            total=total,
            test_details=test_details,
            ast_features=ast_text,
        )

        messages = [
            {"role": "system", "content": "你是严格的 JSON 生成器，只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ]
        try:
            resp = await self.llm.chat(messages, temperature=0.3)
            raw = resp["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            review = json.loads(m.group(0)) if m else {"error": "LLM 未返回合法 JSON", "raw": raw[:300]}
        except Exception as e:
            logger.error(f"批改 LLM 调用失败: {e}")
            review = {"error": f"LLM 调用失败: {e}"}

        return {
            "sandbox_track": test_result,
            "ast_track": ast_feats.__dict__,
            "ast_text": ast_text,
            "review": review,
        }


_grade = None

def get_grade() -> GradingService:
    global _grade
    if _grade is None:
        _grade = GradingService()
    return _grade
