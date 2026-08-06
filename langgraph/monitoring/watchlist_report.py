"""Watchlist Daily Report Generator — 每日报告生成

从当日 watchlist_events 聚合，按重要性分组（★★★★★/★★★★/★★★），
生成 Markdown 报告并写入 watchlist.daily_watchlist_report（按 report_date 幂等 upsert）。
"""

import asyncio
import json
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


async def _generate_key_points(events: list[dict]) -> dict | None:
    """调用 LLM 生成当日跨股票聚合摘要（JSON 结构）

    Returns:
        {"ai_overview": str, "key_points": list[str], "focus_stocks": list[str]}
        失败或超时返回 None，由调用方降级。
    """
    if not events:
        return None
    try:
        from tools.llm import llm_tool

        ev_lines = "\n".join(
            f"- [{ev['stock_name'] or ev['stock_code']}|来源:{ev.get('source_type') or '未知'}"
            f"|情绪:{ev.get('sentiment') or '未知'}|重要度:{ev['importance']}] "
            f"{(ev.get('summary') or '')[:120]}"
            for ev in events[:40]
        )
        system = (
            "你是一名资深投资分析师。请根据今日自选股监控事件，生成一份聚焦的聚合日报摘要。"
            "只基于给定事件，不要编造。请严格返回 JSON（不要 Markdown 代码块），结构如下：\n"
            "{\n"
            '  "ai_overview": "200-300字中文综述，涵盖整体点评、关键事件及影响、风险提示与关注建议",\n'
            '  "key_points": ["3-5句今日关注要点，每句一句话"],\n'
            '  "focus_stocks": ["需要重点关注的股票代码数组，最多3个"]\n'
            "}"
        )
        user = f"今日自选股监控事件：\n{ev_lines}\n\n请生成聚合日报摘要 JSON。"
        resp = await asyncio.wait_for(
            llm_tool.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
                max_tokens=800,
            ),
            timeout=90.0,
        )
        content = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not content or not content.strip():
            return None
        # 剥离可能出现的 markdown 代码围栏
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        return {
            "ai_overview": str(data.get("ai_overview") or "").strip(),
            "key_points": [
                str(k).strip() for k in (data.get("key_points") or []) if str(k).strip()
            ],
            "focus_stocks": [
                str(s).strip() for s in (data.get("focus_stocks") or []) if str(s).strip()
            ],
        }
    except (asyncio.TimeoutError, json.JSONDecodeError):
        logger.warning("[Report] AI key points unavailable, fallback")
    except Exception as e:  # noqa: BLE001
        logger.warning("[Report] AI key points failed | %s", e)
    return None


async def generate_daily_report() -> dict:
    """生成当日报告并落库（幂等 upsert by report_date）

    Returns:
        {"report_date": str, "title": str, "summary": str}
    """
    events = await _load_todays_events()

    # 上海时区当天日期（保留 date 对象用于 SQL 参数，避免 asyncpg toordinal 报错）
    date_rows = await postgres_tool.query(
        "SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date AS d"
    )
    report_date_obj = date_rows[0]["d"] if date_rows else None
    report_date = str(report_date_obj) if report_date_obj else ""

    content, fallback_summary = _build_markdown(events, report_date)

    # AI 聚合摘要：成功则插入综述到报告开头，summary 落库为 JSON（key_points + focus_stocks），
    # 失败降级为模板摘要的 JSON 结构
    ai = await _generate_key_points(events)
    if ai and ai.get("ai_overview"):
        content = f"## AI 日报综述\n\n{ai['ai_overview']}\n\n---\n\n{content}"
        summary = json.dumps(
            {"key_points": ai.get("key_points"), "focus_stocks": ai.get("focus_stocks")},
            ensure_ascii=False,
        )
    else:
        summary = json.dumps(
            {"key_points": [fallback_summary], "focus_stocks": []},
            ensure_ascii=False,
        )

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
        report_date_obj if report_date_obj is not None else report_date,
        title, content, summary,
    )

    logger.info(
        "[Report] Daily report generated | date=%s | events=%d",
        report_date, len(events),
    )
    return {"report_date": report_date, "title": title, "summary": summary}