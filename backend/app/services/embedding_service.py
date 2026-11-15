"""Embedding 服务 — bge-small 本地兜底 + 智谱 embedding-3 远程增强。

策略：
1. ChromaDB 统一存 bge-small（384 维）向量，建库/粗检索都用它，维度稳定、无需 Key；
2. Reranker 阶段若检测到请求携带智谱 Key，则用 embedding-3（2048 维）对
   Top-K 候选文档与 query 重新计算余弦相似度，做精细化重排序；
3. 无 Key 时 Reranker 降级为规则重排（图谱前置关系权重）。
"""
import asyncio
import math
import os
from typing import Optional

import httpx
from app.core.config import get_settings
from app.core.llm_config import LLMConfig
from app.core.logger import get_logger

logger = get_logger("embedding")

# 国内 HuggingFace 镜像，确保模型可下载（可由 .env 的 HF_ENDPOINT 覆盖）
os.environ.setdefault("HF_ENDPOINT", get_settings().hf_endpoint)

# bge-small 本地模型：512 维，中文优化，无 Key 可用
_LOCAL_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
_LOCAL_DIM = 512
_model = None


def _get_model():
    """懒加载本地 bge-small 模型（首次调用时下载/加载）"""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(_LOCAL_MODEL_NAME)
            logger.info(f"🧠 本地 Embedding 模型加载: {_LOCAL_MODEL_NAME} ({_LOCAL_DIM} 维)")
        except Exception as e:
            logger.error(f"本地 Embedding 模型加载失败: {e}")
            _model = None
    return _model


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def embed_local(texts: list[str]) -> list[list[float]]:
    """bge-small 本地 embedding，返回 384 维向量。失败时 fallback 到哈希。"""
    model = _get_model()
    if model is None:
        # fallback：384 维哈希（保证最低可用）
        return _hash_embed(texts)
    try:
        vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vecs]
    except Exception as e:
        logger.warning(f"bge-small 编码失败，降级哈希: {e}")
        return _hash_embed(texts)


def _hash_embed(texts: list[str]) -> list[list[float]]:
    """零依赖 384 维哈希 embedding，作为 bge-small 不可用时的兜底。"""
    import hashlib
    vecs = []
    for text in texts:
        v = [0.0] * _LOCAL_DIM
        t = (text or "").lower().replace(" ", "").replace("\n", "")
        grams = [t[i:i + 2] for i in range(len(t) - 1)] or list(t) or ["empty"]
        for g in grams:
            h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16)
            v[h % 512] += 1.0
        vecs.append(_l2_normalize(v))
    return vecs


async def embed_remote_zhipu(texts: list[str], config: LLMConfig) -> Optional[list[list[float]]]:
    """调用智谱 embedding-3（2048 维）。失败返回 None，让调用方降级。"""
    if not config or "zhipu" not in config.provider and "bigmodel" not in config.base_url:
        return None
    url = config.base_url.rstrip("/") + "/embeddings"
    payload = {"model": "embedding-3", "input": texts}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            })
            resp.raise_for_status()
            data = resp.json()
            vecs = [item["embedding"] for item in data.get("data", [])]
            if not vecs:
                return None
            return [_l2_normalize(v) for v in vecs]
    except Exception as e:
        logger.warning(f"智谱 embedding-3 调用失败: {e}")
        return None


async def cosine_sim_remote(query: str, candidates: list[str], config: LLMConfig) -> list[float]:
    """用智谱 embedding-3 计算 query 与候选文档的余弦相似度（Reranker 用）。

    失败返回空列表，调用方降级到规则重排。
    """
    all_vecs = await embed_remote_zhipu([query] + candidates, config)
    if not all_vecs or len(all_vecs) != len(candidates) + 1:
        return []
    q_vec = all_vecs[0]
    scores = []
    for c_vec in all_vecs[1:]:
        scores.append(sum(a * b for a, b in zip(q_vec, c_vec)))
    return scores
