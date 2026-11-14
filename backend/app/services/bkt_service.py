"""BKT 贝叶斯知识追踪 — 极简实现
基于学生答题历史，计算每个知识点的"掌握概率"
P(掌握) = P(T) / (P(T) + P(F))，其中 T = 答对次数加权，F = 答错次数加权
简化版（比赛 Demo 足够）：
  答对一次 +0.15 掌握度，答错一次 -0.10 掌握度，初始 0.3，范围 [0, 1]
"""
import json
import os
from typing import Optional
from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger("bkt")


class BKTService:
    def __init__(self):
        self.cfg = get_settings()
        self.data_file = os.path.join(self.cfg.data_dir, "bkt_data.json")
        self._data: dict[str, dict[str, float]] = {}  # {student_id: {concept_id: mastery_score}}
        self._history: dict[str, list[dict]] = {}  # {student_id: [{concept_id, correct, timestamp}]}
        self._load()

    def _load(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self._data = d.get("mastery", {})
                self._history = d.get("history", {})
                logger.info(f"📂 BKT 数据加载完成: {len(self._data)} 个学生")
            except Exception as e:
                logger.error(f"BKT 加载失败: {e}")

    def save(self):
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump({"mastery": self._data, "history": self._history}, f, ensure_ascii=False, indent=2)

    def record_answer(self, student_id: str, concept_id: str, correct: bool):
        """记录答题，更新掌握度"""
        if student_id not in self._data:
            self._data[student_id] = {}
        if concept_id not in self._data[student_id]:
            self._data[student_id][concept_id] = 0.3  # 初始掌握度

        # 更新
        delta = 0.15 if correct else -0.10
        self._data[student_id][concept_id] = max(
            0.05, min(0.98, self._data[student_id][concept_id] + delta)
        )

        # 历史
        from datetime import datetime
        if student_id not in self._history:
            self._history[student_id] = []
        self._history[student_id].append({
            "concept_id": concept_id,
            "correct": correct,
            "time": datetime.now().isoformat(),
        })

        self.save()
        logger.info(f"BKT 更新: {student_id} / {concept_id} → {self._data[student_id][concept_id]:.2%}")

    def get_mastery(self, student_id: str) -> dict[str, float]:
        """获取学生所有知识点掌握度"""
        return self._data.get(student_id, {})

    def get_mastery_for(self, student_id: str, concept_id: str) -> float:
        return self._data.get(student_id, {}).get(concept_id, 0.3)

    def get_weak_points(self, student_id: str, threshold: float = 0.6) -> list[dict]:
        """获取薄弱知识点（掌握度低于阈值）"""
        mastery = self.get_mastery(student_id)
        weak = []
        for cid, score in sorted(mastery.items(), key=lambda x: x[1]):
            if score < threshold:
                weak.append({"concept_id": cid, "mastery": round(score, 3)})
        return weak

    def get_class_heatmap(self) -> dict:
        """全班薄弱热力图（教师端用）"""
        aggregate: dict[str, list[float]] = {}
        for sid, concepts in self._data.items():
            for cid, score in concepts.items():
                aggregate.setdefault(cid, []).append(score)
        return {
            cid: {
                "avg": sum(scores) / len(scores),
                "count": len(scores),
                "low_rate": sum(1 for s in scores if s < 0.6) / len(scores),
            }
            for cid, scores in aggregate.items()
        }


_bkt = None

def get_bkt() -> BKTService:
    global _bkt
    if _bkt is None:
        _bkt = BKTService()
    return _bkt
