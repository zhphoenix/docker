"""Source Health 采集指标埋点（NIC-C1）

在采集编排层（scheduler / api.news）每次采集后调用 record_collect_run，
向 news.collect_runs 写一条明细，并同步 news.sources 最近健康状态扩列。

四项指标：
  - Latency    : latency_ms（本次采集耗时，毫秒）
  - Errors     : success / error / error_count
  - Articles   : articles_fetched（采集到的原始文章数）
  - Duplicates : duplicates（去重数 = fetched - stored）

埋点为 fire-and-forget，失败仅记录日志，不阻塞采集主流程。
"""
import logging

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)


async def record_collect_run(
    source_id: str,
    source_name: str | None = None,
    success: bool = True,
    latency_ms: int | None = None,
    articles_fetched: int = 0,
    articles_stored: int = 0,
    error: str | None = None,
) -> None:
    """记录一次采集运行到 news.collect_runs，并同步 news.sources 最近状态"""
    duplicates = max(articles_fetched - articles_stored, 0)
    try:
        await postgres_tool.execute(
            "INSERT INTO news.collect_runs "
            "(source_id, source_name, success, latency_ms, articles_fetched, articles_stored, duplicates, error) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            source_id,
            source_name,
            success,
            latency_ms,
            articles_fetched,
            articles_stored,
            duplicates,
            error,
        )
        # 同步 news.sources 最近状态（按 source_id 匹配，正则 add 的列）
        await postgres_tool.execute(
            "UPDATE news.sources SET "
            "last_latency_ms=$2, last_success=$3, last_error=$4, "
            "error_count=error_count + CASE WHEN $5 THEN 0 ELSE 1 END, "
            "last_collected_at=NOW() "
            "WHERE source_id=$1",
            source_id,
            latency_ms,
            success,
            error,
            success,
        )
    except Exception as e:
        logger.warning("record_collect_run failed for '%s': %s", source_id, e)