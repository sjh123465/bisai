"""API 集成测试 — 健康检查 / 认证流 / 权限守卫 / 限流响应头"""
import pytest


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"username": "teacher", "password": "nope"})
    assert r.status_code == 401


def test_register_and_login(client):
    r = client.post("/api/auth/register", json={"username": "t_new_user", "password": "abc12345"})
    assert r.status_code == 200
    r2 = client.post("/api/auth/login", json={"username": "t_new_user", "password": "abc12345"})
    assert r2.status_code == 200


def test_register_duplicate(client):
    client.post("/api/auth/register", json={"username": "t_dup", "password": "abc12345"})
    r = client.post("/api/auth/register", json={"username": "t_dup", "password": "abc12345"})
    assert r.status_code == 400


def test_me_requires_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_teacher_dashboard_requires_auth(client):
    r = client.get("/api/teacher/classes/not-exist/dashboard")
    assert r.status_code == 401


def test_teacher_dashboard_forbidden_for_student(client, student_headers):
    r = client.get("/api/teacher/classes/not-exist/dashboard", headers=student_headers)
    assert r.status_code == 403


def test_teacher_dashboard_ok(client, teacher_headers):
    r = client.post("/api/classes", headers=teacher_headers, json={"name": "API 测试班"})
    assert r.status_code == 200, r.text
    class_id = r.json()["id"]
    r = client.get(f"/api/teacher/classes/{class_id}/dashboard", headers=teacher_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "heatmap" in data and "class_summary" in data


def test_teacher_registration_blocked(client):
    r = client.post("/api/auth/register", json={
        "username": "t_evil_teacher", "password": "abcdef123", "role": "teacher",
    })
    assert r.status_code == 403


def test_personal_learning_routes_removed(client):
    assert client.get("/api/bkt/mastery/anyone").status_code == 404
    assert client.get("/api/wrongbook/list/anyone").status_code == 404


def test_llm_endpoints_require_user_key(client):
    assert client.post("/api/chat/stream", json={"message": "你好"}).status_code == 400
    assert client.post("/api/exam/generate", json={"concept": "数组"}).status_code == 400
    assert client.get("/api/settings/llm/providers").status_code == 200


def test_metrics_requires_teacher(client, student_headers, teacher_headers):
    assert client.get("/api/metrics").status_code == 401
    assert client.get("/api/metrics", headers=student_headers).status_code == 403
    r = client.get("/api/metrics", headers=teacher_headers)
    assert r.status_code == 200
    assert "total_requests" in r.json()


def test_knowledge_search_open(client):
    r = client.get("/api/knowledge/search?query=快速排序&top_k=3")
    assert r.status_code == 200


def test_sandbox_execute_open(client):
    r = client.post("/api/code/execute", json={"code": "print('api ok')", "language": "python"})
    assert r.status_code == 200
    data = r.json()
    assert "api ok" in (data.get("output") or data.get("result", {}).get("output", ""))


def test_ratelimit_header_present(client):
    r = client.get("/health")
    # /health 豁免限流，无该头；换一个业务接口验证
    r = client.get("/api/knowledge/search?query=链表&top_k=1")
    assert "X-RateLimit-Remaining" in r.headers
