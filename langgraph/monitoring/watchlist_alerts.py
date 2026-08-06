"""Watchlist Alert Engine — 多通道通知（Web / Email / Webhook）

Web 通知写入 watchlist.watchlist_alerts（channel='web'）供 Dashboard 展示。
Email 走 SMTP（环境变量配置，见 _load_smtp_env），Webhook 读取 watchlist_settings.webhook_url。
投递通道由 watchlist_settings.notification_channels JSONB 控制（web/email/webhook）。
单通道失败不抛出，不阻塞监控主流程。
"""

import asyncio
import json
import logging
import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional

import httpx

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)

# 超时（秒）
WEBHOOK_TIMEOUT = 5.0

# 可用通知通道
ALL_CHANNELS = ["web", "email", "webhook"]


async def get_notification_channels() -> list[str]:
    """读取启用的通知通道（JSONB 数组，空列表表示关闭所有外部通知）"""
    rows = await postgres_tool.query(
        "SELECT notification_channels FROM watchlist.watchlist_settings WHERE id = 1"
    )
    if not rows:
        return ["web", "webhook"]
    raw = rows[0].get("notification_channels")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raw = []
    if isinstance(raw, list):
        return [c for c in raw if c in ALL_CHANNELS]
    return ["web", "webhook"]


def _load_smtp_env() -> Optional[dict]:
    """读取 SMTP 环境变量配置（未配置返回 None）"""
    host = os.getenv("WATCHLIST_SMTP_HOST")
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.getenv("WATCHLIST_SMTP_PORT", "465") or "465"),
        "user": os.getenv("WATCHLIST_SMTP_USER", ""),
        "password": os.getenv("WATCHLIST_SMTP_PASSWORD", ""),
        "from_": os.getenv("WATCHLIST_SMTP_FROM", "") or os.getenv("WATCHLIST_SMTP_USER", ""),
        "tls": os.getenv("WATCHLIST_SMTP_TLS", "true").lower() in ("1", "true", "yes"),
    }


def _send_email_sync(cfg: dict, to_addr: str, subject: str, body: str) -> bool:
    """同步发送邮件（放线程池执行）"""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((Header("Watchlist AI", "utf-8"), cfg["from_"]))
    msg["To"] = to_addr
    try:
        if cfg["tls"]:
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15)
        else:
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
            server.starttls()
        try:
            if cfg["user"]:
                server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from_"], [to_addr], msg.as_string())
        finally:
            server.quit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("[Alert][Email] send failed | %s", e)
        return False


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


async def send_email(
    stock_code: str,
    title: str,
    content: str,
    level: str = "info",
    event_id: Optional[str] = None,
) -> bool:
    """发送邮件告警（需 email_enabled=true、email_address 已配置且 SMTP 环境变量就绪）"""
    rows = await postgres_tool.query(
        "SELECT email_enabled, email_address FROM watchlist.watchlist_settings WHERE id = 1"
    )
    to_addr = (rows[0].get("email_address") if rows else None) or ""
    enabled = bool(rows[0].get("email_enabled") if rows else False)
    if not enabled or not to_addr:
        return False
    cfg = _load_smtp_env()
    if not cfg:
        logger.warning("[Alert][Email] SMTP not configured, skip | %s", title)
        return False

    subject = f"[{level.upper()}] {title}"
    body = f"{content}\n\n股票代码: {stock_code}\n事件ID: {event_id or '-'}"
    ok = await asyncio.to_thread(_send_email_sync, cfg, to_addr, subject, body)

    # 记录投递轨迹（无论成败）
    await postgres_tool.execute(
        """
        INSERT INTO watchlist.watchlist_alerts
            (stock_code, title, content, level, event_id, channel, delivered, read)
        VALUES ($1, $2, $3, $4, $5, 'email', $6, true)
        """,
        stock_code, title, content, level, event_id, ok,
    )
    logger.info("[Alert][Email] delivered=%s | %s", ok, title)
    return ok


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
    """对单个监控事件按启用的通知通道分发告警（web/email/webhook）"""
    stock_code = event.get("stock_code") or ""
    level = _level_for_importance(event.get("importance"))
    title = event.get("title") or (event.get("event_title") or event.get("summary") or "Watchlist Event")
    content = event.get("content") or event.get("summary") or ""
    event_id = str(event["event_id"]) if event.get("event_id") else None

    channels = await get_notification_channels()
    if "web" in channels:
        await create_web_alert(stock_code, title, content, level, event_id)
    if "email" in channels:
        await send_email(stock_code, title, content, level, event_id)
    if "webhook" in channels and (await get_webhook_config()):
        await send_webhook(stock_code, title, content, level, event_id)


def _level_for_importance(importance) -> str:
    imp = int(importance or 0)
    if imp >= 5:
        return "critical"
    if imp >= 4:
        return "important"
    return "info"