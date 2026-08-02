-- ============================================================
-- News Tier 分级字段 — DLM 新闻分级策略
-- 基于 docs/design/新闻生命周期管理（DLM）总体原则.md §8
--
-- Tier 1: 永久保存（美联储/政策/战争/并购/财报/技术突破）→ 进入 Knowledge Graph
-- Tier 2: 长期保存 3-5 年（公司新闻/行业新闻/分析文章）
-- Tier 3: 短期保存 30-90 天（市场快讯/重复报道/转载）
--
-- 幂等: 使用 IF NOT EXISTS 保护
-- ============================================================

ALTER TABLE news.articles ADD COLUMN IF NOT EXISTS tier SMALLINT DEFAULT 3;

COMMENT ON COLUMN news.articles.tier IS '1=永久(KG), 2=长期(3-5年), 3=短期(30-90天)';

CREATE INDEX IF NOT EXISTS idx_news_articles_tier ON news.articles(tier);

-- DLM Raw News Layer: MinIO 对象存储路径
ALTER TABLE news.articles ADD COLUMN IF NOT EXISTS minio_key TEXT;

-- DLM Embedding 去重: Qdrant point ID 关联（供 lifecycle cleanup 使用）
ALTER TABLE news.articles ADD COLUMN IF NOT EXISTS embedding_id TEXT;
