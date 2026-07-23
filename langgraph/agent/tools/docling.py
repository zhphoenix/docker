"""Docling Tool - 封装 Docling 文档解析服务（:5001）"""

import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class DoclingTool:
    """Docling 文档解析"""

    def __init__(self):
        self.base_url = settings.DOCLING_URL
        self.timeout = 300.0  # 文档解析可能耗时较长

    async def parse(self, file_url: str) -> dict:
        """解析文档

        Args:
            file_url: 文档 URL（MinIO 内部 URL 或 HTTP URL）

        Returns:
            Docling 解析结果 dict
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/v1/parse",
                    json={"url": file_url},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            logger.error("Docling service unavailable at %s", self.base_url)
            raise


# 模块级单例
docling_tool = DoclingTool()
