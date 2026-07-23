-- ============================================================
-- Phase 1 数据库迁移：补齐缺失表
-- 基于 24_数据底座规范.md 第四章
-- ============================================================

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- chunks 表 — RAG 查询用，向量在 Qdrant
-- ============================================================
CREATE TABLE IF NOT EXISTS chunks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id       UUID REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index       INTEGER NOT NULL,
    content           TEXT NOT NULL,
    page_start        INTEGER,
    page_end          INTEGER,
    heading           VARCHAR(500),
    token_count       INTEGER,
    collection_name   VARCHAR(50),
    qdrant_point_id   UUID,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_qdrant_point_id ON chunks(qdrant_point_id);

-- ============================================================
-- tasks 表 — Agent 工作流任务
-- ============================================================
CREATE TABLE IF NOT EXISTS tasks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id       UUID REFERENCES documents(id) ON DELETE CASCADE,
    task_type         VARCHAR(50) NOT NULL,
    status            VARCHAR(20) DEFAULT 'pending',
    priority          INTEGER DEFAULT 0,
    start_time        TIMESTAMPTZ,
    end_time          TIMESTAMPTZ,
    error             TEXT,
    result            JSONB DEFAULT '{}',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_document_id ON tasks(document_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(task_type);

-- ============================================================
-- agents 表 — Agent 配置
-- ============================================================
CREATE TABLE IF NOT EXISTS agents (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(100) NOT NULL UNIQUE,
    description       TEXT,
    prompt_template   TEXT,
    model             VARCHAR(100),
    temperature       FLOAT DEFAULT 0.7,
    tools             JSONB DEFAULT '[]',
    config            JSONB DEFAULT '{}',
    is_active         BOOLEAN DEFAULT true,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- collections 表 — 统一管理 Qdrant Collection
-- ============================================================
CREATE TABLE IF NOT EXISTS collections (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(50) NOT NULL UNIQUE,
    description       TEXT,
    vector_size       INTEGER NOT NULL,
    distance          VARCHAR(20) DEFAULT 'Cosine',
    domain            VARCHAR(50),
    document_count    INTEGER DEFAULT 0,
    chunk_count       INTEGER DEFAULT 0,
    config            JSONB DEFAULT '{}',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 预置 Qdrant Collection 记录
-- ============================================================
INSERT INTO collections (name, description, vector_size, distance, domain) VALUES
    ('documents_cn', 'A股文档（年报、公告、研报等）', 2560, 'Cosine', 'finance'),
    ('documents_hk', '港股文档', 2560, 'Cosine', 'finance'),
    ('documents_us', '美股文档', 2560, 'Cosine', 'finance')
ON CONFLICT (name) DO NOTHING;
