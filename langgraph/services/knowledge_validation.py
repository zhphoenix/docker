"""Knowledge Validation - KOC-A2 Validation 规则

对 extraction 产出的实体/关系/事实/证据执行合规校验，决定是否直接合并。

三条规则（KOC-A2）：
  1. Evidence 完整性：Fact 必须携带至少 min_evidence_count 条 Evidence；
     缺 Evidence 的 Fact 视为不合规（证据不充分）。
  2. Confidence 阈值：对象置信度低于 policy koc.validation.confidence_threshold
     （默认 0.6）视为不合规，需人工审核。
  3. 实体类型合法性：entity_type 必须在 taxonomy.entity_types（specs/ontology.yaml）
     声明的 id 集合内；未知类型视为不合规。

验收标准：
  - 不合规对象 → 进入 knowledge_inbox READY_REVIEW（由调用方写入）
  - 合规对象 → 直接合并（由调用方走 merger）

本模块为纯校验逻辑（无 DB 依赖），供 KOC-A3 Merge 与 KOC-A4 Inbox 复用。
"""

from __future__ import annotations

import logging
from typing import Any

from config.policy_loader import get_policy
from config.taxonomy import get_entity_types, get_relation_types

logger = logging.getLogger(__name__)

# 默认阈值（policy 未配置时兜底）
DEFAULT_CONFIDENCE_THRESHOLD = 0.6
DEFAULT_MIN_EVIDENCE_COUNT = 1


def _confidence_of(obj: dict) -> float:
    """提取对象置信度：支持 Confidence 对象（dict）或裸 float"""
    conf = obj.get("confidence")
    if isinstance(conf, dict):
        return float(conf.get("score") or 0.0)
    if conf is None:
        return 0.0
    return float(conf)


def _get_confidence_threshold() -> float:
    return float(get_policy("koc.validation.confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD))


def _get_min_evidence_count() -> int:
    return int(get_policy("koc.validation.min_evidence_count", DEFAULT_MIN_EVIDENCE_COUNT))


# ──────────────────────────────────────────────────────────────
# 单对象校验
# ──────────────────────────────────────────────────────────────

def validate_entity(entity: dict) -> list[str]:
    """校验单个实体，返回不合规原因列表（空列表=合规）

    规则：
      1. entity_type 合法性（taxonomy.entity_types）
      2. confidence 阈值
    """
    issues: list[str] = []

    etype = entity.get("entity_type") or ""
    valid_types = get_entity_types()
    if etype and valid_types and etype not in valid_types:
        issues.append(f"invalid_entity_type:{etype}")

    conf = _confidence_of(entity)
    if conf < _get_confidence_threshold():
        issues.append(f"low_confidence:{conf:.2f}")
    return issues


def validate_relation(relation: dict) -> list[str]:
    """校验单个关系，返回不合规原因列表（空列表=合规）

    规则：
      1. relation_type 合法性（taxonomy.relation_types）
      2. confidence 阈值
    """
    issues: list[str] = []

    rtype = relation.get("relation_type") or ""
    valid_types = get_relation_types()
    if rtype and valid_types and rtype not in valid_types:
        issues.append(f"invalid_relation_type:{rtype}")

    conf = _confidence_of(relation)
    if conf < _get_confidence_threshold():
        issues.append(f"low_confidence:{conf:.2f}")
    return issues


def validate_fact(fact: dict, evidence: list[dict]) -> list[str]:
    """校验单个事实，返回不合规原因列表（空列表=合规）

    规则：
      1. Evidence 完整性：关联证据数 >= min_evidence_count
      2. confidence 阈值
    """
    issues: list[str] = []

    min_ev = _get_min_evidence_count()
    ev_count = len([e for e in evidence if e.get("quote") or e.get("location") or e.get("fact_id")])
    if ev_count < min_ev:
        issues.append(f"insufficient_evidence:{ev_count}<{min_ev}")

    conf = _confidence_of(fact)
    if conf < _get_confidence_threshold():
        issues.append(f"low_confidence:{conf:.2f}")
    return issues


# ──────────────────────────────────────────────────────────────
# Package 级校验
# ──────────────────────────────────────────────────────────────

def validate_package(payload: dict) -> dict[str, Any]:
    """校验整个 Package 的 entities/relations/facts，返回校验报告

    Args:
        payload: KnowledgePackage 的 payload dict（含 entities/relations/facts/evidence）

    Returns:
        {
            "entities": [{"id", "name", "issues": [...]}],
            "relations": [{"id", "issues": [...]}],
            "facts": [{"id", "predicate", "issues": [...]}],
            "compliant": {  # 合规对象（可直接合并）
                "entities": [obj_id, ...],
                "relations": [obj_id, ...],
                "facts": [obj_id, ...],
            },
            "non_compliant": {  # 不合规对象（需进 READY_REVIEW）
                "entities": [obj_id, ...],
                "relations": [obj_id, ...],
                "facts": [obj_id, ...],
            },
            "summary": {"total": n, "compliant": n, "non_compliant": n},
        }
    """
    entities = payload.get("entities", []) or []
    relations = payload.get("relations", []) or []
    facts = payload.get("facts", []) or []
    evidence = payload.get("evidence", []) or []

    # evidence 按 fact_id 分组，供 Fact 校验
    evidence_by_fact: dict[str, list[dict]] = {}
    for ev in evidence:
        fid = ev.get("fact_id") or ""
        if fid:
            evidence_by_fact.setdefault(fid, []).append(ev)

    entity_reports: list[dict] = []
    relation_reports: list[dict] = []
    fact_reports: list[dict] = []

    compliant_entities: list[str] = []
    non_compliant_entities: list[str] = []
    compliant_relations: list[str] = []
    non_compliant_relations: list[str] = []
    compliant_facts: list[str] = []
    non_compliant_facts: list[str] = []

    for ent in entities:
        eid = str(ent.get("id") or "")
        issues = validate_entity(ent)
        entity_reports.append({"id": eid, "name": ent.get("name"), "issues": issues})
        (compliant_entities if not issues else non_compliant_entities).append(eid)

    for rel in relations:
        rid = str(rel.get("id") or "")
        issues = validate_relation(rel)
        relation_reports.append({"id": rid, "issues": issues})
        (compliant_relations if not issues else non_compliant_relations).append(rid)

    for fact in facts:
        fid = str(fact.get("id") or "")
        issues = validate_fact(fact, evidence_by_fact.get(fid, []))
        fact_reports.append({"id": fid, "predicate": fact.get("predicate"), "issues": issues})
        (compliant_facts if not issues else non_compliant_facts).append(fid)

    total = len(entities) + len(relations) + len(facts)
    compliant = len(compliant_entities) + len(compliant_relations) + len(compliant_facts)
    non_compliant = total - compliant

    return {
        "entities": entity_reports,
        "relations": relation_reports,
        "facts": fact_reports,
        "compliant": {
            "entities": compliant_entities,
            "relations": compliant_relations,
            "facts": compliant_facts,
        },
        "non_compliant": {
            "entities": non_compliant_entities,
            "relations": non_compliant_relations,
            "facts": non_compliant_facts,
        },
        "summary": {"total": total, "compliant": compliant, "non_compliant": non_compliant},
    }


def is_compliant(payload: dict) -> bool:
    """整包是否全部合规（无任何不合规对象）"""
    report = validate_package(payload)
    return report["summary"]["non_compliant"] == 0