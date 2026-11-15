"""多模态截图答疑服务 — 使用用户自己的远程 Key。

DeepSeek 不支持视觉；选择智谱 GLM 时复用同一个 Key 调用 glm-4v-flash。
服务端不保存任何 Key。
"""
import httpx
from app.core.llm_config import LLMConfig
from app.core.logger import get_logger
from app.services.graphrag_service import get_graphrag

logger = get_logger("multimodal")


class MultimodalService:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.graphrag = get_graphrag()

    def _resolve_vendor(self):
        if not self.config.has_vision:
            return None
        return {
            "api_key": self.config.api_key,
            "base_url": self.config.base_url,
            "models": [self.config.vision_model],
        }

    async def analyze_image(self, image_b64: str, question: str = "这张图里有什么算法或数据结构？请详细讲解。") -> dict:
        """
        调用视觉模型解析图片，结合 GraphRAG 学科知识返回解析
        image_b64: base64 编码的图片（可带 data: 前缀）
        """
        vendor = self._resolve_vendor()
        if vendor is None:
            return {
                "ok": False,
                "message": "当前选择的模型提供方不支持图片理解。请在「模型设置」中切换到智谱 GLM（同一 Key 即可使用视觉模型）。",
            }

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
                    # OCR 类模型不支持 system 角色，把提示词并入用户消息
                    if "ocr" in model.lower():
                        messages = [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"{system_prompt}\n\n{question}"},
                                {"type": "image_url", "image_url": {"url": image_url_value}},
                            ],
                        }]
                    else:
                        messages = [
                            {"role": "system", "content": system_prompt},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": question},
                                    {"type": "image_url", "image_url": {"url": image_url_value}},
                                ],
                            },
                        ]
                    payload = {
                        "model": model,
                        "messages": messages,
                        "temperature": 0.5,
                    }
                    # Omni 系列必须显式声明只返回文本，否则会尝试输出音频
                    if "omni" in model.lower():
                        payload["modalities"] = ["text"]
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

                # 全部失败，返回可理解的错误
                return {
                    "ok": False,
                    "message": (
                        f"视觉模型暂时不可用（{last_err or '未知错误'}）。"
                        "请检查智谱 API Key 是否已开通 glm-4v-flash，或稍后重试。"
                    ),
                }
        except Exception as e:
            logger.error(f"多模态异常: {e}")
            return {"ok": False, "message": f"调用异常: {e}"}


def get_multimodal(config: LLMConfig) -> MultimodalService:
    return MultimodalService(config)
