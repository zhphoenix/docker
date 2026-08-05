"""Watchlist Alert Engine — Web 通知 + 通用 Webhook

Web 通知写入 watchlist.watchlist_alerts（channel='web'）供 Dashboard 展示。
通用 Webhook 读取 watchlist_settings.webhook_url 并 POST JSON；失败不阻塞主流程。
"""

import logging
from typing import Optional

import httpx

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)

# 超时（秒）
WEBHOOK_TIMEOUT = 5.0


async def get_webhook_config() -> Optional[str]:
    """读取配置中的通用 Webhook 地址"""
    rows = await postgres_tool.query(
        "SELECT webhook_url FROM watchlist.watchlist_settings WHERE id = 1"
    )
    if rows and rows[0].get("webhook_url"):
        return rows[0]["webhook_url"]
    return None


async def create_web_alert(
    stock_code: str,
    title: str,
    content: str,
    level: str = "info",
    event_id: Optional[str] = None,
) -> None:
    """写入一条 Web 站内告警"""
    await postgres_tool.execute(
        """
        INSERT INTO watchlist.watchlist_alerts
            (stock_code, title, content, level, event_id, channel, delivered, read)
        VALUES ($1, $2, $3, $4, $5, 'web', true, false)
        """,
        stock_code, title, content, level, event_id,
    )


async def send_webhook(
    stock_code: str,
    title: str,
    content: str,
    level: str = "info",
    event_id: Optional[str] = None,
) -> bool:
    """向通用 Webhook 发送告警（失败不抛出，返回是否投递成功）"""
    url = await get_webhook_config()
    if not url:
        return False

    payload = {
        "event": "watchlist_alert",
        "level": level,
        "stock_code": stock_code,
        "title": title,
        "content": content,
        "event_id": event_id,
        "timestamp": httpx.URL(url).host or "",
    }
    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            ok = resp.status_code < 300
    except Exception as e:  # noqa: BLE001
        logger.error("[Alert][Webhook] send failed | %s | %s", title, e)
        ok = False

    # 记录投递轨迹（无论成败）
    await postgres_tool.execute(
        """
        INSERT INTO watchlist.watchlist_alerts
            (stock_code, title, content, level, event_id, channel, webhook_url, delivered, read)
        VALUES ($1, $2, $3, $4, $5, 'webhook', $6, $7, true)
        """,
        stock_code, title, content, level, event_id,
        url if url else None, ok,
    )
    logger.info("[Alert][Webhook] delivered=%s | %s", ok, title)
    return ok


async def notify_event(event: dict) -> None:
    """对单个监控事件发送 Web 通知 + Webhook"""
    stock_code = event.get("stock_code") or ""
    level = _level_for_importance(event.get("importance"))
    title = event.get("title") or (event.get("event_title") or event.get("summary") or "Watchlist Event")
    content = event.get("content") or event.get("summary") or ""
    event_id = str(event["event_id"]) if event.get("event_id") else None

    await create_web_alert(stock_code, title, content, level, event_id)
    await send_webhook(stock_code, title, content, level, event_id)


def _level_for_importance(importance) -> str:
    imp = int(importance or 0)
    if imp >= 5:
        return "critical"
    if imp >= 4:
        return "important"
    return "info"