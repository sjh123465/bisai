"""个人学情分析 — 基于浏览器本地汇总数据调用用户自己的 LLM。

隐私边界：
- 个人练习数据只保存在浏览器；
- 只有用户主动点击分析时，前端才发送聚合后的掌握度 / 趋势 / 错题计数；
- 服务端不保存请求内容，不写日志，不落盘。
"""
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.llm_config import LLMConfig, require_llm_config
from app.core.logger import get_logger
from app.services.graph_service import get_graph
from app.services.llm_service import LLMService

logger = get_logger("analysis")

router = APIRouter(prefix="/api/analysis", tags=["学情分析"])


class SeriesPoint(BaseModel):
    index: int = 0
    time: str = ""
    mastery: float = 0
    correct: Optional[bool] = None


class ConceptStat(BaseModel):
    concept_id: str
    name: str = ""
    mastery: float = 0
    attempts: int = 0
    correct: int = 0
    accuracy: Optional[float] = None
    wrong_count: int = 0
    first_time: Optional[str] = None
    last_time: Optional[str] = None
    sources: dict[str, int] = Field(default_factory=dict)
    series: list[SeriesPoint] = Field(default_factory=list)


class TrendPoint(BaseModel):
    date: str = ""
    label: str = ""
    answered: int = 0
    correct: int = 0
    accuracy: Optional[float] = None
    mastery: float = 0


class PersonalAnalysisRequest(BaseModel):
    scope: Literal["all", "personal", "assignment"] = "all"
    plugin: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    concepts: list[ConceptStat] = Field(default_factory=list, max_length=200)
    trend: list[TrendPoint] = Field(default_factory=list, max_length=60)
    selected_concept: Optional[str] = None


def _pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


def _plugin_label(plugin: dict[str, Any]) -> str:
    gen = plugin.get("generator") or {}
    grader = plugin.get("grader") or {}
    gen_name = gen.get("name") or gen.get("id") or "未知出题插件"
    grader_name = grader.get("name") or grader.get("id") or "未知判题插件"
    return f"出题：{gen_name} v{gen.get('version', '?')} · 判题：{grader_name} v{grader.get('version', '?')}"


def _scope_label(scope: str) -> str:
    return {
        "personal": "仅个人练习",
        "assignment": "仅班级作业",
        "all": "个人练习 + 班级作业",
    }.get(scope, scope)


def _safe_prereq_names(concept_id: str) -> str:
    try:
        graph = get_graph()
        ups = graph.get_upstream(concept_id)[:3]
        return "、".join((n.get("name") or n.get("id") or "") for n in ups if n)
    except Exception:
        return ""


def _concept_line(c: ConceptStat) -> str:
    name = c.name or c.concept_id
    source_parts = []
    for key, label in (("personal", "个人"), ("assignment", "作业")):
        if c.sources.get(key):
            source_parts.append(f"{label}{c.sources[key]}")
    source_text = " / ".join(source_parts) or "—"
    last = (c.last_time or "")[:10] or "—"
    prereq = _safe_prereq_names(c.concept_id)
    line = (
        f"- {name}（{c.concept_id}）：掌握度 {_pct(c.mastery)}，"
        f"练习 {c.attempts} 次，正确 {c.correct} 次（{_pct(c.accuracy)}），"
        f"错题 {c.wrong_count} 条，最近练习 {last}，来源 {source_text}"
    )
    if not c.attempts:
        line += "，暂无练习记录"
    if prereq:
        line += f"；图谱前置：{prereq}"
    return line


def build_personal_analysis_prompt(req: PersonalAnalysisRequest) -> str:
    """把浏览器本地汇总数据组装成可审计的分析 Prompt（纯函数，便于测试）。"""
    summary = req.summary or {}
    concepts = sorted(req.concepts, key=lambda c: c.mastery)
    weak = concepts[:8]
    strong = sorted(req.concepts, key=lambda c: -c.mastery)[:5]
    selected = next((c for c in req.concepts if c.concept_id == req.selected_concept), None)

    concept_lines = "\n".join(_concept_line(c) for c in concepts[:30]) or "（暂无知识点练习记录）"
    weak_lines = "\n".join(_concept_line(c) for c in weak) or "（暂无薄弱知识点数据）"
    strong_lines = "\n".join(_concept_line(c) for c in strong) or "（暂无已掌握知识点数据）"

    trend_lines = []
    for t in req.trend[-14:]:
        trend_lines.append(
            f"- {t.label or t.date}：答题 {t.answered}，正确率 {_pct(t.accuracy)}，平均掌握度 {_pct(t.mastery)}"
        )
    trend_text = "\n".join(trend_lines) or "（暂无近 30 天趋势数据）"

    selected_text = ""
    if selected:
        points = "\n".join(
            f"  - {p.time[:16].replace('T', ' ')}：掌握度 {_pct(p.mastery)}，{'答对' if p.correct else '答错'}"
            for p in selected.series[-12:]
        )
        selected_text = f"""
【当前选中知识点】
{_concept_line(selected)}
最近答题轨迹：
{points or '  - 暂无足够轨迹（答题少于 1 次）'}
"""

    return f"""以下是一名学生在本地学习系统中的学情汇总（仅用于本次分析，服务端不保存）：
【当前插件】{_plugin_label(req.plugin)}
【数据范围】{_scope_label(req.scope)}
【总体概况】
知识点 {summary.get('concepts_count', len(req.concepts))} 个，已练习 {summary.get('active_concepts', '—')} 个；
答题 {summary.get('total_attempts', 0)} 次，正确率 {_pct(summary.get('accuracy'))}；
平均掌握度 {_pct(summary.get('avg_mastery'))}，薄弱知识点 {summary.get('weak_count', '—')} 个；
连续学习 {summary.get('streak_days', '—')} 天。

【全部知识点（按掌握度升序）】
{concept_lines}

【最需要关注的知识点】
{weak_lines}

【当前掌握较好的知识点】
{strong_lines}

【近 30 天趋势】
{trend_text}
{selected_text}
请输出一份中文 Markdown 学情分析，读者是学生本人。语气冷静、具体、可执行：
1. 总体判断（2-3 句，必须基于数据，不要空泛）
2. 最需要优先补的 3 个知识点及原因（如果数据不足，请直说）
3. 已掌握较好的知识点如何巩固，避免“已经会了就不用练”的误区
4. 如果提供了「当前选中知识点」，详细解读它的掌握趋势、可能原因和下一步
5. 未来 7 天练习计划：按天或按阶段列出知识点顺序、题量、题型、复盘方式
6. 一句风险提示（例如练习样本太少、短期波动、只刷同类题等）

约束：
- 不要编造未提供的数据、题量或分数；
- 不要重复原始表格，不要罗列空话；
- 400-700 字，Markdown 小标题清晰。"""


@router.post("/personal")
async def analyze_personal(
    req: PersonalAnalysisRequest,
    config: LLMConfig = Depends(require_llm_config),
):
    """使用请求头中的用户 Key 生成个人学情分析；不落盘。"""
    prompt = build_personal_analysis_prompt(req)
    messages = [
        {
            "role": "system",
            "content": "你是资深计算机学习教练，擅长依据 BKT 掌握度与答题历史做个性化诊断。只依据用户提供的数据，不编造。",
        },
        {"role": "user", "content": prompt},
    ]
    try:
        resp = await LLMService(config).chat(messages, temperature=0.3, max_tokens=1500)
        content = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        logger.warning("个人学情分析调用失败 provider=%s", config.provider)
        raise HTTPException(status_code=400, detail=f"AI 分析失败：{e}")

    if not content or not content.strip():
        raise HTTPException(status_code=502, detail="AI 未返回有效内容，请稍后重试")
    return {
        "report": content.strip(),
        "scope": req.scope,
        "selected_concept": req.selected_concept,
        "model": config.model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
