"""MinIO Tool - 封装 MinIO 文件操作（:9000）"""

import asyncio
import logging
from io import BytesIO

from minio import Minio
from minio.error import S3Error

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

    async def delete(self, bucket: str, key: str) -> None:
        """删除对象最新版本；对象不存在视为成功（幂等）"""
        def _del():
            try:
                self.client.remove_object(bucket, key)
            except S3Error as e:
                if e.code != "NoSuchKey":
                    raise
        await asyncio.to_thread(_del)
        logger.info("Deleted %s/%s", bucket, key)

    async def delete_versions(self, bucket: str, key: str) -> int:
        """彻底删除对象（含所有历史版本），返回删除的版本数

        版本控制（mc version enable）开启后，remove_object 只删除最新版本，
        历史版本仍残留。本方法通过 list_objects(include_version=True) 列出
        该对象的所有版本（含删除标记），逐个删除以彻底清除。
        """
        def _purge() -> int:
            removed = 0
            try:
                objs = self.client.list_objects(
                    bucket, prefix=key, recursive=True, include_version=True
                )
                for obj in objs:
                    if obj.object_name != key:
                        continue
                    try:
                        self.client.remove_object(
                            bucket, key, version_id=obj.version_id
                        )
                        removed += 1
                    except S3Error as e:
                        if e.code != "NoSuchKey":
                            raise
            except Exception:
                # list 失败（如对象不存在）时兜底删除最新版本
                try:
                    self.client.remove_object(bucket, key)
                    removed += 1
                except S3Error as e:
                    if e.code != "NoSuchKey":
                        raise
            logger.info("Purged %s/%s (versions=%d)", bucket, key, removed)
            return removed
        return await asyncio.to_thread(_purge)

    async def exists(self, bucket: str, key: str) -> bool:
        """检查对象是否存在"""
        def _stat():
            try:
                self.client.stat_object(bucket, key)
                return True
            except Exception:
                return False
        return await asyncio.to_thread(_stat)

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
