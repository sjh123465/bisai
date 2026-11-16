"""Embedding / 向量库单元测试 — 不依赖真实模型下载。"""
import asyncio
import math

import pytest

import app.services.embedding_service as embedding_service
import app.services.vector_service as vector_service


class _FakeEmbeddingModel:
    """记录输入文本的假模型，用于验证 query/passage 分流与小写归一化。"""

    def __init__(self):
        self.calls = []

    def passage_embed(self, texts):
        self.calls.append(("passage", list(texts)))
        return iter([[1.0] + [0.0] * 511 for _ in texts])

    def query_embed(self, texts):
        self.calls.append(("query", list(texts)))
        return iter([[0.0, 1.0] + [0.0] * 510 for _ in texts])


def test_embed_local_lowercases_and_routes_query(monkeypatch):
    fake = _FakeEmbeddingModel()
    monkeypatch.setattr(embedding_service, "_get_model", lambda: fake)

    vecs = embedding_service.embed_local(["DFS 和 HTTP", "Python"], is_query=True)

    assert fake.calls == [("query", ["dfs 和 http", "python"])]
    assert len(vecs) == 2
    assert all(len(v) == 512 for v in vecs)


def test_embed_local_routes_passage(monkeypatch):
    fake = _FakeEmbeddingModel()
    monkeypatch.setattr(embedding_service, "_get_model", lambda: fake)

    embedding_service.embed_local(["红黑树"])

    assert fake.calls == [("passage", ["红黑树"])]


def test_embed_local_falls_back_to_normalized_hash(monkeypatch):
    monkeypatch.setattr(embedding_service, "_get_model", lambda: None)

    vecs = embedding_service.embed_local(["红黑树", "AVL"])

    assert len(vecs) == 2
    assert all(len(v) == 512 for v in vecs)
    assert all(math.isclose(sum(x * x for x in v) ** 0.5, 1.0, rel_tol=1e-9) for v in vecs)


def test_embedding_signature_tracks_backend(monkeypatch):
    monkeypatch.setattr(embedding_service, "_get_model", lambda: object())
    assert embedding_service.embedding_signature() == ("BAAI/bge-small-zh-v1.5", 512)

    monkeypatch.setattr(embedding_service, "_get_model", lambda: None)
    assert embedding_service.embedding_signature() == ("hash-bigram-v1", 512)


class _Cfg:
    def __init__(self, chroma_dir):
        self.chroma_dir = chroma_dir


def _fake_embed(texts, *, is_query=False):
    """固定 512 维向量：query 用 e2，文档用 e1。"""
    base = [0.0, 1.0] if is_query else [1.0, 0.0]
    return [base + [0.0] * 510 for _ in texts]


def test_vector_store_uses_query_and_passage_embeddings(monkeypatch, tmp_path):
    calls = []

    def rec_embed(texts, *, is_query=False):
        calls.append((is_query, list(texts)))
        return _fake_embed(texts, is_query=is_query)

    monkeypatch.setattr(vector_service, "get_settings", lambda: _Cfg(str(tmp_path / "chroma")))
    monkeypatch.setattr(vector_service, "embedding_signature", lambda: ("test-model", 512))
    monkeypatch.setattr(vector_service, "embed_local", rec_embed)

    store = vector_service.VectorStore()
    asyncio.run(store.add_documents([{"id": "d1", "text": "红黑树"}]))
    asyncio.run(store.query("红黑树性质", top_k=1))

    assert store.collection.metadata["embedding_model"] == "test-model"
    assert store.collection.metadata["embedding_dim"] == 512
    assert calls == [(False, ["红黑树"]), (True, ["红黑树性质"])]


def test_vector_store_rebuilds_on_signature_change(monkeypatch, tmp_path):
    chroma_dir = str(tmp_path / "chroma")
    monkeypatch.setattr(vector_service, "get_settings", lambda: _Cfg(chroma_dir))
    monkeypatch.setattr(vector_service, "embed_local", _fake_embed)

    monkeypatch.setattr(vector_service, "embedding_signature", lambda: ("old-model", 512))
    old = vector_service.VectorStore()
    asyncio.run(old.add_documents([{"id": "d1", "text": "红黑树"}]))
    assert old.count() == 1

    monkeypatch.setattr(vector_service, "embedding_signature", lambda: ("new-model", 512))
    new = vector_service.VectorStore()

    assert new.count() == 0
    assert new.collection.metadata["embedding_model"] == "new-model"
