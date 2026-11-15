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

    # Server
    port: int = 8000
    host: str = "0.0.0.0"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
