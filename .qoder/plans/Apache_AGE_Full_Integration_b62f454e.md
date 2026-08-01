# News Intelligence Pipeline 全量实施计划

## 架构决策

基于现有项目模式，采用以下布局：

| 组件 | 位置 | 模式参考 |
|---|---|---|
| News Agent（处理管线） | `langgraph/agent/news_agent/` | 同 `knowledge_agent/` |
| News MCP Server | `mcp-news/` | 同 `mcp-knowledge/` |
| Collector（采集调度） | `langgraph/agent/news_agent/collector/` | 复用 `src/providers/web/crawl4ai_provider.py` |
| DB Schema | `postgres/init/09-news-schema.sql` | 同 `06-knowledge-schema.sql` |
| News Sources 注册 | `registry/news_sources.yaml` | 同 `registry/websites.yaml` |
| Prompts | `langgraph/agent/prompts/news/` | PRM-001~004 |

**关键约束**：
- ARCH-003: nodes/ 不直接 import asyncpg/httpx，通过 tools/ 访问
- MCP-001/002: MCP Tools 不含业务逻辑，通过 storage/ 访问 DB
- PRM-004: `prompts/news/system.md` 必须存在
- 类型枚举引用 `specs/ontology.yaml`（10 Entity Types + 9 Event Types）
- Agent 规范名称: **News Intelligence Agent**（agent-registry.yaml §3）

---

## Phase 1: 数据库 Schema + 基础设施

### 1.1 创建 `postgres/init/09-news-schema.sql`

```sql
CREATE SCHEMA IF NOT EXISTS news;

-- 新闻源注册表
CREATE TABLE news.sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT UNIQUE NOT NULL,        -- reuters, eastmoney...
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,             -- rss / crawler / api
    category TEXT[],                       -- macro, stock, company...
    market TEXT[],                         -- CN, HK, US, Global
    priority TEXT DEFAULT 'normal',        -- high / normal / low
    config JSONB DEFAULT '{}',            -- 采集配置（URL、频率等）
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 新闻文章
CREATE TABLE news.articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES news.sources(id),
    title TEXT NOT NULL,
    content TEXT,
    summary TEXT,
    url TEXT UNIQUE,
    language TEXT DEFAULT 'zh',
    category TEXT,                         -- macro/stock/company/geopolitics
    published_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    content_hash TEXT,                     -- 去重用
    embedding_id TEXT,                     -- Qdrant point ID
    minio_key TEXT,                        -- MinIO 原始文件路径
    metadata JSONB DEFAULT '{}',
    status TEXT DEFAULT 'raw'             -- raw/processed/extracted/indexed
);
CREATE INDEX idx_articles_published ON news.articles(published_at DESC);
CREATE INDEX idx_articles_category ON news.articles(category);
CREATE INDEX idx_articles_hash ON news.articles(content_hash);

-- 新闻实体（文章级，尚未合并到 core.entities）
CREATE TABLE news.entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID REFERENCES news.articles(id),
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,             -- ontology.yaml 10 种
    description TEXT,
    confidence REAL DEFAULT 1.0,
    core_entity_id UUID,                  -- 合并后指向 core.entities.id
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_news_entities_article ON news.entities(article_id);
CREATE INDEX idx_news_entities_name ON news.entities(name);

-- 新闻事件
CREATE TABLE news.events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID REFERENCES news.articles(id),
    event_type TEXT NOT NULL,              -- ontology.yaml 9 种
    title TEXT NOT NULL,
    summary TEXT,
    event_time TIMESTAMPTZ,
    entities UUID[],                       -- 关联 news.entities IDs
    impact_score REAL,                    -- -1.0 ~ 1.0
    impact_direction TEXT,                -- positive/negative/neutral
    market TEXT[],
    sector TEXT[],
    confidence REAL DEFAULT 1.0,
    embedding_id TEXT,                    -- Qdrant point ID
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_news_events_type ON news.events(event_type);
CREATE INDEX idx_news_events_time ON news.events(event_time DESC);

-- 新闻关系（文章级实体间关系）
CREATE TABLE news.relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID REFERENCES news.articles(id),
    source_entity UUID REFERENCES news.entities(id),
    target_entity UUID REFERENCES news.entities(id),
    relation_type TEXT NOT NULL,           -- ontology.yaml 10 种
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 1.2 创建 `registry/news_sources.yaml`

初始新闻源配置（RSS + Crawler + API），参考设计文档 §5 Provider Registry。

### 1.3 Qdrant Collections 初始化脚本

创建 `scripts/init_news_qdrant.py`：
- `news_embeddings`（文章 embedding，用于去重 + 语义搜索）
- `news_events`（事件 embedding，用于事件语义检索）

### 1.4 MinIO Buckets

在 `minio/init-buckets.sh` 中追加：
- `news-raw`（原始 HTML/JSON）
- `news-images`（新闻图片）

---

## Phase 2: News Intelligence Agent（LangGraph 处理管线）

### 2.1 目录结构

```
langgraph/agent/news_agent/
├── __init__.py
├── graph.py              # StateGraph 定义（7 节点）
├── state.py              # NewsState TypedDict
├── collector/
│   ├── __init__.py
│   ├── rss_collector.py      # Feedparser RSS 采集
│   ├── web_collector.py      # Crawl4AI 网页采集（复用 src/providers/web/）
│   └── source_registry.py   # 读取 registry/news_sources.yaml
├── nodes/
│   ├── __init__.py
│   ├── cleaner.py        # Node 1: 语言检测 + 清洗 + 标准化
│   ├── deduplicator.py   # Node 2: 标题相似 + Embedding 去重
│   ├── classifier.py     # Node 3: 分类 + 重要性评分
│   ├── entity.py         # Node 4a: 实体识别（复用 Knowledge Agent prompt 模式）
│   ├── event.py          # Node 4b: 事件抽取
│   ├── impact.py         # Node 5: 投资影响分析
│   └── publisher.py      # Node 6: 存储 + 触发 Knowledge Agent
└── storage/
    ├── __init__.py
    └── postgres.py       # news schema CRUD
```

### 2.2 `state.py` — NewsState

```python
class NewsState(TypedDict):
    # 输入
    source_id: str
    raw_articles: list[dict]     # [{title, content, url, published_at}]
    # 处理中间态
    cleaned_articles: list[dict]
    unique_articles: list[dict]
    classified_articles: list[dict]
    # 提取结果
    entities: list[dict]
    events: list[dict]
    relations: list[dict]
    # 影响分析
    impact_assessments: list[dict]
    # 存储追踪
    stored_article_ids: list[str]
    stored_event_ids: list[str]
    knowledge_agent_triggered: bool
    # 控制
    errors: Annotated[list[str], operator.add]
```

### 2.3 `graph.py` — 工作流拓扑

```
START → cleaner → deduplicator → classifier
    → [entity_extractor || event_extractor]  (fan-out)
    → impact_analyzer                        (fan-in)
    → publisher → END
```

### 2.4 Prompts

创建 `langgraph/agent/prompts/news/`：
- `system.md` — News Intelligence Agent 系统提示（PRM-004）
- `classification.md` — 新闻分类 + 重要性评分
- `entity_extraction.md` — 新闻实体识别（引用 ontology.yaml 10 种）
- `event_extraction.md` — 事件抽取（引用 ontology.yaml 9 种 event_type）
- `impact_analysis.md` — 投资影响分析

### 2.5 Collector 采集层

- `rss_collector.py`: 使用 `feedparser` 解析 RSS/Atom feeds
- `web_collector.py`: 复用 `src/providers/web/crawl4ai_provider.py`（Crawl4AI HTTP API）
- `source_registry.py`: 加载 `registry/news_sources.yaml`，按 priority 排序

### 2.6 与 Knowledge Agent 集成

`publisher.py` 节点在存储新闻实体/事件后，对高置信度（confidence >= 0.8）的实体和关系触发 Knowledge Agent 的 `build_knowledge_organization_graph()` 子图，将新闻知识合并到 `core.entities` / `core.relations`。

---

## Phase 3: News MCP Server

### 3.1 目录结构

```
mcp-news/
├── Dockerfile
├── compose.yml
├── requirements.txt
└── server/
    ├── __init__.py
    ├── main.py           # FastMCP 入口（:8201）
    ├── config.py         # NewsMCPSettings
    ├── storage/
    │   ├── __init__.py
    │   └── postgres.py   # news schema 查询
    └── tools/
        ├── __init__.py
        ├── article.py    # search_news / get_news_article
        ├── event.py      # search_news_event / get_event_impact
        ├── analysis.py   # analyze_news_impact / get_news_timeline
        └── source.py     # list_news_sources
```

### 3.2 Tools 定义（7 个）

| # | Tool | 模块 | 职责 |
|---|---|---|---|
| 1 | `search_news` | article | 关键词 + 时间范围 + 分类搜索新闻 |
| 2 | `get_news_article` | article | 获取文章详情（含实体/事件） |
| 3 | `search_news_event` | event | 按类型/时间/实体搜索事件 |
| 4 | `get_event_impact` | event | 获取事件影响评估 |
| 5 | `analyze_news_impact` | analysis | 聚合分析实体近期新闻影响 |
| 6 | `get_news_timeline` | analysis | 获取实体新闻时间线 |
| 7 | `list_news_sources` | source | 列出新闻源及状态 |

### 3.3 Docker 编排

`mcp-news/compose.yml`：端口 8201，依赖 postgres + qdrant，模式同 `mcp-knowledge/compose.yml`。

---

## Phase 4: Docker 集成 + 调度

### 4.1 更新根 `compose.yml`

```yaml
include:
  # ... existing ...
  - mcp-news/compose.yml
```

### 4.2 采集调度

在现有 `langgraph/agent/scheduler/` 中新增新闻采集定时任务：
- 高优先级源（RSS）：每 30 分钟
- 普通源（Crawler）：每 2 小时
- 低优先级源：每 6 小时

### 4.3 更新 `architecture.yaml`

scope 追加 `"mcp-news/"`，新增 MCP Server 实例注册。

---

## Phase 5: 规范同步 + 验证

### 5.1 更新 `specs/agent-registry.yaml`

- §1: News Intelligence Agent 从「规划中」移至「已实现」
- §2: 新增 News MCP Server 服务条目
- §5: Qdrant Collections 追加 news_embeddings / news_events

### 5.2 更新 `specs/ontology.yaml`

追加 `news_category` 枚举（macro/stock/company/geopolitics/policy/technology）。

### 5.3 验证清单

- [ ] `docker compose up postgres` → `news` schema 5 张表创建成功
- [ ] Qdrant `news_embeddings` + `news_events` Collections 存在
- [ ] MinIO `news-raw` + `news-images` Buckets 存在
- [ ] News Agent 工作流：输入测试文章 → 输出实体/事件/影响
- [ ] News MCP Server `:8201` 健康检查通过
- [ ] `search_news("NVIDIA")` 返回结果
- [ ] 高置信度实体自动合并到 `core.entities`
- [ ] `registry/news_sources.yaml` 新增源无需改代码
- [ ] Prompts 均在 `prompts/news/` 目录（PRM-001/002）
- [ ] nodes/ 无 asyncpg/httpx 直接 import（ARCH-003）

---

## 文件变更清单

| 操作 | 文件 | Phase |
|---|---|---|
| 新建 | `postgres/init/09-news-schema.sql` | 1 |
| 新建 | `registry/news_sources.yaml` | 1 |
| 新建 | `scripts/init_news_qdrant.py` | 1 |
| 修改 | `minio/init-buckets.sh` | 1 |
| 新建 | `langgraph/agent/news_agent/__init__.py` | 2 |
| 新建 | `langgraph/agent/news_agent/state.py` | 2 |
| 新建 | `langgraph/agent/news_agent/graph.py` | 2 |
| 新建 | `langgraph/agent/news_agent/collector/rss_collector.py` | 2 |
| 新建 | `langgraph/agent/news_agent/collector/web_collector.py` | 2 |
| 新建 | `langgraph/agent/news_agent/collector/source_registry.py` | 2 |
| 新建 | `langgraph/agent/news_agent/nodes/cleaner.py` | 2 |
| 新建 | `langgraph/agent/news_agent/nodes/deduplicator.py` | 2 |
| 新建 | `langgraph/agent/news_agent/nodes/classifier.py` | 2 |
| 新建 | `langgraph/agent/news_agent/nodes/entity.py` | 2 |
| 新建 | `langgraph/agent/news_agent/nodes/event.py` | 2 |
| 新建 | `langgraph/agent/news_agent/nodes/impact.py` | 2 |
| 新建 | `langgraph/agent/news_agent/nodes/publisher.py` | 2 |
| 新建 | `langgraph/agent/news_agent/storage/postgres.py` | 2 |
| 新建 | `langgraph/agent/prompts/news/system.md` | 2 |
| 新建 | `langgraph/agent/prompts/news/classification.md` | 2 |
| 新建 | `langgraph/agent/prompts/news/entity_extraction.md` | 2 |
| 新建 | `langgraph/agent/prompts/news/event_extraction.md` | 2 |
| 新建 | `langgraph/agent/prompts/news/impact_analysis.md` | 2 |
| 新建 | `mcp-news/Dockerfile` | 3 |
| 新建 | `mcp-news/compose.yml` | 3 |
| 新建 | `mcp-news/requirements.txt` | 3 |
| 新建 | `mcp-news/server/main.py` | 3 |
| 新建 | `mcp-news/server/config.py` | 3 |
| 新建 | `mcp-news/server/storage/postgres.py` | 3 |
| 新建 | `mcp-news/server/tools/article.py` | 3 |
| 新建 | `mcp-news/server/tools/event.py` | 3 |
| 新建 | `mcp-news/server/tools/analysis.py` | 3 |
| 新建 | `mcp-news/server/tools/source.py` | 3 |
| 修改 | `compose.yml`（追加 mcp-news） | 4 |
| 修改 | `langgraph/agent/scheduler/scheduler.py`（新增采集任务） | 4 |
| 修改 | `specs/architecture.yaml`（scope + News MCP） | 4 |
| 修改 | `specs/agent-registry.yaml`（状态更新） | 5 |
| 修改 | `specs/ontology.yaml`（news_category） | 5 |

**总计**：~30 个新建文件 + 6 个修改文件

---

## 依赖项

新增 Python 依赖（加入 langgraph 和 mcp-news 的 requirements）：
- `feedparser`（RSS 解析）
- `minio`（MinIO Python SDK，原始文件存储）

已有可复用：
- `httpx`（Crawl4AI API 调用）
- `asyncpg`（PostgreSQL）
- `qdrant-client`（向量检索）
- `fastmcp`（MCP Server）
- `langgraph`（StateGraph）
