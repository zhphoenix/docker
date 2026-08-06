-- ============================================================
-- Source Health — 新闻采集健康指标（NIC-C1 / NIC-C2）
--
-- 前置: 在 09-news-schema.sql 之后执行（依赖 news schema）
-- 幂等: 可重复执行（CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS）
--
-- 采集指标四项：Latency / Errors / Articles / Duplicates
--   - 独立表 news.collect_runs：单次采集明细（历史与聚合）
--   - 扩列 news.sources.last_*：每个源最近一次健康状态（面板快速读取）
-- ============================================================

CREATE SCHEMA IF NOT EXISTS news;

-- ============================================================
-- 单次采集运行记录（每次采集一行）
-- ============================================================
CREATE TABLE IF NOT EXISTS news.collect_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id        TEXT NOT NULL,
    source_name      TEXT,
    success          BOOLEAN DEFAULT true,
    latency_ms       BIGINT,                    -- Latency：本次采集耗时
    articles_fetched INTEGER DEFAULT 0,         -- Articles：采集到的原始文章数
    articles_stored  INTEGER DEFAULT 0,         -- 去重后实际入库文章数
    duplicates       INTEGER DEFAULT 0,         -- Duplicates：去重数 = fetched - stored
    error            TEXT,                      -- Errors：失败原因
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_collect_runs_source  ON news.collect_runs(source_id, created_at);
CREATE INDEX IF NOT EXISTS idx_collect_runs_created ON news.collect_runs(created_at DESC);

COMMENT ON TABLE news.collect_runs IS '新闻源单次采集健康指标（Latency/Errors/Articles/Duplicates）';

-- ============================================================
-- news.sources 扩列：最近一次健康状态（面板快速读取，不破坏原表）
-- ============================================================
ALTER TABLE news.sources
    ADD COLUMN IF NOT EXISTS last_latency_ms BIGINT,
    ADD COLUMN IF NOT EXISTS last_success BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS last_error TEXT,
    ADD COLUMN IF NOT EXISTS error_count INTEGER DEFAULT 0;