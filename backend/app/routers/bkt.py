"""BKT 知识追踪路由"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.services.bkt_service import get_bkt

router = APIRouter(prefix="/api/bkt", tags=["学情追踪"])


class AnswerRecord(BaseModel):
    student_id: str
    concept_id: str
    correct: bool


@router.post("/record")
async def record_answer(r: AnswerRecord):
    """记录一次答题"""
    bkt = get_bkt()
    bkt.record_answer(r.student_id, r.concept_id, r.correct)
    return {"ok": True, "mastery": bkt.get_mastery_for(r.student_id, r.concept_id)}


@router.get("/history/{student_id}")
async def get_history(student_id: str, days: int = 7):
    """近 N 天答题趋势（答题数 / 正确率 / 平均掌握度），供学情进步曲线使用"""
    days = max(1, min(days, 30))
    return {"student_id": student_id, "days": days, "trend": get_bkt().get_daily_trend(student_id, days)}


@router.get("/today/{student_id}")
async def get_today(student_id: str):
    """今日练习统计（答题数 / 正确率 / 连续答对），供练一练右侧栏使用"""
    return get_bkt().get_today_stats(student_id)


@router.get("/mastery/{student_id}")
async def get_mastery(student_id: str):
    """获取学生所有知识点掌握度（concept_id 已转为中文名，供雷达图直接展示）"""
    bkt = get_bkt()
    from app.services.graph_service import get_graph
    g = get_graph()
    mastery = bkt.get_mastery(student_id)
    return {
        (g.get_node(cid) or {}).get("name", cid): score
        for cid, score in mastery.items()
    }


@router.get("/mastery-map/{student_id}")
async def get_mastery_map(student_id: str):
    """按节点 ID 返回掌握度（供图谱 hover 联动使用）"""
    return get_bkt().get_mastery(student_id)


@router.get("/weak/{student_id}")
async def get_weak_points(student_id: str, threshold: float = 0.6):
    """获取薄弱知识点"""
    bkt = get_bkt()
    return bkt.get_weak_points(student_id, threshold)


@router.get("/heatmap")
async def get_class_heatmap():
    """班级热力图"""
    bkt = get_bkt()
    return bkt.get_class_heatmap()
