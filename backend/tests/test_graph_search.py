"""知识图谱自然语言检索测试。"""
from app.services.graph_service import get_graph


def test_search_nodes_matches_natural_language_query():
    ids = [n["id"] for n in get_graph().search_nodes("红黑树的五条性质是什么", top_k=5)]
    assert ids[0] == "red_black_tree"


def test_search_nodes_matches_english_acronyms_in_query():
    ids = [n["id"] for n in get_graph().search_nodes("DFS 和 BFS 有什么区别", top_k=5)]
    assert {"dfs", "bfs"} <= set(ids[:2])


def test_search_nodes_keeps_short_query_behavior():
    ids = [n["id"] for n in get_graph().search_nodes("红", top_k=5)]
    assert "red_black_tree" in ids
