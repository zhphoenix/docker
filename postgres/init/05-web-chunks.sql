-- ============================================================
-- Web Chunks 表 — 网页分块存储
-- 基于 Crawl4AI 集成设计规范 第10节: Chunk → Embedding → Qdrant
-- ============================================================

CREATE TABLE IF NOT EXISTS web_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    page_id         UUID NOT NULL REFERENCES web_pages(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL DEFAULT 0,
    heading         VARCHAR(500),
    content         TEXT NOT NULL,
    token_count     INTEGER,
    qdrant_point_id UUID,
    embedded        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    -- 同一页面内 chunk_index 唯一
    UNIQUE (page_id, chunk_index)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_web_chunks_page_id ON web_chunks(page_id);
CREATE INDEX IF NOT EXISTS idx_web_chunks_need_embed
    ON web_chunks(page_id, chunk_index)
    WHERE qdrant_point_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_web_chunks_qdrant_point_id ON web_chunks(qdrant_point_id);

-- 注释
COMMENT ON TABLE web_chunks IS '网页 Markdown 分块，用于 Embedding → Qdrant 向量检索';
COMMENT ON COLUMN web_chunks.page_id IS '关联 web_pages.id';
COMMENT ON COLUMN web_chunks.heading IS '该分块所属的 Markdown 标题';
COMMENT ON COLUMN web_chunks.qdrant_point_id IS 'Qdrant 向量点 ID（嵌入后回写）';
