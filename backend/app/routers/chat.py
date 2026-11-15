"""对话路由 — 核心 SSE 流式接口"""
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from app.agents.agent_service import get_agent, STATUS_SENTINEL
from app.core.llm_config import LLMConfig, require_llm_config

router = APIRouter(prefix="/api/chat", tags=["对话"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户当前消息")
    code: Optional[str] = Field(None, description="可选：用户提交的代码")
    history: Optional[List[ChatMessage]] = Field(None, description="可选：历史对话")
    # 浏览器本地个人学情摘要；仅本次请求用于个性化，服务端不持久化
    profile: Optional[dict] = Field(None, description="可选：本地学情摘要")


def _sse(data: dict) -> str:
    """将 dict 转为 SSE 事件字符串"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(req: ChatRequest, config: LLMConfig = Depends(require_llm_config)):
    """Agent 驱动的流式对话接口（使用请求携带的用户 Key）"""
    agent = get_agent(config)
    history = [{"role": m.role, "content": m.content} for m in (req.history or [])]

    async def event_generator():
        # 开始
        yield _sse({"type": "start"})

        # Agent 流式输出（内部自动调度工具）
        full_text = ""
        async for chunk in agent.chat_stream(req.message, req.code or "", history, req.profile):
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
async def quick_answer(req: ChatRequest, config: LLMConfig = Depends(require_llm_config)):
    """快速问答（不走 Agent 工具调度，直接 GraphRAG + LLM）"""
    agent = get_agent(config)
    answer = await agent.quick_answer(req.message)
    return {"answer": answer}
