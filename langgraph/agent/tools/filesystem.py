"""Filesystem Tool - 预留，本地文件系统操作"""

import logging

logger = logging.getLogger(__name__)


class FilesystemTool:
    """本地文件系统操作（预留）"""

    async def read_file(self, path: str) -> str:
        """读取文件"""
        raise NotImplementedError("Filesystem tool not yet implemented")

    async def write_file(self, path: str, content: str) -> None:
        """写入文件"""
        raise NotImplementedError("Filesystem tool not yet implemented")

    async def list_dir(self, path: str) -> list[str]:
        """列出目录"""
        raise NotImplementedError("Filesystem tool not yet implemented")


filesystem_tool = FilesystemTool()
