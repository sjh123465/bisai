"""Agent 多轮对话组装 / 最终回答路径测试（不调用真实 LLM）"""
import asyncio

from app.agents.agent_service import AgentService


def _final(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content, "tool_calls": []}}]}


def _tool_call(name: str, args: str, call_id: str = "call_1") -> dict:
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                }],
            }
        }]
    }


class _FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.chat_calls = []
        self.stream_calls = []

    async def chat(self, messages, temperature=0.6, tools=None, **kwargs):
        self.chat_calls.append([dict(m) for m in messages])
        return self.responses.pop(0)

    async def chat_stream(self, messages, temperature=0.6, **kwargs):
        self.stream_calls.append([dict(m) for m in messages])
        yield "FALLBACK_STREAM"


def _agent_with(fake):
    agent = object.__new__(AgentService)
    agent.llm = fake
    agent.graphrag = None
    return agent


async def _collect(gen):
    return [chunk async for chunk in gen]


def test_final_answer_uses_first_pass_without_self_continuation():
    fake = _FakeLLM([_final("这是完整回答，不应再调用第二次流式模型。")])
    agent = _agent_with(fake)

    chunks = asyncio.run(_collect(agent.chat_stream("解释一下快速排序")))

    text = "".join(chunks)
    assert "这是完整回答" in text
    assert fake.stream_calls == []          # 不再把 assistant 回答塞回去二次生成
    assert fake.chat_calls[0][-1]["role"] == "user"
    assert fake.chat_calls[0][-1]["content"] == "解释一下快速排序"


def test_tool_round_then_final_answer_keeps_tool_result():
    fake = _FakeLLM([
        _tool_call("search_knowledge", '{"query":"快速排序"}'),
        _final("结合工具结果后的完整回答。"),
    ])
    agent = _agent_with(fake)

    async def fake_run_tool(tool_name, args, profile=None):
        assert tool_name == "search_knowledge"
        return "检索到的知识点：快速排序 / 分区"

    agent._run_tool = fake_run_tool
    chunks = asyncio.run(_collect(agent.chat_stream("快速排序怎么分区？")))

    text = "".join(chunks)
    assert "结合工具结果后的完整回答" in text
    assert fake.stream_calls == []
    second_round = fake.chat_calls[1]
    assert any(m.get("role") == "tool" and "快速排序" in m.get("content", "") for m in second_round)
    assert any(m.get("tool_calls") for m in second_round)


def test_empty_final_content_falls_back_to_stream_without_appending_assistant():
    fake = _FakeLLM([_final("")])
    agent = _agent_with(fake)

    chunks = asyncio.run(_collect(agent.chat_stream("你好")))
    text = "".join(chunks)

    assert "FALLBACK_STREAM" in text
    assert len(fake.stream_calls) == 1
    # 兜底流式时最后一条必须是 user/tool，而不是刚生成的空 assistant
    assert fake.stream_calls[0][-1]["role"] == "user"


def test_history_window_keeps_twelve_messages():
    history = []
    for i in range(6):
        history.append({"role": "user", "content": f"问题 {i}"})
        history.append({"role": "assistant", "content": f"回答 {i}"})
    assert len(history) == 12

    fake = _FakeLLM([_final("收到")])
    agent = _agent_with(fake)
    asyncio.run(_collect(agent.chat_stream("继续追问", history=history)))

    sent = fake.chat_calls[0]
    assert sent[0]["role"] == "system"
    assert len(sent) == 1 + 12 + 1
    assert sent[-1] == {"role": "user", "content": "继续追问"}
    assert sent[1]["content"] == "问题 0"
    assert sent[-2]["content"] == "回答 5"
