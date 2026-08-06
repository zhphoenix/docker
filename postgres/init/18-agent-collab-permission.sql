-- ============================================================
-- 18. Agent Center 迁移 — 跨 Agent 协同监控 + 权限管理
-- 独立迁移文件，幂等（ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS），
-- 不破坏现有数据。init 脚本仅首次初始化生效，存量 DB 需手动 psql 应用。
-- 覆盖: AC-P4-5（agent_runs.trace_id 跨 Agent 调用链）
--       AC-P4-6（agents.api_enabled 权限开关）
-- ============================================================

-- 1. AC-P4-5：agent_runs 增加 trace_id，标识一次跨 Agent 调用链
--    （news_intelligence 触发 knowledge_ingestion 时共享同一 trace_id）
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64);
CREATE INDEX IF NOT EXISTS idx_agent_runs_trace
    ON agent_runs(trace_id, created_at);

-- 2. AC-P4-6：agents 增加 api_enabled 权限开关（停用后其 API 返回 403）
ALTER TABLE agents ADD COLUMN IF NOT EXISTS api_enabled BOOLEAN DEFAULT true;