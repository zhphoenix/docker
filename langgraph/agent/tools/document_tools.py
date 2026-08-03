"""Document Tools - 文档处理语义封装（Docling 解析 + MinIO 存储 + 分片）

在 docling_tool / minio_tool / chunker 之上提供面向 Agent / Node 的
高层文档处理语义，屏蔽各底层工具的调用细节。
"""

import logging

from tools.docling import docling_tool
from tools.minio import minio_tool
from tools.chunker import chunk_markdown

logger = logging.getLogger(__name__)


class DocumentTools:
    """文档处理组合工具"""

    # ------------------------------------------------------------------
    # 解析
    # ------------------------------------------------------------------
    async def parse_to_markdown(self, file_data: bytes, filename: str = "document.pdf") -> str:
        """将文档字节流（PDF 等）解析为 Markdown 文本"""
        return await docling_tool.convert_file(file_data, filename)

    async def docling_available(self) -> bool:
        """Docling 服务是否可用"""
        return await docling_tool.health_check()

    # ------------------------------------------------------------------
    # 存储
    # ------------------------------------------------------------------
    async def save(self, bucket: str, key: str, data: bytes) -> None:
        """保存文档/文件到 MinIO"""
        await minio_tool.upload(bucket, key, data)

    async def load(self, bucket: str, key: str) -> bytes:
        """从 MinIO 读取文档/文件"""
        return await minio_tool.download(bucket, key)

    async def list(self, bucket: str, prefix: str) -> list[str]:
        """列出 MinIO 对象"""
        return await minio_tool.list_objects(bucket, prefix)

    # ------------------------------------------------------------------
    # 分片
    # ------------------------------------------------------------------
    def chunk(
        self,
        markdown: str,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[dict]:
        """将 Markdown 文本分片（默认参数从 policy 读取）"""
        return chunk_markdown(markdown, chunk_size, chunk_overlap)

    # ------------------------------------------------------------------
    # 组合：下载 → 解析 → 分片
    # ------------------------------------------------------------------
    async def ingest(
        self,
        bucket: str,
        key: str,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[dict]:
        """从 MinIO 读取文档并解析、分片

        Returns:
            [{"content","heading","chunk_index"}, ...]
        """
        data = await self.load(bucket, key)
        filename = key.split("/")[-1]
        markdown = await self.parse_to_markdown(data, filename)
        return self.chunk(markdown, chunk_size, chunk_overlap)


document_tools = DocumentTools()
