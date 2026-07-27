-- ============================================================
-- AI 投研平台 — Web Ingestion Layer: web_pages 表
-- 基于 Crawl4AI 集成设计规范 第8节 + 第18.2节 (Phase 1)
-- ============================================================

-- web_pages 表 — 网页抓取元数据 + 重试状态
CREATE TABLE IF NOT EXISTS web_pages (
    -- 基础标识
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url               TEXT NOT NULL,
    title             VARCHAR(500),
    domain            VARCHAR(200) NOT NULL,

    -- HTTP 状态与缓存
    status            INTEGER,                    -- HTTP 状态码
    etag              VARCHAR(200),               -- ETag
    last_modified     VARCHAR(200),               -- Last-Modified 头
    content_hash      VARCHAR(128),               -- 内容 SHA256 Hash

    -- 存储路径
    markdown_path     TEXT,                       -- Markdown 本地/MinIO 路径
    minio_path        TEXT,                       -- MinIO 对象路径

    -- 抓取时间
    crawl_time        TIMESTAMPTZ DEFAULT NOW(),  -- 最近抓取时间

    -- Phase 1: 弹性抓取与失败恢复
    retry_count       INTEGER DEFAULT 0,          -- 当前连续重试次数
    last_error        TEXT,                       -- 最近一次错误信息
    error_code        INTEGER,                    -- HTTP 错误码
    page_status       VARCHAR(20) DEFAULT 'pending',  -- pending/crawling/success/failed/dead
    next_retry_at     TIMESTAMPTZ,                -- 下次允许重试时间

    -- Phase 2: 增量变更检测（预留）
    prev_content_hash VARCHAR(128),               -- 上一次内容 Hash
    content_version   INTEGER DEFAULT 1,          -- 内容版本号
    sync_status       VARCHAR(20) DEFAULT 'pending_sync',  -- synced/pending_sync/stale/archived
    qdrant_point_ids  TEXT[],                     -- 关联的 Qdrant point ID 列表
    last_synced_at    TIMESTAMPTZ,                -- 最近同步至向量库时间

    -- 元数据
    metadata          JSONB DEFAULT '{}',         -- 扩展元数据
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),

    -- 约束
    UNIQUE(url)
);

-- 索引
CREATE INDEX idx_web_pages_domain ON web_pages(domain);
CREATE INDEX idx_web_pages_page_status ON web_pages(page_status);
CREATE INDEX idx_web_pages_sync_status ON web_pages(sync_status);
CREATE INDEX idx_web_pages_next_retry ON web_pages(next_retry_at) WHERE page_status IN ('failed', 'pending');
CREATE INDEX idx_web_pages_crawl_time ON web_pages(crawl_time DESC);
CREATE INDEX idx_web_pages_metadata ON web_pages USING gin(metadata);

-- 触发器：自动更新 updated_at
CREATE OR REPLACE FUNCTION update_web_pages_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_web_pages_updated_at
    BEFORE UPDATE ON web_pages
    FOR EACH ROW
    EXECUTE FUNCTION update_web_pages_updated_at();

-- 注释
COMMENT ON TABLE web_pages IS '网页抓取元数据与状态管理（Crawl4AI Web Ingestion Layer）';
COMMENT ON COLUMN web_pages.page_status IS '页面状态: pending=待抓取, crawling=抓取中, success=成功, failed=失败, dead=死信';
COMMENT ON COLUMN web_pages.sync_status IS '向量同步状态: synced=已同步, pending_sync=待同步, stale=过期, archived=已归档';
COMMENT ON COLUMN web_pages.retry_count IS '当前连续重试次数（成功后重置为0）';
COMMENT ON COLUMN web_pages.next_retry_at IS '下次允许重试时间（指数退避计算）';
