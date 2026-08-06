#!/usr/bin/env python3
"""幂等同步 news.events → core.events（NIC-B1 数据源）

将新闻管线的真实事件（news.events，493 条）批量导入 KOC 知识图谱事件表
（core.events），补齐 KOC-A 的入库缺口，使 Event Monitor 可展示：
  - 今日新增事件数
  - 每事件影响公司数（entities 数组 = 关联 Company 实体名称）

字段映射：
  event_type   ← news.events.event_type
  title        ← news.events.title
  description  ← news.events.summary
  event_date   ← COALESCE(event_time, created_at)::date
  entities     ← 关联文章命中的 Company 实体名称数组（jsonb）
  impact       ← {"score","direction","duration","market","sector"}

幂等：按 (title, event_date) 查重，跳过已存在记录，可重复执行。

用法：
  python3 scripts/sync_news_events_to_core.py            # 全量
  python3 scripts/sync_news_events_to_core.py --limit 50 # 限量
  python3 scripts/sync_news_events_to_core.py --dry-run  # 仅统计
"""

import argparse
import asyncio
import json
import os
import sys

import asyncpg

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5433"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASS = os.environ.get("PG_PASS", "postgres")
PG_DB = os.environ.get("PG_DB", "ai")


async def main() -> None:
    parser = argparse.ArgumentParser(description="sync news.events -> core.events")
    parser.add_argument("--limit", type=int, default=0, help="最多同步条数（0=全量）")
    parser.add_argument("--dry-run", action="store_true", help="仅统计不写入")
    args = parser.parse_args()

    conn = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, database=PG_DB
    )
    try:
        # ── 1. 读取 news.events ──
        events = await conn.fetch(
            """
            SELECT id, article_id, event_type, title, summary, event_time, created_at,
                   impact_score, impact_direction, impact_duration, confidence
            FROM news.events
            ORDER BY COALESCE(event_time, created_at) DESC
            """
        )
        if args.limit > 0:
            events = events[: args.limit]

        # ── 2. 关联 Company 实体名称（按 article_id） ──
        company_by_article: dict = {}
        entity_rows = await conn.fetch(
            """
            SELECT article_id, ARRAY_AGG(DISTINCT name) AS names
            FROM news.entities
            WHERE entity_type = 'Company'
            GROUP BY article_id
            """
        )
        for r in entity_rows:
            if r["article_id"]:
                company_by_article[str(r["article_id"])] = r["names"]

        # ── 3. 查重：已有 (title, event_date) ──
        existing = await conn.fetch(
            "SELECT title, event_date FROM core.events WHERE event_date IS NOT NULL"
        )
        existing_keys = {(r["title"], str(r["event_date"])) for r in existing}

        # ── 4. 组装待插入行 ──
        to_insert = []
        for ev in events:
            event_date = ev["event_time"] or ev["created_at"]
            event_date = event_date.date() if event_date else None
            key = (ev["title"], str(event_date)) if event_date else (ev["title"], "")
            if key in existing_keys:
                continue
            impact = {}
            if ev["impact_score"] is not None:
                impact["score"] = float(ev["impact_score"])
            if ev["impact_direction"]:
                impact["direction"] = ev["impact_direction"]
            if ev["impact_duration"]:
                impact["duration"] = ev["impact_duration"]
            entities = company_by_article.get(str(ev["article_id"]), []) if ev["article_id"] else []
            to_insert.append(
                (
                    ev["event_type"],
                    ev["title"],
                    ev["summary"],
                    event_date,
                    json.dumps(entities, ensure_ascii=False),
                    json.dumps(impact, ensure_ascii=False),
                    float(ev["confidence"] or 1.0),
                )
            )

        print(
            f"[sync] news.events={len(events)} 已存在={len(events) - len(to_insert)} "
            f"待插入={len(to_insert)}"
        )
        if args.dry_run or not to_insert:
            return

        # ── 5. 批量插入（单事务） ──
        async with conn.transaction():
            await conn.executemany(
                """
                INSERT INTO core.events
                    (event_type, title, description, event_date, entities, impact, confidence)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
                """,
                to_insert,
            )
        print(f"[sync] 完成：插入 {len(to_insert)} 条到 core.events")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())