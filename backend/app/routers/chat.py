"""对话路由 — 核心 SSE 流式接口"""
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from app.agents.agent_service import get_agent, STATUS_SENTINEL

router = APIRouter(prefix="/api/chat", tags=["对话"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户当前消息")
    code: Optional[str] = Field(None, description="可选：用户提交的代码")
    history: Optional[List[ChatMessage]] = Field(None, description="可选：历史对话")


def _sse(data: dict) -> str:
    """将 dict 转为 SSE 事件字符串"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """Agent 驱动的流式对话接口"""
    agent = get_agent()
    history = [{"role": m.role, "content": m.content} for m in (req.history or [])]

    async def event_generator():
        # 开始
        yield _sse({"type": "start"})

        # Agent 流式输出（内部自动调度工具）
        full_text = ""
        async for chunk in agent.chat_stream(req.message, req.code or "", history):
            # 旁路思考状态：拦截哨兵，单独以 status 事件下发，不计入正文
            if chunk.startswith(STATUS_SENTINEL):
                try:
                    evt = json.loads(chunk[len(STATUS_SENTINEL):])
                except json.JSONDecodeError:
                    continue
                yield _sse({"type": "status", "stage": evt.get("stage", ""), "detail": evt.get("detail", "")})
                continue
            full_text += chunk
            yield _sse({"type": "chunk", "content": chunk})

        yield _sse({"type": "end", "full_length": len(full_text)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )


@router.post("/quick")
async def quick_answer(req: ChatRequest):
    """快速问答（不走 Agent 工具调度，直接 GraphRAG + LLM）"""
    agent = get_agent()
    answer = await agent.quick_answer(req.message)
    return {"answer": answer}
