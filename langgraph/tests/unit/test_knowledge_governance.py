"""KOC-B1 治理检测单元测试

验证：
  1. 重复实体（trgm 相似）检测 → conflicts 写 duplicate_entity（每对两条）
  2. 冲突事实检测 → 写 value_mismatch（fact_a/fact_b 正确）
  3. 低置信检测 → relations/facts 低于阈值写 low_confidence，高于阈值跳过
  4. 过期知识 → 写 stale_fact
  5. 同步冲突（KOC-F3）→ sync_status 待审/冲突态实体写 sync_conflict，处理后重置 Synced
  6. 幂等：同主体已有 open 记录时不重复写
  7. run_governance_detection 聚合统计（含 sync_conflicts）

隔离策略：mock postgres_tool（query 分场景）+ get_policy 阈值。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.knowledge_governance import (
    CONFLICT_DUPLICATE_ENTITY,
    CONFLICT_LOW_CONFIDENCE,
    CONFLICT_STALE_FACT,
    CONFLICT_SYNC_CONFLICT,
    CONFLICT_VALUE_MISMATCH,
    KnowledgeGovernance,
)


def _fake_policy(duplicate=0.85, low=0.6):
    def _inner(key, default=None):
        if key == "governance.duplicate_threshold":
            return duplicate
        if key == "governance.low_confidence_threshold":
            return low
        return default
    return _inner


@pytest.mark.asyncio
async def test_duplicate_entities_writes_two_conflicts():
    """重复实体对 → 两条 duplicate_entity 记录（各实体一条，resolution 含对方 id）"""
    g = KnowledgeGovernance()
    rows = [
        {"id_a": "aaa", "name_a": "腾讯控股", "id_b": "bbb", "name_b": "腾讯控股公司", "sim": 0.9},
    ]
    with patch("services.knowledge_governance.postgres_tool") as pg, \
         patch("services.knowledge_governance.get_policy", side_effect=_fake_policy()):
        pg.query = AsyncMock(return_value=rows)
        pg.execute = AsyncMock(return_value="INSERT 0 1")

        written = await g.detect_duplicate_entities()

    assert written == 2
    assert pg.execute.await_count == 2
    for call in pg.execute.await_args_list:
        args = call.args
        sql, conflict_type, entity_id = args[0], args[1], args[2]
        assert conflict_type == CONFLICT_DUPLICATE_ENTITY
        assert "WHERE NOT EXISTS" in sql
        assert "status = 'open'" in sql
        assert entity_id in ("aaa", "bbb")


@pytest.mark.asyncio
async def test_conflicting_facts_write_value_mismatch():
    """同 subject+predicate+时间、不同 object → value_mismatch（fact 对）"""
    g = KnowledgeGovernance()
    rows = [
        {
            "fact_a": "f1", "fact_b": "f2", "subject_entity": "e1",
            "predicate": "营收", "object_a": 6000, "object_b": 6500,
        },
    ]
    with patch("services.knowledge_governance.postgres_tool") as pg, \
         patch("services.knowledge_governance.get_policy", side_effect=_fake_policy()):
        pg.query = AsyncMock(return_value=rows)
        pg.execute = AsyncMock(return_value="INSERT 0 1")

        written = await g.detect_conflicting_facts()

    assert written == 1
    args = pg.execute.await_args.args
    assert args[1] == CONFLICT_VALUE_MISMATCH
    assert args[3] == "f1" and args[4] == "f2"  # fact_a / fact_b
    assert "((fact_a = $3 AND fact_b = $4) OR (fact_a = $4 AND fact_b = $3))" in args[0]


@pytest.mark.asyncio
async def test_low_confidence_relations_and_facts():
    """relations/facts 低于阈值 → low_confidence；高于阈值不写"""
    g = KnowledgeGovernance()
    with patch("services.knowledge_governance.postgres_tool") as pg, \
         patch("services.knowledge_governance.get_policy", side_effect=_fake_policy(low=0.6)):
        pg.query = AsyncMock(side_effect=[
            [  # 关系：SQL 已按 confidence < 0.6 过滤，仅返回低置信行
                {"id": "r1", "source_entity": "e1", "target_entity": "e2",
                 "relation_type": "regulates", "confidence": 0.4},
            ],
            [  # 事实：1 条低置信
                {"id": "f1", "subject_entity": "e1", "predicate": "营收", "confidence": 0.3},
            ],
        ])
        pg.execute = AsyncMock(return_value="INSERT 0 1")

        written = await g.detect_low_confidence()

    assert written == 2
    assert pg.execute.await_count == 2
    for call in pg.execute.await_args_list:
        assert call.args[1] == CONFLICT_LOW_CONFIDENCE


@pytest.mark.asyncio
async def test_stale_facts_write_stale_fact():
    """lifecycle_status=expired/archived → stale_fact"""
    g = KnowledgeGovernance()
    rows = [
        {"id": "f9", "subject_entity": "e1", "predicate": "PE", "lifecycle_status": "expired"},
    ]
    with patch("services.knowledge_governance.postgres_tool") as pg, \
         patch("services.knowledge_governance.get_policy", side_effect=_fake_policy()):
        pg.query = AsyncMock(return_value=rows)
        pg.execute = AsyncMock(return_value="INSERT 0 1")

        written = await g.detect_stale_facts()

    assert written == 1
    args = pg.execute.await_args.args
    assert args[1] == CONFLICT_STALE_FACT
    assert args[3] == "f9"  # fact_a
    assert "expired" in str(args[5])


@pytest.mark.asyncio
async def test_insert_idempotent_when_open_exists():
    """同主体 open 记录已存在 → 不重复写（execute 返回 0 行插入）"""
    g = KnowledgeGovernance()
    with patch("services.knowledge_governance.postgres_tool") as pg:
        pg.execute = AsyncMock(return_value="INSERT 0 0")

        ok = await g._insert_conflict(CONFLICT_DUPLICATE_ENTITY, entity_id="e1")

    assert ok is False
    assert "WHERE NOT EXISTS" in pg.execute.await_args.args[0]


@pytest.mark.asyncio
async def test_run_detection_aggregates_stats():
    """run_governance_detection 聚合五类检测统计（含 sync_conflicts）"""
    g = KnowledgeGovernance()
    with patch.object(g, "detect_duplicate_entities", new=AsyncMock(return_value=2)) as d1, \
         patch.object(g, "detect_conflicting_facts", new=AsyncMock(return_value=1)) as d2, \
         patch.object(g, "detect_low_confidence", new=AsyncMock(return_value=3)) as d3, \
         patch.object(g, "detect_stale_facts", new=AsyncMock(return_value=0)) as d4, \
         patch.object(g, "detect_sync_conflicts", new=AsyncMock(return_value=1)) as d5:
        stats = await g.run_governance_detection()

    assert stats == {"duplicate_entities": 2, "conflicting_facts": 1,
                     "low_confidence": 3, "stale_facts": 0,
                     "sync_conflicts": 1, "total": 7}
    d1.assert_awaited_once()
    d2.assert_awaited_once()
    d3.assert_awaited_once()
    d4.assert_awaited_once()
    d5.assert_awaited_once()


# ─── sync_conflict 同步冲突治理（KOC-F3） ─────────────────────


@pytest.mark.asyncio
async def test_detect_sync_conflicts_writes_conflicts():
    """sync_status=Pending Review/Conflict 的实体 → sync_conflict 记录（resolution 含状态）"""
    g = KnowledgeGovernance()
    rows = [
        {"id": "e1", "name": "药明康德", "entity_type": "Company",
         "sync_status": "Conflict", "sync_version": 3},
        {"id": "e2", "name": "腾讯控股", "entity_type": "Company",
         "sync_status": "Pending Review", "sync_version": 1},
    ]
    with patch("services.knowledge_governance.postgres_tool") as pg:
        pg.query = AsyncMock(return_value=rows)
        pg.execute = AsyncMock(return_value="INSERT 0 1")

        written = await g.detect_sync_conflicts()

    assert written == 2
    assert pg.execute.await_count == 2
    for call in pg.execute.await_args_list:
        args = call.args
        assert args[1] == CONFLICT_SYNC_CONFLICT
        assert "sync_status IN ('Pending Review', 'Conflict')" in pg.query.await_args.args[0]
        assert args[2] in ("e1", "e2")  # entity_id
        assert "Conflict" in str(args[5]) or "Pending Review" in str(args[5])


@pytest.mark.asyncio
async def test_detect_sync_conflicts_skips_synced():
    """无待审/冲突实体 → 不写任何记录"""
    g = KnowledgeGovernance()
    with patch("services.knowledge_governance.postgres_tool") as pg:
        pg.query = AsyncMock(return_value=[])
        pg.execute = AsyncMock(return_value="INSERT 0 0")

        written = await g.detect_sync_conflicts()

    assert written == 0
    pg.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_sync_conflict_resets_entity_synced():
    """处理 sync_conflict 治理项 → 实体 sync_status 重置 Synced + sync_version+1"""
    g = KnowledgeGovernance()
    with patch("services.knowledge_governance.postgres_tool") as pg:
        pg.query = AsyncMock(return_value=[{
            "conflict_type": "sync_conflict", "entity_id": "e1", "resolution": None,
        }])
        pg.execute = AsyncMock(return_value="UPDATE 1")

        ok = await g.resolve_conflict("c1", "keep", "已核对")

    assert ok is True
    assert pg.execute.await_count == 2
    # 第一次：重置实体 sync_status
    ent_update = pg.execute.await_args_list[0].args
    assert "sync_status = 'Synced'" in ent_update[0]
    assert "sync_version = sync_version + 1" in ent_update[0]
    assert ent_update[1] == "e1"
    # 第二次：关闭冲突记录
    conflict_update = pg.execute.await_args_list[1].args
    assert "status = 'resolved'" in conflict_update[0]
    assert conflict_update[1] == "c1"


# ─── resolve_conflict 处理动作（KOC-B2） ──────────────────────


@pytest.mark.asyncio
async def test_resolve_keep_updates_conflict_status():
    """keep 动作：回写 resolved + resolution.action"""
    g = KnowledgeGovernance()
    with patch("services.knowledge_governance.postgres_tool") as pg:
        pg.query = AsyncMock(return_value=[{
            "conflict_type": "value_mismatch", "entity_id": "e1", "resolution": None,
        }])
        pg.execute = AsyncMock(return_value="UPDATE 1")

        ok = await g.resolve_conflict("c1", "keep", "已核对")

    assert ok is True
    update = pg.execute.await_args.args
    assert "UPDATE core.knowledge_conflicts" in update[0]
    assert update[1] == "c1" and update[2] == "keep" and update[3] == "已核对"
    assert "status = 'resolved'" in update[0]


@pytest.mark.asyncio
async def test_resolve_merge_duplicate_entity_merges_aliases():
    """merge 动作（duplicate_entity）：name 并入保留实体 aliases，自身置 merged"""
    g = KnowledgeGovernance()
    with patch("services.knowledge_governance.postgres_tool") as pg:
        pg.query = AsyncMock(side_effect=[
            [{"conflict_type": "duplicate_entity", "entity_id": "e-dup",
              "resolution": '{"duplicate_of": "e-keep"}'}],
            [{"name": "万科企业股份"}],
        ])
        pg.execute = AsyncMock(return_value="UPDATE 1")

        ok = await g.resolve_conflict("c1", "merge")

    assert ok is True
    # 两次实体 UPDATE + 一次 conflict UPDATE
    assert pg.execute.await_count == 3
    ent_calls = pg.execute.await_args_list[:2]
    assert "aliases = aliases || jsonb_build_array" in ent_calls[0].args[0]
    assert ent_calls[0].args[1] == "e-keep" and ent_calls[0].args[2] == "万科企业股份"
    assert ent_calls[1].args[1] == "e-dup"


@pytest.mark.asyncio
async def test_resolve_invalid_action_raises():
    """非法 action 抛 ValueError"""
    g = KnowledgeGovernance()
    with pytest.raises(ValueError):
        await g.resolve_conflict("c1", "delete")


@pytest.mark.asyncio
async def test_resolve_missing_conflict_returns_false():
    """记录不存在或已处理 → False"""
    g = KnowledgeGovernance()
    with patch("services.knowledge_governance.postgres_tool") as pg:
        pg.query = AsyncMock(return_value=[])
        pg.execute = AsyncMock(return_value="UPDATE 0")
        ok = await g.resolve_conflict("c1", "keep")
    assert ok is False
    pg.execute.assert_not_awaited()