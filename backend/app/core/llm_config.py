"""请求级 LLM 配置 — 服务端不保存用户 API Key。

前端在每次 LLM 相关请求中携带以下请求头：
  X-LLM-Provider: deepseek | zhipu
  X-LLM-Key:      用户自己的远程 API Key
  X-LLM-Model:    可选，覆盖预设模型

出于安全考虑，Base URL 只能来自服务端预设，不能让客户端任意指定，
避免把后端变成 SSRF 跳板。
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request

PROVIDER_PRESETS: dict[str, dict] = {
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "vision_model": "",
        "has_vision": False,
        "key_hint": "sk-...",
    },
    "zhipu": {
        "id": "zhipu",
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "vision_model": "glm-4v-flash",
        "has_vision": True,
        "key_hint": "智谱开放平台 API Key",
    },
}


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    api_key: str
    base_url: str
    model: str
    vision_model: str = ""

    @property
    def has_vision(self) -> bool:
        return bool(self.vision_model)


def _clean_header(value: Optional[str], max_len: int = 512) -> str:
    text = (value or "").strip()
    if any(ch in text for ch in "\r\n"):
        raise HTTPException(status_code=400, detail="请求头包含非法字符")
    if len(text) > max_len:
        raise HTTPException(status_code=400, detail="请求头过长")
    return text


def get_optional_llm_config(request: Request) -> Optional[LLMConfig]:
    """解析请求头中的用户 Key；未配置时返回 None，不做任何服务端兜底。"""
    provider = (_clean_header(request.headers.get("X-LLM-Provider"), 32) or "deepseek").lower()
    api_key = _clean_header(request.headers.get("X-LLM-Key"))
    if not api_key:
        return None

    preset = PROVIDER_PRESETS.get(provider)
    if not preset:
        raise HTTPException(status_code=400, detail="不支持的模型提供方")
    if len(api_key) < 8:
        raise HTTPException(status_code=400, detail="API Key 格式不正确")

    model = _clean_header(request.headers.get("X-LLM-Model"), 128) or preset["model"]
    return LLMConfig(
        provider=provider,
        api_key=api_key,
        base_url=preset["base_url"],
        model=model,
        vision_model=preset.get("vision_model", ""),
    )


def require_llm_config(request: Request) -> LLMConfig:
    """需要调用 LLM 的接口使用的依赖；未配置时返回友好的 400。"""
    cfg = get_optional_llm_config(request)
    if cfg is None:
        raise HTTPException(
            status_code=400,
            detail="请先在右上角「模型设置」中配置远程 API Key（仅保存在你的浏览器）",
        )
    return cfg


def public_providers() -> list[dict]:
    """返回给前端渲染 provider 下拉框，绝不包含任何 Key。"""
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "base_url": p["base_url"],
            "model": p["model"],
            "has_vision": p["has_vision"],
            "key_hint": p["key_hint"],
        }
        for p in PROVIDER_PRESETS.values()
    ]
