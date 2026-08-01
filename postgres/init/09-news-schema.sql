-- ============================================================
-- News Intelligence Pipeline — 数据库 Schema
-- 基于 docs/design/新闻智能管线规范.md §14
--
-- 前置: 在 06-knowledge-schema.sql 之后执行
-- Schema: news（独立于 core/document/audit）
-- ============================================================

CREATE SCHEMA IF NOT EXISTS news;

-- ============================================================
-- 新闻源注册表
-- ============================================================
CREATE TABLE IF NOT EXISTS news.sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT UNIQUE NOT NULL,            -- reuters, eastmoney, sina_finance...
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,                 -- rss / crawler / api
    category TEXT[],                           -- macro, stock, company, geopolitics, policy
    market TEXT[],                             -- CN, HK, US, Global
    priority TEXT DEFAULT 'normal',            -- high / normal / low
    config JSONB DEFAULT '{}',                -- 采集配置（feed_url, list_url, frequency 等）
    enabled BOOLEAN DEFAULT true,
    last_collected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE news.sources IS '新闻源注册表（对应 registry/news_sources.yaml）';

-- ============================================================
-- 新闻文章
-- ============================================================
CREATE TABLE IF NOT EXISTS news.articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES news.sources(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    content TEXT,
    summary TEXT,
    url TEXT UNIQUE,
    language TEXT DEFAULT 'zh',
    category TEXT,                             -- macro/stock/company/geopolitics/policy/technology
    importance_score REAL DEFAULT 0.5,         -- 0.0 ~ 1.0 重要性评分
    published_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    content_hash TEXT,                         -- SHA-256 去重
    embedding_id TEXT,                         -- Qdrant point ID (news_embeddings)
    minio_key TEXT,                            -- MinIO 原始文件路径 (news-raw bucket)
    metadata JSONB DEFAULT '{}',
    status TEXT DEFAULT 'raw'                  -- raw → cleaned → deduplicated → classified → extracted → indexed
);

CREATE INDEX IF NOT EXISTS idx_news_articles_published ON news.articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_articles_category ON news.articles(category);
CREATE INDEX IF NOT EXISTS idx_news_articles_hash ON news.articles(content_hash);
CREATE INDEX IF NOT EXISTS idx_news_articles_status ON news.articles(status);
CREATE INDEX IF NOT EXISTS idx_news_articles_source ON news.articles(source_id);

COMMENT ON TABLE news.articles IS '新闻文章（从采集到索引的完整生命周期）';

-- ============================================================
-- 新闻实体（文章级，尚未合并到 core.entities）
-- ============================================================
CREATE TABLE IF NOT EXISTS news.entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID REFERENCES news.articles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,                 -- specs/ontology.yaml 10 种 Entity Types
    description TEXT,
    aliases TEXT[],
    confidence REAL DEFAULT 1.0,
    core_entity_id UUID,                       -- 合并后指向 core.entities.id（NULL = 未合并）
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_entities_article ON news.entities(article_id);
CREATE INDEX IF NOT EXISTS idx_news_entities_name ON news.entities(name);
CREATE INDEX IF NOT EXISTS idx_news_entities_type ON news.entities(entity_type);

COMMENT ON TABLE news.entities IS '新闻级实体（文章粒度，高置信度时合并到 core.entities）';

-- ============================================================
-- 新闻事件
-- ============================================================
CREATE TABLE IF NOT EXISTS news.events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID REFERENCES news.articles(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,                  -- specs/ontology.yaml 9 种 Event Types
    title TEXT NOT NULL,
    summary TEXT,
    event_time TIMESTAMPTZ,
    entities UUID[],                           -- 关联 news.entities IDs
    impact_score REAL,                         -- -1.0（极度负面）~ 1.0（极度正面）
    impact_direction TEXT,                     -- positive / negative / neutral
    impact_duration TEXT,                      -- short_term / medium_term / long_term
    market TEXT[],                             -- 影响市场
    sector TEXT[],                             -- 影响行业
    confidence REAL DEFAULT 1.0,
    embedding_id TEXT,                         -- Qdrant point ID (news_events)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_events_type ON news.events(event_type);
CREATE INDEX IF NOT EXISTS idx_news_events_time ON news.events(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_news_events_impact ON news.events(impact_direction);
CREATE INDEX IF NOT EXISTS idx_news_events_article ON news.events(article_id);

COMMENT ON TABLE news.events IS '新闻事件（投资研究关注事件而非文章）';

-- ============================================================
-- 新闻关系（文章级实体间关系）
-- ============================================================
CREATE TABLE IF NOT EXISTS news.relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID REFERENCES news.articles(id) ON DELETE CASCADE,
    source_entity UUID REFERENCES news.entities(id) ON DELETE CASCADE,
    target_entity UUID REFERENCES news.entities(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,               -- specs/ontology.yaml 10 种 Relation Types
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_relations_article ON news.relations(article_id);
CREATE INDEX IF NOT EXISTS idx_news_relations_source ON news.relations(source_entity);
CREATE INDEX IF NOT EXISTS idx_news_relations_target ON news.relations(target_entity);

COMMENT ON TABLE news.relations IS '新闻级实体关系（文章粒度）';

-- ============================================================
-- 验证
-- ============================================================
DO $$
DECLARE
    table_count INT;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'news';

    RAISE NOTICE 'News schema init complete: % tables created', table_count;

    IF table_count < 5 THEN
        RAISE EXCEPTION 'News schema init failed: expected 5 tables, got %', table_count;
    END IF;
END $$;
