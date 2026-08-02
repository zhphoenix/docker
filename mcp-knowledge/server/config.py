"""MCP Knowledge Server 配置 - Pydantic Settings"""

from pydantic_settings import BaseSettings


class MCPSettings(BaseSettings):
    """MCP Knowledge Server 配置"""

    # PostgreSQL 连接池（独立于 langgraph 服务）
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "ai"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    PG_POOL_MIN_SIZE: int = 5
    PG_POOL_MAX_SIZE: int = 30
    PG_STATEMENT_TIMEOUT_MS: int = 15000

    # Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333

    # Embedding
    EMBEDDING_URL: str = "http://embedding:8080/v1"
    EMBEDDING_MODEL: str = "embedding"
    EMBEDDING_TIMEOUT: float = 120.0
    EMBEDDING_MAX_CONCURRENCY: int = 8

    # 缓存
    CACHE_TTL_SECONDS: int = 60
    CACHE_MAX_SIZE: int = 1024
    CACHE_ENABLED: bool = True

    # LLM（GraphRAG 融合推理，OpenAI 兼容 API）
    OPENAI_BASE_URL: str = "http://localhost:8080/v1"
    OPENAI_API_KEY: str = "EMPTY"
    MODEL_NAME: str = "qwen3"
    LLM_TIMEOUT: float = 120.0
    LLM_MAX_RETRIES: int = 3

    # MCP Server
    MCP_HOST: str = "0.0.0.0"
    MCP_PORT: int = 8200

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = MCPSettings()
