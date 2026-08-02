-- ============================================================
-- Knowledge Database — 多 Schema 架构（幂等）
-- 基于 31_Knowledge_Database设计规范.md
--
-- 4-schema: core / document / audit / taxonomy
-- 注: vector schema 已废弃（向量检索由 Qdrant 承担）
-- 兼容: knowledge schema 保留视图
--
-- 场景覆盖:
--   A: 全新数据库 → 直接建表
--   B: 已有 knowledge schema → 迁移到新 schema
--   C: 已迁移完成 → IF NOT EXISTS 跳过
-- ============================================================

-- ── 0. Schema + 扩展 ──
CREATE SCHEMA IF NOT EXISTS knowledge;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS document;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS taxonomy;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── 1. 迁移现有表（knowledge → 新 schema） ──
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='entities' AND table_type='BASE TABLE')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='core' AND table_name='entities')
    THEN ALTER TABLE knowledge.entities SET SCHEMA core; END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='relations' AND table_type='BASE TABLE')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='core' AND table_name='relations')
    THEN ALTER TABLE knowledge.relations SET SCHEMA core; END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='facts' AND table_type='BASE TABLE')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='core' AND table_name='facts')
    THEN ALTER TABLE knowledge.facts SET SCHEMA core; END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='evidence' AND table_type='BASE TABLE')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='core' AND table_name='evidence')
    THEN ALTER TABLE knowledge.evidence SET SCHEMA core; END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='documents' AND table_type='BASE TABLE')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='document' AND table_name='documents')
    THEN ALTER TABLE knowledge.documents SET SCHEMA document; END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='entity_types' AND table_type='BASE TABLE')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='taxonomy' AND table_name='entity_types')
    THEN ALTER TABLE knowledge.entity_types SET SCHEMA taxonomy; END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='relation_types' AND table_type='BASE TABLE')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='taxonomy' AND table_name='relation_types')
    THEN ALTER TABLE knowledge.relation_types SET SCHEMA taxonomy; END IF;
END
$$;

-- ── 2. 基础表 ──

CREATE TABLE IF NOT EXISTS core.entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    description     TEXT,
    aliases         JSONB DEFAULT '[]',
    properties      JSONB DEFAULT '{}',
    canonical_name  TEXT,
    embedding       VECTOR(2560),
    status          TEXT DEFAULT 'active',
    confidence      FLOAT DEFAULT 1.0,
    source_count    INT DEFAULT 0,
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kg_entities_type ON core.entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_kg_entities_canonical ON core.entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_kg_entities_name_trgm ON core.entities USING gin(name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_kg_entities_status ON core.entities(status);
-- 注: 2560维超过pgvector HNSW 2000维限制, 向量搜索由Qdrant承担

CREATE TABLE IF NOT EXISTS core.relations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_entity   UUID REFERENCES core.entities(id) ON DELETE CASCADE,
    target_entity   UUID REFERENCES core.entities(id) ON DELETE CASCADE,
    relation_type   TEXT NOT NULL,
    properties      JSONB DEFAULT '{}',
    confidence      FLOAT,
    valid_from      DATE,
    valid_to        DATE,
    status          TEXT DEFAULT 'active',
    source_fact     UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kg_relations_source ON core.relations(source_entity);
CREATE INDEX IF NOT EXISTS idx_kg_relations_target ON core.relations(target_entity);
CREATE INDEX IF NOT EXISTS idx_kg_relations_type ON core.relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_kg_relations_pair ON core.relations(source_entity, target_entity);
CREATE INDEX IF NOT EXISTS idx_kg_relations_status ON core.relations(status);

CREATE TABLE IF NOT EXISTS core.facts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_entity      UUID REFERENCES core.entities(id) ON DELETE CASCADE,
    predicate           TEXT NOT NULL,
    object_value        JSONB NOT NULL,
    unit                TEXT,
    time_start          DATE,
    time_end            DATE,
    source_document     UUID,
    confidence          FLOAT,
    verification_status TEXT DEFAULT 'unverified',
    lifecycle_status    TEXT DEFAULT 'extracted',
    source_quality      FLOAT,
    extraction_confidence FLOAT,
    validation_score    FLOAT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kg_facts_subject ON core.facts(subject_entity);
CREATE INDEX IF NOT EXISTS idx_kg_facts_predicate ON core.facts(predicate);
CREATE INDEX IF NOT EXISTS idx_kg_facts_time ON core.facts(time_start, time_end);
CREATE INDEX IF NOT EXISTS idx_kg_facts_lifecycle ON core.facts(lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_kg_facts_verification ON core.facts(verification_status);

CREATE TABLE IF NOT EXISTS document.documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT,
    document_type   TEXT,
    source          TEXT,
    url             TEXT,
    file_path       TEXT,
    hash            TEXT,
    publish_date    DATE,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kg_documents_type ON document.documents(document_type);
CREATE INDEX IF NOT EXISTS idx_kg_documents_hash ON document.documents(hash);
CREATE INDEX IF NOT EXISTS idx_kg_documents_source ON document.documents(source);

CREATE TABLE IF NOT EXISTS core.evidence (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_id         UUID REFERENCES core.facts(id) ON DELETE CASCADE,
    document_id     UUID REFERENCES document.documents(id) ON DELETE CASCADE,
    location        TEXT,
    quote           TEXT,
    confidence      FLOAT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kg_evidence_fact ON core.evidence(fact_id);
CREATE INDEX IF NOT EXISTS idx_kg_evidence_doc ON core.evidence(document_id);

CREATE TABLE IF NOT EXISTS taxonomy.entity_types (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS taxonomy.relation_types (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT UNIQUE NOT NULL,
    description TEXT
);

-- ── 3. 补充列（已有表增量） ──
ALTER TABLE core.entities ADD COLUMN IF NOT EXISTS created_by TEXT;
ALTER TABLE core.facts ADD COLUMN IF NOT EXISTS source_quality FLOAT;
ALTER TABLE core.facts ADD COLUMN IF NOT EXISTS extraction_confidence FLOAT;
ALTER TABLE core.facts ADD COLUMN IF NOT EXISTS validation_score FLOAT;

-- ── 4. entity_aliases（§五） ──
CREATE TABLE IF NOT EXISTS core.entity_aliases (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id   UUID NOT NULL REFERENCES core.entities(id) ON DELETE CASCADE,
    alias       TEXT NOT NULL,
    language    TEXT DEFAULT 'zh',
    confidence  FLOAT DEFAULT 1.0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kg_aliases_entity ON core.entity_aliases(entity_id);
CREATE INDEX IF NOT EXISTS idx_kg_aliases_alias_trgm ON core.entity_aliases USING gin(alias gin_trgm_ops);

-- ── 5. events（§九） ──
CREATE TABLE IF NOT EXISTS core.events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type      TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    event_date      DATE,
    entities        JSONB DEFAULT '[]',
    impact          JSONB DEFAULT '{}',
    confidence      FLOAT DEFAULT 1.0,
    source_document UUID REFERENCES document.documents(id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kg_events_type ON core.events(event_type);
CREATE INDEX IF NOT EXISTS idx_kg_events_date ON core.events(event_date);
CREATE INDEX IF NOT EXISTS idx_kg_events_entities ON core.events USING gin(entities);

-- ── 6. knowledge_conflicts（§十六） ──
CREATE TABLE IF NOT EXISTS core.knowledge_conflicts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_a          UUID REFERENCES core.facts(id) ON DELETE CASCADE,
    fact_b          UUID REFERENCES core.facts(id) ON DELETE CASCADE,
    conflict_type   TEXT NOT NULL DEFAULT 'value_mismatch',
    resolution      TEXT,
    status          TEXT DEFAULT 'open',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_kg_conflicts_status ON core.knowledge_conflicts(status);
CREATE INDEX IF NOT EXISTS idx_kg_conflicts_fact_a ON core.knowledge_conflicts(fact_a);
CREATE INDEX IF NOT EXISTS idx_kg_conflicts_fact_b ON core.knowledge_conflicts(fact_b);

-- ── 7. chunks（§十一） ──
CREATE TABLE IF NOT EXISTS document.chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES document.documents(id) ON DELETE CASCADE,
    chunk_index     INT NOT NULL DEFAULT 0,
    content         TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}',
    qdrant_point_id UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_kg_chunks_doc ON document.chunks(document_id);

-- ── 8. entity_embeddings — 已废弃 ──
-- 向量检索由 Qdrant knowledge_entities collection 承担
-- 原 vector.entity_embeddings 表不再创建（2560维超 pgvector HNSW 限制，无实际使用）

-- ── 9. knowledge_versions（§十三） ──
CREATE TABLE IF NOT EXISTS audit.knowledge_versions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    object_type TEXT NOT NULL,
    object_id   UUID NOT NULL,
    version     INT NOT NULL DEFAULT 1,
    content     JSONB NOT NULL,
    created_by  TEXT DEFAULT 'system',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kg_versions_object ON audit.knowledge_versions(object_type, object_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kg_versions_unique ON audit.knowledge_versions(object_type, object_id, version);

-- ── 10. knowledge_statuses（§十四） ──
CREATE TABLE IF NOT EXISTS taxonomy.knowledge_statuses (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT UNIQUE NOT NULL,
    description TEXT
);

-- ── 11. 预置数据 ──
INSERT INTO taxonomy.knowledge_statuses (name, description) VALUES
    ('discovered', '新发现'), ('extracted', 'AI提取'), ('validated', '已验证'),
    ('trusted', '高可信'), ('outdated', '过期'), ('archived', '归档')
ON CONFLICT (name) DO NOTHING;

INSERT INTO taxonomy.entity_types (name, description) VALUES
    ('Company', '企业'), ('Person', '人物'), ('Product', '产品'),
    ('Technology', '技术'), ('Industry', '行业'), ('Country', '国家'),
    ('Organization', '机构'), ('Event', '事件'), ('Metric', '指标'), ('Concept', '概念')
ON CONFLICT (name) DO NOTHING;

INSERT INTO taxonomy.relation_types (name, description) VALUES
    ('owns', '拥有'), ('supplies', '供应'), ('competes_with', '竞争'),
    ('uses', '使用'), ('located_in', '位于'), ('invests_in', '投资'),
    ('depends_on', '依赖'), ('causes', '导致'), ('impacts', '影响'),
    ('supplier', '供应商'), ('customer', '客户'), ('competitor', '竞争对手')
ON CONFLICT (name) DO NOTHING;

-- ── 12. 兼容视图 ──
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.views WHERE table_schema='knowledge' AND table_name='entities')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='entities' AND table_type='BASE TABLE')
    THEN CREATE VIEW knowledge.entities AS SELECT * FROM core.entities; END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.views WHERE table_schema='knowledge' AND table_name='relations')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='relations' AND table_type='BASE TABLE')
    THEN CREATE VIEW knowledge.relations AS SELECT * FROM core.relations; END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.views WHERE table_schema='knowledge' AND table_name='facts')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='facts' AND table_type='BASE TABLE')
    THEN CREATE VIEW knowledge.facts AS SELECT * FROM core.facts; END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.views WHERE table_schema='knowledge' AND table_name='evidence')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='evidence' AND table_type='BASE TABLE')
    THEN CREATE VIEW knowledge.evidence AS SELECT * FROM core.evidence; END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.views WHERE table_schema='knowledge' AND table_name='documents')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='documents' AND table_type='BASE TABLE')
    THEN CREATE VIEW knowledge.documents AS SELECT * FROM document.documents; END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.views WHERE table_schema='knowledge' AND table_name='entity_types')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='entity_types' AND table_type='BASE TABLE')
    THEN CREATE VIEW knowledge.entity_types AS SELECT * FROM taxonomy.entity_types; END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.views WHERE table_schema='knowledge' AND table_name='relation_types')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='knowledge' AND table_name='relation_types' AND table_type='BASE TABLE')
    THEN CREATE VIEW knowledge.relation_types AS SELECT * FROM taxonomy.relation_types; END IF;
END
$$;

-- ── 13. search_path ──
ALTER DATABASE ai SET search_path = public, core, document, vector, audit, taxonomy, knowledge;
