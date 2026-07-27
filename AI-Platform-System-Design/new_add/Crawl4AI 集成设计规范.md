# AI Platform 规范：Crawl4AI 集成设计规范

> Version: v1.0
> Status: Recommended
> Scope: AI Platform Web Ingestion Layer

---

# 1. 目标

Crawl4AI 在 AI Platform 中**不是一个独立的爬虫工具**，而是整个系统的 **Web Ingestion Layer（网页知识采集层）**。

它与 Docling（文档解析）、API Provider（AKShare、TuShare 等）共同组成统一的数据采集体系。

整体设计原则：

- 数据源统一管理
- 数据流统一处理
- Storage 统一管理
- Agent 不直接调用爬虫
- Provider 解耦

---

# 2. 总体架构

```

AI Platform
│
├── Document Ingestion (Docling)
├── Web Ingestion (Crawl4AI)
└── API Ingestion (AKShare / TuShare / REST)

↓

Unified Ingestion Pipeline

↓

Chunk

↓

Embedding

↓

Reranker

↓

Qdrant

↓

LangGraph Agent

```

三类数据源最终全部进入统一 Pipeline。

---

# 3. 目录规范

建议新增 Web Ingestion 子系统。

```

src/
│
├── ingestion/
│   ├── documents/
│   ├── web/
│   ├── api/
│   └── scheduler/

```

其中：

```

src/ingestion/web/

├── crawler.py
├── extractor.py
├── markdown.py
├── filters.py
├── robots.py
├── scheduler.py

```

职责：

| 文件 | 作用 |
|-------|------|
| crawler.py | Crawl4AI 调用 |
| extractor.py | 内容抽取 |
| markdown.py | Markdown 清洗 |
| filters.py | URL 过滤 |
| robots.py | robots.txt 检查 |
| scheduler.py | 定时抓取 |

---

# 4. Docker 部署规范

增加 Crawl4AI 服务：

```yaml
crawl4ai:
  image: unclecode/crawl4ai:latest

  container_name: crawl4ai

  restart: unless-stopped

  ports:
    - "11235:11235"

  shm_size: 2g

  networks:
    - ai-platform
```

原则：

- 单独容器
- 与 AI Platform 同一 Docker Network
- Agent 不直接启动浏览器
- 所有浏览器资源统一由 Crawl4AI 管理

---

# 5. 配置规范

新增：

```

config/

crawl4ai.yaml

```

示例：

```yaml
browser:
  headless: true
  timeout: 30000
  max_tabs: 5

crawl:
  max_depth: 2
  max_pages: 100
  same_domain: true

markdown:
  remove_images: true
  remove_navigation: true
  remove_footer: true

storage:
  bucket: documents

chunk:
  enabled: false
```

禁止：

- 在代码中写死浏览器参数
- 在代码中写死 URL 规则

所有配置统一 YAML 管理。

---

# 6. Website Registry

新增：

```

registry/

websites.yaml

```

例如：

```yaml
sites:

  - sec.gov

  - cninfo.com.cn

  - hkexnews.hk

  - eastmoney.com

  - finance.sina.com.cn

  - investor.tencent.com
```

作用：

统一维护允许抓取的网站。

Agent 不允许直接抓任意网址。

新增网站：

仅修改 YAML。

---

# 7. Source Registry

新增：

```

registry/

sources.yaml

```

例如：

```yaml
sources:

  - id: cninfo
    type: web
    provider: crawl4ai

  - id: sec
    type: web
    provider: crawl4ai

  - id: hkex
    type: web
    provider: crawl4ai

  - id: akshare
    type: api
    provider: akshare

  - id: tushare
    type: api
    provider: tushare

  - id: pdf
    type: document
    provider: docling
```

Agent 调用流程：

```

Research Agent

↓

Source Selection Agent

↓

Source Registry

↓

对应 Provider

```

禁止：

```

if source=="cninfo"

if source=="sec"

if source=="hkex"

```

所有数据源必须通过 Registry。

---

# 8. PostgreSQL 元数据规范

新增：

```

web_pages

```

建议字段：

| 字段 | 说明 |
|------|------|
| id | UUID |
| url | 原始 URL |
| title | 页面标题 |
| domain | 域名 |
| status | HTTP 状态 |
| etag | ETag |
| last_modified | Last-Modified |
| content_hash | 内容 Hash |
| crawl_time | 抓取时间 |
| markdown_path | Markdown 路径 |
| minio_path | MinIO 路径 |

目的：

避免重复抓取。

---

# 9. URL 去重规范

流程：

```

URL

↓

HEAD

↓

ETag

↓

是否变化

↓

否

↓

跳过

```

如果服务器支持：

- ETag
- Last-Modified

优先利用。

否则：

计算 Content Hash。

---

# 10. 数据流规范

推荐流程：

```

网页

↓

Crawl4AI

↓

Markdown

↓

MinIO

↓

Metadata(Postgres)

↓

Chunk

↓

Embedding

↓

Qdrant

```

禁止：

```

网页

↓

Embedding

```

原因：

重新 Chunk 时无需重新抓网页。

---

# 11. Scheduler 规范

新增：

```

scheduler/

crawl_scheduler.py

```

流程：

```

网站列表

↓

URL Queue

↓

Worker

↓

Crawl4AI

↓

Markdown

↓

MinIO

↓

Chunk

↓

Embedding

↓

Qdrant

```

支持：

- 每日
- 每周
- 指定时间
- 手动触发

---

# 12. Provider 规范

新增：

```

providers/

web/

```

例如：

```

providers/web/

├── crawl4ai_provider.py
├── browser_provider.py
├── parser_provider.py

```

禁止：

```

Agent

↓

requests.get()

```

统一：

```

Agent

↓

Provider

↓

Crawl4AI

```

---

# 13. Pipeline 规范

新增：

```

pipelines/

```

例如：

```

pipelines/

├── document_pipeline.py
├── web_pipeline.py
├── api_pipeline.py

```

统一入口：

```

Document

↓

Pipeline

↓

Storage

```

而不是：

```

Document

↓

Agent

↓

Storage

```

---

# 14. Agent 调用规范

推荐：

```

Research Agent

↓

Source Selection Agent

↓

Web Provider

↓

Crawl4AI

↓

Markdown

↓

Chunk

↓

Embedding

↓

Qdrant

↓

LLM

```

Agent 永远不直接抓网页。

---

# 15. 推荐最终目录结构

```

AI-Platform/

│

├── agents/

│

├── ingestion/

│   ├── documents/

│   ├── web/

│   ├── api/

│   └── scheduler/

│

├── providers/

│   ├── document/

│   ├── web/

│   └── api/

│

├── registry/

│   ├── sources.yaml

│   ├── websites.yaml

│   └── collections.yaml

│

├── storage/

│   ├── postgres/

│   ├── minio/

│   └── qdrant/

│

├── pipelines/

│   ├── document_pipeline.py

│   ├── web_pipeline.py

│   └── api_pipeline.py

│

├── config/

│   └── crawl4ai.yaml

│

└── scheduler/

    └── crawl_scheduler.py

```

---

# 16. 设计原则

## 单一职责（Single Responsibility）

- Crawl4AI 负责网页抓取。
- Docling 负责文档解析。
- API Provider 负责接口数据获取。

---

## 数据源解耦（Source Decoupling）

新增数据源无需修改 Agent，仅需新增 Provider 并在 Registry 注册。

---

## 配置集中（Configuration First）

所有运行参数统一放置于 YAML 配置文件，禁止硬编码。

---

## Provider 模式（Provider Pattern）

Agent 仅调用 Provider，不直接依赖底层工具。

---

## Registry 驱动（Registry Driven）

数据源、网站、Collection 等统一由 Registry 管理。

---

## Pipeline 优先（Pipeline First）

所有数据统一进入标准化 Pipeline：

```

Source

↓

Normalize

↓

Storage

↓

Chunk

↓

Embedding

↓

Vector DB

```

---

## 存储优先（Storage First）

所有原始数据必须先保存至 MinIO，并在 PostgreSQL 中维护元数据，再进行 Chunk 与 Embedding。

这样可以支持：

- 重新 Chunk
- 更换 Embedding 模型
- 增量更新
- 数据回溯
- 多版本管理

---

# 17. 长期演进目标

未来 AI Platform 应支持更多数据源，而无需修改核心架构，例如：

- GitHub Repository
- RSS Feed
- Notion
- Confluence
- 企业 Wiki
- SharePoint
- Google Drive
- S3 Bucket
- 本地文件系统
- Firecrawl
- Browser Use
- MCP Server

所有数据源均通过统一的 Provider + Pipeline 接入，实现可扩展、可维护、可演进的企业级知识采集平台。

---

# 18. 功能新增规划

> Version: v1.1 新增
> Status: Planned
> Scope: Web Ingestion Layer 能力增强

---

## 18.1 规划概述

### 背景

当前规范（第 1–17 节）定义了 Web Ingestion Layer 的架构骨架与数据流，但以下生产能力尚未覆盖：

- 抓取失败后的容错与恢复
- 页面内容变化后的增量同步闭环
- 抓取任务的可观测性
- 需认证网站的抓取支持
- 内容质量评估与过滤

### 目标

在不改变现有架构边界和设计原则的前提下，分阶段补齐上述能力。

### 路线图

| 阶段 | 功能 | 优先级 | 预估工期 |
|------|------|--------|----------|
| Phase 1 | 弹性抓取与失败恢复 | P0 | 2–3 天 |
| Phase 2 | 增量变更检测与向量同步 | P0 | 3–5 天 |
| Phase 3 | 抓取任务可观测性与告警 | P1 | 2–3 天 |
| Phase 4 | 认证抓取 / 内容质量评估 | P2 | 按需 |

Phase 1 为 Phase 2 的前置保障，建议连续实施。

---

## 18.2 Phase 1：弹性抓取与失败恢复

### 18.2.1 功能名称与目标

**名称**：Resilient Crawling — 弹性抓取与失败恢复

**目标**：

- 抓取失败时按策略自动重试（指数退避 + 最大次数）
- 支持域名级速率限制（requests/min）
- 超过最大重试次数后标记为死信（dead），支持定时重跑
- 可选代理池配置
- 所有失败信息持久化至 PostgreSQL

---

### 18.2.2 使用场景

| 场景 | 描述 |
|------|------|
| 临时限流 | Scheduler 批量抓取 100 页，5 页返回 429 → 自动退避重试 → 最终成功 |
| 持续不可用 | 某网站连续 5 次超时 → 标记 dead → 告警通知 |
| 反爬保护 | 配置 `rate_limit: 20/min` 避免触发目标站封禁 |
| 网络波动 | 单次 DNS 解析失败 → 等待 2s 后重试 → 成功 |

---

### 18.2.3 与现有模块关系

| 模块 | 关系 |
|------|------|
| Crawl4AI | 底层抓取引擎不变，重试逻辑封装于 Provider 层 |
| Provider | `crawl4ai_provider.py` 增加 RetryPolicy 包装 |
| Pipeline | 失败页面不进入后续 Pipeline；死信页面可定时重跑 |
| Registry | `websites.yaml` 支持按站点覆盖重试参数 |
| Scheduler | 任务级记录成功/失败计数；新增死信重跑 cron |
| PostgreSQL | `web_pages` 扩展重试与错误字段 |
| MinIO | 无影响 |
| Qdrant | 无影响 |
| Agent | 无感知，重试在 Provider 内部闭环 |

---

### 18.2.4 新增或修改内容

#### 新增文件

```

src/ingestion/web/

├── retry.py            # RetryPolicy（指数退避、可重试状态码）
├── rate_limiter.py     # 域名级令牌桶限速

```

#### 配置新增（config/crawl4ai.yaml）

```yaml
retry:
  max_attempts: 3
  backoff_base: 2          # 退避基数（秒）
  backoff_max: 60          # 单次最大等待
  retry_on_status: [429, 500, 502, 503, 504]
  dead_letter_after: 5     # 累计失败标记 dead

rate_limit:
  default_rpm: 60          # 默认每分钟请求数
  per_domain:
    cninfo.com.cn: 20
    sec.gov: 30

proxy:
  enabled: false
  pool: []                 # 代理地址列表
```

#### Registry 扩展（registry/websites.yaml）

```yaml
sites:

  - domain: cninfo.com.cn
    retry_override:
      max_attempts: 5
    rate_limit_rpm: 15

  - domain: sec.gov
    rate_limit_rpm: 30
```

#### PostgreSQL 字段扩展（web_pages 表）

| 字段 | 类型 | 说明 |
|------|------|------|
| retry_count | INT | 当前连续重试次数 |
| last_error | TEXT | 最近一次错误信息 |
| error_code | INT | HTTP 错误码 |
| page_status | VARCHAR | pending / crawling / success / failed / dead |
| next_retry_at | TIMESTAMP | 下次允许重试时间 |

#### 数据流

```

Scheduler 触发

↓

Provider.fetch(url)

↓

Crawl4AI 执行

↓

成功 → Markdown → MinIO → Pipeline

失败 → 记录 error → retry_count++

↓

retry_count < max_attempts ?

├── 是 → 计算 next_retry_at → 等待 → 重新执行
└── 否 → page_status = dead → 告警

```

---

### 18.2.5 部署与调用链影响

| 维度 | 影响 |
|------|------|
| Docker 部署 | 无变化，Crawl4AI 容器配置不变 |
| 调度任务 | Scheduler 新增死信重跑任务（建议 cron: `0 4 * * *`） |
| Agent 调用链 | 无变化，Agent 仍通过 Provider 调用 |
| 现有数据源接入 | 无影响，Document/API Pipeline 不涉及 |

---

### 18.2.6 验收标准与测试

#### 验收标准

| 项目 | 标准 |
|------|------|
| 重试触发 | 模拟 429/500/502/503/504 响应，验证按配置重试 |
| 指数退避 | 第 n 次等待时间 = min(backoff_base^n, backoff_max) |
| 死信标记 | 累计失败 ≥ dead_letter_after 后 page_status = dead |
| 速率限制 | 单域名实际 RPM 不超过配置值 |
| 数据完整 | PostgreSQL 正确记录 retry_count、last_error、error_code |
| 死信重跑 | 定时任务可将 dead 页面重置为 pending 并重新抓取 |

#### 测试方式

- 单元测试：mock HTTP 响应，验证 RetryPolicy 逻辑
- 集成测试：对测试容器发送限流/错误响应，验证端到端流程
- 压力测试：高并发下验证 rate_limiter 准确性

#### 风险点

| 风险 | 缓解措施 |
|------|----------|
| 退避时间过长导致批量任务超时 | 设置任务级总超时（task_timeout） |
| 代理池全部不可用 | 降级为直连，记录 warning |
| 死信积压过多 | 监控 dead 数量，超阈值告警 |

---

### 18.2.7 设计原则兼容性

| 原则 | 兼容情况 |
|------|----------|
| Provider 模式 | ✅ 重试逻辑封装在 Provider 内部，Agent 无感知 |
| Registry 驱动 | ✅ 按站点 YAML 覆盖策略，无硬编码 |
| Pipeline 优先 | ✅ 失败页面不进入 Pipeline，成功后仍走标准流程 |
| 存储优先 | ✅ 成功页面先落 MinIO + PostgreSQL |
| 配置集中 | ✅ 所有重试/限速/代理参数在 YAML |
| Agent 不直接调用爬虫 | ✅ Agent 调用链无变化 |
| 单一职责 | ✅ retry.py / rate_limiter.py 各司其职 |

---

## 18.3 Phase 2：增量变更检测与向量同步

### 18.3.1 功能名称与目标

**名称**：Incremental Sync — 增量变更检测与向量库同步

**目标**：

- 抓取时对比 content_hash，检测内容是否变化
- 变化页面：重新 Markdown → MinIO → Chunk → Embedding → Qdrant（替换旧向量）
- 未变化页面：仅更新 crawl_time，跳过下游处理
- 页面下线时标记 archived 并清理向量
- 支持强制全量刷新模式

---

### 18.3.2 使用场景

| 场景 | 描述 |
|------|------|
| 日常增量 | 每日抓取 50 个公告页，仅 3 个有更新 → 只处理 3 个 |
| 模型更换 | 更换 Embedding 模型后触发全量刷新 |
| 页面下线 | 目标页面返回 404 → 标记 archived → 从 Qdrant 删除向量 |
| 版本回溯 | MinIO 保留历史版本 Markdown，支持数据回溯 |

---

### 18.3.3 与现有模块关系

| 模块 | 关系 |
|------|------|
| Crawl4AI | 抓取逻辑不变 |
| Provider | 返回结果附带 content_hash |
| Pipeline | 增加增量分支：changed → full pipeline / unchanged → skip |
| Registry | 无变化 |
| Scheduler | 触发时传入模式参数（incremental / full） |
| PostgreSQL | 扩展变更追踪与向量关联字段 |
| MinIO | 新版本 Markdown 覆盖或版本化存储 |
| Qdrant | 变化页面 delete old points + insert new points |
| Agent | 无感知 |

---

### 18.3.4 新增或修改内容

#### 新增文件

```

src/ingestion/web/

├── diff_detector.py    # 内容变更检测（hash 对比 + 状态判定）

```

#### 配置新增（config/crawl4ai.yaml）

```yaml
incremental:
  enabled: true
  hash_algorithm: sha256
  versioning: true              # MinIO 保留历史版本
  on_page_removed: archive      # archive | delete | ignore
  full_refresh_cron: "0 3 * * 0"  # 每周日 03:00 全量刷新
```

#### PostgreSQL 字段扩展（web_pages 表）

| 字段 | 类型 | 说明 |
|------|------|------|
| prev_content_hash | VARCHAR | 上一次内容 Hash |
| content_version | INT | 内容版本号（递增） |
| sync_status | VARCHAR | synced / pending_sync / stale / archived |
| qdrant_point_ids | TEXT[] | 关联的 Qdrant point ID 列表 |
| last_synced_at | TIMESTAMP | 最近同步至向量库时间 |

#### 数据流

```

Scheduler (mode=incremental)

↓

Crawl4AI → Markdown + content_hash

↓

对比 PostgreSQL.content_hash

↓

├── 未变化 → 更新 crawl_time → 结束
│
└── 已变化 → MinIO（新版本）
            → Chunk
            → Embedding
            → Qdrant（delete old + insert new）
            → PostgreSQL（new hash, version+1, synced）

```

页面下线流程：

```

HTTP 404 / 持续 dead

↓

on_page_removed 配置

├── archive → page_status=archived, sync_status=archived, 删除 Qdrant points
├── delete → 删除 MinIO + PostgreSQL + Qdrant 记录
└── ignore → 仅标记，不处理

```

---

### 18.3.5 部署与调用链影响

| 维度 | 影响 |
|------|------|
| Docker 部署 | 无变化 |
| 调度任务 | Scheduler 增加 mode 参数；新增周全量刷新 cron |
| Agent 调用链 | 无变化 |
| 现有数据源接入 | Document/API Pipeline 未来可复用相同增量逻辑 |

---

### 18.3.6 验收标准与测试

#### 验收标准

| 项目 | 标准 |
|------|------|
| 变更检测 | 修改页面内容后 hash 不一致，触发全流程 |
| 跳过未变化 | hash 一致时不触发 Chunk/Embedding |
| 向量替换 | Qdrant 旧 point 删除，新 point 写入 |
| 版本追踪 | content_version 递增，MinIO 保留历史 |
| 页面下线 | 按配置执行 archive/delete/ignore |
| 全量刷新 | 强制模式下所有页面重新处理 |

#### 测试方式

- 集成测试：修改测试页面 → 触发增量 → 验证 Qdrant 更新
- 回归测试：未变化页面确认无下游调用
- 边界测试：空页面、超大页面、编码异常

#### 风险点

| 风险 | 缓解措施 |
|------|----------|
| Qdrant delete + insert 非原子 | 使用相同 point ID 覆盖写入 |
| 高并发 hash 对比压力 | 批量查询 + 数据库索引 |
| MinIO 版本存储膨胀 | 配置生命周期策略（保留最近 N 版） |

---

### 18.3.7 设计原则兼容性

| 原则 | 兼容情况 |
|------|----------|
| Provider 模式 | ✅ 检测逻辑在 Pipeline 层，Provider 只返回数据 |
| Registry 驱动 | ✅ 无影响 |
| Pipeline 优先 | ✅ 增量分支仍在 Pipeline 内闭环 |
| 存储优先 | ✅ 先更新 MinIO 再处理下游 |
| 配置集中 | ✅ 增量策略全部 YAML 管理 |
| Agent 不直接调用爬虫 | ✅ Agent 无感知 |
| 单一职责 | ✅ diff_detector.py 独立职责 |

---

## 18.4 后续候选功能

以下功能在 Phase 1/2 完成后按需推进：

### 抓取任务可观测性与告警（P1）

- 新增 `crawl_tasks` 表，记录任务级状态（queued/running/success/failed）
- 成功率、耗时分布统计
- 异常阈值告警（可接入日志监控系统）

### 认证抓取支持（P2）

- 新增 `auth_provider.py`，支持 Cookie / Bearer Token / OAuth
- `websites.yaml` 扩展认证配置段
- 凭据引用环境变量或 Secret Manager，禁止明文写入 YAML

### 内容质量评估与智能过滤（P2）

- Pipeline 中 Normalize → Chunk 之间新增 Quality Gate
- 评分维度：字数、信息密度、重复率、广告占比
- 低于阈值不进入 Embedding
- `web_pages` 增加 `quality_score` 字段

---

## 18.5 约束与禁止事项

- 禁止在 Provider 外部实现重试逻辑
- 禁止在代码中硬编码重试次数或速率限制参数
- 禁止跳过 PostgreSQL 元数据更新直接操作 Qdrant
- 禁止 Agent 直接感知重试/增量逻辑
- 禁止在 YAML 配置中存放明文凭据（认证抓取阶段）
- 所有新增字段必须提供数据库迁移脚本