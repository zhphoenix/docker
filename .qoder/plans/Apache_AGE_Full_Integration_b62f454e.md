# News Intelligence Pipeline — Web UI 集成实施计划

## Summary

在现有 React 前端（:3001）新增 "News" 导航栏栏目，通过 FastAPI（:8100）新增 `/api/news` REST 端点桥接 PostgreSQL news schema，实现新闻列表/搜索、文章详情、事件浏览、影响分析、实体时间线五大功能模块。

---

## 1. 导航栏入口与路由设计

**命名**: "News"（图标: `Newspaper` from lucide-react）
**位置**: Sidebar navItems 中，置于 "Research" 之后、"Models" 之前
**路由**: `/news`（主页面，内含 Tab 切换）

修改文件:
- `frontend/src/components/layout/Sidebar.tsx` — navItems 数组新增 `{ to: '/news', icon: Newspaper, label: 'News' }`
- `frontend/src/app/router.tsx` — lazy import + route 注册

页面结构（单页面 + Tab 切换）:
```
NewsPage
├── Tab: 新闻列表 (默认)    — 搜索/过滤 + 文章卡片列表
├── Tab: 事件               — 事件列表 + 影响评估
├── Tab: 影响分析           — 实体影响聚合面板
└── Tab: 时间线             — 实体新闻时间线
```

文章详情使用 Sheet/Drawer 侧滑展示（不新增路由），保持单页面体验。

---

## 2. 功能模块划分

### 2.1 新闻列表/搜索 (NewsListTab)
- 关键词搜索框 + 分类下拉（macro/stock/company/geopolitics/policy/technology）+ 时间范围选择（1/7/30/90 天）
- 文章卡片: 标题、摘要、来源、分类 Badge、重要度、发布时间
- 分页/无限滚动（limit + offset）

### 2.2 文章详情 (ArticleDetailSheet)
- 全文内容、摘要
- 关联实体列表（entity_name + entity_type Badge）
- 关联事件列表（event_type + impact_direction 颜色标注）
- 原文链接

### 2.3 事件浏览 (EventsTab)
- 事件类型过滤（earnings/regulation/merger/acquisition/product_launch/macro_policy/geopolitical/supply_chain/technology）
- 事件卡片: 标题、类型 Badge、影响方向（positive/negative/neutral 颜色）、影响分数、时间
- 点击展开影响评估详情

### 2.4 影响分析 (ImpactTab)
- 实体名称输入框 + 时间范围
- 聚合面板: 总事件数、正面/负面/中性计数、平均影响分数
- 事件列表（按影响分数排序）

### 2.5 时间线 (TimelineTab)
- 实体名称输入 + 时间范围
- 垂直时间线组件: 按日期分组，每条显示标题、分类、来源、重要度

---

## 3. 数据接口对接方案

**方案: 在 FastAPI 新增 `/api/news` Router，直接查询 PostgreSQL news schema**

理由:
- 前端已有成熟模式: `apiFetch` → Vite proxy `/api` → FastAPI :8100
- LangGraph Agent 已有 PostgreSQL 连接池（`tools/postgres.py`），可复用
- mcp-news 的 storage 层 SQL 可直接迁移，无需跨服务调用
- 避免前端直连 MCP Server（协议不兼容，MCP 是 stdio/SSE 非 REST）

### 新增后端端点 (`langgraph/agent/api/news.py`)

| Method | Path | 对应 mcp-news tool | 说明 |
|--------|------|-------------------|------|
| GET | `/api/news/articles` | search_news | 搜索新闻列表 (query params: keyword, category, days, limit, offset) |
| GET | `/api/news/articles/{id}` | get_news_article | 文章详情（含 entities/events） |
| GET | `/api/news/events` | search_news_event | 搜索事件 (query params: event_type, entity_name, days, limit) |
| GET | `/api/news/events/{id}/impact` | get_event_impact | 事件影响评估 |
| GET | `/api/news/impact` | analyze_news_impact | 实体影响聚合 (query params: entity_name, days) |
| GET | `/api/news/timeline` | get_news_timeline | 实体时间线 (query params: entity_name, days, limit) |
| GET | `/api/news/sources` | list_news_sources | 新闻源列表 |

### 新增后端存储层 (`langgraph/agent/services/news_storage.py`)

从 `mcp-news/server/storage/postgres.py` 迁移查询逻辑，复用 LangGraph Agent 已有的 PostgreSQL 连接（`tools/postgres.py` 中的连接池）。SQL 查询基本照搬 mcp-news storage 层的 7 个方法。

### 新增前端服务层 (`frontend/src/services/news.ts`)

```typescript
// 遵循 knowledge.ts 的模式
export function fetchNewsArticles(params: NewsQuery): Promise<NewsListResponse>
export function fetchNewsArticle(id: string): Promise<NewsArticle>
export function fetchNewsEvents(params: EventQuery): Promise<EventListResponse>
export function fetchEventImpact(id: string): Promise<EventImpact>
export function fetchNewsImpact(entityName: string, days?: number): Promise<ImpactAnalysis>
export function fetchNewsTimeline(entityName: string, days?: number): Promise<TimelineItem[]>
export function fetchNewsSources(): Promise<NewsSource[]>
```

---

## 4. 任务分解（含依赖顺序）

### Phase A: 后端 API 层（无前端依赖）

| # | 任务 | 文件 | 依赖 |
|---|------|------|------|
| A1 | 创建 news_storage.py — 迁移 mcp-news 的 7 个 SQL 查询方法 | `langgraph/agent/services/news_storage.py` | 无 |
| A2 | 创建 api/news.py — 7 个 REST 端点 + Pydantic response models | `langgraph/agent/api/news.py` | A1 |
| A3 | 注册路由 — app/main.py 添加 news_router | `langgraph/agent/app/main.py` | A2 |
| A4 | 验证 — curl 测试所有端点返回正确 JSON | - | A3 |

### Phase B: 前端基础框架（依赖 Phase A 完成）

| # | 任务 | 文件 | 依赖 |
|---|------|------|------|
| B1 | 创建 services/news.ts — TypeScript 类型 + 7 个 fetch 函数 | `frontend/src/services/news.ts` | A3 |
| B2 | 创建 NewsPage 骨架 — Tab 布局 + 路由注册 + 侧栏入口 | `frontend/src/app/pages/NewsPage.tsx`, `router.tsx`, `Sidebar.tsx` | 无 |
| B3 | 实现 NewsListTab — 搜索/过滤 + 文章卡片 + 分页 | `frontend/src/components/news/NewsListTab.tsx` | B1, B2 |
| B4 | 实现 ArticleDetailSheet — 侧滑详情 + 实体/事件展示 | `frontend/src/components/news/ArticleDetailSheet.tsx` | B1, B3 |

### Phase C: 前端高级功能（依赖 Phase B）

| # | 任务 | 文件 | 依赖 |
|---|------|------|------|
| C1 | 实现 EventsTab — 事件列表 + 类型过滤 + 影响方向标注 | `frontend/src/components/news/EventsTab.tsx` | B1, B2 |
| C2 | 实现 ImpactTab — 实体影响聚合面板 + 统计卡片 | `frontend/src/components/news/ImpactTab.tsx` | B1, B2 |
| C3 | 实现 TimelineTab — 垂直时间线 + 日期分组 | `frontend/src/components/news/TimelineTab.tsx` | B1, B2 |

### Phase D: 集成验证

| # | 任务 | 依赖 |
|---|------|------|
| D1 | 端到端验证 — 启动后端 + 前端，验证所有 Tab 数据加载正常 | A4, C3 |
| D2 | 边界测试 — 空数据/错误状态/Loading 状态展示 | D1 |

---

## 5. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LangGraph Agent 的 PG 连接池未配置 news schema 搜索路径 | 查询失败 | SQL 中显式使用 `news.articles` 全限定表名 |
| news schema 数据量大，无索引时搜索慢 | 响应超时 | 确认 published_at / category 已有索引；添加 LIMIT 保护 |
| 前端组件数量多，一次性开发量大 | 进度风险 | Phase B/C 可逐步交付，每个 Tab 独立可用 |
| mcp-news storage SQL 迁移后字段不一致 | 数据展示错误 | 迁移时逐方法对照验证，保持返回字段名一致 |

---

## 6. 验证方式

1. **后端验证**: `curl http://localhost:8100/api/news/articles?days=7&limit=5` 返回 JSON 数组
2. **前端验证**: 浏览器访问 `http://localhost:3001/news`，确认:
   - 侧栏 "News" 入口高亮正确
   - 新闻列表加载数据、搜索/过滤功能正常
   - 点击文章弹出详情 Sheet，展示实体/事件
   - 事件 Tab 过滤和影响方向颜色正确
   - 影响分析输入实体名后展示聚合统计
   - 时间线按日期分组展示
3. **异常验证**: 后端未启动时，前端展示友好错误提示（非白屏）

---

## 新增文件清单

```
langgraph/agent/services/news_storage.py     (后端存储层)
langgraph/agent/api/news.py                  (后端 API Router)
frontend/src/services/news.ts                (前端服务层)
frontend/src/app/pages/NewsPage.tsx           (主页面)
frontend/src/components/news/NewsListTab.tsx  (新闻列表)
frontend/src/components/news/ArticleDetailSheet.tsx (文章详情)
frontend/src/components/news/EventsTab.tsx    (事件浏览)
frontend/src/components/news/ImpactTab.tsx    (影响分析)
frontend/src/components/news/TimelineTab.tsx  (时间线)
```

## 修改文件清单

```
langgraph/agent/app/main.py                  (注册 news_router)
frontend/src/app/router.tsx                  (添加 /news 路由)
frontend/src/components/layout/Sidebar.tsx   (添加 News 导航项)
```
