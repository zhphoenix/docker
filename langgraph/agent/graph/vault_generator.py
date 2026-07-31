"""Vault Generator - 从 Platform 数据自动生成/更新 Obsidian 笔记

功能:
  - 更新公司 README.md（文档状态、财务摘要）
  - 生成研究笔记（从 research_tasks 情景记忆）
  - 同步分析报告到 Vault

写入方式: 直接文件系统（Vault 路径挂载）
触发方式: Scheduler 每日 / API 手动触发
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from tools.postgres import postgres_tool
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)

# Vault 根目录（容器内挂载路径或宿主机路径）
VAULT_ROOT = get_policy("vault.root_path", "/vault")


def _get_vault_root() -> Path:
    """获取 Vault 根目录（优先环境变量）"""
    root = os.environ.get("VAULT_ROOT", VAULT_ROOT)
    return Path(root)


async def generate_company_notes(limit: int = 100) -> dict[str, int]:
    """为所有公司生成/更新 Vault 笔记

    Returns:
        {"updated": N, "created": N, "skipped": N}
    """
    vault = _get_vault_root()
    companies_dir = vault / "companies"
    companies_dir.mkdir(parents=True, exist_ok=True)

    # 获取所有公司（按 symbol 分组）
    rows = await postgres_tool.query(
        """
        SELECT symbol, market, company,
               COUNT(*) as doc_count,
               MAX(year) as latest_year,
               ARRAY_AGG(DISTINCT status) as statuses
        FROM documents
        WHERE symbol IS NOT NULL AND symbol != ''
        GROUP BY symbol, market, company
        ORDER BY symbol
        LIMIT $1
        """,
        limit,
    )

    stats = {"updated": 0, "created": 0, "skipped": 0}

    for row in rows:
        symbol = row["symbol"]
        market = row["market"]
        company = row.get("company") or symbol
        doc_count = row["doc_count"]

        # 公司目录名: {symbol}_{company}
        dir_name = f"{symbol}_{company}" if company != symbol else symbol
        company_dir = companies_dir / dir_name

        try:
            readme_path = company_dir / "README.md"
            content = _build_company_readme(row)

            if readme_path.exists():
                # 检查是否需要更新（比较 updated 日期）
                existing = readme_path.read_text(encoding="utf-8")
                if f"updated: {datetime.now().strftime('%Y-%m-%d')}" in existing:
                    stats["skipped"] += 1
                    continue
                stats["updated"] += 1
            else:
                company_dir.mkdir(parents=True, exist_ok=True)
                stats["created"] += 1

            readme_path.write_text(content, encoding="utf-8")

        except Exception as e:
            logger.warning("Vault write failed | %s | %s", symbol, e)
            stats["skipped"] += 1

    logger.info(
        "Vault generate complete | updated=%d | created=%d | skipped=%d",
        stats["updated"], stats["created"], stats["skipped"],
    )
    return stats


def _build_company_readme(row: dict) -> str:
    """构建公司 README.md 内容"""
    symbol = row["symbol"]
    market = row["market"]
    company = row.get("company") or symbol
    doc_count = row["doc_count"]
    latest_year = row.get("latest_year", "")

    market_label = {"cn": "A股", "hk": "港股", "us": "美股"}.get(market, market)
    today = datetime.now().strftime("%Y-%m-%d")

    # 获取文档列表
    lines = [
        "---",
        f'symbol: "{symbol}"',
        f'company: "{company}"',
        f'market: "{market}"',
        f"tags: [company, {market_label}]",
        f"updated: {today}",
        "---",
        "",
        f"# {company} ({symbol})",
        "",
        f"> 市场: {market_label} | 文档数: {doc_count}",
        "",
    ]

    return "\n".join(lines)


async def generate_research_notes(limit: int = 50) -> dict[str, int]:
    """从 research_tasks 生成研究笔记

    将完成的研究任务写入 Vault 的 queries/ 目录。
    """
    vault = _get_vault_root()
    queries_dir = vault / "queries"
    queries_dir.mkdir(parents=True, exist_ok=True)

    # 获取已完成的研究任务
    tasks = await postgres_tool.query(
        """
        SELECT id, question, agent_type, market, symbol,
               answer, quality, confidence, elapsed_seconds,
               completed_at
        FROM research_tasks
        WHERE status = 'completed' AND answer IS NOT NULL
        ORDER BY completed_at DESC
        LIMIT $1
        """,
        limit,
    )

    stats = {"written": 0, "skipped": 0}

    for task in tasks:
        task_id = str(task["id"])[:8]
        filename = f"{task_id}_{task.get('symbol', 'general')}.md"
        filepath = queries_dir / filename

        if filepath.exists():
            stats["skipped"] += 1
            continue

        content = _build_research_note(task)
        filepath.write_text(content, encoding="utf-8")
        stats["written"] += 1

    logger.info("Research notes | written=%d | skipped=%d",
                stats["written"], stats["skipped"])
    return stats


def _build_research_note(task: dict) -> str:
    """构建研究笔记"""
    question = task.get("question", "")
    answer = task.get("answer", "")
    symbol = task.get("symbol", "")
    market = task.get("market", "")
    quality = task.get("quality", "unknown")
    elapsed = task.get("elapsed_seconds", 0)
    completed = task.get("completed_at", "")

    if completed:
        completed = completed.strftime("%Y-%m-%d %H:%M")

    return f"""---
type: research
symbol: "{symbol}"
market: "{market}"
quality: {quality}
date: {completed}
tags: [research, {market}]
---

# {question}

## 研究结果

{answer[:5000]}

---
*耗时: {elapsed:.1f}s | 质量: {quality}*
"""


async def sync_analysis_reports(report_dir: str = "") -> dict[str, int]:
    """同步分析报告到 Vault

    将 analysis_reports 目录中的报告
    复制到 Vault 对应公司目录下。
    """
    vault = _get_vault_root()
    companies_dir = vault / "companies"

    # 默认报告源目录
    if not report_dir:
        report_dir = os.environ.get(
            "REPORT_SOURCE_DIR",
            "/data/analysis_reports",
        )

    source = Path(report_dir)
    if not source.exists():
        logger.warning("Report source not found: %s", report_dir)
        return {"synced": 0, "error": 1}

    stats = {"synced": 0, "skipped": 0}

    for md_file in source.glob("*_大师分析报告.md"):
        # 解析文件名: {symbol}_{company}_{year}_大师分析报告.md
        parts = md_file.stem.split("_")
        if len(parts) < 2:
            continue

        symbol = parts[0]
        # 找公司目录
        target_dir = None
        if companies_dir.exists():
            for d in companies_dir.iterdir():
                if d.name.startswith(f"{symbol}_"):
                    target_dir = d
                    break

        if not target_dir:
            target_dir = companies_dir / symbol
            target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / md_file.name
        if target_file.exists():
            stats["skipped"] += 1
            continue

        target_file.write_text(md_file.read_text(encoding="utf-8"), encoding="utf-8")
        stats["synced"] += 1

    logger.info("Report sync | synced=%d | skipped=%d",
                stats["synced"], stats["skipped"])
    return stats
