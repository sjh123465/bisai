"""知识图谱路由"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.services.graph_service import get_graph

router = APIRouter(prefix="/api/knowledge", tags=["知识图谱"])


class NodeAdd(BaseModel):
    node_id: str
    name: str
    category: str = "concept"
    description: str = ""


class EdgeAdd(BaseModel):
    source: str
    target: str
    relation: str = "related"


@router.get("/stats")
async def graph_stats():
    """图谱统计"""
    g = get_graph()
    return g.get_stats()


@router.get("/nodes")
async def list_nodes(category: Optional[str] = None, top: int = 100):
    """列出所有节点，可按 category 过滤"""
    g = get_graph()
    nodes = g.all_nodes()
    if category:
        nodes = [n for n in nodes if n.get("category") == category]
    return nodes[:top]


@router.get("/search")
async def search(query: str, top_k: int = 10):
    """模糊搜索节点"""
    g = get_graph()
    return g.search_nodes(query, top_k=top_k)


@router.get("/node/{node_id}")
async def get_node_detail(node_id: str, depth: int = 2):
    """获取节点详情 + 多跳邻居"""
    g = get_graph()
    node = g.get_node(node_id)
    if not node:
        return {"error": "节点不存在"}
    neighbors = g.get_neighbors(node_id, max_depth=depth)
    upstream = g.get_upstream(node_id)
    downstream = g.get_downstream(node_id)
    return {
        "node": node,
        "upstream": upstream,
        "downstream": downstream,
        "neighbors": neighbors,
    }


@router.get("/graph")
async def export_graph():
    """导出完整图（前端可视化用）"""
    g = get_graph()
    nodes = [{"id": nid, **attrs} for nid, attrs in g.graph.nodes(data=True)]
    edges = [{"source": u, "target": v, **attrs} for u, v, attrs in g.graph.edges(data=True)]
    return {"nodes": nodes, "edges": edges}


@router.post("/nodes")
async def add_node(node: NodeAdd):
    g = get_graph()
    g.add_node(node.node_id, node.name, node.category, description=node.description)
    g.save()
    return {"ok": True}


@router.post("/edges")
async def add_edge(edge: EdgeAdd):
    g = get_graph()
    g.add_edge(edge.source, edge.target, edge.relation)
    g.save()
    return {"ok": True}
