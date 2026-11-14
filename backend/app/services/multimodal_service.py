"""多模态截图答疑服务 — 接入视觉大模型（Qwen-VL / GPT-4o 等 OpenAI 兼容接口）
DeepSeek 不支持视觉，需单独配置 MULTIMODAL_*；未配置时返回引导信息
"""
import base64
import httpx
from app.core.config import get_settings
from app.core.logger import get_logger
from app.services.graphrag_service import get_graphrag

logger = get_logger("multimodal")


class MultimodalService:
    def __init__(self):
        self.cfg = get_settings()
        self.graphrag = get_graphrag()

    def _resolve_vendor(self):
        # 优先用独立的多模态配置，否则回退到主 LLM
        if self.cfg.multimodal_api_key and self.cfg.multimodal_base_url and self.cfg.multimodal_model:
            return {
                "api_key": self.cfg.multimodal_api_key,
                "base_url": self.cfg.multimodal_base_url,
                "model": self.cfg.multimodal_model,
                "separate": True,
            }
        return {
            "api_key": self.cfg.llm_api_key,
            "base_url": self.cfg.llm_base_url,
            "model": self.cfg.llm_model,
            "separate": False,
        }

    async def analyze_image(self, image_b64: str, question: str = "这张图里有什么算法或数据结构？请详细讲解。") -> dict:
        """
        调用视觉模型解析图片，结合 GraphRAG 学科知识返回解析
        image_b64: base64 编码的图片（不带 data: 前缀）
        """
        vendor = self._resolve_vendor()
        if not vendor["api_key"]:
            return {"ok": False, "message": "未配置 LLM_API_KEY"}

        # 先做一次 GraphRAG 检索拿到学科上下文（基于用户问题）
        ctx_text = ""
        try:
            retrieved = await self.graphrag.retrieve(question or "算法 数据结构", vector_top_k=2)
            ctx_text = self.graphrag.format_for_llm(retrieved, max_chunks=2)
        except Exception as e:
            logger.warning(f"GraphRAG 预检索失败: {e}")

        system_prompt = (
            "你是计算机学科的多模态导师，擅长识别算法流程图、数据结构示意图、手写代码截图、公式图。"
            "请结合图中内容和学科知识进行讲解。支持 Markdown 格式。\n\n"
            "以下是可能相关的学科上下文（供参考，若不相关可忽略）:\n"
            f"{ctx_text}"
        )

        url = f"{vendor['base_url'].rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {vendor['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": vendor["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                },
            ],
            "temperature": 0.5,
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    err = resp.text[:300]
                    logger.error(f"多模态调用失败: {resp.status_code} {err}")
                    if not vendor["separate"]:
                        return {
                            "ok": False,
                            "message": (
                                f"当前模型 {vendor['model']} 不支持图片识别（错误 {resp.status_code}）。\n\n"
                                "请在 .env 中配置多模态视觉模型，例如阿里通义千问 VL：\n"
                                "MULTIMODAL_API_KEY=你的-DashScope-Key\n"
                                "MULTIMODAL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1\n"
                                "MULTIMODAL_MODEL=qwen-vl-plus"
                            ),
                        }
                    return {"ok": False, "message": f"多模态服务调用失败({resp.status_code})"}
                data = resp.json()
                answer = data["choices"][0]["message"]["content"]
                return {"ok": True, "answer": answer, "model": vendor["model"]}
        except Exception as e:
            logger.error(f"多模态异常: {e}")
            return {"ok": False, "message": f"调用异常: {e}"}


_mm = None

def get_multimodal() -> MultimodalService:
    global _mm
    if _mm is None:
        _mm = MultimodalService()
    return _mm
