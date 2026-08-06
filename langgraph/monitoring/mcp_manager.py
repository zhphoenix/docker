"""MCP 连接管理 - 纳管平台 MCP 服务并维护心跳状态

将 mcp-knowledge / mcp-news 纳管到 mcp_connections 表，
通过 JSON-RPC initialize 探测连通性并记录延迟。
"""
import logging
import time

import httpx

from config.settings import settings
from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)

CHECK_TIMEOUT = 5.0

# 已知 MCP 服务（与 api/health.MCP_CHECKS 对齐）
KNOWN_MCP = [
    ("mcp-knowledge", settings.MCP_KNOWLEDGE_URL, "mcp"),
    ("mcp-news", settings.MCP_NEWS_URL, "mcp"),
]


async def seed_mcp() -> int:
    """将已知 MCP 服务写入 mcp_connections（幂等 upsert），返回纳管数量"""
    count = 0
    for name, url, kind in KNOWN_MCP:
        try:
            await postgres_tool.execute(
                "INSERT INTO mcp_connections (name, url, kind) "
                "VALUES ($1, $2, $3) "
                "ON CONFLICT (name) DO UPDATE SET url=EXCLUDED.url, kind=EXCLUDED.kind",
                name,
                url,
                kind,
            )
            count += 1
        except Exception as e:
            logger.warning("seed mcp '%s' failed: %s", name, e)
    logger.info("MCP seeded: %d servers", count)
    return count


async def _probe(name: str, url: str) -> tuple[bool, int]:
    """探测单个 MCP 服务的连通性与延迟（ms）"""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=CHECK_TIMEOUT) as client:
            response = await client.post(
                f"{url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "mcp-manager", "version": "0.1"},
                    },
                },
                headers={"Accept": "application/json, text/event-stream"},
            )
            latency = int((time.monotonic() - start) * 1000)
            return response.status_code < 500, latency
    except Exception as e:
        logger.warning("MCP probe '%s' failed: %s", name, e)
        latency = int((time.monotonic() - start) * 1000)
        return False, latency


async def check_heartbeat(name: str | None = None) -> list[dict]:
    """执行一次心跳探测并更新 mcp_connections

    Args:
        name: 指定单个服务名；None 时探测全部已知服务
    """
    targets = KNOWN_MCP if name is None else [t for t in KNOWN_MCP if t[0] == name]
    results = []
    for mcp_name, url, _kind in targets:
        up, latency = await _probe(mcp_name, url)
        status = "connected" if up else "disconnected"
        try:
            await postgres_tool.execute(
                "UPDATE mcp_connections SET status=$2, last_heartbeat=NOW(), "
                "latency_ms=$3, "
                "retry_count=CASE WHEN $2::varchar='connected' THEN 0 ELSE retry_count+1 END, "
                "updated_at=NOW() WHERE name=$1",
                mcp_name,
                status,
                latency,
            )
        except Exception as e:
            logger.warning("update mcp '%s' failed: %s", mcp_name, e)
        results.append({"name": mcp_name, "status": status, "latency_ms": latency})
    return results