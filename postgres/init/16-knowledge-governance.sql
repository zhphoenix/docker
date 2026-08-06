-- ============================================================
-- 16. Knowledge Governance（KOC-B1）
-- 目标：core.knowledge_conflicts 支持实体级冲突表达
--   （duplicate_entity / low_confidence / sync_conflict 使用 entity_id，
--     value_mismatch / stale_fact 使用 fact_a/fact_b）
-- 幂等：ALTER TABLE ADD COLUMN IF NOT EXISTS，可重复执行
-- 执行：docker compose -f postgres/compose.yml exec postgres_pg16.5 \
--         psql -U postgres -d ai -f /docker-entrypoint-initdb.d/16-knowledge-governance.sql
--       或手动 psql -f
-- ============================================================

ALTER TABLE core.knowledge_conflicts
    ADD COLUMN IF NOT EXISTS entity_id UUID REFERENCES core.entities(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_kg_conflicts_entity
    ON core.knowledge_conflicts(entity_id)
    WHERE entity_id IS NOT NULL;

COMMENT ON COLUMN core.knowledge_conflicts.entity_id
    IS '冲突关联实体（duplicate_entity/low_confidence/sync_conflict 类型使用）';
COMMENT ON COLUMN core.knowledge_conflicts.conflict_type
    IS '冲突类型: duplicate_entity / value_mismatch / low_confidence / stale_fact / sync_conflict';