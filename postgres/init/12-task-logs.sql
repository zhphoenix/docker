-- ============================================================
-- 12. task_logs 表 — 任务执行日志（Workflow 处理中心）
-- 独立迁移文件，幂等（CREATE TABLE IF NOT EXISTS），不破坏现有数据
-- ============================================================

CREATE TABLE IF NOT EXISTS task_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id     UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    level       VARCHAR(20) DEFAULT 'info',
    message     TEXT NOT NULL,
    stage       VARCHAR(50) DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs(task_id, created_at);