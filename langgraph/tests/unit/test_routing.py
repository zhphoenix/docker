"""DP-B3 Routing 策略单测

覆盖：
  1. annual_report → docling 解析、needs_download=True
  2. markdown（document_type）→ general 策略、direct 解析
  3. source_type 优先于 document_type（采集元数据优先）
  4. 未知 document_type → general
  5. object_key 补充判断（.md → general/direct）
  6. RoutingPlan.to_dict 结构
  7. _normalize_source_type 兜底 general
"""

from __future__ import annotations

from pipelines.routing import (
    RoutingPlan,
    RoutingStrategy,
    _normalize_source_type,
    resolve_routing,
)


def test_annual_report_docling():
    plan = resolve_routing(document_type="annual_report")
    assert plan.strategy is RoutingStrategy.ANNUAL_REPORT
    assert plan.parser == "docling"
    assert plan.needs_download is True
    assert plan.source_type == "annual_report"


def test_markdown_direct():
    plan = resolve_routing(document_type="markdown")
    assert plan.strategy is RoutingStrategy.GENERAL
    assert plan.parser == "direct"
    assert plan.source_type == "markdown"


def test_source_type_priority():
    # acquire.source_type 优先于 document_type
    plan = resolve_routing(
        document_type="markdown",
        source_type="annual_report",
    )
    assert plan.strategy is RoutingStrategy.ANNUAL_REPORT
    assert plan.parser == "docling"
    assert plan.source_type == "annual_report"


def test_unknown_document_type_general():
    plan = resolve_routing(document_type="unknown_type")
    assert plan.strategy is RoutingStrategy.GENERAL
    assert plan.parser == "direct"
    assert plan.source_type == "general"


def test_object_key_md():
    plan = resolve_routing(document_type=None, object_key="a/b.md")
    assert plan.strategy is RoutingStrategy.GENERAL
    assert plan.parser == "direct"
    assert plan.source_type == "general"


def test_object_key_pdf_still_general_without_type():
    # 无 document_type/source_type 时，即使 .pdf 也走 general（无采集元数据）
    plan = resolve_routing(object_key="a/report.pdf")
    assert plan.strategy is RoutingStrategy.GENERAL
    assert plan.parser == "direct"
    assert plan.needs_download is True


def test_to_dict():
    plan = resolve_routing(document_type="annual_report")
    d = plan.to_dict()
    assert d["strategy"] == "annual_report"
    assert d["parser"] == "docling"
    assert d["needs_download"] is True
    assert d["source_type"] == "annual_report"
    assert "label" in d


def test_normalize_fallback():
    assert _normalize_source_type(None, None) == "general"
    assert _normalize_source_type("news", None) == "news"
    assert _normalize_source_type("markdown", "annual_report") == "annual_report"