"""MinIO Tool - 封装 MinIO 文件操作（:9000）"""

import asyncio
import logging
from io import BytesIO

from minio import Minio

from config.settings import settings

logger = logging.getLogger(__name__)


class MinIOTool:
    """MinIO 文件操作"""

    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ROOT_USER,
            secret_key=settings.MINIO_ROOT_PASSWORD,
            secure=False,
        )

    async def upload(self, bucket: str, key: str, data: bytes) -> None:
        """上传文件"""
        await asyncio.to_thread(
            self.client.put_object, bucket, key, BytesIO(data), len(data)
        )
        logger.info("Uploaded %s/%s (%d bytes)", bucket, key, len(data))

    async def download(self, bucket: str, key: str) -> bytes:
        """下载文件"""
        def _download():
            response = self.client.get_object(bucket, key)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        return await asyncio.to_thread(_download)

    async def list_objects(self, bucket: str, prefix: str) -> list[str]:
        """列出对象"""
        def _list():
            objects = self.client.list_objects(bucket, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects]
        return await asyncio.to_thread(_list)

    async def health_check(self) -> bool:
        """检查 MinIO 连通性"""
        try:
            buckets = await asyncio.to_thread(self.client.list_buckets)
            return buckets is not None
        except Exception:
            return False


# 模块级单例
minio_tool = MinIOTool()
