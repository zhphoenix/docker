# 知识库页面重构规划

## 目标
依据后端已实现 API 盘点结果，重构 Knowledge 前端页面结构，使前端组件与后端接口一一对应；优先完善「处理」按钮交互，实现处理进度直接显示在 documents_cn 集合卡片上（实时进度条、百分比、已完成文件数、当前文件名）。

## 上下文分析（前后端功能对照）
后端已验证能力：
- `/api/knowledge/collections`、`/entities`、`/entities/{id}`、`/entities/{id}/neighbors`、`/facts`、`/search`、`/search/rag`、`/extract`、`/browse-dirs`、`/ingest-minio`、`/ingest`
- `/api/tasks`、`/tasks/{id}`、`/tasks/{id}/retry`、`/tasks/pipeline/status`、`/tasks/pipeline/trigger`、`/tasks/batch-embed`、`/tasks/reindex`

前端功能缺口（需补齐）：search/rag、extract、ingest-minio、pipeline/trigger、batch-embed、reindex、entities neighbors。

## 「处理」任务定义（设计依据）
点击「处理」→ `triggerIngest` → `POST /api/knowledge/ingest` `{path, collection:'documents_cn'}` → 后端 `trigger_ingest` 校验并创建 `doc_pipeline` 任务 → `_run_ingest` 后台执行：读 .md → chunk → embedding → 写入 Qdrant documents_cn → 更新 documents/chunks → 更新任务进度（start/update/complete/fail）→ 返回 `{status:'accepted', task_id}`。

## 关键改动

### 1. 服务层补齐（文件：`frontend/src/services/knowledge.ts`、`frontend/src/services/tasks.ts`）
- `knowledge.ts`：新增 `graphragSearch()`（POST /search/rag）、`triggerExtraction()`（POST /extract）、`triggerIngestMinio()`（POST /ingest-minio）。修正 `IngestResponse` 增加 `task_id`。
- `tasks.ts`：新增 `triggerBatchEmbed()`（POST /tasks/batch-embed）、`triggerPipeline()`（POST /tasks/pipeline/trigger）、`reindexDocument()`（POST /tasks/reindex）、`fetchPipelineStatus()`（GET /tasks/pipeline/status）。

### 2. 「处理」按钮与卡片内实时进度（文件：`frontend/src/components/knowledge/CollectionGrid.tsx`）
- 保留目录输入 + 目录选择弹窗（复用 browse-dirs）。
- 卡片内进度区域：匹配 `runningTask.params.collection === coll.name`，取该集合最新 running 任务；显示「处理中」Loader + 百分比 + 进度条 + 「已完成 X/Y 个文件 · 当前文件名」。用高亮边框（primary/20）与卡片已有「向量化进度」（chunk 维度）明确区分。
- 匹配逻辑：`list_tasks` 已返回 `params`（含 collection），需确认 `params` 为 dict 并取 `collection` 字段。
- 状态反馈：ingest 触发后显示成功/失败 toast；running 期间 5s 轮询；任务完成后自动刷新 `knowledge-collections`（更新 embedded/chunk 计数）。
- 集总和：多任务并发时取 `created_at` 最新者。

### 3. 处理详情 Tab 补充触发入口（文件：`frontend/src/components/knowledge/KnowledgeTasksPanel.tsx`）
- 过滤器区新增「批量向量化」「重新索引」触发按钮（调用 batch-embed / reindex），弥补后端能力缺口。
- 点击概览卡片进度条 → 通过回调/事件跳转到 tasks Tab 并定位该任务。

### 4. 语义搜索扩展（文件：`frontend/src/components/knowledge/SemanticSearchPanel.tsx`）
- 增加检索模式切换：混合检索（/search，现有）与 GraphRAG（/search/rag，新增）。

### 5. 页面结构（文件：`frontend/src/app/pages/KnowledgePage.tsx`）
- 保留 5 Tab 结构；概览为「集合 + 处理」主入口；「处理详情」与概览通过 Tab 联动；知识图谱保持 disabled（Soon）。

## Todo 列表
1. 服务层补齐缺失 API 函数（knowledge.ts / tasks.ts）
2. CollectionGrid 完善「处理」交互与卡片内实时进度匹配逻辑
3. KnowledgePage 概览与处理详情 Tab 联动
4. KnowledgeTasksPanel 补充触发入口（batch-embed / reindex）
5. SemanticSearchPanel 增加 GraphRAG 检索模式
6. 类型检查（tsc --noEmit）与后端接口验证

## 执行调度
- 先做服务层（依赖），再 CollectionGrid（核心），再 Task 联动与触发入口，最后页面结构验证。
- 前端改动后运行 `npx tsc --noEmit -p tsconfig.app.json` 验证；后端改动后 `py_compile` + 重启 langgraph 容器验证 `/api/tasks` 返回 params。

## 风险控制
- `list_tasks` 已补 `params` 字段，需验证 asyncpg 将 jsonb 解析为 dict，避免 `params.collection` 匹配失败。
- 「处理」默认导入 documents_cn；同一集合并发任务时取最新任务，避免进度互相覆盖。
- 后端业务任务（extract/batch-embed）可能依赖 worker 运行，前端仅提供触发入口，不阻塞。
- 不读取 .env；不修改后端既有业务逻辑，仅增补前端入口与展示。

## 假设
- 采用「固定 documents_cn」作为默认处理目标，暂不增加 collection 选择器（保持简单，接口已支持扩展）。
- 「处理」任务以文件数为进度单位，与卡片「向量化进度」（chunk 数）为不同维度，UI 上明确区分。