"""多模态截图答疑路由"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.llm_config import LLMConfig, require_llm_config
from app.services.multimodal_service import get_multimodal

router = APIRouter(prefix="/api/multimodal", tags=["多模态"])


class MultimodalRequest(BaseModel):
    image: str  # base64
    question: str = "这张图里有什么算法或数据结构？请详细讲解。"


@router.post("/analyze")
async def analyze_image(req: MultimodalRequest, config: LLMConfig = Depends(require_llm_config)):
    mm = get_multimodal(config)
    return await mm.analyze_image(req.image, req.question)
