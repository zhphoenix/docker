"""Watchlist Daily Report Generator — 每日报告生成

从当日 watchlist_events 聚合，按重要性分组（★★★★★/★★★★/★★★），
生成 Markdown 报告并写入 watchlist.daily_watchlist_report（按 report_date 幂等 upsert）。
"""

import logging

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)

# 重要性 → 星级文案
_IMPORTANCE_STARS = {
    5: "★★★★★",
    4: "★★★★",
    3: "★★★",
    2: "★★",
    1: "★",
}

# 监控范围 → 中文标签
_SOURCE_LABEL = {
    "company": "公司",
    "industry": "行业",
    "supply_chain": "产业链",
    "policy": "政策",
    "macro": "宏观",
    "market": "市场",
}


async def _load_todays_events() -> list[dict]:
    """加载当日自选股事件（上海时区）"""
    return await postgres_tool.query(
        """
        SELECT we.stock_code, w.stock_name, we.news_id, we.event_id,
               we.importance, we.sentiment, we.confidence, we.impact_horizon,
               we.summary, we.source_type, we.event_time, we.created_at
        FROM watchlist.watchlist_events we
        LEFT JOIN watchlist.watchlist w ON w.stock_code = we.stock_code
        WHERE (we.created_at AT TIME ZONE 'Asia/Shanghai')::date
            = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date
        ORDER BY we.importance DESC, we.created_at DESC
        """
    )


def _build_markdown(events: list[dict], report_date: str) -> tuple[str, str]:
    """根据事件构建报告 Markdown 与摘要"""
    lines: list[str] = []
    lines.append(f"# Watchlist Daily Report")
    lines.append(report_date)
    lines.append("=" * 40)

    if not events:
        lines.append("今日无重要事件。")
        return "\n".join(lines), "今日无重要事件。"

    # 按重要性分组展示
    by_importance: dict[int, list[dict]] = {}
    for ev in events:
        by_importance.setdefault(ev["importance"], []).append(ev)

    for importance in sorted(by_importance.keys(), reverse=True):
        group = by_importance[importance]
        stars = _IMPORTANCE_STARS.get(importance, "★")
        lines.append(f"\n{stars}（{len(group)}）")
        lines.append("-" * 32)
        for ev in group:
            source_label = _SOURCE_LABEL.get(ev["source_type"] or "", ev["source_type"] or "公司")
            name = ev["stock_name"] or ev["stock_code"]
            lines.append(f"- [{name}] {ev['summary'] or ev.get('event_title') or '（无摘要）'} ({source_label})")

    # 按股票聚合
    lines.append("\n## 个股明细")
    lines.append("-" * 40)
    by_stock: dict[str, list[dict]] = {}
    for ev in events:
        by_stock.setdefault(ev["stock_code"], []).append(ev)

    for code, evs in by_stock.items():
        name = evs[0]["stock_name"] or code
        lines.append(f"\n### {name}（{code}）")
        for ev in evs:
            stars = _IMPORTANCE_STARS.get(ev["importance"], "★")
            sentiment = ev["sentiment"] or "neutral"
            lines.append(f"- {stars} {ev['summary'] or ev.get('event_title') or '（无摘要）'} | 情绪: {sentiment}")

    content = "\n".join(lines)

    # 摘要：重点事件概览
    top = [ev for ev in events if ev["importance"] >= 4]
    if top:
        summary = f"今日重点事件 {len(top)} 条：" + "；".join(
            f"{ev['stock_name'] or ev['stock_code']}·{(ev['summary'] or '')[:30]}"
            for ev in top[:5]
        )
    else:
        summary = "今日无高优先事件。"
    return content, summary


async def generate_daily_report() -> dict:
    """生成当日报告并落库（幂等 upsert by report_date）

    Returns:
        {"report_date": str, "title": str, "summary": str}
    """
    events = await _load_todays_events()

    # 上海时区当天日期
    date_rows = await postgres_tool.query(
        "SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date AS d"
    )
    report_date = str(date_rows[0]["d"]) if date_rows else ""

    content, summary = _build_markdown(events, report_date)
    title = f"Watchlist Daily Report {report_date}"

    await postgres_tool.execute(
        """
        INSERT INTO watchlist.daily_watchlist_report (report_date, title, content, summary)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (report_date)
        DO UPDATE SET title = EXCLUDED.title,
                      content = EXCLUDED.content,
                      summary = EXCLUDED.summary,
                      created_at = NOW()
        """,
        report_date, title, content, summary,
    )

    logger.info(
        "[Report] Daily report generated | date=%s | events=%d",
        report_date, len(events),
    )
    return {"report_date": report_date, "title": title, "summary": summary}