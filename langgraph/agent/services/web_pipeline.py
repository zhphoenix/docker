"""Web Pipeline — 网页抓取数据流

基于 Crawl4AI 集成设计规范:
- 第10节: 数据流规范（网页 → Crawl4AI → Markdown → MinIO → Metadata → Chunk → Embedding → Qdrant）
- 第13节: Pipeline 规范
- 第18.2节: Phase 1 弹性抓取
- 第18.3节: Phase 2 增量变更检测

职责:
- 编排抓取 → 存储 → 元数据更新流程
- 失败页面不进入后续 Pipeline
- 死信页面标记并记录
- 增量模式：仅处理变化内容

用法:
    pipeline = WebPipeline.from_config(config)

    # 全量模式
    result = await pipeline.process_url("https://...")

    # 增量模式
    result = await pipeline.process_url_incremental("https://...")
"""

from __future__ import annotations

import io
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

from ingestion.web.chunker import WebChunker
from ingestion.web.diff_detector import ChangeStatus, DiffDetector

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    """Pipeline 执行统计"""

    total: int = 0
    success: int = 0
    failed: int = 0
    dead: int = 0
    skipped: int = 0
    # Phase 2 增量统计
    unchanged: int = 0
    changed: int = 0
    new: int = 0
    removed: int = 0
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()

    def summary(self) -> str:
        return (
            f"Pipeline 完成: total={self.total}, success={self.success}, "
            f"failed={self.failed}, dead={self.dead}, skipped={self.skipped}, "
            f"unchanged={self.unchanged}, changed={self.changed}, "
            f"new={self.new}, removed={self.removed}, "
            f"duration={self.duration_seconds:.1f}s"
        )


class WebPipeline:
    """网页抓取 Pipeline

    数据流:
        URL → Crawl4AI Provider → Markdown → MinIO → PostgreSQL (web_pages)

    失败处理:
        - 失败页面不进入 MinIO
        - 记录错误到 PostgreSQL
        - 死信页面标记 page_status='dead'
    """

    def __init__(
        self,
        provider,  # Crawl4AIProvider
        minio_client,  # MinIO 客户端
        pg_pool,  # asyncpg 连接池
        bucket: str = "documents",
        prefix: str = "website/",
        diff_detector: DiffDetector | None = None,
        chunker: WebChunker | None = None,
        embed_url: str = "http://localhost:8001/v1/embeddings",
        embed_model: str = "qwen3-embedding",
        embed_batch_size: int = 16,
        embed_max_chars: int = 800,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        qdrant_collection: str = "web_pages",
    ):
        """
        Args:
            provider: Crawl4AIProvider 实例
            minio_client: MinIO 客户端
            pg_pool: asyncpg 连接池
            bucket: MinIO bucket 名称
            prefix: MinIO 路径前缀
            diff_detector: 增量变更检测器（Phase 2）
            chunker: Markdown 分块器
            embed_url: Embedding 服务地址
            embed_model: Embedding 模型名
            embed_batch_size: Embedding 批量大小
            embed_max_chars: Embedding 文本截断
            qdrant_host: Qdrant 主机
            qdrant_port: Qdrant 端口
            qdrant_collection: Qdrant collection 名
        """
        self.provider = provider
        self.minio = minio_client
        self.pg = pg_pool
        self.bucket = bucket
        self.prefix = prefix
        self.diff_detector = diff_detector or DiffDetector()
        self.chunker = chunker or WebChunker()
        self._embed_url = embed_url
        self._embed_model = embed_model
        self._embed_batch_size = embed_batch_size
        self._embed_max_chars = embed_max_chars
        self._qdrant_host = qdrant_host
        self._qdrant_port = qdrant_port
        self._qdrant_collection = qdrant_collection

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        provider,
        minio_client,
        pg_pool,
    ) -> "WebPipeline":
        """从配置构建 Pipeline"""
        storage_cfg = config.get("storage", {})
        embed_cfg = config.get("embedding", {})
        qdrant_cfg = config.get("qdrant", {})
        diff_detector = DiffDetector.from_config(config)
        chunker = WebChunker.from_config(config)
        return cls(
            provider=provider,
            minio_client=minio_client,
            pg_pool=pg_pool,
            bucket=storage_cfg.get("bucket", "documents"),
            prefix=storage_cfg.get("prefix", "website/"),
            diff_detector=diff_detector,
            chunker=chunker,
            embed_url=embed_cfg.get("url", "http://localhost:8001/v1/embeddings"),
            embed_model=embed_cfg.get("model", "qwen3-embedding"),
            embed_batch_size=embed_cfg.get("batch_size", 16),
            embed_max_chars=embed_cfg.get("max_chars", 800),
            qdrant_host=qdrant_cfg.get("host", "localhost"),
            qdrant_port=qdrant_cfg.get("port", 6333),
            qdrant_collection=qdrant_cfg.get("collection", "web_pages"),
        )

    def _get_minio_path(self, url: str, content_hash: str | None) -> str:
        """生成 MinIO 存储路径

        格式: website/{domain}/{hash[:8]}.md
        """
        domain = urlparse(url).netloc
        hash_suffix = content_hash[:8] if content_hash else "unknown"
        return f"{self.prefix}{domain}/{hash_suffix}.md"

    async def process_url(self, url: str) -> dict[str, Any]:
        """处理单个 URL

        流程:
            1. 调用 Provider 抓取
            2. 成功 → 上传 MinIO → 更新 PostgreSQL
            3. 失败 → 更新 PostgreSQL 错误状态

        Args:
            url: 目标 URL

        Returns:
            处理结果字典
        """
        domain = urlparse(url).netloc

        # 1. 抓取
        result = await self.provider.fetch(url)

        if result.success:
            # 2. 上传 MinIO
            minio_path = self._get_minio_path(url, result.content_hash)
            await self._upload_to_minio(minio_path, result.markdown or "")

            # 3. 更新 PostgreSQL（成功）
            await self._upsert_page_success(
                url=url,
                title=result.title,
                domain=domain,
                status_code=result.status_code,
                content_hash=result.content_hash,
                etag=result.etag,
                last_modified=result.last_modified,
                minio_path=minio_path,
            )

            logger.info(f"Pipeline 成功: {url} -> {minio_path}")
            return {"url": url, "status": "success", "minio_path": minio_path}

        else:
            # 失败处理
            is_dead = self.provider.retry_policy.is_dead_letter(
                result.attempts, domain
            )
            page_status = "dead" if is_dead else "failed"

            await self._upsert_page_failure(
                url=url,
                domain=domain,
                error=result.error,
                error_code=result.status_code,
                retry_count=result.attempts,
                page_status=page_status,
            )

            logger.warning(f"Pipeline 失败: {url} -> {page_status}: {result.error}")
            return {"url": url, "status": page_status, "error": result.error}

    async def process_batch(self, urls: list[str], concurrency: int = 3) -> PipelineStats:
        """批量处理 URL

        Args:
            urls: URL 列表
            concurrency: 最大并发数

        Returns:
            PipelineStats 统计
        """
        import asyncio

        stats = PipelineStats(total=len(urls))
        semaphore = asyncio.Semaphore(concurrency)

        async def _process_one(url: str):
            async with semaphore:
                try:
                    result = await self.process_url(url)
                    status = result.get("status")
                    if status == "success":
                        stats.success += 1
                    elif status == "dead":
                        stats.dead += 1
                    else:
                        stats.failed += 1
                except Exception as e:
                    logger.error(f"Pipeline 异常: {url} -> {e}")
                    stats.failed += 1

        await asyncio.gather(*[_process_one(u) for u in urls])

        stats.end_time = datetime.now(timezone.utc)
        logger.info(stats.summary())
        return stats

    async def _upload_to_minio(self, path: str, content: str) -> None:
        """上传 Markdown 到 MinIO"""
        try:
            data = content.encode("utf-8")
            self.minio.put_object(
                self.bucket,
                path,
                io.BytesIO(data),
                length=len(data),
                content_type="text/markdown",
            )
        except Exception as e:
            logger.error(f"MinIO 上传失败: {path} -> {e}")
            raise

    async def _upsert_page_success(
        self,
        url: str,
        title: str | None,
        domain: str,
        status_code: int | None,
        content_hash: str | None,
        etag: str | None,
        last_modified: str | None,
        minio_path: str,
    ) -> None:
        """更新 PostgreSQL 成功状态"""
        await self.pg.execute(
            """
            INSERT INTO web_pages (
                url, title, domain, status, content_hash,
                etag, last_modified, minio_path, markdown_path,
                page_status, retry_count, crawl_time
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8, 'success', 0, NOW())
            ON CONFLICT (url) DO UPDATE SET
                title = EXCLUDED.title,
                status = EXCLUDED.status,
                content_hash = EXCLUDED.content_hash,
                etag = EXCLUDED.etag,
                last_modified = EXCLUDED.last_modified,
                minio_path = EXCLUDED.minio_path,
                markdown_path = EXCLUDED.markdown_path,
                page_status = 'success',
                retry_count = 0,
                last_error = NULL,
                error_code = NULL,
                crawl_time = NOW()
            """,
            url, title, domain, status_code, content_hash,
            etag, last_modified, minio_path,
        )

    async def _upsert_page_failure(
        self,
        url: str,
        domain: str,
        error: str | None,
        error_code: int | None,
        retry_count: int,
        page_status: str,
    ) -> None:
        """更新 PostgreSQL 失败状态"""
        # 计算下次重试时间
        next_retry = self.provider.retry_policy.get_next_retry_time(retry_count, domain)

        await self.pg.execute(
            """
            INSERT INTO web_pages (
                url, domain, page_status, last_error, error_code,
                retry_count, next_retry_at, crawl_time
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            ON CONFLICT (url) DO UPDATE SET
                page_status = EXCLUDED.page_status,
                last_error = EXCLUDED.last_error,
                error_code = EXCLUDED.error_code,
                retry_count = web_pages.retry_count + 1,
                next_retry_at = EXCLUDED.next_retry_at,
                crawl_time = NOW()
            """,
            url, domain, page_status, error, error_code,
            retry_count, next_retry,
        )

    async def get_dead_letters(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取死信页面列表"""
        rows = await self.pg.fetch(
            """
            SELECT url, domain, last_error, error_code, retry_count, crawl_time
            FROM web_pages
            WHERE page_status = 'dead'
            ORDER BY crawl_time DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]

    async def retry_dead_letters(self, limit: int = 50) -> PipelineStats:
        """重跑死信页面"""
        rows = await self.pg.fetch(
            """
            SELECT url FROM web_pages
            WHERE page_status = 'dead'
            ORDER BY crawl_time ASC
            LIMIT $1
            """,
            limit,
        )
        urls = [r["url"] for r in rows]

        if not urls:
            logger.info("无死信页面需要重跑")
            return PipelineStats()

        # 重置状态为 pending
        await self.pg.execute(
            """
            UPDATE web_pages
            SET page_status = 'pending', retry_count = 0
            WHERE url = ANY($1)
            """,
            urls,
        )

        logger.info(f"重跑 {len(urls)} 个死信页面")
        return await self.process_batch(urls)

    # ──────────────────────────────────────────────
    # Phase 2: 增量处理方法
    # ──────────────────────────────────────────────

    async def process_url_incremental(self, url: str) -> dict[str, Any]:
        """增量模式处理单个 URL

        流程:
            1. 抓取页面
            2. 检测变更状态
            3. 根据状态决定是否处理

        Args:
            url: 目标 URL

        Returns:
            处理结果字典
        """
        domain = urlparse(url).netloc

        # 1. 抓取
        result = await self.provider.fetch(url)

        if not result.success:
            # 抓取失败，走原有失败处理逻辑
            is_dead = self.provider.retry_policy.is_dead_letter(result.attempts, domain)
            page_status = "dead" if is_dead else "failed"
            await self._upsert_page_failure(
                url=url, domain=domain, error=result.error,
                error_code=result.status_code, retry_count=result.attempts,
                page_status=page_status,
            )
            return {"url": url, "status": page_status, "error": result.error}

        # 2. 检测变更
        change = await self.diff_detector.detect_change(
            url=url,
            new_content_hash=result.content_hash,
            pg_pool=self.pg,
            http_status=result.status_code,
        )

        # 3. 根据状态处理
        if change.status == ChangeStatus.UNCHANGED:
            # 内容未变化，仅更新 crawl_time
            await self.pg.execute(
                "UPDATE web_pages SET crawl_time = NOW() WHERE url = $1",
                url,
            )
            logger.debug(f"内容未变化，跳过: {url}")
            return {"url": url, "status": "unchanged", "skipped": True}

        elif change.status == ChangeStatus.REMOVED:
            # 页面下线
            await self._handle_page_removed(url, change)
            return {"url": url, "status": "removed", "message": change.message}

        else:
            # NEW 或 CHANGED，执行完整流程
            minio_path = self._get_minio_path(url, result.content_hash)
            await self._upload_to_minio(minio_path, result.markdown or "")

            # 更新 PostgreSQL（含版本信息）
            await self._upsert_page_incremental(
                url=url, title=result.title, domain=domain,
                status_code=result.status_code, content_hash=result.content_hash,
                etag=result.etag, last_modified=result.last_modified,
                minio_path=minio_path, content_version=change.new_version,
                prev_content_hash=change.old_hash,
            )

            logger.info(f"增量处理: {url} -> {change.status.value} (v{change.new_version})")
            return {
                "url": url,
                "status": change.status.value,
                "minio_path": minio_path,
                "version": change.new_version,
                "needs_sync": change.needs_sync,
            }

    async def process_batch_incremental(
        self, urls: list[str], concurrency: int = 3
    ) -> PipelineStats:
        """批量增量处理

        Args:
            urls: URL 列表
            concurrency: 最大并发数

        Returns:
            PipelineStats 统计
        """
        import asyncio

        stats = PipelineStats(total=len(urls))
        semaphore = asyncio.Semaphore(concurrency)

        async def _process_one(url: str):
            async with semaphore:
                try:
                    result = await self.process_url_incremental(url)
                    status = result.get("status")
                    if status == "unchanged":
                        stats.unchanged += 1
                        stats.skipped += 1
                    elif status == "new":
                        stats.new += 1
                        stats.success += 1
                    elif status == "changed":
                        stats.changed += 1
                        stats.success += 1
                    elif status == "removed":
                        stats.removed += 1
                    elif status == "dead":
                        stats.dead += 1
                    else:
                        stats.failed += 1
                except Exception as e:
                    logger.error(f"Pipeline 异常: {url} -> {e}")
                    stats.failed += 1

        await asyncio.gather(*[_process_one(u) for u in urls])

        stats.end_time = datetime.now(timezone.utc)
        logger.info(stats.summary())
        return stats

    async def _upsert_page_incremental(
        self,
        url: str,
        title: str | None,
        domain: str,
        status_code: int | None,
        content_hash: str | None,
        etag: str | None,
        last_modified: str | None,
        minio_path: str,
        content_version: int,
        prev_content_hash: str | None,
    ) -> None:
        """更新 PostgreSQL（增量模式，含版本信息）"""
        await self.pg.execute(
            """
            INSERT INTO web_pages (
                url, title, domain, status, content_hash,
                etag, last_modified, minio_path, markdown_path,
                page_status, retry_count, crawl_time,
                content_version, prev_content_hash, sync_status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8, 'success', 0, NOW(), $9, $10, 'pending_sync')
            ON CONFLICT (url) DO UPDATE SET
                title = EXCLUDED.title,
                status = EXCLUDED.status,
                prev_content_hash = web_pages.content_hash,
                content_hash = EXCLUDED.content_hash,
                etag = EXCLUDED.etag,
                last_modified = EXCLUDED.last_modified,
                minio_path = EXCLUDED.minio_path,
                markdown_path = EXCLUDED.markdown_path,
                page_status = 'success',
                retry_count = 0,
                last_error = NULL,
                error_code = NULL,
                crawl_time = NOW(),
                content_version = EXCLUDED.content_version,
                sync_status = 'pending_sync'
            """,
            url, title, domain, status_code, content_hash,
            etag, last_modified, minio_path,
            content_version, prev_content_hash,
        )

    async def _handle_page_removed(self, url: str, change) -> None:
        """处理页面下线"""
        strategy = self.diff_detector.on_page_removed

        if strategy == "archive":
            await self.pg.execute(
                """
                UPDATE web_pages
                SET page_status = 'archived', sync_status = 'archived'
                WHERE url = $1
                """,
                url,
            )
            logger.info(f"页面归档: {url}")

        elif strategy == "delete":
            # 删除 MinIO + PostgreSQL 记录
            row = await self.pg.fetchrow(
                "SELECT minio_path, qdrant_point_ids FROM web_pages WHERE url = $1",
                url,
            )
            if row and row["minio_path"]:
                try:
                    self.minio.remove_object(self.bucket, row["minio_path"])
                except Exception as e:
                    logger.warning(f"MinIO 删除失败: {e}")

            await self.pg.execute("DELETE FROM web_pages WHERE url = $1", url)
            logger.info(f"页面删除: {url}")

        # ignore 策略不做任何处理

    # ──────────────────────────────────────────────
    # 下游 Pipeline: Chunk → Embedding → Qdrant
    # ──────────────────────────────────────────────

    async def chunk_and_embed_page(self, url: str) -> dict[str, Any]:
        """对单个页面执行分块 + 向量化

        流程:
            1. 从 MinIO 读取 Markdown
            2. 分块 → 写入 web_chunks
            3. Embedding → 写入 Qdrant
            4. 回写 qdrant_point_id + 更新 sync_status

        Args:
            url: 页面 URL

        Returns:
            处理结果
        """
        # 获取页面信息
        page = await self.pg.fetchrow(
            "SELECT id, minio_path, title, domain, qdrant_point_ids FROM web_pages WHERE url = $1",
            url,
        )
        if not page:
            return {"url": url, "status": "not_found"}

        if not page["minio_path"]:
            return {"url": url, "status": "no_content"}

        # 1. 从 MinIO 读取 Markdown
        try:
            resp = self.minio.get_object(self.bucket, page["minio_path"])
            markdown = resp.read().decode("utf-8")
            resp.close()
            resp.release_conn()
        except Exception as e:
            logger.error(f"MinIO 读取失败: {page['minio_path']} -> {e}")
            return {"url": url, "status": "minio_error", "error": str(e)}

        if not markdown.strip():
            return {"url": url, "status": "empty_content"}

        # 2. 分块
        chunks = self.chunker.chunk(markdown)
        if not chunks:
            return {"url": url, "status": "no_chunks"}

        # 清除旧数据（幂等：双源定位旧 Qdrant points）
        # 源 1: web_pages.qdrant_point_ids（页面级记录，始终可靠）
        # 源 2: web_chunks.qdrant_point_id（chunk 级记录，可能已被删除）
        # 取并集确保完整清理
        old_point_ids: set[str] = set()

        # 从 web_pages 获取
        if page["qdrant_point_ids"]:
            old_point_ids.update(page["qdrant_point_ids"])

        # 从 web_chunks 获取（补充）
        chunk_points = await self.pg.fetch(
            "SELECT qdrant_point_id FROM web_chunks WHERE page_id = $1 AND qdrant_point_id IS NOT NULL",
            page["id"],
        )
        old_point_ids.update(str(r["qdrant_point_id"]) for r in chunk_points)

        # 批量删除旧 Qdrant points
        if old_point_ids:
            await self._delete_qdrant_points(list(old_point_ids))
            logger.debug(f"清理旧向量: {url} -> {len(old_point_ids)} points")

        # 删除旧 chunks 记录
        await self.pg.execute(
            "DELETE FROM web_chunks WHERE page_id = $1", page["id"]
        )

        # 写入 web_chunks
        chunk_ids = []
        for c in chunks:
            row = await self.pg.fetchrow(
                """
                INSERT INTO web_chunks (page_id, chunk_index, heading, content, token_count)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                page["id"], c.chunk_index, c.heading, c.content, c.token_count,
            )
            chunk_ids.append(row["id"])

        # 3. Embedding
        texts = [c.content[:self._embed_max_chars] for c in chunks]
        vectors = await self._embed_texts(texts)

        if not vectors:
            return {"url": url, "status": "embed_failed", "chunks": len(chunks)}

        # 4. 写入 Qdrant
        point_ids = await self._upsert_to_qdrant(
            page_id=str(page["id"]),
            url=url,
            title=page["title"] or "",
            domain=page["domain"] or "",
            chunks=chunks,
            vectors=vectors,
        )

        # 5. 回写 qdrant_point_id
        for chunk_id, point_id in zip(chunk_ids, point_ids):
            await self.pg.execute(
                "UPDATE web_chunks SET qdrant_point_id = $1, embedded = TRUE WHERE id = $2",
                point_id, chunk_id,
            )

        # 6. 更新 web_pages sync_status
        await self.pg.execute(
            """
            UPDATE web_pages
            SET sync_status = 'synced', last_synced_at = NOW(),
                qdrant_point_ids = $2
            WHERE id = $1
            """,
            page["id"], point_ids,
        )

        logger.info(f"向量化完成: {url} -> {len(chunks)} chunks")
        return {
            "url": url,
            "status": "synced",
            "chunks": len(chunks),
            "points": len(point_ids),
        }

    async def sync_pending_pages(self, limit: int = 50) -> dict[str, Any]:
        """批量同步待向量化页面

        查找 sync_status='pending_sync' 的页面，执行 Chunk → Embedding → Qdrant

        Args:
            limit: 最大处理数

        Returns:
            统计结果
        """
        rows = await self.pg.fetch(
            """
            SELECT url FROM web_pages
            WHERE sync_status = 'pending_sync' AND page_status = 'success'
            ORDER BY crawl_time ASC
            LIMIT $1
            """,
            limit,
        )

        if not rows:
            logger.info("无待同步页面")
            return {"total": 0, "synced": 0, "failed": 0}

        synced = 0
        failed = 0

        for r in rows:
            try:
                result = await self.chunk_and_embed_page(r["url"])
                if result.get("status") == "synced":
                    synced += 1
                else:
                    failed += 1
                    logger.warning(f"同步失败: {r['url']} -> {result.get('status')}")
            except Exception as e:
                failed += 1
                logger.error(f"同步异常: {r['url']} -> {e}")

        logger.info(f"批量同步完成: total={len(rows)}, synced={synced}, failed={failed}")
        return {"total": len(rows), "synced": synced, "failed": failed}

    async def _embed_texts(self, texts: list[str]) -> list[list[float]] | None:
        """调用 Embedding 服务"""
        if not texts:
            return []

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # 分批处理
                all_vectors: list[list[float]] = []
                batch_size = self._embed_batch_size

                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    resp = await client.post(
                        self._embed_url,
                        json={"input": batch, "model": self._embed_model},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    all_vectors.extend(
                        [item["embedding"] for item in data["data"]]
                    )

                return all_vectors

        except Exception as e:
            logger.error(f"Embedding 失败: {e}")
            return None

    async def _upsert_to_qdrant(
        self,
        page_id: str,
        url: str,
        title: str,
        domain: str,
        chunks: list,
        vectors: list[list[float]],
    ) -> list[str]:
        """写入 Qdrant 向量库"""
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct

        point_ids: list[str] = []
        points = []

        for chunk, vec in zip(chunks, vectors):
            pid = str(uuid.uuid4())
            point_ids.append(pid)
            points.append(PointStruct(
                id=pid,
                vector=vec,
                payload={
                    "page_id": page_id,
                    "url": url,
                    "title": title,
                    "domain": domain,
                    "heading": chunk.heading or "",
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content[:2000],
                },
            ))

        # 同步写入（qdrant_client 是同步库）
        import asyncio
        qdrant = QdrantClient(
            host=self._qdrant_host, port=self._qdrant_port, timeout=60
        )
        try:
            await asyncio.to_thread(
                qdrant.upsert,
                collection_name=self._qdrant_collection,
                points=points,
                wait=True,
            )
        finally:
            qdrant.close()

        return point_ids

    async def _delete_qdrant_points(self, point_ids: list[str]) -> None:
        """删除 Qdrant 中的旧向量点（幂等：删除不存在的 point 不报错）"""
        if not point_ids:
            return

        from qdrant_client import QdrantClient
        from qdrant_client.models import PointIdsList
        import asyncio

        qdrant = QdrantClient(
            host=self._qdrant_host, port=self._qdrant_port, timeout=60
        )
        try:
            await asyncio.to_thread(
                qdrant.delete,
                collection_name=self._qdrant_collection,
                points_selector=PointIdsList(points=point_ids),
                wait=True,
            )
            logger.debug(f"Qdrant 删除 {len(point_ids)} 个旧 points")
        except Exception as e:
            # 删除失败不应阻断整个同步流程（下次同步会再次尝试）
            logger.warning(f"Qdrant 删除失败 ({len(point_ids)} points): {e}")
        finally:
            qdrant.close()
