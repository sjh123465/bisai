"""知识图谱服务 — 基于 NetworkX + JSON 持久化
支持：节点增删、关系增删、多跳邻居检索、子图序列化
"""
import json
import os
import networkx as nx
from typing import Optional
from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger("graph")


class KnowledgeGraph:
    def __init__(self):
        self.cfg = get_settings()
        os.makedirs(self.cfg.data_dir, exist_ok=True)
        self.graph = nx.DiGraph()
        self._load()

    # ---------- 持久化 ----------
    def _load(self):
        if os.path.exists(self.cfg.graph_file):
            try:
                with open(self.cfg.graph_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for node in data.get("nodes", []):
                    self.graph.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
                for edge in data.get("edges", []):
                    attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
                    self.graph.add_edge(edge["source"], edge["target"], **attrs)
                logger.info(
                    f"📂 图谱加载完成: {self.graph.number_of_nodes()} 节点, "
                    f"{self.graph.number_of_edges()} 边"
                )
            except Exception as e:
                logger.error(f"图谱加载失败: {e}")
                self.graph = nx.DiGraph()
        else:
            logger.info("📂 未找到图谱文件，创建空图谱")

    def save(self):
        data = {
            "nodes": [{"id": nid, **attrs} for nid, attrs in self.graph.nodes(data=True)],
            "edges": [{"source": u, "target": v, **attrs} for u, v, attrs in self.graph.edges(data=True)],
        }
        with open(self.cfg.graph_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 图谱已保存: {self.graph.number_of_nodes()} 节点, {self.graph.number_of_edges()} 边")

    # ---------- 基础操作 ----------
    def add_node(self, node_id: str, name: str, category: str = "concept", **attrs):
        self.graph.add_node(node_id, name=name, category=category, **attrs)

    def add_edge(self, source: str, target: str, relation: str = "related"):
        self.graph.add_edge(source, target, relation=relation)

    def get_node(self, node_id: str) -> Optional[dict]:
        if node_id not in self.graph:
            return None
        return {"id": node_id, **self.graph.nodes[node_id]}

    def all_nodes(self) -> list[dict]:
        return [{"id": nid, **attrs} for nid, attrs in self.graph.nodes(data=True)]

    # ---------- 检索 ----------
    def search_nodes(self, query: str, top_k: int = 5) -> list[dict]:
        """模糊搜索节点（ID / name），支持双向包含。

        既支持「红」→「红黑树」这类短查询，也支持
        「红黑树的五条性质是什么」→「红黑树」这类自然语言长问句：
        后者要求节点名出现在问题里，否则整句永远无法成为节点名的子串。
        """
        q = (query or "").strip().lower()
        if not q:
            return []
        scored = []
        for nid, attrs in self.graph.nodes(data=True):
            nid_l = nid.lower()
            name = str(attrs.get("name", "")).lower()
            score = 0.0
            if q == nid_l or q == name:
                score += 12
            elif q in nid_l:
                score += 6
            elif q in name:
                score += 5
            # 反向包含：节点名出现在问题里（长问句的主要命中路径）
            if name and name in q and name != q:
                score += 6 + min(len(name), 6)
            if nid_l in q and nid_l != q:
                score += 5
            if score > 0:
                scored.append((score, len(name), {"id": nid, **attrs}))
        # 同名/高分时优先更长的节点名，避免「堆」压过「堆排序」这类情况
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [item[2] for item in scored[:top_k]]

    def get_neighbors(self, node_id: str, max_depth: int = 2) -> list[dict]:
        """获取节点的多跳邻居，返回子图节点列表"""
        if node_id not in self.graph:
            return []
        visited = {node_id}
        queue = [(node_id, 0)]
        neighbors = []
        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            # 前驱 + 后继
            for n in list(self.graph.successors(curr)) + list(self.graph.predecessors(curr)):
                if n not in visited:
                    visited.add(n)
                    neighbors.append({"id": n, **self.graph.nodes[n]})
                    queue.append((n, depth + 1))
        return neighbors

    def get_upstream(self, node_id: str) -> list[dict]:
        """获取前置节点（有向图前驱）"""
        if node_id not in self.graph:
            return []
        return [{"id": p, **self.graph.nodes[p]} for p in self.graph.predecessors(node_id)]

    def get_downstream(self, node_id: str) -> list[dict]:
        """获取后继节点（有向图后继）"""
        if node_id not in self.graph:
            return []
        return [{"id": s, **self.graph.nodes[s]} for s in self.graph.successors(node_id)]

    def get_stats(self) -> dict:
        """返回图谱统计"""
        categories = {}
        for _, attrs in self.graph.nodes(data=True):
            cat = attrs.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "categories": categories,
        }


_graph = None


def get_graph() -> KnowledgeGraph:
    global _graph
    if _graph is None:
        _graph = KnowledgeGraph()
    return _graph
