#!/usr/bin/env python3
"""从本地 PDF 文件名提取公司基本信息 → PostgreSQL company_basic

无需网络，直接从 data/stock_a/, stock_h/, stock_us/ 文件名解析。
"""

import os
import re
import psycopg2
from pathlib import Path

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5433"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASS = os.environ.get("PG_PASS", "postgres")
PG_DB = os.environ.get("PG_DB", "ai")

DATA_ROOT = Path(os.environ.get("DATA_ROOT", "/mnt/e/ai-platform/data"))

# 市场目录映射
MARKET_DIRS = {
    "cn": DATA_ROOT / "stock_a",
    "hk": DATA_ROOT / "stock_h",
    "us": DATA_ROOT / "stock_us",
}


def parse_filename(filename: str, market: str) -> tuple[str, str] | None:
    """从文件名解析 symbol 和 company_name"""
    name = filename.replace(".pdf", "").replace(".json", "")

    if market == "cn":
        # 格式: 000001_平安银行_2023年年度报告
        m = re.match(r'^(\d{6})_(.+?)_\d{4}年年度报告$', name)
        if m:
            return m.group(1), m.group(2).strip()
    elif market == "hk":
        # 格式: 00001_長和_2025年年度报告 或 00700_騰訊控股_2024年年度报告
        m = re.match(r'^(\d{4,5})_(.+?)_\d{4}年年度报告$', name)
        if m:
            return m.group(1), m.group(2).strip()
    elif market == "us":
        # 格式: AAPL_Apple_Inc_2024年年度报告 或 NVDA_2024年年度报告
        m = re.match(r'^([A-Z]+)_(.+?)_\d{4}年年度报告$', name)
        if m:
            return m.group(1), m.group(2).replace('_', ' ').strip()
        m = re.match(r'^([A-Z]+)_\d{4}年年度报告$', name)
        if m:
            return m.group(1), m.group(1)

    return None


def get_exchange(symbol: str, market: str) -> str:
    if market == "cn":
        if symbol.startswith('6'):
            return 'SSE'
        elif symbol.startswith(('0', '3')):
            return 'SZSE'
        elif symbol.startswith(('8', '4')):
            return 'BSE'
    elif market == "hk":
        return 'HKEX'
    elif market == "us":
        return 'NASDAQ/NYSE'
    return 'UNKNOWN'


def main():
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER,
        password=PG_PASS, dbname=PG_DB,
    )
    cur = conn.cursor()

    print("=" * 60)
    print("  从本地文件名导入 company_basic")
    print("=" * 60)

    # 收集所有 symbol → company_name（取最新年份的名称）
    companies: dict[str, dict[str, str]] = {}  # {market:symbol -> {name, market, symbol}}

    for market, dir_path in MARKET_DIRS.items():
        if not dir_path.exists():
            print(f"  [SKIP] {dir_path} 不存在")
            continue

        count = 0
        for f in dir_path.iterdir():
            if f.suffix not in ('.pdf', '.json'):
                continue
            result = parse_filename(f.name, market)
            if result is None:
                continue
            symbol, name = result
            key = f"{market}:{symbol}"
            # 保留最新的（后面的文件通常年份更新）
            companies[key] = {"market": market, "symbol": symbol, "name": name}
            count += 1

        print(f"  {market}: 扫描 {count} 文件")

    print(f"\n  共 {len(companies)} 个独立公司")

    # 写入数据库
    inserted = 0
    updated = 0
    for key, info in companies.items():
        market = info["market"]
        symbol = info["symbol"]
        name = info["name"]
        exchange = get_exchange(symbol, market)

        try:
            cur.execute("""
                INSERT INTO company_basic (market, symbol, company_name, exchange, source)
                VALUES (%s, %s, %s, %s, 'local_file')
                ON CONFLICT (market, symbol, source) DO UPDATE SET
                    company_name = EXCLUDED.company_name,
                    exchange = EXCLUDED.exchange,
                    updated_at = NOW()
            """, (market, symbol, name, exchange))
            if cur.rowcount > 0:
                inserted += 1
        except Exception as e:
            pass

        if inserted > 0 and inserted % 1000 == 0:
            conn.commit()
            print(f"    已写入 {inserted}...")

    conn.commit()

    # 统计
    cur.execute("SELECT market, COUNT(*) FROM company_basic GROUP BY market ORDER BY market")
    rows = cur.fetchall()
    print(f"\n  写入完成: {inserted} 条")
    for market, cnt in rows:
        print(f"    {market}: {cnt} 条")

    print("=" * 60)
    conn.close()


if __name__ == "__main__":
    main()
