-- ============================================================
-- 14. Watchlist Intelligence Center 迁移 — AI 评分 / 统计冗余 / 监控配置 / 历史聚合
-- 独立迁移文件，幂等（IF NOT EXISTS / ADD COLUMN IF NOT EXISTS），
-- 不破坏现有数据。init 脚本仅首次初始化生效，存量 DB 需手动 psql 应用。
-- 覆盖: P1-1(watchlist扩展) / P1-1(settings扩展) / P1-1(daily_stats表)
-- ============================================================

-- 1. watchlist.watchlist 扩展：AI 评分与统计冗余（Stock Detail / WatchlistGrid 快速展示）
ALTER TABLE watchlist.watchlist
  ADD COLUMN IF NOT EXISTS ai_score INT DEFAULT 0;              -- 0-100
ALTER TABLE watchlist.watchlist
  ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMPTZ;           -- 最近事件时间
ALTER TABLE watchlist.watchlist
  ADD COLUMN IF NOT EXISTS today_event_count INT DEFAULT 0;     -- 今日事件数（定时刷新）
ALTER TABLE watchlist.watchlist
  ADD COLUMN IF NOT EXISTS today_news_count INT DEFAULT 0;      -- 今日新闻数（定时刷新）
ALTER TABLE watchlist.watchlist
  ADD COLUMN IF NOT EXISTS ai_summary TEXT;                     -- 个股 AI 摘要（Stock Detail 展示）
ALTER TABLE watchlist.watchlist
  ADD COLUMN IF NOT EXISTS item_type TEXT DEFAULT 'stock';      -- 监控对象类型
  -- stock / etf / index / industry / company / person / fund / macro_theme


-- 2. watchlist.watchlist_settings 扩展：监控维度 + AI 功能开关
ALTER TABLE watchlist.watchlist_settings
  ADD COLUMN IF NOT EXISTS monitoring_scopes JSONB DEFAULT '["news","announcement","earnings","industry","policy"]';
ALTER TABLE watchlist.watchlist_settings
  ADD COLUMN IF NOT EXISTS ai_summary_enabled BOOLEAN DEFAULT true;
ALTER TABLE watchlist.watchlist_settings
  ADD COLUMN IF NOT EXISTS daily_report_enabled BOOLEAN DEFAULT true;
ALTER TABLE watchlist.watchlist_settings
  ADD COLUMN IF NOT EXISTS email_enabled BOOLEAN DEFAULT false;
ALTER TABLE watchlist.watchlist_settings
  ADD COLUMN IF NOT EXISTS email_address TEXT;
ALTER TABLE watchlist.watchlist_settings
  ADD COLUMN IF NOT EXISTS update_frequency TEXT DEFAULT 'daily';  -- 'realtime'/'hourly'/'daily'
ALTER TABLE watchlist.watchlist_settings
  ADD COLUMN IF NOT EXISTS alert_threshold INT DEFAULT 4;          -- 告警重要性阈值
ALTER TABLE watchlist.watchlist_settings
  ADD COLUMN IF NOT EXISTS notification_channels JSONB DEFAULT '["web","webhook"]'; -- 通知通道

-- 3. 监控历史聚合表（每日一条，缓存统计；History 趋势图数据源）
CREATE TABLE IF NOT EXISTS watchlist.watchlist_daily_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stat_date DATE NOT NULL UNIQUE,
    total_stocks INT NOT NULL DEFAULT 0,
    total_events INT NOT NULL DEFAULT 0,
    high_priority_events INT NOT NULL DEFAULT 0,   -- importance>=4
    total_alerts INT NOT NULL DEFAULT 0,
    critical_alerts INT NOT NULL DEFAULT 0,
    ai_reports_generated INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON watchlist.watchlist_daily_stats(stat_date DESC);

COMMENT ON TABLE watchlist.watchlist_daily_stats IS 'Watchlist 每日监控统计快照';