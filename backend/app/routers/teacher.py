"""教师端路由 — 全部接口需 teacher 角色（Bearer Token）"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.security import require_role
from app.services.bkt_service import get_bkt
from app.services.graph_service import get_graph
from app.services.wrongbook_service import get_wrongbook

router = APIRouter(
    prefix="/api/teacher",
    tags=["教师端"],
    dependencies=[Depends(require_role("teacher"))],  # 整组接口需 teacher 角色
)


class LLMService:
    """延迟导入避免循环"""
    @staticmethod
    async def summarize(prompt: str) -> str:
        from app.services.llm_service import get_llm
        llm = get_llm()
        messages = [
            {"role": "system", "content": "你是资深教育数据分析专家，用简洁中文总结班级学情，突出薄弱点和改进建议。"},
            {"role": "user", "content": prompt},
        ]
        try:
            resp = await llm.chat(messages, temperature=0.3)
            return resp["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[LLM 摘要失败: {e}]"


def _build_ranking_with_names(ranking: list[dict]) -> list[dict]:
    """把知识点 ID 转成中文名称，方便展示"""
    g = get_graph()
    for item in ranking:
        node = g.get_node(item["concept_id"])
        item["concept_name"] = (node or {}).get("name", item["concept_id"])
    return ranking


@router.get("/dashboard")
async def dashboard():
    """教师端仪表盘：聚合数据（含高频错题榜）"""
    bkt = get_bkt()
    g = get_graph()
    wb = get_wrongbook()
    heatmap = bkt.get_class_heatmap()
    stats = g.get_stats()

    # 班级概览
    total_students = len(bkt._data)
    avg_mastery = 0
    total = 0
    for concept_id, info in heatmap.items():
        avg_mastery += info["avg"] * info["count"]
        total += info["count"]
    avg_mastery = avg_mastery / total if total > 0 else 0

    # 高频薄弱点（转中文名）
    def _name(cid: str) -> str:
        return (g.get_node(cid) or {}).get("name", cid)
    weak_top = sorted(heatmap.items(), key=lambda x: x[1]["avg"])[:10]
    weak_named = [{"concept_id": k, "concept_name": _name(k), **v} for k, v in weak_top]

    # 热力图转中文 key（前端直接展示）
    heatmap_named = {_name(cid): info for cid, info in heatmap.items()}

    # 高频错题榜
    wrong_ranking = _build_ranking_with_names(wb.get_wrong_ranking(top_n=10))

    return {
        "class_summary": {
            "total_students": total_students,
            "avg_mastery": round(avg_mastery, 3),
            "total_concepts_tracked": len(heatmap),
        },
        "graph_stats": stats,
        "weak_concepts": weak_named,
        "wrong_ranking": wrong_ranking,
        "heatmap": heatmap_named,
    }


@router.get("/wrong-top")
async def wrong_top(top_n: int = 10):
    """高频错题榜：按知识点聚合全班答错次数"""
    wb = get_wrongbook()
    ranking = _build_ranking_with_names(wb.get_wrong_ranking(top_n))
    return {"ranking": ranking}


@router.get("/students")
async def list_students():
    """列出所有学生及其学情概览"""
    bkt = get_bkt()
    wb = get_wrongbook()
    students = []
    for sid in bkt.get_all_students():
        mastery = bkt.get_mastery(sid)
        avg = sum(mastery.values()) / len(mastery) if mastery else 0
        weak_count = sum(1 for v in mastery.values() if v < 0.6)
        wrong_counts = wb.get_wrong_count_by_student(sid)
        total_wrong = sum(wrong_counts.values())
        students.append({
            "student_id": sid,
            "avg_mastery": round(avg, 3),
            "tracked_concepts": len(mastery),
            "weak_count": weak_count,
            "total_wrong": total_wrong,
        })
    # 按平均掌握度升序（薄弱的排前面）
    students.sort(key=lambda x: x["avg_mastery"])
    return {"students": students}


@router.get("/student/{student_id}")
async def student_detail(student_id: str):
    """单个学生学情详情（掌握度 + 错题数 + 薄弱点）"""
    bkt = get_bkt()
    wb = get_wrongbook()
    g = get_graph()
    mastery = bkt.get_mastery(student_id)
    weak = bkt.get_weak_points(student_id)
    wrong_counts = wb.get_wrong_count_by_student(student_id)

    # 把知识点 ID 转中文名（掌握度 + 薄弱点 + 错题统计统一处理）
    def _name(cid: str) -> str:
        return (g.get_node(cid) or {}).get("name", cid)

    mastery_with_names = {_name(cid): round(score, 3) for cid, score in mastery.items()}
    weak_with_names = [
        {**w, "concept_name": _name(w["concept_id"])} for w in weak
    ]
    wrong_with_names = {_name(cid): n for cid, n in wrong_counts.items()}

    return {
        "student_id": student_id,
        "mastery": mastery_with_names,
        "weak_points": weak_with_names,
        "wrong_counts": wrong_with_names,
        "total_wrong": sum(wrong_counts.values()),
    }


@router.get("/report")
async def generate_report():
    """LLM 自动生成学情报告（含 BKT 掌握度 + 高频错题）"""
    bkt = get_bkt()
    wb = get_wrongbook()
    heatmap = bkt.get_class_heatmap()

    # 构造掌握度 Prompt
    heatmap_text = "\n".join(
        f"- {cid}: 平均掌握度 {info['avg']:.1%}，{info['count']}人答题，薄弱率 {info['low_rate']:.0%}"
        for cid, info in sorted(heatmap.items(), key=lambda x: x[1]["avg"])
    )

    # 构造高频错题 Prompt
    wrong_ranking = _build_ranking_with_names(wb.get_wrong_ranking(top_n=8))
    wrong_text = "\n".join(
        f"- {item['concept_name']}（{item['concept_id']}）: 答错 {item['wrong_count']} 次，涉及 {item['student_count']} 人"
        for item in wrong_ranking
    )

    prompt = f"""以下是一个计算机专业班级的学情数据：

【知识点掌握度】
{heatmap_text or '（暂无答题数据）'}

【高频错题榜】
{wrong_text or '（暂无错题数据）'}

请生成一份学情分析报告，包括：
1. 整体情况概述
2. 前5个最薄弱知识点（必须重点讲）
3. 高频错题反映出的共性问题
4. 建议教师重点复习的内容
5. 后续教学建议

用 Markdown 格式输出，不超过 600 字。"""

    summary = await LLMService.summarize(prompt)
    return {"report": summary, "heatmap": heatmap, "wrong_ranking": wrong_ranking}
