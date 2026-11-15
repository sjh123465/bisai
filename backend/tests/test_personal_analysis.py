"""个人学情分析接口 / Prompt 测试（不调用真实 LLM）"""
from app.routers.analysis import (
    ConceptStat,
    PersonalAnalysisRequest,
    SeriesPoint,
    TrendPoint,
    build_personal_analysis_prompt,
)


class _FakeGraph:
    def get_upstream(self, concept_id):
        return []


class _FakeLLM:
    last_prompt = ""

    def __init__(self, config):
        self.config = config

    async def chat(self, messages, temperature=0.3, max_tokens=None):
        _FakeLLM.last_prompt = messages[-1]["content"]
        return {"choices": [{"message": {"content": "# 学情分析\n\n先巩固快速排序的边界条件。"}}]}


def _payload():
    return {
        "scope": "all",
        "plugin": {
            "generator": {"id": "llm_default", "name": "LLM 标准出题 + 判题方案", "version": "1"},
            "grader": {"id": "plan_based", "name": "判题方案确定性判分", "version": "1"},
        },
        "summary": {
            "concepts_count": 2,
            "active_concepts": 2,
            "total_attempts": 6,
            "correct_attempts": 4,
            "accuracy": 0.667,
            "avg_mastery": 0.55,
            "weak_count": 1,
            "streak_days": 3,
        },
        "concepts": [
            {
                "concept_id": "quick_sort",
                "name": "快速排序",
                "mastery": 0.45,
                "attempts": 4,
                "correct": 2,
                "accuracy": 0.5,
                "wrong_count": 2,
                "first_time": "2026-11-10T10:00:00Z",
                "last_time": "2026-11-15T10:00:00Z",
                "sources": {"personal": 3, "assignment": 1},
                "series": [
                    {"index": 1, "time": "2026-11-10T10:00:00Z", "mastery": 0.45, "correct": False},
                    {"index": 2, "time": "2026-11-11T10:00:00Z", "mastery": 0.35, "correct": True},
                ],
            },
            {
                "concept_id": "array",
                "name": "数组",
                "mastery": 0.65,
                "attempts": 2,
                "correct": 2,
                "accuracy": 1.0,
                "wrong_count": 0,
                "sources": {"personal": 2},
                "series": [],
            },
        ],
        "trend": [
            {"date": "2026-11-14", "label": "11/14", "answered": 3, "correct": 2, "accuracy": 0.667, "mastery": 0.5},
        ],
        "selected_concept": "quick_sort",
    }


def test_prompt_contains_profile_and_selected_concept(monkeypatch):
    import app.routers.analysis as analysis
    monkeypatch.setattr(analysis, "get_graph", lambda: _FakeGraph())
    req = PersonalAnalysisRequest.model_validate(_payload())
    prompt = build_personal_analysis_prompt(req)
    assert "快速排序" in prompt
    assert "数组" in prompt
    assert "当前选中知识点" in prompt
    assert "7 天" in prompt
    assert "LLM 标准出题 + 判题方案" in prompt
    assert "第 1 次" not in prompt  # 不复述原始表格


def test_personal_analysis_requires_key(client):
    r = client.post("/api/analysis/personal", json=_payload())
    assert r.status_code == 400
    assert "API Key" in r.json()["detail"]


def test_personal_analysis_returns_report(client, monkeypatch):
    import app.routers.analysis as analysis
    monkeypatch.setattr(analysis, "get_graph", lambda: _FakeGraph())
    monkeypatch.setattr(analysis, "LLMService", _FakeLLM)
    r = client.post(
        "/api/analysis/personal",
        json=_payload(),
        headers={"X-LLM-Key": "sk-test-12345678", "X-LLM-Provider": "deepseek"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "学情分析" in data["report"]
    assert data["scope"] == "all"
    assert data["selected_concept"] == "quick_sort"
    assert "快速排序" in _FakeLLM.last_prompt
    assert "仅用于本次分析" in _FakeLLM.last_prompt


def test_plugins_endpoint(client):
    r = client.get("/api/plugins")
    assert r.status_code == 200
    data = r.json()
    assert data["generator"]["id"] == "llm_default"
    assert data["grader"]["id"] == "plan_based"
    assert data["available"]["generators"]
    assert data["available"]["graders"]
