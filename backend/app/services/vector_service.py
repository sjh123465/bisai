"""向量检索服务 — ChromaDB + bge-small 本地 Embedding（384 维）

ChromaDB 固定用 bge-small 384 维向量，保证维度稳定、无需 Key。
Reranker 阶段的 embedding-3 增强在 graphrag_service 中处理。
"""
import os
import chromadb
from typing import Optional
from app.core.config import get_settings
from app.core.logger import get_logger
from app.services.embedding_service import embed_local

logger = get_logger("vector")

COLLECTION_NAME = "code_knowledge"


class VectorStore:
    def __init__(self):
        self.cfg = get_settings()
        os.makedirs(self.cfg.chroma_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.cfg.chroma_dir)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"📚 ChromaDB 集合加载: {self.collection.count()} 条文档（bge-small 512 维）")

    async def add_document(self, doc_id: str, text: str, metadata: Optional[dict] = None):
        embeddings = embed_local([text])
        meta = metadata or {}
        meta["chunk_id"] = doc_id
        self.collection.add(
            ids=[doc_id], documents=[text], metadatas=[meta], embeddings=embeddings,
        )

    async def add_documents(self, docs: list[dict]):
        if not docs:
            return
        texts = [d["text"] for d in docs]
        embeddings = embed_local(texts)
        ids = [d["id"] for d in docs]
        metadatas = [d.get("metadata", {}) for d in docs]
        for m in metadatas:
            m.setdefault("chunk_id", "")
        self.collection.add(
            ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings,
        )
        logger.info(f"📥 批量添加 {len(docs)} 条文档（bge-small）")

    async def query(self, query_text: str, top_k: int = 5) -> list[dict]:
        if self.collection.count() == 0:
            return []
        embeddings = embed_local([query_text])
        try:
            results = self.collection.query(
                query_embeddings=embeddings,
                n_results=min(top_k, self.collection.count()),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.warning(f"向量检索失败（可能需要删除 data/chroma 重建）: {e}")
            return []
        out = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        for i in range(len(ids)):
            out.append({
                "id": ids[i],
                "text": docs[i] if docs else "",
                "metadata": metas[i] if metas else {},
                "distance": dists[i] if dists else 1.0,
            })
        return out

    def clear(self):
        self.client.delete_collection(COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"},
        )
        logger.info("🗑️ 向量库已清空")

    def count(self) -> int:
        return self.collection.count()


_vector = None

def get_vector() -> VectorStore:
    global _vector
    if _vector is None:
        _vector = VectorStore()
    return _vector
