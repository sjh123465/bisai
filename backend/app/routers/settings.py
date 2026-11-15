"""模型设置路由 — 只返回 provider 元数据与连接测试，不保存任何 Key。"""
from fastapi import APIRouter, Depends, HTTPException

from app.core.llm_config import LLMConfig, public_providers, require_llm_config
from app.services.llm_service import LLMService

router = APIRouter(prefix="/api/settings", tags=["设置"])


@router.get("/llm/providers")
async def list_providers():
    return {"providers": public_providers()}


@router.post("/llm/test")
async def test_llm(config: LLMConfig = Depends(require_llm_config)):
    """使用请求头中的 Key 发起一次极小的调用，验证连通性。"""
    llm = LLMService(config)
    try:
        resp = await llm.chat(
            [{"role": "user", "content": "只回复 OK"}],
            temperature=0,
            max_tokens=8,
        )
        reply = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return {
            "ok": True,
            "provider": config.provider,
            "model": config.model,
            "reply": (reply or "")[:80],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"连接失败：{e}")
