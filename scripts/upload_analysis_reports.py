"""上传大师分析报告到 MinIO artifacts/research/ Bucket

路径规范: artifacts/research/{market}/{symbol}/master_analysis_{year}.md
"""

import os
import re
import hashlib
from pathlib import Path
from minio import Minio
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# MinIO 连接
client = Minio(
    "localhost:9000",
    access_key=os.getenv("MINIO_ROOT_USER"),
    secret_key=os.getenv("MINIO_ROOT_PASSWORD"),
    secure=False,
)

REPORTS_DIR = Path(os.environ.get("REPORT_SOURCE_DIR", "/mnt/e/ai-platform/data/reports"))
BUCKET = "artifacts"

# 港股代码列表（用于判断市场）
HK_CODES = {"00325", "00666", "00700", "00853", "09988"}
# 美股代码列表
US_CODES = {"AAPL", "ABNB", "GPCR", "NVDA", "VRT"}


def parse_filename(filename: str) -> dict:
    """解析文件名，提取 market, symbol, company, year"""
    name = filename.replace(".md", "")

    # 美股格式: AAPL_大师分析报告
    us_match = re.match(r"^([A-Z]+)_大师分析报告$", name)
    if us_match:
        return {
            "market": "us",
            "symbol": us_match.group(1).lower(),
            "company": us_match.group(1),
            "year": "2025",
        }

    # A股/港股格式: 000002_万科A_2025年_大师分析报告
    cn_hk_match = re.match(r"^(\d+)_(.+?)_(\d{4})年_大师分析报告$", name)
    if cn_hk_match:
        code = cn_hk_match.group(1)
        company = cn_hk_match.group(2)
        year = cn_hk_match.group(3)

        # 判断市场
        if code in HK_CODES or (len(code) == 5 and code.startswith("0")):
            market = "hk"
        else:
            market = "cn"

        return {
            "market": market,
            "symbol": code,
            "company": company,
            "year": year,
        }

    return None


def upload_reports():
    """上传所有分析报告"""
    files = sorted(REPORTS_DIR.glob("*.md"))
    print(f"Found {len(files)} analysis reports")

    success = 0
    failed = 0

    for f in files:
        info = parse_filename(f.name)
        if not info:
            print(f"  SKIP (cannot parse): {f.name}")
            failed += 1
            continue

        # 构建 object key: research/{market}/{symbol}/master_analysis_{year}.md
        object_key = f"research/{info['market']}/{info['symbol']}/master_analysis_{info['year']}.md"

        # 读取文件
        data = f.read_bytes()

        # 上传
        from io import BytesIO
        client.put_object(
            BUCKET,
            object_key,
            BytesIO(data),
            length=len(data),
            content_type="text/markdown",
        )

        print(f"  OK: {f.name} -> {BUCKET}/{object_key} ({len(data)} bytes)")
        success += 1

    print(f"\nDone: {success} uploaded, {failed} skipped")


if __name__ == "__main__":
    upload_reports()
