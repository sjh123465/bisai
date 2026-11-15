"""班级 / 统一作业 API 集成测试（判分不调用 LLM）"""
import json
import uuid

from app.plugins.base import GradingCriterion, GradingPlan, Question
from app.services.classroom_service import get_classroom


def _make_question():
    qid = "q_" + uuid.uuid4().hex[:8]
    return Question(
        id=qid,
        type="choice",
        concept="快速排序",
        concept_id="quick_sort",
        concept_ids=["quick_sort"],
        question="快速排序的平均时间复杂度是？",
        options=["A. O(n²)", "B. O(n log n)", "C. O(n)", "D. O(1)"],
        answer="B",
        explanation="平均 O(n log n)",
        grading_plan=GradingPlan(
            method="objective",
            answer_key="B",
            accepted_answers=["B", "B. O(n log n)"],
            criteria=[GradingCriterion(id="correctness", kind="answer", weight=1.0)],
        ),
    )


def _new_class(client, teacher_headers):
    name = "测试班-" + uuid.uuid4().hex[:6]
    r = client.post("/api/classes", headers=teacher_headers, json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()


def test_classroom_assignment_flow(client, teacher_headers, student_headers):
    cls = _new_class(client, teacher_headers)
    r = client.post("/api/classes/join", headers=student_headers, json={"join_code": cls["join_code"]})
    assert r.status_code == 200, r.text

    q = _make_question()
    title = "统一作业-" + uuid.uuid4().hex[:6]
    assignment = get_classroom().create_assignment(
        teacher_id="teacher",
        title=title,
        class_ids=[cls["id"]],
        questions=[q.model_dump(mode="json")],
    )
    aid = assignment["id"]

    # 学生列表与详情：不包含答案/解析/判题方案
    r = client.get("/api/assignments/mine", headers=student_headers)
    assert r.status_code == 200, r.text
    assert any(a["id"] == aid for a in r.json()["assignments"])

    r = client.get(f"/api/assignments/{aid}", headers=student_headers)
    assert r.status_code == 200, r.text
    public_q = r.json()["questions"][0]
    assert "answer" not in public_q
    assert "explanation" not in public_q
    assert "grading_plan" not in public_q
    assert public_q["question"]

    # 提交一次并确定性判分
    r = client.post(
        f"/api/assignments/{aid}/submit",
        headers=student_headers,
        json={"answers": {q.id: "B. O(n log n)"}},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["score"] == 100.0
    assert data["correct_count"] == 1
    assert data["results"][0]["correct"] is True

    # 不能重复提交
    r2 = client.post(
        f"/api/assignments/{aid}/submit",
        headers=student_headers,
        json={"answers": {q.id: "B"}},
    )
    assert r2.status_code == 409

    # 教师看板只基于作业提交
    r = client.get(f"/api/teacher/classes/{cls['id']}/dashboard", headers=teacher_headers)
    assert r.status_code == 200, r.text
    dash = r.json()
    assert dash["class_summary"]["total_students"] == 1
    assert dash["class_summary"]["total_submissions"] == 1
    assert dash["students"][0]["submitted"] == 1
    assert dash["assignments"][0]["submitted_count"] == 1
    assert dash["heatmap"]

    # 教师可查看作业提交明细
    r = client.get(f"/api/teacher/assignments/{aid}", headers=teacher_headers)
    assert r.status_code == 200, r.text
    assert "student" in r.json()["submissions"]

    # 学生不能访问教师看板
    r = client.get(f"/api/teacher/classes/{cls['id']}/dashboard", headers=student_headers)
    assert r.status_code == 403


def test_assignment_wrong_question_retry_uses_server_snapshot(client, teacher_headers, student_headers):
    """作业错题重做不能被公开快照（无答案）误判；服务端用完整快照判分。"""
    cls = _new_class(client, teacher_headers)
    r = client.post("/api/classes/join", headers=student_headers, json={"join_code": cls["join_code"]})
    assert r.status_code == 200, r.text

    q = _make_question()
    assignment = get_classroom().create_assignment(
        teacher_id="teacher",
        title="错题重做-" + uuid.uuid4().hex[:6],
        class_ids=[cls["id"]],
        questions=[q.model_dump(mode="json")],
    )
    aid = assignment["id"]

    # 未提交作业前不能重做
    r = client.post(
        f"/api/assignments/{aid}/retry",
        headers=student_headers,
        json={"question_id": q.id, "answer": "B. O(n log n)"},
    )
    assert r.status_code == 409

    # 故意答错并提交，使该题成为错题
    r = client.post(
        f"/api/assignments/{aid}/submit",
        headers=student_headers,
        json={"answers": {q.id: "A. O(n²)"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["correct_count"] == 0

    # 公开题目仍不包含答案/判题方案
    r = client.get(f"/api/assignments/{aid}", headers=student_headers)
    public_q = r.json()["questions"][0]
    assert "answer" not in public_q
    assert "grading_plan" not in public_q

    # 重做答对：使用服务端完整快照判分
    r = client.post(
        f"/api/assignments/{aid}/retry",
        headers=student_headers,
        json={"question_id": q.id, "answer": "B. O(n log n)"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["correct"] is True
    assert data["score"] == 100.0
    assert data.get("details") is None
    assert "answer_key" not in json.dumps(data, ensure_ascii=False)

    # 重做答错
    r = client.post(
        f"/api/assignments/{aid}/retry",
        headers=student_headers,
        json={"question_id": q.id, "answer": "A. O(n²)"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["correct"] is False

    # 教师不能调用学生重做接口
    r = client.post(
        f"/api/assignments/{aid}/retry",
        headers=teacher_headers,
        json={"question_id": q.id, "answer": "B. O(n log n)"},
    )
    assert r.status_code == 403


def test_assignment_requires_llm_key(client, teacher_headers):
    cls = _new_class(client, teacher_headers)
    r = client.post(
        "/api/teacher/assignments",
        headers=teacher_headers,
        json={"title": "无 Key 作业", "class_ids": [cls["id"]], "count": 1},
    )
    assert r.status_code == 400
    assert "API Key" in r.json()["detail"] or "模型" in r.json()["detail"]
