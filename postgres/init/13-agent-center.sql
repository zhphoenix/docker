-- ============================================================
-- 13. Agent Center 迁移 — Agent 生命周期 / Prompt / 配置 / 运行记录
-- 独立迁移文件，幂等（IF NOT EXISTS / ADD COLUMN IF NOT EXISTS），
-- 不破坏现有数据。init 脚本仅首次初始化生效，存量 DB 需手动 psql 应用。
-- 覆盖: P1-1(agents扩展) / P1-5(agent_prompts) / P1-6(agent_configs_history)
--       P3-1(agent_runs) / P2-2(agent_tool_stats) / P2-3(mcp_connections)
--       P2-1增强(agent_skills)
-- ============================================================

-- 1. agents 表扩展（Agent 生命周期 / 版本 / 最后活跃）
ALTER TABLE agents ADD COLUMN IF NOT EXISTS version          VARCHAR(20)  DEFAULT 'v1.0';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS display_name     VARCHAR(100);
ALTER TABLE agents ADD COLUMN IF NOT EXISTS status           VARCHAR(20)  DEFAULT 'active'; -- active/paused/deprecated
ALTER TABLE agents ADD COLUMN IF NOT EXISTS last_active_at   TIMESTAMPTZ;

-- 2. agent_prompts 表：Prompt 持久化 + 版本（全量迁移 DB 后的唯一事实源）
CREATE TABLE IF NOT EXISTS agent_prompts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    VARCHAR(100) NOT NULL,          -- 对应 AGENT_REGISTRY key（chat/research/kb/investment）或 common
    name        VARCHAR(100) NOT NULL,          -- 如 "system" / "planner" / "reason"
    content     TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    is_active   BOOLEAN DEFAULT true,
    status      VARCHAR(32) DEFAULT 'published',  -- draft / pending_approval / published（AC-P4-2）
    traffic_weight INTEGER NOT NULL DEFAULT 100, -- A/B 分流权重（AC-P4-3），0=不参与分流
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_id, name, version)
);
CREATE INDEX IF NOT EXISTS idx_agent_prompts_active
    ON agent_prompts(agent_id, name) WHERE is_active = true;

-- 3. agent_configs_history 表：配置回滚
CREATE TABLE IF NOT EXISTS agent_configs_history (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    VARCHAR(100) NOT NULL,
    config      JSONB NOT NULL,
    changed_by  VARCHAR(100) DEFAULT 'ui',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_configs_history_agent
    ON agent_configs_history(agent_id, created_at);

-- 4. agent_runs 表：Agent 运行记录（Metrics/Logs 统一数据源）
CREATE TABLE IF NOT EXISTS agent_runs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id       VARCHAR(100) NOT NULL,
    task_kind      VARCHAR(50) NOT NULL,          -- chat / research / pipeline
    status         VARCHAR(20) DEFAULT 'running', -- running / success / failed
    question       TEXT,
    duration_ms    BIGINT,
    tokens_in      INTEGER DEFAULT 0,
    tokens_out     INTEGER DEFAULT 0,
    error          TEXT,
    error_category VARCHAR(50),                   -- tool_timeout / embedding_error / mcp_error / other
    variant        VARCHAR(50),                   -- A/B 命中的 prompt 版本（AC-P4-3），如 v1 / v2
    trace          JSONB DEFAULT '[]',            -- 节点级轨迹
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent   ON agent_runs(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status  ON agent_runs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_variant ON agent_runs(agent_id, variant, created_at);

-- 5. agent_tool_stats 表：Tool 调用统计（P2-2）
CREATE TABLE IF NOT EXISTS agent_tool_stats (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_name   VARCHAR(100) NOT NULL,
    agent_id    VARCHAR(100),
    duration_ms BIGINT,
    success     BOOLEAN DEFAULT true,
    error_type  VARCHAR(50),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_tool_stats_tool ON agent_tool_stats(tool_name, created_at);

-- 6. mcp_connections 表：MCP 连接状态（P2-3）
CREATE TABLE IF NOT EXISTS mcp_connections (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           VARCHAR(100) NOT NULL UNIQUE,
    url            VARCHAR(500),
    kind           VARCHAR(50) DEFAULT 'mcp',      -- mcp / http / redis ...
    status         VARCHAR(20) DEFAULT 'unknown',  -- connected / disconnected / unknown
    last_heartbeat TIMESTAMPTZ,
    latency_ms     INTEGER DEFAULT 0,
    retry_count    INTEGER DEFAULT 0,
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

-- 7. agent_skills 表：Skill 启用状态持久化（P2-1 增强）
CREATE TABLE IF NOT EXISTS agent_skills (
    name       VARCHAR(100) PRIMARY KEY,
    enabled    BOOLEAN DEFAULT true,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);