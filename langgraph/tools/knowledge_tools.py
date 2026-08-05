"""Knowledge Tools - Knowledge MCP Server 调用封装

通过 MCP 协议（JSON-RPC over HTTP POST /mcp, Streamable HTTP）调用
mcp-knowledge 服务（settings.MCP_KNOWLEDGE_URL, 默认 :8200），
提供知识检索、实体/关系查询等能力。对上层 Agent / Node 隐藏 MCP 细节。

调用流程（遵循平台 health.py 既有的 MCP 约定）：
  1. initialize        → 建立会话，捕获 Mcp-Session-Id 响应头
  2. notifications/initialized
  3. tools/call        → 实际调用目标工具

支持 JSON 与 text/event-stream 两种响应体。
"""

import json
import logging
from typing import Any, Optional

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-03-26"


class KnowledgeTools:
    """Knowledge MCP Server 客户端封装"""

    def __init__(self) -> None:
        self.endpoint = f"{settings.MCP_KNOWLEDGE_URL.rstrip('/')}/mcp"
        self._timeout = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
        self._headers = {"Accept": "application/json, text/event-stream"}

    # ------------------------------------------------------------------
    # 底层 JSON-RPC
    # ------------------------------------------------------------------
    async def _post(self, payload: dict, session_id: Optional[str] = None) -> tuple[dict, Optional[str]]:
        """POST 一个 JSON-RPC 请求，返回 (解析后的 result, 会话 ID)"""
        headers = dict(self._headers)
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self.endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            new_session = resp.headers.get("Mcp-Session-Id", session_id)
            return self._parse_body(resp.text), new_session

    @staticmethod
    def _parse_body(text: str) -> dict:
        """解析响应体（兼容 JSON 与 SSE）"""
        text = text.strip()
        if not text:
            return {}
        # SSE: 取 data: 行中的 JSON
        if text.startswith("event:") or "\ndata:" in text or text.startswith("data:"):
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    data = line[len("data:"):].strip()
                    if data and data != "[DONE]":
                        try:
                            return json.loads(data)
                        except json.JSONDecodeError:
                            continue
            return {}
        return json.loads(text)

    async def _session(self) -> tuple[dict, Optional[str]]:
        """initialize 并返回会话 ID"""
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "ai-platform-agent", "version": "1.0"},
            },
        }
        _, session_id = await self._post(init_payload)
        # 发送 initialized 通知（无需响应）
        try:
            await self._post(
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                session_id=session_id,
            )
        except Exception:
            pass
        return {}, session_id

    async def call_tool(self, name: str, arguments: Optional[dict] = None) -> Any:
        """调用 Knowledge MCP Server 上的指定工具"""
        try:
            _, session_id = await self._session()
            payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
            result, _ = await self._post(payload, session_id=session_id)
            if "error" in result and result["error"]:
                logger.error("MCP tool '%s' error: %s", name, result["error"])
                return None
            return result.get("result")
        except Exception as e:
            logger.error("MCP call_tool '%s' failed: %s", name, e)
            return None

    # ------------------------------------------------------------------
    # 高层语义方法（按 mcp-knowledge 注册的 tool 名调用）
    # ------------------------------------------------------------------
    async def health(self) -> bool:
        """健康检查"""
        result = await self.call_tool("health_check")
        return result is not None

    async def search(self, query: str, limit: int = 10) -> Any:
        """语义/混合知识检索"""
        return await self.call_tool("semantic_search", {"query": query, "limit": limit})

    async def get_entity(self, name: str) -> Any:
        """按名称查询实体"""
        return await self.call_tool("search_entities", {"query": name})


knowledge_tools = KnowledgeTools()
