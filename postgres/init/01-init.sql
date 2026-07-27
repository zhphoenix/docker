-- ============================================================
-- AI 投研平台 PostgreSQL 初始化脚本
-- 基于 24_数据底座规范.md 第四章
-- ============================================================

-- 创建 langgraph 数据库（必须在 pgvector 扩展之前）
CREATE DATABASE langgraph;

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 清理旧表（按依赖顺序）
-- ============================================================
DROP TABLE IF EXISTS chunks CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS agents CASCADE;
DROP TABLE IF EXISTS collections CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP TABLE IF EXISTS companies CASCADE;
DROP TABLE IF EXISTS research_tasks CASCADE;
DROP TABLE IF EXISTS providers CASCADE;

-- ============================================================
-- 4.1 documents 表 — 文档状态管理（plan_data.md Phase 3 规范）
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market            VARCHAR(10) NOT NULL,
    symbol            VARCHAR(20) NOT NULL,
    company           VARCHAR(200),
    year              INTEGER NOT NULL,
    document_type     VARCHAR(50) NOT NULL,
    language          VARCHAR(10) DEFAULT 'zh',
    bucket            VARCHAR(50) DEFAULT 'documents',
    object_key        TEXT,
    hash              VARCHAR(128),
    parser            VARCHAR(50),
    parser_version    VARCHAR(20),
    status            VARCHAR(20) DEFAULT 'pending',
    chunk_count       INTEGER DEFAULT 0,
    metadata          JSONB DEFAULT '{}',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(market, symbol, year, document_type)
);

CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_symbol_year ON documents(symbol, year);
CREATE INDEX idx_documents_market ON documents(market);
CREATE INDEX idx_documents_metadata ON documents USING gin(metadata);

-- ============================================================
-- 4.2 chunks 表 — RAG 查询用，向量在 Qdrant
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

CREATE INDEX idx_chunks_document_id ON chunks(document_id);
CREATE INDEX idx_chunks_qdrant_point_id ON chunks(qdrant_point_id);

-- ============================================================
-- 4.3 tasks 表 — 统一任务队列（Pipeline / Scheduler / Agent）
-- ============================================================
CREATE TABLE IF NOT EXISTS tasks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type         VARCHAR(50) NOT NULL,
    title             VARCHAR(500) NOT NULL DEFAULT '',
    status            VARCHAR(20) DEFAULT 'pending',
    priority          INTEGER DEFAULT 0,
    params            JSONB DEFAULT '{}',
    total_items       INTEGER DEFAULT 0,
    current_item      INTEGER DEFAULT 0,
    progress          NUMERIC(5,2) DEFAULT 0,
    stage             VARCHAR(50) DEFAULT '',
    current_name      VARCHAR(200) DEFAULT '',
    created_by        VARCHAR(100) DEFAULT 'system',
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ,
    duration_ms       BIGINT,
    retry_count       INTEGER DEFAULT 0,
    max_retries       INTEGER DEFAULT 3,
    error_message     TEXT,
    result            JSONB DEFAULT '{}',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_type ON tasks(task_type);
CREATE INDEX idx_tasks_priority ON tasks(priority DESC, created_at ASC);

-- ============================================================
-- 4.4 agents 表 — Agent 配置
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
-- 4.5 collections 表 — 统一管理 Qdrant Collection
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

-- ============================================================
-- 4.6 providers 表 — 数据源注册表（从 providers.yaml 导入）
-- ============================================================
CREATE TABLE IF NOT EXISTS providers (
    id                VARCHAR(50) PRIMARY KEY,
    name              VARCHAR(200) NOT NULL,
    name_en           VARCHAR(200),
    market            JSONB DEFAULT '[]',
    category          JSONB DEFAULT '[]',
    official          BOOLEAN DEFAULT false,
    free              BOOLEAN DEFAULT true,
    status            VARCHAR(20) DEFAULT 'unknown',
    protocol          JSONB DEFAULT '[]',
    base_url          TEXT,
    sdk               VARCHAR(100),
    supports          JSONB DEFAULT '[]',
    fallback          JSONB DEFAULT '[]',
    rate_limit        JSONB DEFAULT '{}',
    authentication    BOOLEAN DEFAULT false,
    priority          INTEGER DEFAULT 0,
    config            JSONB DEFAULT '{}',
    doc_url           TEXT,
    notes             TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_providers_status ON providers(status);
CREATE INDEX idx_providers_priority ON providers(priority DESC);
CREATE INDEX idx_providers_category ON providers USING gin(category);

-- ============================================================
-- 4.7 research_tasks 表 — 情景记忆（研究任务历史）
-- ============================================================
CREATE TABLE IF NOT EXISTS research_tasks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question          TEXT NOT NULL,
    agent_type        VARCHAR(50) DEFAULT 'research',
    market            VARCHAR(10),
    symbol            VARCHAR(20),
    plan              JSONB DEFAULT '{}',
    answer            TEXT,
    quality           VARCHAR(20),
    confidence        FLOAT,
    document_count    INTEGER DEFAULT 0,
    elapsed_seconds   FLOAT,
    status            VARCHAR(20) DEFAULT 'running',
    error             TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    completed_at      TIMESTAMPTZ
);

CREATE INDEX idx_research_tasks_symbol ON research_tasks(symbol);
CREATE INDEX idx_research_tasks_status ON research_tasks(status);
CREATE INDEX idx_research_tasks_created ON research_tasks(created_at DESC);
