-- ============================================================
-- 17. Agent Marketplace 迁移 — agent_templates 模板表
-- 独立迁移文件，幂等（IF NOT EXISTS），不破坏现有数据。
-- 覆盖: AC-P4-4（Agent Marketplace）
-- ============================================================

-- 1. agent_templates 表：Agent 定义模板（发布/导入/导出）
-- definition 为完整 Agent 定义 JSON（含 prompt 版本），可在另一实例导入重建 Agent
CREATE TABLE IF NOT EXISTS agent_templates (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(100) NOT NULL UNIQUE,   -- 模板名（通常 = agent name）
    display_name VARCHAR(100),
    description  TEXT,
    category     VARCHAR(50) DEFAULT 'general',  -- general / research / pipeline ...
    version      VARCHAR(20) DEFAULT 'v1.0',
    author       VARCHAR(100) DEFAULT 'community',
    definition   JSONB NOT NULL,                 -- 完整 Agent 定义（含 prompts）
    installs     INTEGER NOT NULL DEFAULT 0,     -- 安装次数
    source_agent VARCHAR(100),                   -- 来源 Agent（发布时记录）
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_templates_category ON agent_templates(category);
CREATE INDEX IF NOT EXISTS idx_agent_templates_installs ON agent_templates(installs DESC);