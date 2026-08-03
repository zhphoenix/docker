"""Docling Tool - 封装 Docling 文档解析服务

支持:
  - 同步转换（小文件 < 50 页）
  - 异步转换（大文件，轮询等待）
  - 连接池 + 超时配置化
  - 健康检查
"""

import asyncio
import logging

import httpx

from config.settings import settings
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)


class DoclingTool:
    """Docling 文档解析服务客户端"""

    def __init__(self) -> None:
        self._base_url = settings.DOCLING_URL.rstrip("/")
        self._timeout = get_policy("pipeline.docling_timeout", 600.0)
        self._poll_interval = get_policy("pipeline.docling_poll_interval", 5.0)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=self._timeout,
                    write=60.0,
                    pool=10.0,
                ),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        """检查 Docling 服务可用性"""
        try:
            client = await self._get_client()
            resp = await client.get("/health", timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def convert_file(self, file_data: bytes, filename: str = "document.pdf") -> str:
        """同步转换文件 → Markdown

        Args:
            file_data: PDF 文件字节
            filename: 文件名

        Returns:
            Markdown 文本内容

        Raises:
            DoclingError: 解析失败
        """
        client = await self._get_client()

        # 小文件用同步 API
        if len(file_data) < 20 * 1024 * 1024:  # < 20MB
            return await self._convert_sync(client, file_data, filename)

        # 大文件用异步 API
        return await self._convert_async(client, file_data, filename)

    async def _convert_sync(
        self, client: httpx.AsyncClient, file_data: bytes, filename: str
    ) -> str:
        """同步转换（POST /v1/convert/file）"""
        files = {"files": (filename, file_data, "application/pdf")}
        data = {
            "to_formats": "md",
            "do_ocr": "true",
            "ocr_lang": "zh",
            "table_mode": "fast",
            "image_export_mode": "placeholder",
        }

        resp = await client.post("/v1/convert/file", files=files, data=data)
        resp.raise_for_status()
        result = resp.json()

        status = result.get("status", "")
        if status == "failure":
            errors = result.get("errors", [])
            raise DoclingError(f"Docling conversion failed: {errors}")

        md_content = result.get("document", {}).get("md_content", "")
        if not md_content:
            raise DoclingError("Docling returned empty markdown")

        logger.info(
            "Docling sync done | file=%s | time=%.1fs | chars=%d",
            filename, result.get("processing_time", 0), len(md_content),
        )
        return md_content

    async def _convert_async(
        self, client: httpx.AsyncClient, file_data: bytes, filename: str
    ) -> str:
        """异步转换（POST /v1/convert/file/async → poll → result）"""
        files = {"files": (filename, file_data, "application/pdf")}
        data = {
            "to_formats": "md",
            "do_ocr": "true",
            "ocr_lang": "zh",
            "table_mode": "fast",
            "image_export_mode": "placeholder",
        }

        # 提交任务
        resp = await client.post("/v1/convert/file/async", files=files, data=data)
        resp.raise_for_status()
        task = resp.json()
        task_id = task.get("task_id", "")
        logger.info("Docling async submitted | task_id=%s | file=%s", task_id, filename)

        # 轮询等待
        while True:
            await asyncio.sleep(self._poll_interval)
            poll_resp = await client.get(f"/v1/status/poll/{task_id}")
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()
            task_status = poll_data.get("task_status", "")

            if task_status == "success":
                break
            elif task_status == "failure":
                raise DoclingError(f"Docling async task failed: {task_id}")

        # 获取结果
        result_resp = await client.get(f"/v1/result/{task_id}")
        result_resp.raise_for_status()
        result = result_resp.json()

        md_content = result.get("document", {}).get("md_content", "")
        if not md_content:
            raise DoclingError("Docling async returned empty markdown")

        logger.info(
            "Docling async done | task_id=%s | chars=%d", task_id, len(md_content)
        )
        return md_content


class DoclingError(Exception):
    """Docling 解析错误"""
    pass


# 模块级单例
docling_tool = DoclingTool()
