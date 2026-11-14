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
            # MULTIMODAL_MODEL 支持逗号分隔多个候选，按顺序尝试，哪个开通了就用哪个
            models = [m.strip() for m in self.cfg.multimodal_model.split(",") if m.strip()]
            return {
                "api_key": self.cfg.multimodal_api_key,
                "base_url": self.cfg.multimodal_base_url,
                "models": models,
                "separate": True,
            }
        return {
            "api_key": self.cfg.llm_api_key,
            "base_url": self.cfg.llm_base_url,
            "models": [self.cfg.llm_model],
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

        # 兼容两种入参：完整 data URL 或裸 base64（裸 base64 默认按 png 处理）
        if image_b64.startswith("data:"):
            image_url_value = image_b64
        else:
            image_url_value = f"data:image/png;base64,{image_b64}"

        last_err = ""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                # 依次尝试候选模型，第一个成功的就直接返回
                for model in vendor["models"]:
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": question},
                                    {"type": "image_url", "image_url": {"url": image_url_value}},
                                ],
                            },
                        ],
                        "temperature": 0.5,
                    }
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        answer = data["choices"][0]["message"]["content"]
                        self._working_model = model
                        logger.info(f"✅ 多模态成功: {model}")
                        return {"ok": True, "answer": answer, "model": model}

                    err = resp.text[:200]
                    last_err = f"{model} -> {resp.status_code}"
                    logger.warning(f"多模态模型 {model} 不可用({resp.status_code})，尝试下一个")

                # 全部失败，返回开通指引
                return {
                    "ok": False,
                    "message": (
                        f"所有候选视觉模型均不可用（{last_err}）。\n\n"
                        "请按以下步骤开通（每个模型独立 100 万 Token 免费额度）：\n"
                        "1. 打开 https://bailian.console.aliyun.com/\n"
                        "2. 左侧「模型广场」→ 搜索 qwen-vl\n"
                        "3. 找到 qwen3-vl-plus / qwen-vl-max，点「开通服务」\n"
                        "4. 开通后重新上传图片即可"
                    ),
                }
        except Exception as e:
            logger.error(f"多模态异常: {e}")
            return {"ok": False, "message": f"调用异常: {e}"}


_mm = None

def get_multimodal() -> MultimodalService:
    global _mm
    if _mm is None:
        _mm = MultimodalService()
    return _mm
