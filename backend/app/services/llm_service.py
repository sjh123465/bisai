"""LLM 服务 — 直接 HTTP 调用，支持 Function Calling 和 Embedding"""
import json
import httpx
from typing import AsyncGenerator, Optional
from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger("llm")


class LLMService:
    def __init__(self):
        self.cfg = get_settings()
        if not self.cfg.llm_api_key:
            logger.warning("⚠️ LLM_API_KEY 未设置，LLM 调用将失败，请在 .env 中填入真实 Key")

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> dict:
        """非流式对话，返回完整响应 dict"""
        url = f"{self.cfg.llm_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.cfg.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.cfg.llm_model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error(f"LLM 调用失败: {resp.status_code} {resp.text[:500]}")
                raise RuntimeError(f"LLM API 错误: {resp.status_code}")
            return resp.json()

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """SSE 流式输出，yield 纯文本片段"""
        url = f"{self.cfg.llm_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.cfg.llm_api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        payload = {
            "model": self.cfg.llm_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        # 收紧超时：连接 10s、单次读取 60s（SSE 每个 chunk 间隔通常很短）
        # 避免模型卡住时浏览器长时间挂起后抛 net::ERR_ABORTED
        timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    logger.error(f"LLM 流式调用失败: {resp.status_code} {err[:500]}")
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
                        except (json.JSONDecodeError, KeyError):
                            continue

    @staticmethod
    def _local_hash_embed(texts: list[str]) -> list[list[float]]:
        """零依赖本地 Embedding：字符 bigram 哈希到 384 维并 L2 归一化
        确定性 + 词法敏感：相似文本共享 bigram → 有余弦重叠，可支撑基础向量检索
        """
        import hashlib
        import math
        vecs = []
        for text in texts:
            v = [0.0] * 384
            t = text.lower().replace(" ", "").replace("\n", "")
            grams = [t[i:i + 2] for i in range(len(t) - 1)] or list(t) or ["empty"]
            for g in grams:
                h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16)
                v[h % 384] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            vecs.append([x / norm for x in v])
        return vecs

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """获取文本 embedding — API 失败时降级为本地哈希向量"""
        if self.cfg.embedding_local:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            return model.encode(texts).tolist()

        # 无 API Key → 直接本地哈希向量
        if not self.cfg.llm_api_key:
            logger.warning("⚠️ 无 API Key，Embedding 用本地哈希向量")
            return self._local_hash_embed(texts)

        try:
            url = f"{self.cfg.embedding_base_url().rstrip('/')}/embeddings"
            headers = {
                "Authorization": f"Bearer {self.cfg.embedding_api_key()}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.cfg.embedding_model,
                "input": texts,
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    # DeepSeek 等 Chat 服务无 /embeddings 接口 → 降级本地哈希
                    logger.warning(f"Embedding API 不可用({resp.status_code})，降级为本地哈希向量")
                    return self._local_hash_embed(texts)
                data = resp.json()
                return [item["embedding"] for item in data["data"]]
        except Exception as e:
            logger.error(f"Embedding 异常: {e}，降级为本地哈希向量")
            return self._local_hash_embed(texts)


# 单例
_llm = None

def get_llm() -> LLMService:
    global _llm
    if _llm is None:
        _llm = LLMService()
    return _llm
