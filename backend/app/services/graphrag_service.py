"""GraphRAG 混合检索 — 图谱多跳 + 向量检索 + 规则/Embedding Reranker

Reranker 策略：
- 有智谱 Key → 用 embedding-3（2048 维）对 Top-K 候选文档重新计算余弦相似度
- 无 Key → 用规则（图谱前置关系权重 + 向量距离）重排
"""
from typing import Optional
from app.services.graph_service import get_graph
from app.services.vector_service import get_vector
from app.services.embedding_service import cosine_sim_remote
from app.core.llm_config import LLMConfig
from app.core.logger import get_logger

logger = get_logger("graphrag")

# 规则重排时，图谱节点在向量相似度之外的权重加成
GRAPH_NODE_WEIGHT = 0.3
# embedding-3 Reranker 与规则分数的阈值差（小于此值认为接近，才触发 LLM 裁决）
RERANK_THRESHOLD = 0.1


class GraphRAGService:
    def __init__(self):
        self.graph = get_graph()
        self.vector = get_vector()

    async def retrieve(
        self,
        query: str,
        graph_depth: int = 2,
        vector_top_k: int = 5,
        node_top_k: int = 5,
        config: Optional[LLMConfig] = None,
    ) -> dict:
        """
        混合检索 + Reranker：
        1. 图谱节点模糊匹配 → 多跳邻居
        2. 向量粗检索 Top-K
        3. Reranker 重排序：有智谱 Key 用 embedding-3，否则规则
        """
        # 1. 图谱检索
        matched_nodes = self.graph.search_nodes(query, top_k=node_top_k)
        graph_context = []
        seen_ids = set()
        for node in matched_nodes:
            node_id = node["id"]
            if node_id not in seen_ids:
                graph_context.append(node)
                seen_ids.add(node_id)
            neighbors = self.graph.get_neighbors(node_id, max_depth=graph_depth)
            for nb in neighbors:
                if nb["id"] not in seen_ids:
                    graph_context.append(nb)
                    seen_ids.add(nb["id"])

        upstream_map = {}
        downstream_map = {}
        for node in graph_context[:3]:
            upstream_map[node["id"]] = self.graph.get_upstream(node["id"])
            downstream_map[node["id"]] = self.graph.get_downstream(node["id"])

        # 2. 向量粗检索
        vector_results = await self.vector.query(query, top_k=vector_top_k)

        # 3. Reranker
        vector_results = await self._rerank(query, vector_results, config)

        return {
            "query": query,
            "graph_nodes": graph_context,
            "graph_upstream": upstream_map,
            "graph_downstream": downstream_map,
            "vector_chunks": vector_results,
        }

    async def _rerank(
        self, query: str, candidates: list[dict], config: Optional[LLMConfig]
    ) -> list[dict]:
        """对向量候选重排序。优先用 embedding-3，失败则规则。"""
        if len(candidates) <= 1:
            return candidates

        # 尝试 embedding-3 重排
        if config:
            texts = [c["text"] for c in candidates]
            scores = await cosine_sim_remote(query, texts, config)
            if scores and len(scores) == len(candidates):
                reranked = sorted(
                    zip(candidates, scores), key=lambda x: -x[1]
                )
                logger.info(f"🔁 Reranker(embedding-3): {len(candidates)} 候选已重排")
                return [c for c, _ in reranked]

        # 规则重排：向量距离越近分越高（cosine 距离 = 1 - 相似度，所以越小越好）
        # 加上图谱节点匹配权重
        graph_ids = set(n["id"] for n in self.graph.search_nodes(query, top_k=5))
        scored = []
        for c in candidates:
            dist = c.get("distance", 1.0)
            base = 1.0 - dist  # 相似度
            # 如果该文档关联图谱节点，加权重
            chapter = c.get("metadata", {}).get("chapter", "")
            if chapter in graph_ids:
                base += GRAPH_NODE_WEIGHT
            scored.append((c, base))
        scored.sort(key=lambda x: -x[1])
        logger.info(f"🔁 Reranker(规则): {len(candidates)} 候选已重排")
        return [c for c, _ in scored]

    def format_for_llm(self, retrieved: dict, max_chunks: int = 4) -> str:
        parts = []

        if retrieved["graph_nodes"]:
            parts.append("## 📌 知识图谱匹配节点")
            for node in retrieved["graph_nodes"][:8]:
                line = f"- [{node['id']}] {node.get('name', node['id'])} ({node.get('category', 'concept')})"
                desc = node.get("description", "")
                if desc:
                    line += f"\n  说明: {desc}"
                parts.append(line)

            for nid, ups in retrieved.get("graph_upstream", {}).items():
                if ups:
                    names = [u.get("name", u["id"]) for u in ups]
                    parts.append(f"  ⬅️ [{nid}] 的前置知识: {', '.join(names)}")
            for nid, downs in retrieved.get("graph_downstream", {}).items():
                if downs:
                    names = [d.get("name", d["id"]) for d in downs]
                    parts.append(f"  ➡️ [{nid}] 的后续知识: {', '.join(names)}")

        if retrieved["vector_chunks"]:
            parts.append("\n## 📖 教材相关片段")
            for i, chunk in enumerate(retrieved["vector_chunks"][:max_chunks], 1):
                source = chunk.get("metadata", {}).get("source", "未知")
                parts.append(f"[片段{i} | 来源: {source}]\n{chunk['text']}")

        return "\n".join(parts)


_graphrag = None

def get_graphrag() -> GraphRAGService:
    global _graphrag
    if _graphrag is None:
        _graphrag = GraphRAGService()
    return _graphrag
