"""MCP News Server 配置 - Pydantic Settings"""

from pydantic_settings import BaseSettings


class NewsMCPSettings(BaseSettings):
    """MCP News Server 配置"""

    # PostgreSQL 连接池（独立于 langgraph 服务）
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "ai"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    PG_POOL_MIN_SIZE: int = 3
    PG_POOL_MAX_SIZE: int = 15
    PG_STATEMENT_TIMEOUT_MS: int = 15000

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # MCP Server
    MCP_HOST: str = "0.0.0.0"
    MCP_PORT: int = 8201

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = NewsMCPSettings()
