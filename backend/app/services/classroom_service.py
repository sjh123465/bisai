"""班级与作业数据层 — 单文件 JSON + 原子写入，不引入额外依赖。

设计约束（比赛规模：一位/多位教师、几个班、几十到几百学生）：
- 所有班级/作业/提交放在 data/classroom.json；
- 写入：临时文件 -> fsync -> .bak -> os.replace，避免半截文件；
- 进程内 RLock 串行化读改写；部署使用单 Uvicorn worker；
- Pydantic 校验结构，schema_version 预留迁移；
- 日常练习数据完全在浏览器本地，不进入这个文件。
"""
import json
import os
import secrets
import shutil
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.core.logger import get_logger
from app.plugins.base import GradingContext, Question
from app.plugins.registry import get_grader
from app.services.graph_service import get_graph
from app.services.grading_service import get_grade

logger = get_logger("classroom")

_JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class ClassroomError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# ---------------- 数据模型 ----------------

class ClassRecord(BaseModel):
    id: str
    name: str
    teacher_id: str
    join_code: str
    members: list[str] = Field(default_factory=list)
    created_at: str


class AssignmentRecord(BaseModel):
    id: str
    title: str
    teacher_id: str
    class_ids: list[str]
    scenario: str = "default"
    generator: str = "llm_default@1"
    grader: str = "plan_based@1"
    questions: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["published", "closed"] = "published"
    due_at: Optional[str] = None
    created_at: str


class SubmissionRecord(BaseModel):
    assignment_id: str
    student_id: str
    answers: dict[str, Any] = Field(default_factory=dict)
    results: list[dict[str, Any]] = Field(default_factory=list)
    score: float = 0.0
    correct_count: int = 0
    total: int = 0
    late: bool = False
    submitted_at: str
    teacher_override: Optional[float] = None


class ClassroomData(BaseModel):
    schema_version: int = 1
    classes: dict[str, ClassRecord] = Field(default_factory=dict)
    assignments: dict[str, AssignmentRecord] = Field(default_factory=dict)
    submissions: dict[str, dict[str, SubmissionRecord]] = Field(default_factory=dict)


# ---------------- 工具 ----------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ClassroomError("截止时间格式不正确，需使用 ISO 时间")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _normalize_due(value: Optional[str]) -> Optional[str]:
    dt = _parse_dt(value)
    return dt.isoformat() if dt else None


def _is_late(due_at: Optional[str]) -> bool:
    due = _parse_dt(due_at)
    return bool(due and datetime.now(timezone.utc) > due)


def _make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class ClassroomStore:
    def __init__(self):
        self.cfg = get_settings()
        os.makedirs(self.cfg.data_dir, exist_ok=True)
        self.path = os.path.join(self.cfg.data_dir, "classroom.json")
        self.bak_path = self.path + ".bak"
        self._lock = threading.RLock()
        self._data = self._load()

    # ---------- 持久化 ----------
    def _load(self) -> ClassroomData:
        for path in (self.path, self.bak_path):
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                data = ClassroomData.model_validate(raw)
                if path == self.bak_path:
                    logger.warning("classroom.json 损坏，已从 .bak 恢复")
                logger.info(
                    f"🏫 班级数据加载: {len(data.classes)} 个班, "
                    f"{len(data.assignments)} 份作业"
                )
                return data
            except Exception as e:
                logger.error(f"班级数据加载失败 {path}: {e}")
        return ClassroomData()

    def _persist(self):
        """调用方必须持有 self._lock。"""
        payload = self._data.model_dump(mode="json")
        tmp = self.path + ".tmp"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(self.path):
            try:
                shutil.copy2(self.path, self.bak_path)
            except Exception as e:
                logger.warning(f"班级数据备份失败: {e}")
        os.replace(tmp, self.path)

    def _save(self):
        self._persist()

    # ---------- 班级 ----------
    def _join_code(self) -> str:
        existing = {c.join_code for c in self._data.classes.values()}
        for _ in range(40):
            code = "".join(secrets.choice(_JOIN_ALPHABET) for _ in range(6))
            if code not in existing:
                return code
        raise ClassroomError("班级邀请码生成失败，请重试", 500)

    def _get_class(self, class_id: str) -> ClassRecord:
        cls = self._data.classes.get(class_id)
        if not cls:
            raise ClassroomError("班级不存在", 404)
        return cls

    def _require_teacher_class(self, class_id: str, teacher_id: str) -> ClassRecord:
        cls = self._get_class(class_id)
        if cls.teacher_id != teacher_id:
            raise ClassroomError("无权操作该班级", 403)
        return cls

    def create_class(self, teacher_id: str, name: str) -> dict:
        name = (name or "").strip()
        if not (1 <= len(name) <= 40):
            raise ClassroomError("班级名称需为 1-40 个字符")
        with self._lock:
            cls = ClassRecord(
                id=_make_id("cls"),
                name=name,
                teacher_id=teacher_id,
                join_code=self._join_code(),
                members=[],
                created_at=_now_iso(),
            )
            self._data.classes[cls.id] = cls
            self._save()
            logger.info(f"🏫 创建班级: {name} ({cls.id}) / teacher={teacher_id}")
            return cls.model_dump(mode="json")

    def list_classes_for_teacher(self, teacher_id: str) -> list[dict]:
        with self._lock:
            out = []
            for cls in self._data.classes.values():
                if cls.teacher_id != teacher_id:
                    continue
                assignments = [
                    a for a in self._data.assignments.values()
                    if cls.id in a.class_ids and a.teacher_id == teacher_id
                ]
                out.append({
                    **cls.model_dump(mode="json"),
                    "member_count": len(cls.members),
                    "assignment_count": len(assignments),
                })
            out.sort(key=lambda c: c.get("created_at") or "", reverse=True)
            return out

    def list_classes_for_student(self, student_id: str) -> list[dict]:
        with self._lock:
            out = []
            for cls in self._data.classes.values():
                if student_id in cls.members:
                    out.append({
                        "id": cls.id,
                        "name": cls.name,
                        "teacher_id": cls.teacher_id,
                        "member_count": len(cls.members),
                        "created_at": cls.created_at,
                    })
            out.sort(key=lambda c: c.get("created_at") or "", reverse=True)
            return out

    def join_class(self, join_code: str, student_id: str) -> dict:
        code = (join_code or "").strip().upper()
        if not code:
            raise ClassroomError("请输入班级邀请码")
        with self._lock:
            cls = next((c for c in self._data.classes.values() if c.join_code == code), None)
            if not cls:
                raise ClassroomError("邀请码无效", 404)
            if student_id not in cls.members:
                cls.members.append(student_id)
                self._save()
                logger.info(f"🎓 学生加入班级: {student_id} -> {cls.id}")
            return {
                "id": cls.id,
                "name": cls.name,
                "teacher_id": cls.teacher_id,
                "member_count": len(cls.members),
            }

    def remove_member(self, class_id: str, teacher_id: str, student_id: str) -> dict:
        with self._lock:
            cls = self._require_teacher_class(class_id, teacher_id)
            if student_id in cls.members:
                cls.members.remove(student_id)
                self._save()
            return {"ok": True, "member_count": len(cls.members)}

    def get_class(self, class_id: str, user: dict) -> dict:
        with self._lock:
            cls = self._get_class(class_id)
            if user.get("role") == "teacher":
                if cls.teacher_id != user.get("username"):
                    raise ClassroomError("无权查看该班级", 403)
            elif user.get("username") not in cls.members:
                raise ClassroomError("你不在该班级中", 403)
            return cls.model_dump(mode="json")

    # ---------- 作业 ----------
    def create_assignment(
        self,
        teacher_id: str,
        title: str,
        class_ids: list[str],
        questions: list[dict],
        due_at: Optional[str] = None,
        scenario: str = "default",
        generator: str = "llm_default@1",
        grader: str = "plan_based@1",
    ) -> dict:
        title = (title or "").strip()
        if not (1 <= len(title) <= 80):
            raise ClassroomError("作业标题需为 1-80 个字符")
        class_ids = list(dict.fromkeys([str(c) for c in (class_ids or []) if c]))
        if not class_ids:
            raise ClassroomError("请至少选择一个班级")
        if not (1 <= len(questions) <= 30):
            raise ClassroomError("作业题数需在 1-30 之间")

        # 强制每条题目都可被 Pydantic 解析，且含判题方案
        validated_questions = []
        for idx, raw in enumerate(questions):
            try:
                q = Question.model_validate(raw)
            except ValidationError as e:
                raise ClassroomError(f"第 {idx + 1} 题结构不合法: {e}")
            if not q.question:
                raise ClassroomError(f"第 {idx + 1} 题缺少题干")
            validated_questions.append(q.model_dump(mode="json"))

        with self._lock:
            for cid in class_ids:
                self._require_teacher_class(cid, teacher_id)
            assignment = AssignmentRecord(
                id=_make_id("asg"),
                title=title,
                teacher_id=teacher_id,
                class_ids=class_ids,
                scenario=scenario or "default",
                generator=generator,
                grader=grader,
                questions=validated_questions,
                status="published",
                due_at=_normalize_due(due_at),
                created_at=_now_iso(),
            )
            self._data.assignments[assignment.id] = assignment
            self._save()
            logger.info(f"📝 发布作业: {title} ({assignment.id}) -> {len(class_ids)} 个班 / {len(validated_questions)} 题")
            return assignment.model_dump(mode="json")

    def _assignment_summary(self, a: AssignmentRecord, class_members: Optional[set[str]] = None) -> dict:
        submissions = self._data.submissions.get(a.id, {})
        if class_members is not None:
            submissions = {sid: s for sid, s in submissions.items() if sid in class_members}
        scores = [s.teacher_override if s.teacher_override is not None else s.score for s in submissions.values()]
        return {
            "id": a.id,
            "title": a.title,
            "class_ids": list(a.class_ids),
            "status": a.status,
            "due_at": a.due_at,
            "created_at": a.created_at,
            "question_count": len(a.questions),
            "submitted_count": len(submissions),
            "total_students": len(class_members) if class_members is not None else None,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        }

    def list_assignments_for_teacher(self, teacher_id: str, class_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            if class_id:
                cls = self._require_teacher_class(class_id, teacher_id)
                members = set(cls.members)
            else:
                members = None
            out = []
            for a in self._data.assignments.values():
                if a.teacher_id != teacher_id:
                    continue
                if class_id and class_id not in a.class_ids:
                    continue
                out.append(self._assignment_summary(a, members))
            out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            return out

    def _assignment_accessible_by_student(self, a: AssignmentRecord, student_id: str) -> list[ClassRecord]:
        classes = [
            c for c in self._data.classes.values()
            if c.id in a.class_ids and student_id in c.members
        ]
        return classes

    def get_assignment_for_teacher(self, assignment_id: str, teacher_id: str) -> dict:
        with self._lock:
            a = self._data.assignments.get(assignment_id)
            if not a:
                raise ClassroomError("作业不存在", 404)
            if a.teacher_id != teacher_id:
                raise ClassroomError("无权查看该作业", 403)
            submissions = self._data.submissions.get(a.id, {})
            classes = [self._data.classes.get(cid) for cid in a.class_ids]
            return {
                "assignment": a.model_dump(mode="json"),
                "classes": [
                    {"id": c.id, "name": c.name, "member_count": len(c.members)} for c in classes if c
                ],
                "submissions": {sid: s.model_dump(mode="json") for sid, s in submissions.items()},
                "submitted_count": len(submissions),
            }

    def close_assignment(self, assignment_id: str, teacher_id: str) -> dict:
        with self._lock:
            a = self._data.assignments.get(assignment_id)
            if not a:
                raise ClassroomError("作业不存在", 404)
            if a.teacher_id != teacher_id:
                raise ClassroomError("无权操作该作业", 403)
            a.status = "closed"
            self._save()
            return {"ok": True, "status": a.status}

    def list_assignments_for_student(self, student_id: str) -> list[dict]:
        with self._lock:
            out = []
            for a in self._data.assignments.values():
                classes = self._assignment_accessible_by_student(a, student_id)
                if not classes:
                    continue
                sub = self._data.submissions.get(a.id, {}).get(student_id)
                out.append({
                    **self._assignment_summary(a),
                    "class_names": [c.name for c in classes],
                    "my_submission": self._submission_brief(sub),
                })
            out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            return out

    def _submission_brief(self, sub: Optional[SubmissionRecord]) -> Optional[dict]:
        if not sub:
            return None
        return {
            "submitted": True,
            "score": sub.teacher_override if sub.teacher_override is not None else sub.score,
            "correct_count": sub.correct_count,
            "total": sub.total,
            "late": sub.late,
            "submitted_at": sub.submitted_at,
            "results": sub.results,
            "teacher_override": sub.teacher_override,
        }

    def get_assignment_for_student(self, assignment_id: str, student_id: str) -> dict:
        with self._lock:
            a = self._data.assignments.get(assignment_id)
            if not a:
                raise ClassroomError("作业不存在", 404)
            classes = self._assignment_accessible_by_student(a, student_id)
            if not classes:
                raise ClassroomError("你不在该作业的班级中", 403)
            public_questions = []
            for raw in a.questions:
                try:
                    public_questions.append(Question.model_validate(raw).to_public().model_dump(mode="json"))
                except ValidationError:
                    continue
            sub = self._data.submissions.get(a.id, {}).get(student_id)
            return {
                "assignment": {
                    "id": a.id,
                    "title": a.title,
                    "status": a.status,
                    "due_at": a.due_at,
                    "created_at": a.created_at,
                    "question_count": len(public_questions),
                    "class_names": [c.name for c in classes],
                },
                "questions": public_questions,
                "my_submission": self._submission_brief(sub),
            }

    def submit_assignment(self, assignment_id: str, student_id: str, answers: dict[str, Any]) -> dict:
        with self._lock:
            a = self._data.assignments.get(assignment_id)
            if not a:
                raise ClassroomError("作业不存在", 404)
            classes = self._assignment_accessible_by_student(a, student_id)
            if not classes:
                raise ClassroomError("你不在该作业的班级中", 403)
            if a.status != "published":
                raise ClassroomError("作业已关闭，无法提交", 409)
            existing = self._data.submissions.setdefault(a.id, {})
            if student_id in existing:
                raise ClassroomError("该作业已提交，不能重复提交", 409)
            if not isinstance(answers, dict):
                raise ClassroomError("answers 必须是 {题目ID: 作答} 对象")

            grader = get_grader()
            results = []
            total_score = 0.0
            correct_count = 0
            for raw in a.questions:
                try:
                    q = Question.model_validate(raw)
                except ValidationError as e:
                    raise ClassroomError(f"题目快照损坏: {e}", 500)
                raw_answer = answers.get(q.id, "")
                answer_text = "" if raw_answer is None else str(raw_answer)
                if q.type == "code":
                    gr = grader.grade(GradingContext(question=q, answer="", code=answer_text))
                else:
                    gr = grader.grade(GradingContext(question=q, answer=answer_text))
                total_score += float(gr.score or 0)
                if gr.correct:
                    correct_count += 1
                results.append({
                    "question_id": q.id,
                    "type": q.type,
                    "concept": q.concept,
                    "concept_ids": q.concept_ids or ([q.concept_id] if q.concept_id else []),
                    "correct": bool(gr.correct),
                    "score": float(gr.score or 0),
                    "passed": bool(gr.passed),
                    "needs_human_review": bool(gr.needs_human_review),
                    "feedback": gr.feedback,
                    "criteria": [c.model_dump(mode="json") for c in gr.criteria],
                    "details": gr.details,
                })

            total = len(a.questions)
            overall = round(total_score / total, 1) if total else 0.0
            record = SubmissionRecord(
                assignment_id=a.id,
                student_id=student_id,
                answers=answers,
                results=results,
                score=overall,
                correct_count=correct_count,
                total=total,
                late=_is_late(a.due_at),
                submitted_at=_now_iso(),
            )
            existing[student_id] = record
            self._save()
            logger.info(f"📥 作业提交: {a.id} / {student_id} / {overall}分")
            return {
                "assignment_id": a.id,
                "title": a.title,
                "score": overall,
                "correct_count": correct_count,
                "total": total,
                "late": record.late,
                "results": results,
                "submitted_at": record.submitted_at,
            }

    def retry_assignment_question(self, assignment_id: str, student_id: str,
                                  question_id: str, answer: str = "", code: str = "") -> dict:
        """错题重做：已提交作业的学生用服务端完整快照重新判分。

        公开题目快照不含答案/解析/判题方案；重做时不能按公开快照本地判分，
        否则单选题正确答案也会被判错。这里使用服务端冻结的完整快照判分，
        但只返回判分结果与反馈，不下发答案、解析或判题方案。
        """
        with self._lock:
            a = self._data.assignments.get(assignment_id)
            if not a:
                raise ClassroomError("作业不存在", 404)
            if not self._assignment_accessible_by_student(a, student_id):
                raise ClassroomError("你不在该作业的班级中", 403)
            sub = (self._data.submissions.get(assignment_id) or {}).get(student_id)
            if not sub:
                raise ClassroomError("请先完成并提交该作业，再进行错题重做", 409)
            raw = next((item for item in a.questions if item.get("id") == question_id), None)
            if not raw:
                raise ClassroomError("题目不存在", 404)
            try:
                q = Question.model_validate(raw)
            except ValidationError as e:
                raise ClassroomError(f"题目快照损坏: {e}", 500)

        payload = get_grade().grade(q, answer=answer or "", code=code or "")
        # details 里含有 answer_key 等内部判题信息，不能下发给学生。
        payload.pop("details", None)
        return payload

    def override_submission(
        self, assignment_id: str, student_id: str,
        teacher_id: str, score: float, feedback: str = "",
    ) -> dict:
        with self._lock:
            a = self._data.assignments.get(assignment_id)
            if not a:
                raise ClassroomError("作业不存在", 404)
            if a.teacher_id != teacher_id:
                raise ClassroomError("无权操作该作业", 403)
            sub = self._data.submissions.get(a.id, {}).get(student_id)
            if not sub:
                raise ClassroomError("该学生尚未提交", 404)
            try:
                score = float(score)
            except (TypeError, ValueError):
                raise ClassroomError("分数格式不正确")
            sub.teacher_override = max(0.0, min(100.0, score))
            if feedback:
                sub.results.append({
                    "question_id": "__teacher_feedback__",
                    "type": "feedback",
                    "feedback": str(feedback)[:1000],
                    "teacher_note": True,
                })
            self._save()
            return sub.model_dump(mode="json")

    # ---------- 班级看板（只基于作业提交） ----------
    def class_stats(self, class_id: str, teacher_id: str) -> dict:
        with self._lock:
            cls = self._require_teacher_class(class_id, teacher_id)
            members = set(cls.members)
            assignments = [
                a for a in self._data.assignments.values()
                if class_id in a.class_ids and a.teacher_id == teacher_id
            ]
            graph = get_graph()

            def name_of(cid: str) -> str:
                node = graph.get_node(cid) or {}
                return node.get("name") or cid

            concept_agg: dict[str, dict] = {}
            wrong_agg: dict[str, dict] = {}
            student_stats: dict[str, dict] = {
                sid: {
                    "student_id": sid,
                    "submitted": 0,
                    "total_assignments": len(assignments),
                    "scores": [],
                    "weak": {},
                    "wrong": 0,
                } for sid in cls.members
            }
            assignment_rows = []
            total_submissions = 0
            all_scores = []

            for a in assignments:
                subs = {
                    sid: s for sid, s in self._data.submissions.get(a.id, {}).items()
                    if sid in members
                }
                total_submissions += len(subs)
                scores = []
                for sid, sub in subs.items():
                    effective = sub.teacher_override if sub.teacher_override is not None else sub.score
                    scores.append(effective)
                    all_scores.append(effective)
                    st = student_stats.setdefault(sid, {
                        "student_id": sid, "submitted": 0, "total_assignments": len(assignments),
                        "scores": [], "weak": {}, "wrong": 0,
                    })
                    st["submitted"] += 1
                    st["scores"].append(effective)

                    for r in sub.results:
                        if r.get("teacher_note"):
                            continue
                        concept_ids = r.get("concept_ids") or []
                        cid = (concept_ids[0] if concept_ids else None) or r.get("concept")
                        if not cid:
                            continue
                        score = float(r.get("score") or 0)
                        correct = bool(r.get("correct"))
                        agg = concept_agg.setdefault(cid, {"scores": [], "count": 0, "low": 0, "correct": 0})
                        agg["scores"].append(score / 100.0)
                        agg["count"] += 1
                        agg["low"] += 1 if score < 60 else 0
                        agg["correct"] += 1 if correct else 0

                        acc = st["weak"].setdefault(cid, {"attempts": 0, "correct": 0})
                        acc["attempts"] += 1
                        acc["correct"] += 1 if correct else 0
                        if not correct:
                            st["wrong"] += 1
                            w = wrong_agg.setdefault(cid, {"count": 0, "students": set()})
                            w["count"] += 1
                            w["students"].add(sid)

                assignment_rows.append({
                    "id": a.id,
                    "title": a.title,
                    "status": a.status,
                    "due_at": a.due_at,
                    "question_count": len(a.questions),
                    "submitted_count": len(subs),
                    "total_students": len(members),
                    "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
                })

            assignment_rows.sort(key=lambda x: x.get("due_at") or "", reverse=True)

            students_out = []
            for sid, st in student_stats.items():
                weak = [
                    cid for cid, v in st["weak"].items()
                    if v["attempts"] and v["correct"] / v["attempts"] < 0.6
                ]
                avg = sum(st["scores"]) / len(st["scores"]) if st["scores"] else 0.0
                students_out.append({
                    "student_id": sid,
                    "avg_score": round(avg, 1),
                    "submitted": st["submitted"],
                    "total_assignments": st["total_assignments"],
                    "weak_count": len(weak),
                    "weak_concepts": [name_of(cid) for cid in weak[:5]],
                    "total_wrong": st["wrong"],
                    "completion": round(
                        st["submitted"] / st["total_assignments"], 3
                    ) if st["total_assignments"] else 0.0,
                })
            students_out.sort(key=lambda x: (x["avg_score"], x["submitted"]))

            heatmap = {
                name_of(cid): {
                    "avg": round(sum(v["scores"]) / len(v["scores"]), 3) if v["scores"] else 0.0,
                    "count": v["count"],
                    "low_rate": round(v["low"] / v["count"], 3) if v["count"] else 0.0,
                    "accuracy": round(v["correct"] / v["count"], 3) if v["count"] else 0.0,
                }
                for cid, v in concept_agg.items()
            }
            wrong_ranking = [
                {
                    "concept_id": cid,
                    "concept_name": name_of(cid),
                    "wrong_count": v["count"],
                    "student_count": len(v["students"]),
                }
                for cid, v in sorted(wrong_agg.items(), key=lambda kv: kv[1]["count"], reverse=True)
            ]

            total_possible = len(members) * len(assignments)
            return {
                "class": {
                    "id": cls.id,
                    "name": cls.name,
                    "join_code": cls.join_code,
                    "teacher_id": cls.teacher_id,
                },
                "class_summary": {
                    "total_students": len(cls.members),
                    "assignments_count": len(assignments),
                    "total_submissions": total_submissions,
                    "avg_score": round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
                    "completion_rate": round(total_submissions / total_possible, 3) if total_possible else 0.0,
                },
                "assignments": assignment_rows,
                "heatmap": heatmap,
                "wrong_ranking": wrong_ranking,
                "students": students_out,
            }

    # ---------- 教师报告数据（可选 LLM 输入） ----------
    def report_prompt_data(self, class_id: str, teacher_id: str) -> str:
        stats = self.class_stats(class_id, teacher_id)
        cls = stats["class"]
        summary = stats["class_summary"]
        lines = [
            f"班级：{cls['name']}；学生 {summary['total_students']} 人；作业 {summary['assignments_count']} 份；"
            f"提交 {summary['total_submissions']} 次；平均分 {summary['avg_score']}；完成率 {summary['completion_rate']:.0%}",
            "作业列表：",
        ]
        for a in stats["assignments"]:
            lines.append(
                f"- {a['title']}：提交 {a['submitted_count']}/{a['total_students']}，平均分 {a['avg_score']}"
            )
        if stats["wrong_ranking"]:
            lines.append("作业高频错误知识点：")
            for w in stats["wrong_ranking"][:8]:
                lines.append(f"- {w['concept_name']}：答错 {w['wrong_count']} 次，涉及 {w['student_count']} 人")
        else:
            lines.append("（暂无作业提交数据）")
        lines.append("请只基于以上作业数据生成班级学情报告，不要臆测日常练习。")
        return "\n".join(lines)


_store: Optional[ClassroomStore] = None


def get_classroom() -> ClassroomStore:
    global _store
    if _store is None:
        _store = ClassroomStore()
    return _store
