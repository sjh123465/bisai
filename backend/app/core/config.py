"""全局配置 — 从 .env 加载"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # 模型 Key 由请求头 X-LLM-* 提供，服务端不保存、不读取任何 LLM Key。

    # Sandbox
    sandbox_timeout: int = 5
    sandbox_allowed_langs: str = "python"
    # 沙箱隔离模式: auto(有 Docker 用 Docker，否则 subprocess) / docker / subprocess
    sandbox_mode: str = "auto"
    sandbox_docker_image: str = "python:3.11-slim"

    # 安全
    auth_secret: str = ""                      # HMAC 签名密钥，留空用开发默认
    rate_limit_per_min: int = 60               # 每 IP 每分钟请求上限

    # Data
    data_dir: str = "./data"
    chroma_dir: str = "./data/chroma"
    graph_file: str = "./data/knowledge_graph.json"

    # 用户书架（上传的电子书）
    books_dir: str = "./data/books"
    book_max_mb: int = 50                      # 单个文件上限
    book_chunk_size: int = 500                 # 目标切片字数
    book_chunk_overlap: int = 80               # 切片重叠字数
    book_embed_batch: int = 32                 # 编码/入库批大小

    # Embedding 模型下载源（国内默认走镜像，官方源可设为 https://huggingface.co）
    hf_endpoint: str = "https://hf-mirror.com"
    # FastEmbed 模型缓存目录（首次启动下载 bge-small，约 91MB）
    embedding_cache_dir: str = "./data/models"

    # Server
    port: int = 8000
    host: str = "0.0.0.0"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
