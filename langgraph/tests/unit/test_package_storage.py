"""DP-B4 单测：KnowledgePackage 落库（package_storage._insert / save_draft）

覆盖：
  1. save_draft 能把含 datetime 的 ProcessingStage 正确序列化（回归修复：
     _insert 用 model_dump(mode="json")，避免 json.dumps 报 datetime 不可序列化）
  2. 处理回流出的 KnowledgePackage 草稿：source_type / processing_metadata 字段完整
  3. save_draft 失败返回 None 不抛出
"""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from schemas.knowledge_package import (
    KnowledgePackage,
    PackageStatus,
    ProcessingMetadata,
    ProcessingStage,
    SourceMetadata,
    SourceType,
)
from storage.knowledge.package import PackageStorage


def _make_package(parser: str = "docling", routing: str = "annual_report") -> KnowledgePackage:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return KnowledgePackage(
        id="pk-1",
        source_type=SourceType.ANNUAL_REPORT,
        document_id="doc-1",
        source=SourceMetadata(source_type=SourceType.ANNUAL_REPORT, source_id="prov"),
        processing_metadata=ProcessingMetadata(
            parser=parser,
            routing_strategy=routing,
            embedding_model="embedding",
            llm_model="qwen3",
            ocr_engine="paddleocr",
            processing_time=1.25,
            stages=[
                ProcessingStage(
                    stage="parse",
                    status="success",
                    started_at=now,
                    finished_at=now,
                    duration_ms=100,
                )
            ],
        ),
    )


class TestSaveDraft:
    @pytest.mark.asyncio
    @patch("storage.knowledge.package.postgres_tool.execute", return_value=None)
    async def test_insert_serializes_datetime(self, execute):
        """回归：processing_metadata 含 datetime 时不能 json.dumps 报错"""
        pkg = _make_package()

        result = await PackageStorage().save_draft(pkg)

        assert result is not None
        # 校验 execute 收到的 processing_metadata 参数可被 json.dumps 序列化
        args = execute.call_args[0]
        assert args[0].lstrip().startswith("INSERT INTO knowledge_packages")
        processing_json = args[8]  # 第 9 个参数（$8）是 processing_metadata JSON
        payload = json.loads(processing_json)
        assert payload["parser"] == "docling"
        assert payload["routing_strategy"] == "annual_report"
        assert payload["stages"][0]["status"] == "success"
        assert payload["stages"][0]["started_at"].startswith("2025-01-01")

    @pytest.mark.asyncio
    @patch(
        "storage.knowledge.package.postgres_tool.execute",
        side_effect=RuntimeError("db down"),
    )
    async def test_insert_failure_returns_none(self, _execute):
        """落库失败返回 None 不抛出（fire-and-forget）"""
        pkg = _make_package()
        result = await PackageStorage().save_draft(pkg)
        assert result is None

    def test_package_draft_status(self):
        pkg = _make_package()
        assert pkg.status is PackageStatus.DRAFT
        assert pkg.package_version == 1