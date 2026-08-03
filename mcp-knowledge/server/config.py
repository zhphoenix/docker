"""MCP Knowledge Server 配置 - Pydantic Settings"""

from pydantic_settings import BaseSettings


class MCPSettings(BaseSettings):
    """MCP Knowledge Server 配置"""

    # PostgreSQL 连接池（独立于 langgraph 服务）
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "ai"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    PG_POOL_MIN_SIZE: int = 5
    PG_POOL_MAX_SIZE: int = 30
    PG_STATEMENT_TIMEOUT_MS: int = 15000

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # Embedding
    EMBEDDING_URL: str = "http://localhost:8001/v1"
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

    # ── SiYuan Knowledge Workspace（展示层，PostgreSQL 为 SoT）──
    SIYUAN_URL: str = "http://localhost:6806"
    SIYUAN_ACCESS_AUTH_CODE: str = ""
    SIYUAN_CONCURRENCY: int = 4          # API 并发上限（Semaphore 限流）
    SIYUAN_QUEUE_SIZE: int = 100         # 渲染队列背压上限
    SIYUAN_MAX_RETRIES: int = 3          # 指数退避重试次数
    SIYUAN_TIMEOUT: float = 30.0         # 单请求超时（秒）
    SIYUAN_SYNC_USER: str = "ai-platform"  # last_modified_by / 文档 created_by

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = MCPSettings()
