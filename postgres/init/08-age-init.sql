-- ============================================================
-- Apache AGE 初始化 — Knowledge Graph 基础设施
-- 基于 docs/design/Apache_AGE_Knowledge_Graph_DDL_Schema.md
--
-- 前置: 08-age-init.sql 在 06/07 之后执行
-- 幂等: 使用 IF NOT EXISTS / DO $$ 保护
-- ============================================================

-- 启用 AGE 扩展
CREATE EXTENSION IF NOT EXISTS age;

-- 加载 AGE（shared_preload_libraries 已配置，此处为兼容）
LOAD 'age';

-- 设置搜索路径（当前会话）
SET search_path = ag_catalog, "$user", public;

-- ============================================================
-- 创建 Knowledge Graph（幂等）
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'investment_knowledge_graph'
    ) THEN
        PERFORM create_graph('investment_knowledge_graph');
        RAISE NOTICE 'Created graph: investment_knowledge_graph';
    END IF;
END $$;

-- ============================================================
-- Vertex Labels（10 种实体类型 + 1 通用 Entity）
-- 对齐 specs/ontology.yaml entity_types
-- ============================================================
DO $$
DECLARE
    vlabel TEXT;
    vlabels TEXT[] := ARRAY[
        'Entity',       -- 通用基类（所有节点继承）
        'Company',
        'Person',
        'Product',
        'Technology',
        'Industry',
        'Country',
        'Organization',
        'Event',
        'Metric',
        'Concept'
    ];
BEGIN
    FOREACH vlabel IN ARRAY vlabels LOOP
        IF NOT EXISTS (
            SELECT 1 FROM ag_catalog.ag_label
            WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'investment_knowledge_graph')
              AND name = vlabel
              AND kind = 'v'
        ) THEN
            PERFORM ag_catalog.create_vlabel('investment_knowledge_graph'::cstring, vlabel::cstring);
            RAISE NOTICE 'Created vlabel: %', vlabel;
        END IF;
    END LOOP;
END $$;

-- ============================================================
-- Edge Labels（10 种关系类型 + SUPERSEDES 事件版本链）
-- 对齐 specs/ontology.yaml relation_types
-- ============================================================
DO $$
DECLARE
    elabel TEXT;
    elabels TEXT[] := ARRAY[
        'supplier',
        'customer',
        'competitor',
        'depends_on',
        'owns',
        'uses',
        'invests_in',
        'located_in',
        'impacts',
        'causes',
        'SUPERSEDES'    -- 事件版本链（Event Versioning）
    ];
BEGIN
    FOREACH elabel IN ARRAY elabels LOOP
        IF NOT EXISTS (
            SELECT 1 FROM ag_catalog.ag_label
            WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'investment_knowledge_graph')
              AND name = elabel
              AND kind = 'e'
        ) THEN
            PERFORM ag_catalog.create_elabel('investment_knowledge_graph'::cstring, elabel::cstring);
            RAISE NOTICE 'Created elabel: %', elabel;
        END IF;
    END LOOP;
END $$;

-- ============================================================
-- 验证
-- ============================================================
DO $$
DECLARE
    graph_count INT;
    vlabel_count INT;
    elabel_count INT;
BEGIN
    SELECT COUNT(*) INTO graph_count FROM ag_catalog.ag_graph WHERE name = 'investment_knowledge_graph';
    SELECT COUNT(*) INTO vlabel_count FROM ag_catalog.ag_label
        WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'investment_knowledge_graph') AND kind = 'v';
    SELECT COUNT(*) INTO elabel_count FROM ag_catalog.ag_label
        WHERE graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'investment_knowledge_graph') AND kind = 'e';

    RAISE NOTICE 'AGE Init Complete: graph=%, vlabels=%, elabels=%', graph_count, vlabel_count, elabel_count;

    IF graph_count = 0 THEN
        RAISE EXCEPTION 'AGE initialization failed: graph not created';
    END IF;
END $$;
