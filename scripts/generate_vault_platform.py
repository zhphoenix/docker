#!/usr/bin/env python3
"""Platform Vault Generator — 从 PostgreSQL 生成 Obsidian 知识库笔记

从 Platform 数据库读取：
  - documents 表（年报文档元数据）
  - financial_statements 表（三表数据）
  - artifacts metadata（大师分析报告）

生成 Obsidian Vault 结构：
  vault/companies/{symbol}_{name}/
    ├── README.md          ← 公司总览（财务摘要 + 链接）
    ├── {year}_年报.md     ← 年报笔记（链接到 MinIO 原文）
    └── 财务数据.md        ← 三表关键指标

用法：
  python3 scripts/generate_vault_platform.py                   # 全量
  python3 scripts/generate_vault_platform.py --symbol 000002   # 单个
  python3 scripts/generate_vault_platform.py --limit 100       # 前100个
  python3 scripts/generate_vault_platform.py --vault-root /path/to/vault
"""

import os
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

# ── 配置 ──────────────────────────────────────────────────────────────────────

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5433"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASS = os.environ.get("PG_PASS", "postgres")
PG_DB = os.environ.get("PG_DB", "ai")

DEFAULT_VAULT = "/mnt/e/Value_capitalism/data/vault"


def get_conn():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER,
        password=PG_PASS, dbname=PG_DB,
    )


def fetch_companies(cur, symbol=None, limit=0) -> list[dict]:
    """获取公司列表（从 documents 表去重）"""
    sql = """
        SELECT DISTINCT d.symbol,
               COALESCE(cb.company_name, d.symbol) as company_name,
               d.market
        FROM documents d
        LEFT JOIN company_basic cb ON d.symbol = cb.symbol
        WHERE d.symbol IS NOT NULL AND d.symbol != ''
    """
    params = []
    if symbol:
        sql += " AND d.symbol = %s"
        params.append(symbol)
    sql += " ORDER BY d.symbol"
    if limit > 0:
        sql += f" LIMIT {limit}"

    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def fetch_documents(cur, symbol: str) -> list[dict]:
    """获取公司所有文档"""
    cur.execute("""
        SELECT id, symbol, year, market, document_type, status,
               object_key, company, created_at
        FROM documents
        WHERE symbol = %s
        ORDER BY year DESC
    """, (symbol,))
    return [dict(r) for r in cur.fetchall()]


def fetch_financials(cur, symbol: str) -> list[dict]:
    """获取财务数据（利润表 + 资产负债表 + 现金流，最新3年）"""
    results = []
    # 利润表
    cur.execute("""
        SELECT year, revenue, net_profit, operating_revenue
        FROM financial_income WHERE symbol = %s
        ORDER BY year DESC LIMIT 3
    """, (symbol,))
    for r in cur.fetchall():
        results.append({"year": r["year"], "type": "income", "data": dict(r)})
    # 资产负债表
    cur.execute("""
        SELECT year, total_assets, total_equity
        FROM financial_balance WHERE symbol = %s
        ORDER BY year DESC LIMIT 3
    """, (symbol,))
    for r in cur.fetchall():
        results.append({"year": r["year"], "type": "balance", "data": dict(r)})
    # 现金流
    cur.execute("""
        SELECT year, net_operating_cashflow
        FROM financial_cashflow WHERE symbol = %s
        ORDER BY year DESC LIMIT 3
    """, (symbol,))
    for r in cur.fetchall():
        results.append({"year": r["year"], "type": "cashflow", "data": dict(r)})
    return results


def fetch_analysis_reports(cur, symbol: str) -> list[dict]:
    """获取大师分析报告（从 documents 表中 document_type='analysis_report'）"""
    cur.execute("""
        SELECT id, company, year, object_key, created_at
        FROM documents
        WHERE symbol = %s AND document_type = 'analysis_report'
        ORDER BY year DESC
    """, (symbol,))
    return [dict(r) for r in cur.fetchall()]


def generate_company_note(company: dict, documents: list, financials: list, analyses: list) -> str:
    """生成公司 README.md 内容"""
    symbol = company["symbol"]
    name = company["company_name"]
    market = company["market"]

    market_label = {"cn": "A股", "hk": "港股", "us": "美股"}.get(market, market)

    lines = [
        "---",
        f'symbol: "{symbol}"',
        f'company: "{name}"',
        f'market: "{market}"',
        f"tags: [company, {market_label}]",
        f"updated: {datetime.now().strftime('%Y-%m-%d')}",
        "---",
        "",
        f"# {name} ({symbol})",
        "",
        f"> 市场: {market_label} | 文档数: {len(documents)}",
        "",
    ]

    # 大师分析报告
    if analyses:
        lines.append("## 📊 大师分析报告")
        lines.append("")
        for a in analyses:
            yr = a.get("year", "")
            lines.append(f"- [[{name}_{yr}_大师分析报告|{yr}年 大师分析报告]]")
        lines.append("")

    # 年报文档
    if documents:
        lines.append("## 📄 年报文档")
        lines.append("")
        for doc in documents:
            if doc.get("document_type") == "analysis_report":
                continue
            year = doc.get("year", "?")
            status = doc.get("status", "unknown")
            icon = "✅" if status == "parsed" else "⏳"
            lines.append(f"- {icon} {year}年年报 ({status})")
        lines.append("")

    # 财务摘要
    if financials:
        lines.append("## 💰 财务数据")
        lines.append("")

        # 按年份分组
        by_year: dict[int, dict] = {}
        for f in financials:
            yr = f["year"]
            if yr not in by_year:
                by_year[yr] = {}
            by_year[yr][f["type"]] = f["data"]

        for yr in sorted(by_year.keys(), reverse=True)[:3]:
            data = by_year[yr]
            income = data.get("income", {})
            balance = data.get("balance", {})
            cashflow = data.get("cashflow", {})

            revenue = income.get("revenue") or "N/A"
            net_profit = income.get("net_profit") or "N/A"
            total_assets = balance.get("total_assets") or "N/A"
            ocf = cashflow.get("net_operating_cashflow") or "N/A"

            lines.append(f"### {yr}年")
            lines.append(f"| 指标 | 数值 |")
            lines.append(f"|------|------|")
            lines.append(f"| 营业总收入 | {_fmt_num(revenue)} |")
            lines.append(f"| 净利润 | {_fmt_num(net_profit)} |")
            lines.append(f"| 总资产 | {_fmt_num(total_assets)} |")
            lines.append(f"| 经营现金流 | {_fmt_num(ocf)} |")
            lines.append("")

    # 脚注
    lines.extend([
        "---",
        f"*由 AI Platform 自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
    ])

    return "\n".join(lines)


def _fmt_num(val) -> str:
    """格式化数字（亿元）"""
    if val == "N/A" or val is None:
        return "N/A"
    try:
        num = float(val)
        if abs(num) >= 1e8:
            return f"{num/1e8:.2f} 亿"
        elif abs(num) >= 1e4:
            return f"{num/1e4:.2f} 万"
        return f"{num:.2f}"
    except (ValueError, TypeError):
        return str(val)


def main():
    parser = argparse.ArgumentParser(description="Platform Vault Generator")
    parser.add_argument("--symbol", type=str, help="单个公司代码")
    parser.add_argument("--limit", type=int, default=0, help="限制数量")
    parser.add_argument("--vault-root", type=str, default=DEFAULT_VAULT)
    args = parser.parse_args()

    vault_root = Path(args.vault_root)
    companies_dir = vault_root / "companies"
    companies_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  Platform Vault Generator")
    print(f"  Vault: {vault_root}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    companies = fetch_companies(cur, symbol=args.symbol, limit=args.limit)
    print(f"\n  公司数: {len(companies)}")

    t0 = time.time()
    count = 0
    errors = 0

    for i, company in enumerate(companies):
        symbol = company["symbol"]
        name = company["company_name"]

        try:
            docs = fetch_documents(cur, symbol)
            fins = fetch_financials(cur, symbol)
            analyses = fetch_analysis_reports(cur, symbol)

            content = generate_company_note(company, docs, fins, analyses)

            # 写入文件
            safe_name = name.replace("/", "_").replace("\\", "_")
            out_dir = companies_dir / f"{symbol}_{safe_name}"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "README.md").write_text(content, encoding="utf-8")
            count += 1

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  [ERROR] {symbol}: {e}")

        # 进度
        if (i + 1) % 500 == 0 or i == len(companies) - 1:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  [{i+1}/{len(companies)}] {rate:.0f} companies/s")
            sys.stdout.flush()

    elapsed = time.time() - t0
    print()
    print("=" * 60)
    print(f"  完成！生成: {count} | 失败: {errors}")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  Vault: {vault_root}")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    main()
