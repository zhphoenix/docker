-- Watchlist Intelligence Module — 数据库 Schema
-- 基于 docs/design/Watchlist_Intelligence_Module_Design.md §7
--
-- 前置: 在 09-news-schema.sql 之后执行（引用 news.articles / news.events）
-- Schema: watchlist（独立于 news / core / document / audit）
-- 简化去用户：单用户，无 user_id
-- ============================================================

CREATE SCHEMA IF NOT EXISTS watchlist;

-- ============================================================
-- 自选股表
-- ============================================================
CREATE TABLE IF NOT EXISTS watchlist.watchlist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_code TEXT NOT NULL,                 -- 000858 / 00700 / AAPL
    stock_name TEXT NOT NULL,
    market TEXT,                              -- CN / HK / US
    industry TEXT,                            -- 申万行业 / 行业分类
    group_name TEXT,                          -- 分组（科技/消费/新能源/港股...）
    tags JSONB DEFAULT '[]',                  -- 标签数组
    enabled BOOLEAN DEFAULT true,             -- 是否参与每日监控
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (stock_code)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_group ON watchlist.watchlist(group_name);
CREATE INDEX IF NOT EXISTS idx_watchlist_enabled ON watchlist.watchlist(enabled);

COMMENT ON TABLE watchlist.watchlist IS '自选股（用户关注对象管理，单用户）';

-- ============================================================
-- 自选股事件表（每日监控发现的重要事件）
-- ============================================================
CREATE TABLE IF NOT EXISTS watchlist.watchlist_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_code TEXT NOT NULL,
    news_id UUID,                             -- 关联 news.articles.id（可追溯 Evidence）
    event_id UUID,                            -- 关联 news.events.id（可追溯 Evidence）
    importance INT NOT NULL DEFAULT 3,        -- 1~5（对账 watch_analysis_enums.importance_levels）
    sentiment TEXT DEFAULT 'neutral',         -- bullish / bearish / neutral
    confidence TEXT DEFAULT 'medium',         -- official / high / medium / low / rumor
    impact_horizon TEXT DEFAULT 'short_term', -- short_term / mid_term / long_term
    summary TEXT,                             -- AI 摘要
    source_type TEXT,                         -- company / industry / supply_chain / policy / macro / market
    event_time TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_watchlist_events_code ON watchlist.watchlist_events(stock_code);
CREATE INDEX IF NOT EXISTS idx_watchlist_events_importance ON watchlist.watchlist_events(importance);
CREATE INDEX IF NOT EXISTS idx_watchlist_events_created ON watchlist.watchlist_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_events_news ON watchlist.watchlist_events(news_id);

COMMENT ON TABLE watchlist.watchlist_events IS '自选股监控事件（每日发现的重要新闻/公告/行业/政策事件）';

-- ============================================================
-- 每日报告表
-- ============================================================
CREATE TABLE IF NOT EXISTS watchlist.daily_watchlist_report (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_date DATE NOT NULL UNIQUE,         -- 每日一份
    title TEXT NOT NULL,
    content TEXT,                             -- Markdown 全文
    summary TEXT,                             -- 简要汇总
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_report_date ON watchlist.daily_watchlist_report(report_date DESC);

COMMENT ON TABLE watchlist.daily_watchlist_report IS '每日 Watchlist 研究报告（按 report_date 幂等 upsert）';

-- ============================================================
-- 告警表（Web 通知 + 通用 Webhook）
-- ============================================================
CREATE TABLE IF NOT EXISTS watchlist.watchlist_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_code TEXT,
    title TEXT NOT NULL,
    content TEXT,
    level TEXT DEFAULT 'info',                -- critical / important / info
    event_id UUID,
    channel TEXT NOT NULL DEFAULT 'web',      -- 'web' / 'webhook'
    webhook_url TEXT,                         -- 实际发送的 webhook 地址
    delivered BOOLEAN DEFAULT true,           -- 是否投递成功
    read BOOLEAN DEFAULT false,               -- Web 通知是否已读
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_watchlist_alerts_read ON watchlist.watchlist_alerts(read);
CREATE INDEX IF NOT EXISTS idx_watchlist_alerts_created ON watchlist.watchlist_alerts(created_at DESC);

COMMENT ON TABLE watchlist.watchlist_alerts IS 'Watchlist 告警记录（Web 站内通知 + Webhook 投递轨迹）';

-- ============================================================
-- 配置表（单行：定时时间 / 自动运行开关 / Webhook）
-- ============================================================
CREATE TABLE IF NOT EXISTS watchlist.watchlist_settings (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- 强制单行
    schedule_time TIME NOT NULL DEFAULT '07:00',        -- 每日定时执行时间
    auto_enabled BOOLEAN NOT NULL DEFAULT true,         -- 自动运行开关
    webhook_url TEXT,                                   -- 通用 Webhook 地址
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE watchlist.watchlist_settings IS 'Watchlist 每日工作流配置（单行）';

-- 初始化默认配置行
INSERT INTO watchlist.watchlist_settings (id, schedule_time, auto_enabled, webhook_url)
VALUES (1, '07:00', true, NULL)
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- 验证
-- ============================================================
DO $$
DECLARE
    table_count INT;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'watchlist';

    RAISE NOTICE 'Watchlist schema init complete: % tables created', table_count;

    IF table_count < 5 THEN
        RAISE EXCEPTION 'Watchlist schema init failed: expected 5 tables, got %', table_count;
    END IF;
END $$;