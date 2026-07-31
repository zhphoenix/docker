-- ============================================================
-- Knowledge Schema - 知识图谱核心表
-- 基于 30_Knowledge_Schema设计规范.md
-- ============================================================

-- 启用 pg_trgm 扩展（实体名模糊匹配）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 创建独立 schema（逻辑隔离，不影响 public 表）
CREATE SCHEMA IF NOT EXISTS knowledge;

-- ============================================================
-- 1. entities 表 — 知识实体节点
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge.entities (
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
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 性能索引
CREATE INDEX IF NOT EXISTS idx_kg_entities_type ON knowledge.entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_kg_entities_canonical ON knowledge.entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_kg_entities_name_trgm ON knowledge.entities USING gin(name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_kg_entities_status ON knowledge.entities(status);
-- 注: 2560维超过pgvector HNSW 2000维限制, 不建HNSW索引
-- 向量相似搜索由 Qdrant knowledge_entities collection 承担

-- ============================================================
-- 2. relations 表 — 实体关系
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge.relations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_entity   UUID REFERENCES knowledge.entities(id) ON DELETE CASCADE,
    target_entity   UUID REFERENCES knowledge.entities(id) ON DELETE CASCADE,
    relation_type   TEXT NOT NULL,
    properties      JSONB DEFAULT '{}',
    confidence      FLOAT,
    valid_from      DATE,
    valid_to        DATE,
    status          TEXT DEFAULT 'active',
    source_fact     UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kg_relations_source ON knowledge.relations(source_entity);
CREATE INDEX IF NOT EXISTS idx_kg_relations_target ON knowledge.relations(target_entity);
CREATE INDEX IF NOT EXISTS idx_kg_relations_type ON knowledge.relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_kg_relations_pair ON knowledge.relations(source_entity, target_entity);
CREATE INDEX IF NOT EXISTS idx_kg_relations_status ON knowledge.relations(status);

-- ============================================================
-- 3. facts 表 — 结构化事实
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge.facts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_entity      UUID REFERENCES knowledge.entities(id) ON DELETE CASCADE,
    predicate           TEXT NOT NULL,
    object_value        JSONB NOT NULL,
    unit                TEXT,
    time_start          DATE,
    time_end            DATE,
    source_document     UUID,
    confidence          FLOAT,
    verification_status TEXT DEFAULT 'unverified',
    lifecycle_status    TEXT DEFAULT 'extracted',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kg_facts_subject ON knowledge.facts(subject_entity);
CREATE INDEX IF NOT EXISTS idx_kg_facts_predicate ON knowledge.facts(predicate);
CREATE INDEX IF NOT EXISTS idx_kg_facts_time ON knowledge.facts(time_start, time_end);
CREATE INDEX IF NOT EXISTS idx_kg_facts_lifecycle ON knowledge.facts(lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_kg_facts_verification ON knowledge.facts(verification_status);

-- ============================================================
-- 4. documents 表 — 知识来源文档
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge.documents (
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

CREATE INDEX IF NOT EXISTS idx_kg_documents_type ON knowledge.documents(document_type);
CREATE INDEX IF NOT EXISTS idx_kg_documents_hash ON knowledge.documents(hash);
CREATE INDEX IF NOT EXISTS idx_kg_documents_source ON knowledge.documents(source);

-- ============================================================
-- 5. evidence 表 — 证据链
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge.evidence (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_id         UUID REFERENCES knowledge.facts(id) ON DELETE CASCADE,
    document_id     UUID REFERENCES knowledge.documents(id) ON DELETE CASCADE,
    location        TEXT,
    quote           TEXT,
    confidence      FLOAT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kg_evidence_fact ON knowledge.evidence(fact_id);
CREATE INDEX IF NOT EXISTS idx_kg_evidence_doc ON knowledge.evidence(document_id);

-- ============================================================
-- 6. entity_types 表 — 实体类型枚举
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge.entity_types (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT UNIQUE NOT NULL,
    description TEXT
);

-- ============================================================
-- 7. relation_types 表 — 关系类型枚举
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge.relation_types (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT UNIQUE NOT NULL,
    description TEXT
);

-- ============================================================
-- 预置实体类型
-- ============================================================
INSERT INTO knowledge.entity_types (name, description) VALUES
    ('Company', '企业'),
    ('Person', '人物'),
    ('Product', '产品'),
    ('Technology', '技术'),
    ('Industry', '行业'),
    ('Country', '国家'),
    ('Organization', '机构'),
    ('Event', '事件'),
    ('Metric', '指标'),
    ('Concept', '概念')
ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- 预置关系类型
-- ============================================================
INSERT INTO knowledge.relation_types (name, description) VALUES
    ('owns', '拥有'),
    ('supplies', '供应'),
    ('competes_with', '竞争'),
    ('uses', '使用'),
    ('located_in', '位于'),
    ('invests_in', '投资'),
    ('depends_on', '依赖'),
    ('causes', '导致'),
    ('impacts', '影响')
ON CONFLICT (name) DO NOTHING;
