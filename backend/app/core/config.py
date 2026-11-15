"""全局配置 — 从 .env 加载"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # LLM
    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"

    # Embedding
    embedding_local: bool = False
    embedding_model: str = "text-embedding-v3"
    embedding_base: str = ""       # EMBEDDING_BASE_URL：为空则回退多模态 / 主 LLM 地址
    embedding_key: str = ""        # EMBEDDING_API_KEY：为空则回退多模态 / 主 LLM Key

    # Multimodal（截图答疑，默认复用 LLM 配置；若主模型不支持视觉需单独指定）
    multimodal_api_key: str = ""
    multimodal_base_url: str = ""
    multimodal_model: str = ""

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

    def embedding_base_url(self) -> str:
        # 优先专用 Embedding 地址 → 多模态服务（智谱同一 Key 可调 embedding-3）→ 主 LLM
        return (self.embedding_base or self.multimodal_base_url or self.llm_base_url).rstrip("/")

    def embedding_api_key(self) -> str:
        return self.embedding_key or self.multimodal_api_key or self.llm_api_key


@lru_cache()
def get_settings() -> Settings:
    return Settings()
