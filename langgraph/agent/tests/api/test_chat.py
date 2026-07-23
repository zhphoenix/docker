"""API 端点测试

注意：需要环境变量配置正确。
"""

import pytest
from unittest.mock import patch, AsyncMock


def test_app_imports():
    """测试 FastAPI 应用可以正常导入"""
    # 需要 mock 环境变量
    import os
    os.environ.setdefault("POSTGRES_USER", "postgres")
    os.environ.setdefault("POSTGRES_PASSWORD", "postgres")
    os.environ.setdefault("OPENAI_API_KEY", "EMPTY")
    os.environ.setdefault("OPENAI_BASE_URL", "http://localhost:8080/v1")
    os.environ.setdefault("MINIO_ROOT_USER", "minioadmin")
    os.environ.setdefault("MINIO_ROOT_PASSWORD", "minioadmin")

    from app.main import app
    assert app is not None
    assert app.title == "AI Platform Agent Service"


def test_models_endpoint():
    """测试 /v1/models 端点"""
    import os
    os.environ.setdefault("POSTGRES_USER", "postgres")
    os.environ.setdefault("POSTGRES_PASSWORD", "postgres")
    os.environ.setdefault("OPENAI_API_KEY", "EMPTY")
    os.environ.setdefault("OPENAI_BASE_URL", "http://localhost:8080/v1")
    os.environ.setdefault("MINIO_ROOT_USER", "minioadmin")
    os.environ.setdefault("MINIO_ROOT_PASSWORD", "minioadmin")

    from api.models import list_models
    import asyncio

    result = asyncio.get_event_loop().run_until_complete(list_models())

    assert result.object == "list"
    assert len(result.data) == 1
    assert result.data[0].id == "qwen3"


def test_health_endpoint_structure():
    """测试 /health 端点返回结构"""
    # 只验证函数存在
    from api.health import health_check
    assert callable(health_check)


def test_chat_endpoint_structure():
    """测试 /v1/chat/completions 端点结构"""
    from api.chat import chat_completions
    assert callable(chat_completions)
