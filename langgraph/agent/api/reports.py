"""Reports API - 大师分析报告（文件系统）+ 触发分析

报告数据源: REPORT_SOURCE_DIR 环境变量指定的目录（容器内 /data/analysis_reports）
"""

import asyncio
import logging
import os
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["reports"])

# 保持后台任务引用，防止被 GC 回收
_background_tasks: set[asyncio.Task] = set()

# 报告目录（容器内挂载路径）
REPORTS_DIR = Path(os.environ.get("REPORT_SOURCE_DIR", "/data/analysis_reports"))

# 扫描缓存（避免每次请求都遍历目录）
_cache: list[dict] = []
_cache_ts: float = 0.0
_CACHE_TTL = 60  # 秒

# 港股代码列表
HK_CODES = {"00325", "00666", "00700", "00853", "09988"}
# 美股代码列表
US_CODES = {"AAPL", "ABNB", "GPCR", "NVDA", "VRT"}


def parse_filename(filename: str) -> dict | None:
    """解析报告文件名，提取 market, symbol, company, year"""
    name = filename.replace(".md", "")

    # 美股格式: AAPL_大师分析报告
    us_match = re.match(r"^([A-Z]+)_大师分析报告$", name)
    if us_match:
        return {
            "market": "us",
            "symbol": us_match.group(1),
            "company": us_match.group(1),
            "year": "2025",
        }

    # A股/港股格式: 000002_万科A_2025年_大师分析报告
    cn_hk_match = re.match(r"^(\d+)_(.+?)_(\d{4})年_大师分析报告$", name)
    if cn_hk_match:
        code = cn_hk_match.group(1)
        company = cn_hk_match.group(2)
        year = cn_hk_match.group(3)

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


def build_report_id(info: dict) -> str:
    """构建报告 ID: {symbol}_{company}_{year}"""
    return f"{info['symbol']}_{info['company']}_{info['year']}"


def scan_reports() -> list[dict]:
    """扫描报告目录，返回报告元数据列表（带 60s TTL 缓存）"""
    global _cache, _cache_ts

    now = time.time()
    if _cache and (now - _cache_ts) < _CACHE_TTL:
        return _cache

    reports = []
    if not REPORTS_DIR.exists():
        logger.warning("Reports directory not found: %s", REPORTS_DIR)
        return reports

    for f in sorted(REPORTS_DIR.glob("*.md")):
        info = parse_filename(f.name)
        if not info:
            continue
        report_id = build_report_id(info)
        reports.append({
            "id": report_id,
            "symbol": info["symbol"],
            "company": info["company"],
            "market": info["market"],
            "year": info["year"],
            "filename": f.name,
            "size_bytes": f.stat().st_size,
        })

    _cache = reports
    _cache_ts = now
    return reports


@router.get("")
async def list_reports(
    market: str | None = None,
    search: str | None = None,
):
    """报告列表（从文件系统扫描）"""
    reports = scan_reports()

    # 筛选
    if market:
        reports = [r for r in reports if r["market"] == market]
    if search:
        q = search.lower()
        reports = [
            r for r in reports
            if q in r["symbol"].lower() or q in r["company"].lower()
        ]

    return {"reports": reports, "total": len(reports)}


@router.get("/{report_id}")
async def get_report(report_id: str):
    """单份报告详情（返回 markdown 全文 + 元数据）"""
    reports = scan_reports()
    target = next((r for r in reports if r["id"] == report_id), None)

    if not target:
        raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")

    filepath = REPORTS_DIR / target["filename"]
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Report file missing on disk")

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        logger.exception("Failed to read report %s", report_id)
        raise HTTPException(status_code=500, detail=str(e))

    return {**target, "content": content}


# ===== 触发分析 =====

class AnalyzeRequest(BaseModel):
    symbol: str
    market: str = "cn"
    dimension: str = "comprehensive"
    year: str | None = None


@router.post("/analyze")
async def trigger_analysis(req: AnalyzeRequest):
    """触发新的大师分析任务（异步执行）"""
    from skills.master_analysis import ANALYSIS_DIMENSIONS

    if req.dimension not in ANALYSIS_DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dimension '{req.dimension}'. Choose from: {', '.join(ANALYSIS_DIMENSIONS.keys())}",
        )

    task_id = str(uuid.uuid4())
    question = f"{req.symbol} {ANALYSIS_DIMENSIONS[req.dimension]}"

    # 写入 research_tasks 表
    try:
        await postgres_tool.execute(
            "INSERT INTO research_tasks (id, question, agent_type, market, symbol, status, created_at) "
            "VALUES ($1, $2, 'master_analysis', $3, $4, 'running', NOW())",
            task_id, question, req.market, req.symbol,
        )
    except Exception as e:
        logger.exception("Failed to create research task")
        raise HTTPException(status_code=500, detail=str(e))

    # 后台异步执行分析
    task = asyncio.create_task(_run_analysis(task_id, req))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {
        "task_id": task_id,
        "status": "running",
        "message": f"分析任务已提交: {req.symbol} ({req.dimension})",
    }


async def _run_analysis(task_id: str, req: AnalyzeRequest):
    """后台执行大师分析并更新 DB"""
    from skills.master_analysis import MasterAnalysisSkill

    skill = MasterAnalysisSkill()
    start = time.time()

    try:
        result = await skill.execute(
            symbol=req.symbol,
            market=req.market,
            dimension=req.dimension,
            year=int(req.year) if req.year else None,
        )

        elapsed = time.time() - start

        if result.get("success"):
            answer = result["data"].get("analysis", "")
            doc_count = result["data"].get("document_count", 0)
            await postgres_tool.execute(
                "UPDATE research_tasks SET status='completed', answer=$1, "
                "document_count=$2, elapsed_seconds=$3, completed_at=NOW() WHERE id=$4",
                answer, doc_count, elapsed, task_id,
            )
            logger.info("Analysis completed: task=%s, elapsed=%.1fs", task_id, elapsed)
        else:
            error = result.get("error", "Unknown error")
            await postgres_tool.execute(
                "UPDATE research_tasks SET status='failed', error=$1, "
                "elapsed_seconds=$2, completed_at=NOW() WHERE id=$3",
                error, elapsed, task_id,
            )
            logger.error("Analysis failed: task=%s, error=%s", task_id, error)

    except Exception as e:
        elapsed = time.time() - start
        logger.exception("Analysis exception: task=%s", task_id)
        try:
            await postgres_tool.execute(
                "UPDATE research_tasks SET status='failed', error=$1, "
                "elapsed_seconds=$2, completed_at=NOW() WHERE id=$3",
                str(e), elapsed, task_id,
            )
        except Exception:
            logger.exception("Failed to update task status")
