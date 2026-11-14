"""GraphRAG 混合检索 — 图谱多跳 + 向量检索融合"""
from typing import Optional
from app.services.graph_service import get_graph
from app.services.vector_service import get_vector
from app.core.logger import get_logger

logger = get_logger("graphrag")


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
    ) -> dict:
        """
        混合检索：
        1. 图谱节点模糊匹配 → 取节点的多跳邻居
        2. 向量检索 → 取最相关的文档片段
        3. 融合返回
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
            # 多跳邻居
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

        # 2. 向量检索
        vector_results = await self.vector.query(query, top_k=vector_top_k)

        # 3. 融合
        return {
            "query": query,
            "graph_nodes": graph_context,
            "graph_upstream": upstream_map,
            "graph_downstream": downstream_map,
            "vector_chunks": vector_results,
        }

    def format_for_llm(self, retrieved: dict, max_chunks: int = 4) -> str:
        """将检索结果格式化为 LLM 可读的上下文文本"""
        parts = []

        # 图谱节点
        if retrieved["graph_nodes"]:
            parts.append("## 📌 知识图谱匹配节点")
            for node in retrieved["graph_nodes"][:8]:
                line = f"- [{node['id']}] {node.get('name', node['id'])} ({node.get('category', 'concept')})"
                desc = node.get("description", "")
                if desc:
                    line += f"\n  说明: {desc}"
                parts.append(line)

            # 前后置关系
            for nid, ups in retrieved.get("graph_upstream", {}).items():
                if ups:
                    names = [u.get("name", u["id"]) for u in ups]
                    parts.append(f"  ⬅️ [{nid}] 的前置知识: {', '.join(names)}")
            for nid, downs in retrieved.get("graph_downstream", {}).items():
                if downs:
                    names = [d.get("name", d["id"]) for d in downs]
                    parts.append(f"  ➡️ [{nid}] 的后续知识: {', '.join(names)}")

        # 向量片段
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
