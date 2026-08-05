"""配置管理 - Pydantic Settings，从 .env 加载所有环境变量"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局配置"""

    # PostgreSQL
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "ai"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    PG_POOL_MIN_SIZE: int = 5
    PG_POOL_MAX_SIZE: int = 20
    PG_STATEMENT_TIMEOUT_MS: int = 30000
    PG_HNSW_EF_SEARCH: int = 100

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # MinIO
    MINIO_ROOT_USER: str
    MINIO_ROOT_PASSWORD: str
    MINIO_ENDPOINT: str = "localhost:9000"

    # LLM
    OPENAI_BASE_URL: str
    OPENAI_API_KEY: str
    MODEL_NAME: str = "qwen3"

    # Embedding
    EMBEDDING_URL: str = "http://localhost:8001/v1"
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
    RERANKER_URL: str = "http://localhost:8002/v1"
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
    DOCLING_URL: str = "http://localhost:5001"

    # PaddleOCR
    PADDLEOCR_URL: str = "http://localhost:8118"

    # SiYuan（展示层，PostgreSQL 为 SoT）
    SIYUAN_URL: str = "http://localhost:6806"
    SIYUAN_TOKEN: str = ""
    SIYUAN_NOTEBOOK: str = "Web Summaries"
    SIYUAN_ENABLED: bool = True

    # Crawl4AI
    CRAWL4AI_URL: str = "http://localhost:11235"

    # Open WebUI（宿主机映射端口 3000 → 容器内 8084；3001 留给前端 Vite 开发服务器）
    OPENWEBUI_URL: str = "http://localhost:3000"

    # MCP 服务（FastMCP，JSON-RPC over HTTP POST /mcp）
    MCP_KNOWLEDGE_URL: str = "http://localhost:8200"
    MCP_NEWS_URL: str = "http://localhost:8201"

    # LangGraph
    LANGGRAPH_PORT: int = 8100

    # Financial Data (AKShare / yfinance)
    FINANCIAL_DATA_TIMEOUT: float = 30.0

    # Checkpoint
    CHECKPOINT_CONNSTRING: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5433/langgraph"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
