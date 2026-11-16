"""预热本地 Embedding 模型（部署 / 断网演示前执行）。

用法（在 backend 目录下）:
    python scripts/warm_embedding.py

成功时退出码 0；若降级为哈希兜底（模型未就绪）则退出码 1。
"""
import sys
from pathlib import Path

# 允许直接运行 scripts/ 下的脚本
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.services.embedding_service import embed_local, warm_up


def main() -> int:
    cfg = get_settings()
    print(f"模型缓存目录: {cfg.embedding_cache_dir}")
    print(f"下载源(HF_ENDPOINT): {cfg.hf_endpoint}")
    name, dim = warm_up()
    vecs = embed_local(["快速排序", "Red-Black Tree"], is_query=True)
    print(f"后端: {name} | 维度: {dim} | 试编码: {len(vecs)} 条, {len(vecs[0])} 维")
    if name.startswith("hash"):
        print("❌ 模型未就绪，已降级为哈希兜底。请检查网络/缓存后重试。")
        return 1
    print("✅ 本地 Embedding 已就绪，断网环境可直接启动。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
