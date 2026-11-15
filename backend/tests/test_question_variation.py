"""出题变体：同一知识点重复出题时，Prompt 必须换角度并携带最近题干去重。"""
import asyncio
import json

import pytest

from app.core.llm_config import LLMConfig
from app.services.exam_service import ExamService, VARIATION_ANGLES


QUESTION = {
    "type": "choice",
    "question": "插入排序在最好情况下的时间复杂度是？",
    "options": ["A. O(n)", "B. O(n log n)", "C. O(n^2)", "D. O(1)"],
    "answer": "A",
    "explanation": "最好情况是数组已有序，只需比较 n-1 次。",
    "grading_plan": {
        "version": 1,
        "method": "objective",
        "answer_key": "A",
        "accepted_answers": ["A", "A. O(n)"],
        "pass_threshold": 0.6,
        "criteria": [{
            "id": "correctness",
            "description": "答案匹配",
            "weight": 1.0,
            "kind": "answer",
            "params": {},
            "auto": True,
        }],
    },
}


@pytest.fixture
def exam_with_fake_llm(monkeypatch):
    config = LLMConfig(
        provider="deepseek",
        api_key="sk-test-key-12345678",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
    )
    exam = ExamService(config)
    captured = []

    async def fake_chat(messages, temperature=0.7, **kwargs):
        captured.append({"messages": messages, "temperature": temperature})
        return {"choices": [{"message": {"content": json.dumps(QUESTION, ensure_ascii=False)}}]}

    monkeypatch.setattr(exam.llm, "chat", fake_chat)
    return exam, captured


def test_repeated_question_rotates_angles_without_full_stems(exam_with_fake_llm):
    exam, captured = exam_with_fake_llm

    first = asyncio.run(exam.generate_question("插入排序", "choice", "easy"))
    assert "error" not in first
    assert len(first["variation"]) == 2

    # 只回传角度指纹，不再传完整题干
    second = asyncio.run(
        exam.generate_question("插入排序", "choice", "easy", avoid_variants=first["variation"])
    )
    assert "error" not in second
    assert not set(first["variation"]) & set(second["variation"])

    prompt1 = captured[0]["messages"][1]["content"]
    prompt2 = captured[1]["messages"][1]["content"]

    # 温度提高，增加采样差异
    assert captured[0]["temperature"] == 1.0
    # 每次至少命中一个随机切入角度
    assert any(angle in prompt1 for angle in VARIATION_ANGLES)
    # 明确要求重复出题必须换题干与考查角度
    assert "题干、选项与考查角度必须有明显差异" in prompt1
    # 第二次只带角度指纹：有避让说明，但不出现完整题干
    assert "最近已经使用过这些切入角度" in prompt2
    assert all(key in prompt2 for key in first["variation"])
    assert QUESTION["question"] not in prompt2
