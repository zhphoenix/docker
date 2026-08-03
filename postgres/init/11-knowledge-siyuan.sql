-- ============================================================
-- Knowledge SiYuan Integration — 增量迁移（幂等）
-- 基于 docs/design/SiYuan/* 设计规范
--
-- 新增:
--   core.knowledge_inbox         — Knowledge Inbox（HITL 规范 §4）
--   core.knowledge_render_jobs   — Render Queue（AI 自动生成页面规范 §16）
--   core.entities 同步字段        — last_synced_at / last_modified_by /
--                                  sync_version / sync_status
--   audit.knowledge_review_log   — 审核日志（HITL 规范）
--
-- 兼容: 全新数据库直接建表；已有库 IF NOT EXISTS 跳过
-- ============================================================

-- ── 1. Knowledge Inbox 表（HITL 规范 §4） ──
CREATE TABLE IF NOT EXISTS core.knowledge_inbox (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    object_type   TEXT NOT NULL,                 -- entity / fact / relation / event / document
    object_id     UUID,
    status        TEXT NOT NULL DEFAULT 'NEW',   -- NEW/EXTRACTED/READY_REVIEW/APPROVED/REJECTED/ARCHIVED
    confidence    FLOAT,
    source        TEXT,
    content       JSONB DEFAULT '{}',
    reviewer      TEXT,
    review_time   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inbox_status ON core.knowledge_inbox(status);
CREATE INDEX IF NOT EXISTS idx_inbox_obj ON core.knowledge_inbox(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_inbox_created ON core.knowledge_inbox(created_at);

-- ── 2. Render Queue 表（AI 自动生成页面规范 §16） ──
CREATE TABLE IF NOT EXISTS core.knowledge_render_jobs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity       UUID REFERENCES core.entities(id) ON DELETE CASCADE,
    type         TEXT NOT NULL,                     -- Company/Industry/Event/Person/Security/Document
    section      TEXT,                              -- 增量更新用：Financial/Operations/...
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending/running/done/failed
    retry        INT DEFAULT 0,
    priority     INT DEFAULT 5,                     -- 越小越优先
    error_message TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_render_jobs_status ON core.knowledge_render_jobs(status, priority);
CREATE INDEX IF NOT EXISTS idx_render_jobs_entity ON core.knowledge_render_jobs(entity);
CREATE INDEX IF NOT EXISTS idx_render_jobs_created ON core.knowledge_render_jobs(created_at);

-- ── 3. entities 同步字段（SiYuan 接入规范 §12） ──
ALTER TABLE core.entities ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ;
ALTER TABLE core.entities ADD COLUMN IF NOT EXISTS last_modified_by TEXT;   -- AI / Human
ALTER TABLE core.entities ADD COLUMN IF NOT EXISTS sync_version INT DEFAULT 0;
ALTER TABLE core.entities ADD COLUMN IF NOT EXISTS sync_status TEXT DEFAULT 'Synced';
-- sync_status 枚举: Synced / Pending Review / Conflict

-- ── 4. 审核日志（HITL 规范） ──
CREATE TABLE IF NOT EXISTS audit.knowledge_review_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inbox_id      UUID REFERENCES core.knowledge_inbox(id) ON DELETE CASCADE,
    action        TEXT NOT NULL,                    -- approve / reject / auto_approve
    reviewer      TEXT,
    reason        TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_review_log_inbox ON audit.knowledge_review_log(inbox_id);

-- ── 5. 预置数据：render job 类型枚举（供校验/文档） ──
INSERT INTO taxonomy.knowledge_statuses (name, description) VALUES
    ('pending_review', '待人工审核（SiYuan 同步冲突）'),
    ('synced', '已同步至 SiYuan')
ON CONFLICT (name) DO NOTHING;