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

    # Multimodal（截图答疑，默认复用 LLM 配置；若主模型不支持视觉需单独指定）
    multimodal_api_key: str = ""
    multimodal_base_url: str = ""
    multimodal_model: str = ""

    # Sandbox
    sandbox_timeout: int = 5
    sandbox_allowed_langs: str = "python"

    # Data
    data_dir: str = "./data"
    chroma_dir: str = "./data/chroma"
    graph_file: str = "./data/knowledge_graph.json"

    # Server
    port: int = 8000
    host: str = "0.0.0.0"

    def embedding_base_url(self) -> str:
        return self.llm_base_url

    def embedding_api_key(self) -> str:
        return self.llm_api_key


@lru_cache()
def get_settings() -> Settings:
    return Settings()
