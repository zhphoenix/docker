-- ============================================================
-- 15. knowledge_packages 表 — Document Pipeline 产出的知识包契约载体
-- 独立迁移文件，幂等（CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS），
-- 不破坏现有数据。init 脚本仅首次初始化生效，存量 DB 需手动 psql 应用。
-- 覆盖: DP-A2（knowledge_packages 幂等迁移表）
-- 契约来源: AI-Platform-System-Design/schemas/ai_platform/knowledge_package.schema.json
--          + langgraph/schemas/knowledge_package.py (pydantic v2)
-- payload: KnowledgePackage 完整序列化（JSONB）
-- processing_metadata: 处理元信息冗余列（便于按处理信息索引）
-- ============================================================

CREATE TABLE IF NOT EXISTS knowledge_packages (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    package_version      INTEGER NOT NULL DEFAULT 1,            -- Package 版本号（从 1 递增）
    schema_version       VARCHAR(20) NOT NULL DEFAULT '1.0',    -- 契约 schema 版本（预留演进）
    source_type          VARCHAR(30) NOT NULL,                  -- annual_report / news / web / general
    document_id          UUID,                                  -- 关联文档 ID（document.documents.id）
    status               VARCHAR(20) NOT NULL DEFAULT 'draft',  -- draft / published / consumed / failed
    payload              JSONB NOT NULL,                        -- KnowledgePackage 完整序列化
    processing_metadata  JSONB,                                 -- 处理元信息（冗余列）
    publish_time         TIMESTAMPTZ,                           -- 发布为 published 的时间
    retry_count          INTEGER NOT NULL DEFAULT 0,            -- 消费/发布失败重试计数
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_knowledge_packages_status CHECK (status IN ('draft', 'published', 'consumed', 'failed')),
    CONSTRAINT chk_knowledge_packages_source_type CHECK (source_type IN ('annual_report', 'news', 'web', 'general'))
);

-- 状态 + 创建时间索引（KOC Inbox 轮询 published/draft 消费用）
CREATE INDEX IF NOT EXISTS idx_knowledge_packages_status_created
    ON knowledge_packages(status, created_at);

-- 文档纬度索引（按 document_id 追溯某文档的全部 Package 版本）
CREATE INDEX IF NOT EXISTS idx_knowledge_packages_document
    ON knowledge_packages(document_id);

-- 源类型 + 最新优先索引（统计/列表用）
CREATE INDEX IF NOT EXISTS idx_knowledge_packages_source_type
    ON knowledge_packages(source_type, created_at DESC);