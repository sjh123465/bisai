"""多模态截图答疑路由"""
from fastapi import APIRouter
from pydantic import BaseModel
from app.services.multimodal_service import get_multimodal

router = APIRouter(prefix="/api/multimodal", tags=["多模态"])


class MultimodalRequest(BaseModel):
    image: str  # base64
    question: str = "这张图里有什么算法或数据结构？请详细讲解。"


@router.post("/analyze")
async def analyze_image(req: MultimodalRequest):
    mm = get_multimodal()
    return await mm.analyze_image(req.image, req.question)
