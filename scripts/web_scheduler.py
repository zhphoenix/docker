#!/usr/bin/env python3
"""Web Crawl Scheduler — 定时增量抓取 + 向量化同步 + 数据清理

基于 Crawl4AI 集成设计规范 第18节:
- 周期性增量抓取（检测内容变化）
- 自动向量化同步（Chunk → Embedding → Qdrant）
- 死信重跑
- 定时数据清理（死信/孤儿/过期数据）

调度策略:
- 增量抓取: 每 6 小时
- 向量化同步: 每 30 分钟（处理 pending_sync 页面）
- 死信重跑: 每日凌晨 3:00
- 数据清理: 每日凌晨 4:00

用法:
    # 前台运行（开发调试）
    python3 scripts/web_scheduler.py

    # 单次执行（适合 cron 调用）
    python3 scripts/web_scheduler.py --once

    # 仅执行增量抓取
    python3 scripts/web_scheduler.py --once --job crawl

    # 仅执行向量化同步
    python3 scripts/web_scheduler.py --once --job sync

    # 仅执行数据清理
    python3 scripts/web_scheduler.py --once --job cleanup

    # 清理预览模式（仅统计，不删除）
    python3 scripts/web_scheduler.py --once --job cleanup --dry-run
"""

import asyncio
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "langgraph", "agent"))

import asyncpg
import yaml
from minio import Minio

from providers.web.crawl4ai_provider import Crawl4AIProvider
from services.web_pipeline import WebPipeline

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("web_scheduler")

# 服务连接（从环境变量或默认值）
CRAWL4AI_URL = os.getenv("CRAWL4AI_URL", "http://localhost:11235")
CRAWL4AI_TOKEN = os.getenv("CRAWL4AI_API_TOKEN", "crawl4ai-dev-token")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
PG_DSN = os.getenv("PG_DSN", "postgresql://postgres:postgres@localhost:5433/ai")
EMBED_URL = os.getenv("EMBEDDING_URL", "http://localhost:8001/v1/embeddings")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

# 调度间隔
CRAWL_INTERVAL_HOURS = 6
SYNC_INTERVAL_MINUTES = 30
DEAD_LETTER_HOUR = 3   # 凌晨 3 点
CLEANUP_HOUR = 4       # 凌晨 4 点

# 清理策略参数
CLEANUP_DEAD_DAYS = 30        # 死信页面保留天数
CLEANUP_FAILED_DAYS = 30      # 失败页面保留天数
CLEANUP_MAX_RETRY = 5         # 达到此重试次数视为耗尽

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBSITES_YAML = os.path.join(PROJECT_ROOT, "registry", "websites.yaml")


# ──────────────────────────────────────────────
# 初始化
# ──────────────────────────────────────────────

def create_pipeline(pg_pool) -> WebPipeline:
    """创建 Pipeline 实例"""
    provider = Crawl4AIProvider(
        base_url=CRAWL4AI_URL,
        timeout=60,
        api_token=CRAWL4AI_TOKEN,
    )
    minio_client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )
    return WebPipeline(
        provider=provider,
        minio_client=minio_client,
        pg_pool=pg_pool,
        bucket="documents",
        prefix="website/",
        embed_url=EMBED_URL,
        embed_model="qwen3-embedding",
        embed_batch_size=16,
        qdrant_host=QDRANT_HOST,
        qdrant_port=QDRANT_PORT,
        qdrant_collection="web_pages",
    )


def load_target_urls() -> list[str]:
    """从 websites.yaml + web_pages 表加载目标 URL

    优先使用 web_pages 中已有的 URL（已注册页面），
    如果为空则从 websites.yaml 的首页 URL 开始。
    """
    # 这里简单返回已注册站点的首页
    # 实际生产中应从 web_pages 表 + sitemap 扩展
    try:
        with open(WEBSITES_YAML, "r", encoding="utf-8") as f:
            registry = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"注册表不存在: {WEBSITES_YAML}")
        return []

    urls = []
    for site in registry.get("sites", []):
        if site.get("enabled", True):
            domain = site["domain"]
            urls.append(f"https://{domain}/")

    return urls


# ──────────────────────────────────────────────
# 定时任务
# ──────────────────────────────────────────────

async def job_incremental_crawl(pg_pool):
    """增量抓取任务

    对已注册页面执行增量抓取:
    - 检测内容变化（Hash 对比）
    - 仅处理变化/新增页面
    - 失败页面进入重试/死信
    """
    logger.info("=" * 50)
    logger.info("[Job] 增量抓取开始")

    pipeline = create_pipeline(pg_pool)

    # 获取目标 URL（已注册 + 已抓取过的）
    urls = await pg_pool.fetch(
        "SELECT url FROM web_pages WHERE page_status IN ('success', 'failed', 'pending') ORDER BY crawl_time ASC"
    )
    target_urls = [r["url"] for r in urls]

    # 如果数据库为空，使用注册表首页
    if not target_urls:
        target_urls = load_target_urls()
        logger.info(f"使用注册表 URL: {len(target_urls)} 个")

    if not target_urls:
        logger.info("无目标 URL，跳过")
        return

    # 执行增量抓取
    stats = await pipeline.process_batch_incremental(target_urls, concurrency=2)

    logger.info(
        f"[Job] 增量抓取完成: total={stats.total}, new={stats.new}, "
        f"changed={stats.changed}, unchanged={stats.unchanged}, "
        f"failed={stats.failed}, dead={stats.dead}, "
        f"duration={stats.duration_seconds:.1f}s"
    )

    await pipeline.provider.close()


async def job_sync_vectors(pg_pool):
    """向量化同步任务

    处理 sync_status='pending_sync' 的页面:
    - Chunk → Embedding → Qdrant
    """
    logger.info("[Job] 向量化同步开始")

    pipeline = create_pipeline(pg_pool)
    result = await pipeline.sync_pending_pages(limit=100)

    logger.info(
        f"[Job] 向量化同步完成: total={result['total']}, "
        f"synced={result['synced']}, failed={result['failed']}"
    )

    await pipeline.provider.close()


async def job_dead_letter_retry(pg_pool):
    """死信重跑任务

    重试累计失败超过阈值的页面（可能是临时故障恢复）
    """
    logger.info("[Job] 死信重跑开始")

    pipeline = create_pipeline(pg_pool)
    stats = await pipeline.retry_dead_letters(limit=20)

    logger.info(
        f"[Job] 死信重跑完成: total={stats.total}, "
        f"success={stats.success}, failed={stats.failed}"
    )

    await pipeline.provider.close()


async def job_cleanup(pg_pool, dry_run: bool = False):
    """数据清理任务

    清理策略（按顺序执行，先下游后上游）:
      1. 死信页面: page_status='dead' 且超过 N 天未恢复
      2. 失败耗尽: page_status='failed' 且 retry_count >= 上限、超过 N 天
      3. 孤儿 chunks: web_chunks.page_id 在 web_pages 中不存在
      4. 孤儿 Qdrant: payload.page_id 在 PG 中已删除

    删除顺序: Qdrant points → web_chunks → MinIO objects → web_pages
    """
    mode = "预览" if dry_run else "执行"
    logger.info("=" * 55)
    logger.info(f"[Job] 数据清理开始 ({mode}模式)")
    logger.info("=" * 55)

    minio_client = Minio(
        MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY, secure=False,
    )

    stats = {
        "dead_pages": 0,
        "failed_pages": 0,
        "orphan_chunks": 0,
        "orphan_qdrant_points": 0,
        "minio_objects": 0,
        "qdrant_points_deleted": 0,
    }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. 识别待清理的死信页面
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    dead_pages = await pg_pool.fetch(
        """
        SELECT id, url, minio_path, qdrant_point_ids
        FROM web_pages
        WHERE page_status = 'dead'
          AND crawl_time < NOW() - INTERVAL '1 day' * $1
        """,
        CLEANUP_DEAD_DAYS,
    )
    stats["dead_pages"] = len(dead_pages)
    logger.info(f"  [1] 死信页面 (>{CLEANUP_DEAD_DAYS}天): {len(dead_pages)} 个")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. 识别失败耗尽页面
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    failed_pages = await pg_pool.fetch(
        """
        SELECT id, url, minio_path, qdrant_point_ids
        FROM web_pages
        WHERE page_status = 'failed'
          AND retry_count >= $1
          AND crawl_time < NOW() - INTERVAL '1 day' * $2
        """,
        CLEANUP_MAX_RETRY, CLEANUP_FAILED_DAYS,
    )
    stats["failed_pages"] = len(failed_pages)
    logger.info(f"  [2] 失败耗尽页面 (retry>={CLEANUP_MAX_RETRY}, >{CLEANUP_FAILED_DAYS}天): {len(failed_pages)} 个")

    # 合并待清理页面
    pages_to_clean = dead_pages + failed_pages
    page_ids_to_clean = [r["id"] for r in pages_to_clean]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. 识别孤儿 chunks
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    orphan_chunks = await pg_pool.fetch(
        """
        SELECT wc.id, wc.qdrant_point_id
        FROM web_chunks wc
        LEFT JOIN web_pages wp ON wc.page_id = wp.id
        WHERE wp.id IS NULL
        """
    )
    stats["orphan_chunks"] = len(orphan_chunks)
    logger.info(f"  [3] 孤儿 chunks (page已删除): {len(orphan_chunks)} 个")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. 识别孤儿 Qdrant points
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    orphan_point_ids = await _find_orphan_qdrant_points(pg_pool)
    stats["orphan_qdrant_points"] = len(orphan_point_ids)
    logger.info(f"  [4] 孤儿 Qdrant points (PG中无对应页面): {len(orphan_point_ids)} 个")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 汇总待删除的 Qdrant point IDs
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    all_point_ids: set[str] = set()

    # 从待清理页面收集
    for page in pages_to_clean:
        if page["qdrant_point_ids"]:
            all_point_ids.update(page["qdrant_point_ids"])

    # 从待清理页面的 chunks 收集
    if page_ids_to_clean:
        chunk_points = await pg_pool.fetch(
            "SELECT qdrant_point_id FROM web_chunks WHERE page_id = ANY($1) AND qdrant_point_id IS NOT NULL",
            page_ids_to_clean,
        )
        all_point_ids.update(str(r["qdrant_point_id"]) for r in chunk_points)

    # 孤儿 chunks 的 points
    for oc in orphan_chunks:
        if oc["qdrant_point_id"]:
            all_point_ids.add(str(oc["qdrant_point_id"]))

    # 孤儿 Qdrant points
    all_point_ids.update(orphan_point_ids)

    stats["qdrant_points_deleted"] = len(all_point_ids)

    # 收集 MinIO 路径
    minio_paths = [p["minio_path"] for p in pages_to_clean if p["minio_path"]]
    stats["minio_objects"] = len(minio_paths)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 预览模式: 仅输出统计
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if dry_run:
        logger.info("")
        logger.info("  ─── 预览汇总 (未实际删除) ───")
        logger.info(f"  Qdrant points 待删除: {stats['qdrant_points_deleted']}")
        logger.info(f"  web_chunks 待删除:    {stats['orphan_chunks']} (孤儿) + 关联页面的 chunks")
        logger.info(f"  MinIO objects 待删除: {stats['minio_objects']}")
        logger.info(f"  web_pages 待删除:     {stats['dead_pages']} (死信) + {stats['failed_pages']} (失败耗尽)")
        logger.info("  ─── 使用 --dry-run 去除以执行实际删除 ───")
        return stats

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 执行删除（顺序: Qdrant → web_chunks → MinIO → web_pages）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # Step A: 删除 Qdrant points
    if all_point_ids:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import PointIdsList

            qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=60)
            # 分批删除（每批 200）
            point_list = list(all_point_ids)
            for i in range(0, len(point_list), 200):
                batch = point_list[i:i + 200]
                qdrant.delete(
                    collection_name="web_pages",
                    points_selector=PointIdsList(points=batch),
                    wait=True,
                )
            qdrant.close()
            logger.info(f"  [A] Qdrant 删除: {len(all_point_ids)} points")
        except Exception as e:
            logger.error(f"  [A] Qdrant 删除失败: {e}")

    # Step B: 删除 web_chunks
    if page_ids_to_clean:
        result = await pg_pool.execute(
            "DELETE FROM web_chunks WHERE page_id = ANY($1)",
            page_ids_to_clean,
        )
        logger.info(f"  [B] web_chunks 删除 (关联页面): {result}")

    if orphan_chunks:
        orphan_ids = [r["id"] for r in orphan_chunks]
        result = await pg_pool.execute(
            "DELETE FROM web_chunks WHERE id = ANY($1)",
            orphan_ids,
        )
        logger.info(f"  [B] web_chunks 删除 (孤儿): {result}")

    # Step C: 删除 MinIO objects
    deleted_minio = 0
    for path in minio_paths:
        try:
            minio_client.remove_object("documents", path)
            deleted_minio += 1
        except Exception as e:
            logger.warning(f"  [C] MinIO 删除失败: {path} -> {e}")
    if minio_paths:
        logger.info(f"  [C] MinIO 删除: {deleted_minio}/{len(minio_paths)} objects")

    # Step D: 删除 web_pages
    if page_ids_to_clean:
        result = await pg_pool.execute(
            "DELETE FROM web_pages WHERE id = ANY($1)",
            page_ids_to_clean,
        )
        logger.info(f"  [D] web_pages 删除: {result}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 输出统计
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    logger.info("")
    logger.info("  ─── 清理统计 ───")
    logger.info(f"  死信页面删除:       {stats['dead_pages']}")
    logger.info(f"  失败耗尽页面删除:   {stats['failed_pages']}")
    logger.info(f"  孤儿 chunks 删除:   {stats['orphan_chunks']}")
    logger.info(f"  Qdrant points 删除: {stats['qdrant_points_deleted']}")
    logger.info(f"  MinIO objects 删除: {deleted_minio}")
    logger.info("  ─── 清理完成 ───")

    return stats


async def _find_orphan_qdrant_points(pg_pool) -> list[str]:
    """扫描 Qdrant 中 payload.page_id 在 PG 中已不存在的 points"""
    try:
        from qdrant_client import QdrantClient

        qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=60)

        # 获取 PG 中所有有效 page_id
        valid_ids = await pg_pool.fetch("SELECT id::text FROM web_pages")
        valid_set = {r["id"] for r in valid_ids}

        # Scroll Qdrant 获取所有 points 的 page_id
        orphan_ids: list[str] = []
        offset = None

        while True:
            records, offset = qdrant.scroll(
                collection_name="web_pages",
                limit=100,
                offset=offset,
                with_payload=["page_id"],
                with_vectors=False,
            )
            for record in records:
                pid = record.payload.get("page_id", "")
                if pid and pid not in valid_set:
                    orphan_ids.append(str(record.id))

            if offset is None:
                break

        qdrant.close()
        return orphan_ids

    except Exception as e:
        logger.warning(f"  Qdrant 孤儿扫描失败: {e}")
        return []


# ──────────────────────────────────────────────
# 调度循环
# ──────────────────────────────────────────────

async def run_scheduler():
    """主调度循环（简易版，生产建议用 APScheduler）"""
    logger.info("=" * 60)
    logger.info("  Web Crawl Scheduler 启动")
    logger.info(f"  增量抓取: 每 {CRAWL_INTERVAL_HOURS}h")
    logger.info(f"  向量同步: 每 {SYNC_INTERVAL_MINUTES}min")
    logger.info(f"  死信重跑: 每日 {DEAD_LETTER_HOUR}:00")
    logger.info(f"  数据清理: 每日 {CLEANUP_HOUR}:00")
    logger.info("=" * 60)

    pg_pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=3)

    last_crawl = 0.0
    last_sync = 0.0
    last_dead_letter = ""
    last_cleanup = ""

    try:
        while True:
            now = time.time()
            now_dt = datetime.now()
            today_str = now_dt.strftime("%Y-%m-%d")

            # 增量抓取
            if now - last_crawl >= CRAWL_INTERVAL_HOURS * 3600:
                try:
                    await job_incremental_crawl(pg_pool)
                except Exception as e:
                    logger.error(f"[Scheduler] 增量抓取异常: {e}")
                last_crawl = now

            # 向量化同步
            if now - last_sync >= SYNC_INTERVAL_MINUTES * 60:
                try:
                    await job_sync_vectors(pg_pool)
                except Exception as e:
                    logger.error(f"[Scheduler] 向量同步异常: {e}")
                last_sync = now

            # 死信重跑（每日一次）
            if now_dt.hour >= DEAD_LETTER_HOUR and last_dead_letter != today_str:
                try:
                    await job_dead_letter_retry(pg_pool)
                except Exception as e:
                    logger.error(f"[Scheduler] 死信重跑异常: {e}")
                last_dead_letter = today_str

            # 数据清理（每日一次，与死信重跑错开 1 小时）
            if now_dt.hour >= CLEANUP_HOUR and last_cleanup != today_str:
                try:
                    await job_cleanup(pg_pool, dry_run=False)
                except Exception as e:
                    logger.error(f"[Scheduler] 数据清理异常: {e}")
                last_cleanup = today_str

            # 休眠 60s
            await asyncio.sleep(60)

    except KeyboardInterrupt:
        logger.info("[Scheduler] 收到中断信号，停止")
    finally:
        await pg_pool.close()


async def run_once(job: str = "all", dry_run: bool = False):
    """单次执行模式（适合 cron 调用）"""
    pg_pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=3)

    try:
        if job in ("all", "crawl"):
            await job_incremental_crawl(pg_pool)

        if job in ("all", "sync"):
            await job_sync_vectors(pg_pool)

        if job in ("all", "dead"):
            await job_dead_letter_retry(pg_pool)

        if job in ("all", "cleanup"):
            await job_cleanup(pg_pool, dry_run=dry_run)
    finally:
        await pg_pool.close()


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Web Crawl Scheduler")
    parser.add_argument(
        "--once", action="store_true",
        help="单次执行后退出（适合 cron）",
    )
    parser.add_argument(
        "--job", type=str, default="all",
        choices=["all", "crawl", "sync", "dead", "cleanup"],
        help="指定执行的任务",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="预览模式：仅统计待清理数量，不实际删除（仅对 cleanup 有效）",
    )
    args = parser.parse_args()

    if args.once:
        asyncio.run(run_once(args.job, dry_run=args.dry_run))
    else:
        asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
