"""KOC-A2 Validation 规则单测

验证：
  1. Evidence 完整性：Fact 缺 Evidence 或不足 → 不合规
  2. Confidence 阈值（policy 配置）：低于阈值 → 不合规
  3. 实体类型合法性（taxonomy.entity_types）：未知类型 → 不合规
  4. 合规对象标记 compliant，不合规对象标记 non_compliant

隔离策略：patch get_policy 与 taxonomy 加载器，避免依赖真实配置文件。
"""

from __future__ import annotations

from unittest.mock import patch

from services.knowledge_validation import (
    is_compliant,
    validate_entity,
    validate_fact,
    validate_package,
    validate_relation,
)


def _entity(**over) -> dict:
    base = {"id": "e-1", "name": "腾讯控股", "entity_type": "Company", "confidence": 0.9}
    base.update(over)
    return base


def _relation(**over) -> dict:
    base = {
        "id": "r-1", "relation_type": "owns",
        "source_entity": "e-1", "target_entity": "e-2", "confidence": 0.9,
    }
    base.update(over)
    return base


def _fact(**over) -> dict:
    base = {"id": "f-1", "subject_entity": "e-1", "predicate": "营收", "confidence": 0.9}
    base.update(over)
    return base


def _evidence(**over) -> dict:
    base = {"id": "ev-1", "fact_id": "f-1", "quote": "2024年度营收6000亿元"}
    base.update(over)
    return base


# ── 1. Confidence 阈值 ──

def test_validate_entity_high_confidence_compliant():
    with patch("services.knowledge_validation.get_policy", return_value=0.6), \
         patch("services.knowledge_validation.get_entity_types", return_value={"Company", "Person"}):
        assert validate_entity(_entity(confidence=0.9)) == []


def test_validate_entity_low_confidence_non_compliant():
    with patch("services.knowledge_validation.get_policy", return_value=0.6), \
         patch("services.knowledge_validation.get_entity_types", return_value={"Company", "Person"}):
        issues = validate_entity(_entity(confidence=0.3))
        assert any(i.startswith("low_confidence") for i in issues)


def test_confidence_threshold_from_policy():
    """阈值由 policy 配置决定（配置 0.95 时 0.9 视为不合规）"""
    with patch("services.knowledge_validation.get_policy", return_value=0.95), \
         patch("services.knowledge_validation.get_entity_types", return_value={"Company"}):
        issues = validate_entity(_entity(confidence=0.9))
        assert any(i.startswith("low_confidence") for i in issues)


# ── 2. 实体类型合法性 ──

def test_validate_entity_unknown_type_non_compliant():
    with patch("services.knowledge_validation.get_policy", return_value=0.0), \
         patch("services.knowledge_validation.get_entity_types", return_value={"Company", "Person"}):
        issues = validate_entity(_entity(entity_type="Alien"))
        assert any(i.startswith("invalid_entity_type") for i in issues)


def test_validate_entity_valid_type_compliant():
    with patch("services.knowledge_validation.get_policy", return_value=0.0), \
         patch("services.knowledge_validation.get_entity_types", return_value={"Company", "Person"}):
        assert validate_entity(_entity(entity_type="Person")) == []


def test_validate_relation_invalid_type_non_compliant():
    with patch("services.knowledge_validation.get_policy", return_value=0.0), \
         patch("services.knowledge_validation.get_relation_types", return_value={"owns", "uses"}):
        issues = validate_relation(_relation(relation_type="eats"))
        assert any(i.startswith("invalid_relation_type") for i in issues)


# ── 3. Evidence 完整性 ──

def test_validate_fact_with_evidence_compliant():
    with patch("services.knowledge_validation.get_policy", return_value=0.0), \
         patch("services.knowledge_validation._get_min_evidence_count", return_value=1):
        assert validate_fact(_fact(), [_evidence()]) == []


def test_validate_fact_missing_evidence_non_compliant():
    with patch("services.knowledge_validation.get_policy", return_value=0.0), \
         patch("services.knowledge_validation._get_min_evidence_count", return_value=1):
        issues = validate_fact(_fact(), [])
        assert any(i.startswith("insufficient_evidence") for i in issues)


def test_validate_fact_evidence_below_min_non_compliant():
    with patch("services.knowledge_validation.get_policy", return_value=0.0), \
         patch("services.knowledge_validation._get_min_evidence_count", return_value=2):
        issues = validate_fact(_fact(), [_evidence()])
        assert any(i.startswith("insufficient_evidence") for i in issues)


# ── 4. Package 级校验 ──

def test_validate_package_mixes_compliant_and_non():
    payload = {
        "entities": [_entity(confidence=0.9), _entity(id="e-2", name="神秘实体", entity_type="Alien", confidence=0.9)],
        "relations": [_relation()],
        "facts": [_fact()],
        "evidence": [_evidence()],
    }
    with patch("services.knowledge_validation.get_policy", return_value=0.6), \
         patch("services.knowledge_validation.get_entity_types", return_value={"Company", "Person"}), \
         patch("services.knowledge_validation.get_relation_types", return_value={"owns"}), \
         patch("services.knowledge_validation._get_min_evidence_count", return_value=1):
        report = validate_package(payload)

    assert report["summary"]["total"] == 4  # 2 实体 + 1 关系 + 1 事实
    assert report["summary"]["compliant"] == 3
    assert report["summary"]["non_compliant"] == 1

    # 合法实体进 compliant
    assert "e-1" in report["compliant"]["entities"]
    # 非法类型实体进 non_compliant
    assert "e-2" in report["non_compliant"]["entities"]
    # 事实有证据 → compliant
    assert report["compliant"]["facts"] == ["f-1"]

    assert is_compliant(payload) is False


def test_validate_package_all_compliant():
    payload = {
        "entities": [_entity()],
        "relations": [_relation()],
        "facts": [_fact()],
        "evidence": [_evidence()],
    }
    with patch("services.knowledge_validation.get_policy", return_value=0.6), \
         patch("services.knowledge_validation.get_entity_types", return_value={"Company", "Person"}), \
         patch("services.knowledge_validation.get_relation_types", return_value={"owns"}), \
         patch("services.knowledge_validation._get_min_evidence_count", return_value=1):
        assert is_compliant(payload) is True