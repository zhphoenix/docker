"""配置管理 - Pydantic Settings，从 .env 加载所有环境变量"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局配置"""

    # PostgreSQL
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "ai"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

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

    # Reranker
    RERANKER_URL: str = "http://reranker:8080/v1"

    # Docling
    DOCLING_URL: str = "http://docling:5001"

    # Obsidian Local REST API
    OBSIDIAN_URL: str = "https://host.docker.internal:27124"
    OBSIDIAN_API_KEY: str = ""

    # LangGraph
    LANGGRAPH_PORT: int = 8100

    # Checkpoint
    CHECKPOINT_CONNSTRING: str = (
        "postgresql+asyncpg://postgres:postgres@postgres:5432/langgraph"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
