"""LLM 服务 — 每个请求使用用户自己的远程 API Key。

服务端不读取 .env 中的 LLM Key，也不做任何兜底；Key 仅存在于请求生命周期内。
本地 Embedding 统一由 embedding_service（FastEmbed / bge-small）提供，避免不同
provider 的向量维度不一致导致 ChromaDB 查询失败。
"""
import json
from typing import AsyncGenerator, Optional

import httpx

from app.core.llm_config import LLMConfig
from app.core.logger import get_logger

logger = get_logger("llm")


class LLMService:
    def __init__(self, config: LLMConfig):
        self.config = config

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    @property
    def _chat_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/chat/completions"

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> dict:
        """非流式对话，返回完整响应 dict。"""
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(self._chat_url, headers=self._headers(), json=payload)
            if resp.status_code != 200:
                logger.error(
                    "LLM 调用失败: provider=%s status=%s body=%s",
                    self.config.provider, resp.status_code, resp.text[:300],
                )
                raise RuntimeError(f"LLM API 错误: {resp.status_code}")
            return resp.json()

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """SSE 流式输出，yield 纯文本片段。"""
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        headers = {**self._headers(), "Accept": "text/event-stream"}
        timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", self._chat_url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    logger.error(
                        "LLM 流式调用失败: provider=%s status=%s body=%s",
                        self.config.provider, resp.status_code, err[:300],
                    )
                    yield f"[LLM 连接失败: {resp.status_code}]"
                    return
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
