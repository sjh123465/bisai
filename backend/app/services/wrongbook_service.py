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
