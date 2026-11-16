"""书架 API 与知识源组合测试。"""
import asyncio
import time


def _upload(client, headers, name: str, content: bytes):
    return client.post(
        "/api/books",
        headers=headers,
        files={"file": (name, content, "text/plain")},
    )


def _wait_finished(client, headers, book_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/books/{book_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        book = resp.json()["book"]
        if book["status"] in ("ready", "failed"):
            return book
        time.sleep(0.2)
    raise AssertionError("书籍处理超时")


def test_book_upload_ingest_scope_and_delete(client, student_headers, teacher_headers):
    text = (
        "第1章 树\n\n红黑树是一种自平衡二叉搜索树，根节点是黑色，红节点的子节点必须是黑色。\n\n"
        "第2章 操作系统\n\n死锁的四个必要条件是互斥、占有并等待、不可剥夺、循环等待。"
    ).encode("utf-8")
    resp = _upload(client, student_headers, "学生笔记.txt", text)
    assert resp.status_code == 200, resp.text
    book = resp.json()["book"]
    assert book["format"] == "TXT"
    assert book["status"] in ("pending", "parsing", "embedding", "ready")

    ready = _wait_finished(client, student_headers, book["id"])
    assert ready["status"] == "ready", ready
    assert ready["chunk_count"] >= 1
    assert ready["title"] == "学生笔记"

    listing = client.get("/api/books", headers=student_headers)
    assert listing.status_code == 200
    data = listing.json()
    assert any(b["id"] == book["id"] for b in data["books"])
    assert "PDF" in data["supported_formats"] and "Word" in data["supported_formats"]

    # 只有上传者可以访问
    assert client.get(f"/api/books/{book['id']}", headers=teacher_headers).status_code == 403
    assert client.delete(f"/api/books/{book['id']}", headers=teacher_headers).status_code == 403

    # 书架作为唯一知识源：不返回内置图谱节点
    from app.knowledge.router import get_knowledge_router
    router = get_knowledge_router()
    books_only = asyncio.run(router.retrieve(
        "红黑树有哪些性质", user_id="student", source_ids=["books"],
        book_ids=[book["id"]], top_k=3,
    ))
    assert books_only.chunks
    assert all(c.source_type == "book" for c in books_only.chunks)
    assert not books_only.graph_nodes
    assert "学生笔记" in router.format_for_llm(books_only)

    # 内置课程 + 书架：两路都能出结果（内置库在测试启动时已灌入 14 条）
    mixed = asyncio.run(router.retrieve(
        "红黑树有哪些性质", user_id="student", source_ids=["builtin", "books"],
        book_ids=[book["id"]], top_k=3,
    ))
    assert any(c.source_type == "book" for c in mixed.chunks)
    assert any(c.source_type == "builtin" for c in mixed.chunks)
    assert mixed.graph_nodes

    # 重复上传 → 409
    dup = _upload(client, student_headers, "学生笔记.txt", text)
    assert dup.status_code == 409

    # 删除后不可见
    assert client.delete(f"/api/books/{book['id']}", headers=student_headers).status_code == 200
    assert client.get(f"/api/books/{book['id']}", headers=student_headers).status_code == 404


def test_book_rejects_unsupported_format(client, student_headers):
    resp = _upload(client, student_headers, "malware.exe", b"MZ...")
    assert resp.status_code == 400
    assert "不支持" in resp.json()["detail"]


def test_book_requires_login(client):
    resp = client.get("/api/books")
    assert resp.status_code == 401


def test_empty_book_scope_returns_empty_instead_of_falling_back():
    from app.knowledge.router import get_knowledge_router
    result = asyncio.run(get_knowledge_router().retrieve(
        "红黑树", user_id="student", source_ids=["books"], book_ids=[], top_k=3
    ))
    assert result.chunks == []
    assert result.graph_nodes == []


def test_knowledge_source_plugin_can_be_registered():
    from app.knowledge.base import KnowledgeChunk, KnowledgeResult
    from app.knowledge.registry import register_knowledge_source
    from app.knowledge.router import KnowledgeRouter

    class FakeSource:
        id = "fake_source"
        name = "Fake Source"
        kind = "test"

        async def retrieve(self, query, **kwargs):
            return KnowledgeResult(chunks=[KnowledgeChunk(
                text="fake knowledge",
                source_type="fake",
                source_name="Fake Source",
                chunk_id="f1",
            )])

    register_knowledge_source("fake_source", FakeSource, name="Fake Source", kind="test")
    result = asyncio.run(KnowledgeRouter().retrieve("anything", source_ids=["fake_source"]))
    assert [c.text for c in result.chunks] == ["fake knowledge"]
