"""pytest 全局夹具 — 在导入 app 前重定向数据目录，保证测试隔离"""
import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="codementor_test_")
_DATA = os.path.join(_TMP, "data")

# 拷贝真实 data（图谱 + 向量库），避免测试触发 LLM 种子流程
_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
if os.path.isdir(_SRC):
    shutil.copytree(_SRC, _DATA, dirs_exist_ok=True)
else:
    os.makedirs(_DATA, exist_ok=True)

os.environ["DATA_DIR"] = _DATA
os.environ["CHROMA_DIR"] = os.path.join(_DATA, "chroma")
os.environ["GRAPH_FILE"] = os.path.join(_DATA, "knowledge_graph.json")
os.environ["RATE_LIMIT_PER_MIN"] = "100000"   # API 测试不受限流干扰
os.environ["SANDBOX_MODE"] = "subprocess"      # 测试环境无 Docker 依赖
os.environ["AUTH_SECRET"] = "test-secret"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def teacher_headers(client):
    r = client.post("/api/auth/login", json={"username": "teacher", "password": "123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def student_headers(client):
    r = client.post("/api/auth/login", json={"username": "student", "password": "123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
