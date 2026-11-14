"""错题本服务 — 记录学生答错的题目，便于回顾"""
import json
import os
from datetime import datetime
from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger("wrongbook")


class WrongBookService:
    def __init__(self):
        self.cfg = get_settings()
        self.file = os.path.join(self.cfg.data_dir, "wrong_book.json")
        self._data: dict[str, list[dict]] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.file):
            try:
                with open(self.file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def add(self, student_id: str, concept_id: str, question: dict, student_answer: str, is_wrong: bool = True):
        """记录错题，同时联动 BKT 降低该知识点掌握度"""
        if not is_wrong:
            return
        item = {
            "concept_id": concept_id,
            "question": question,
            "student_answer": student_answer,
            "time": datetime.now().isoformat(),
        }
        self._data.setdefault(student_id, []).append(item)
        self._save()
        logger.info(f"📕 错题本新增: {student_id} / {concept_id}")
        # 联动 BKT：答错 → 掌握度下降
        try:
            from app.services.bkt_service import get_bkt
            get_bkt().record_answer(student_id, concept_id, correct=False)
        except Exception as e:
            logger.error(f"错题本联动 BKT 失败: {e}")

    def record_result(self, student_id: str, concept_id: str, question: dict,
                      student_answer: str, correct: bool):
        """统一记录答题结果：
        - 答对 → 仅更新 BKT 掌握度上升
        - 答错 → 加入错题本 + BKT 掌握度下降
        """
        # BKT 始终更新
        try:
            from app.services.bkt_service import get_bkt
            get_bkt().record_answer(student_id, concept_id, correct=correct)
        except Exception as e:
            logger.error(f"BKT 更新失败: {e}")
        # 答错才进错题本
        if not correct:
            self.add(student_id, concept_id, question, student_answer, is_wrong=True)

    def get_all_wrong(self) -> dict[str, list[dict]]:
        """获取所有学生的错题（教师端聚合用）"""
        return self._data

    def get_wrong_ranking(self, top_n: int = 10) -> list[dict]:
        """高频错题榜：按知识点聚合所有学生的错题，统计答错次数和涉及学生数"""
        from collections import defaultdict
        agg = defaultdict(lambda: {"count": 0, "students": set(), "questions": []})
        for sid, items in self._data.items():
            for it in items:
                cid = it.get("concept_id", "unknown")
                agg[cid]["count"] += 1
                agg[cid]["students"].add(sid)
                if len(agg[cid]["questions"]) < 2:  # 保留前2道题作为示例
                    agg[cid]["questions"].append({
                        "question": it.get("question", {}).get("question", "")[:60],
                        "time": it.get("time", ""),
                    })
        ranking = sorted(agg.items(), key=lambda x: x[1]["count"], reverse=True)[:top_n]
        return [
            {
                "concept_id": cid,
                "wrong_count": info["count"],
                "student_count": len(info["students"]),
                "sample_questions": info["questions"],
            }
            for cid, info in ranking
        ]

    def list(self, student_id: str, concept_id: str = None) -> list[dict]:
        items = self._data.get(student_id, [])
        if concept_id:
            items = [i for i in items if i["concept_id"] == concept_id]
        return items[::-1]  # 倒序

    def clear(self, student_id: str):
        self._data[student_id] = []
        self._save()


_wb = None

def get_wrongbook() -> WrongBookService:
    global _wb
    if _wb is None:
        _wb = WrongBookService()
    return _wb
