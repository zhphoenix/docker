"""Obsidian Tool - 通过 Local REST API 插件与 Obsidian Vault 交互

依赖：Obsidian 桌面端运行 + Local REST API 插件启用
默认端口：HTTPS 27124
认证：Bearer API_KEY

已验证 API 端点（v4.1.7）：
  GET    /vault/{path}     读取笔记
  PUT    /vault/{path}     创建/覆盖笔记（Content-Type: text/markdown）
  PATCH  /vault/{path}     追加内容（Operation: append, Content-Type: text/markdown）
  DELETE /vault/{path}     删除笔记
  GET    /vault/           列出文件
"""

import logging
from typing import Optional

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class ObsidianTool:
    """Obsidian Vault 读写，通过 Local REST API 插件"""

    def __init__(self):
        self.base_url = settings.OBSIDIAN_URL
        self.api_key = settings.OBSIDIAN_API_KEY
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取复用的 httpx 客户端"""
        if self._client is None or self._client.is_closed:
            headers = {}
            if self.api_key:
                token = self.api_key.strip()
                if not token.startswith("Bearer "):
                    token = f"Bearer {token}"
                headers["Authorization"] = token
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(15.0),
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
                verify=False,
            )
        return self._client

    async def read_note(self, path: str) -> str:
        """读取笔记全文

        Args:
            path: Vault 相对路径，如 "03_Investment/Companies/贵州茅台.md"

        Returns:
            Markdown 原始内容
        """
        client = self._get_client()
        response = await client.get(f"/vault/{path}")
        response.raise_for_status()
        return response.text

    async def write_note(self, path: str, content: str) -> dict:
        """创建或覆盖笔记

        Args:
            path: Vault 相对路径
            content: Markdown 内容

        Returns:
            {"path": str, "status": str}
        """
        client = self._get_client()
        response = await client.put(
            f"/vault/{path}",
            content=content.encode("utf-8"),
            headers={"Content-Type": "text/markdown"},
        )
        response.raise_for_status()
        return {"path": path, "status": "ok"}

    async def append_to_note(
        self,
        path: str,
        content: str,
        heading: Optional[str] = None,
    ) -> dict:
        """追加内容到笔记

        Args:
            path: Vault 相对路径
            content: 要追加的 Markdown 内容
            heading: 可选，追加到指定标题下（v4 可能不支持定向追加）

        Returns:
            {"path": str, "status": str}
        """
        client = self._get_client()
        headers = {
            "Operation": "append",
            "Target-Type": "heading",
            "Content-Type": "text/markdown",
        }
        if heading:
            headers["Target"] = heading

        response = await client.patch(
            f"/vault/{path}",
            content=content.encode("utf-8"),
            headers=headers,
        )
        response.raise_for_status()
        return {"path": path, "status": "ok"}

    async def list_notes(self, path: str = "") -> list[str]:
        """列出笔记/目录

        Args:
            path: Vault 相对目录路径，空字符串为根目录

        Returns:
            文件/目录名列表
        """
        client = self._get_client()
        response = await client.get(f"/vault/{path}")
        response.raise_for_status()
        data = response.json()
        return data.get("files", [])

    async def delete_note(self, path: str) -> dict:
        """删除笔记

        Args:
            path: Vault 相对路径

        Returns:
            {"path": str, "status": str}
        """
        client = self._get_client()
        response = await client.delete(f"/vault/{path}")
        response.raise_for_status()
        return {"path": path, "status": "deleted"}

    async def health_check(self) -> bool:
        """检查 Obsidian Local REST API 是否可用（无需认证）"""
        try:
            async with httpx.AsyncClient(verify=False, timeout=3.0) as client:
                response = await client.get(f"{self.base_url}/")
                return response.status_code == 200
        except Exception:
            return False

    async def close(self):
        """关闭客户端连接池"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# 模块级单例
obsidian_tool = ObsidianTool()
