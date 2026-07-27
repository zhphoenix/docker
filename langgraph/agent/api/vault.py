"""Vault API - Obsidian Vault 生成管理"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel

from graph.vault_generator import (
    generate_company_notes,
    generate_research_notes,
    sync_analysis_reports,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vault", tags=["vault"])


class GenerateRequest(BaseModel):
    limit: int = 100
    include_research: bool = True
    include_reports: bool = False
    report_dir: str = ""


@router.post("/generate")
async def trigger_generate(req: GenerateRequest):
    """触发 Vault 笔记生成"""
    results = {}

    # 公司笔记
    results["companies"] = await generate_company_notes(limit=req.limit)

    # 研究笔记
    if req.include_research:
        results["research"] = await generate_research_notes(limit=50)

    # 分析报告同步
    if req.include_reports:
        results["reports"] = await sync_analysis_reports(req.report_dir)

    return {"status": "ok", "results": results}


@router.get("/status")
async def vault_status():
    """获取 Vault 状态"""
    import os
    from pathlib import Path

    vault_root = Path(os.environ.get("VAULT_ROOT", "/vault"))
    companies_dir = vault_root / "companies"

    company_count = 0
    file_count = 0
    if companies_dir.exists():
        company_count = sum(1 for d in companies_dir.iterdir() if d.is_dir())
        file_count = sum(1 for _ in companies_dir.rglob("*.md"))

    return {
        "vault_root": str(vault_root),
        "exists": vault_root.exists(),
        "companies": company_count,
        "markdown_files": file_count,
    }
