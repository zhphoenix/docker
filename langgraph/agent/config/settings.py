"""配置管理 - Pydantic Settings，从 .env 加载所有环境变量"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局配置"""

    # PostgreSQL
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "ai"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    PG_POOL_MIN_SIZE: int = 5
    PG_POOL_MAX_SIZE: int = 20
    PG_STATEMENT_TIMEOUT_MS: int = 30000
    PG_HNSW_EF_SEARCH: int = 100

    # Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333

    # MinIO
    MINIO_ROOT_USER: str
    MINIO_ROOT_PASSWORD: str
    MINIO_ENDPOINT: str = "minio:9000"

    # LLM
    OPENAI_BASE_URL: str
    OPENAI_API_KEY: str
    MODEL_NAME: str = "qwen3"

    # Embedding
    EMBEDDING_URL: str = "http://embedding:8080/v1"
    EMBEDDING_MODEL: str = "embedding"
    EMBEDDING_CONNECT_TIMEOUT: float = 5.0
    EMBEDDING_READ_TIMEOUT: float = 120.0
    EMBEDDING_WRITE_TIMEOUT: float = 30.0
    EMBEDDING_POOL_TIMEOUT: float = 5.0
    EMBEDDING_MAX_CONNECTIONS: int = 100
    EMBEDDING_KEEPALIVE_CONNECTIONS: int = 20
    EMBEDDING_MAX_CONCURRENCY: int = 8
    EMBEDDING_MAX_RETRIES: int = 3

    # Reranker
    RERANKER_URL: str = "http://reranker:8080/v1"
    RERANKER_MODEL: str = "reranker"
    RERANKER_CONNECT_TIMEOUT: float = 5.0
    RERANKER_READ_TIMEOUT: float = 120.0
    RERANKER_WRITE_TIMEOUT: float = 30.0
    RERANKER_POOL_TIMEOUT: float = 5.0
    RERANKER_MAX_CONNECTIONS: int = 20
    RERANKER_KEEPALIVE_CONNECTIONS: int = 5
    RERANKER_MAX_CONCURRENCY: int = 2
    RERANKER_MAX_RETRIES: int = 2
    RERANK_TOP_K: int = 5
    RERANK_MAX_CHARS: int = 1000

    # Docling
    DOCLING_URL: str = "http://docling:5001"

    # Obsidian Local REST API
    # 容器化部署（obsidian-remote），挂载 data/obsidian_vault，经 ai-platform 网络以容器名访问
    # 插件提供 HTTPS :27124（自签证书，obsidian.py 已设 verify=False），绑定 0.0.0.0，与 MCP 配置一致
    OBSIDIAN_URL: str = "https://obsidian:27124"
    OBSIDIAN_API_KEY: str = ""

    # LangGraph
    LANGGRAPH_PORT: int = 8100

    # Financial Data (AKShare / yfinance)
    FINANCIAL_DATA_TIMEOUT: float = 30.0

    # Checkpoint
    CHECKPOINT_CONNSTRING: str = (
        "postgresql+asyncpg://postgres:postgres@postgres:5432/langgraph"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
