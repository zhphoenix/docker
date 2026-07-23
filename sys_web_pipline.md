# AI 投研平台 - 数据管线架构

> 版本: 2.0 | 2026-07-21 | 反映系统实际运行状态
> 设计稿见 `sys_architecture.md`，本文档聚焦**数据流转全链路**

---

## 一、系统运行全景

### 1.1 运行中的服务（6 个 Docker 容器）

| 容器 | 镜像 | 端口 | 状态 | 职责 |
|------|------|------|------|------|
| postgres | pgvector/pgvector:pg18 | 5433 | ✅ healthy | 业务真相源，11 张表 |
| qdrant | qdrant/qdrant | 6333-6334 | ✅ running | 向量数据库，2 collections |
| embedding | llama.cpp:server-cuda13 | 8001 | ✅ healthy | Qwen3-Embedding-4B, 2560 维 |
| reranker | llama.cpp:server | 8002 | ✅ healthy | Qwen3-Reranker-0.6B |
| minio | minio:2025-07-23 | 9000-9001 | ✅ healthy | 对象存储，5 buckets |
| open-webui | open-webui:v0.10.2-cuda | 3000 | ✅ healthy | Web 交互界面 |

**未部署：** Docling :5001、LangGraph :8100、LLM :8080、Crawl4AI :11235

### 1.2 数据规模快照

| 维度 | 数量 | 说明 |
|------|-----:|------|
| PDF 年报 | 19,776 份 | A股 19,729 + 港股 47 |
| MD 文件 | 19,776 个 | Docling 解析产出 |
| PG Chunks | 1,509,899 条 | 四级切块，≤4000 chars/chunk |
| Qdrant 向量 | ~359K points | 嵌入中（43%） |
| AkShare 数据 | 18,273 条 | 6 张业务表 |
| MinIO 文件 | 5 buckets | documents/knowledge/datasets/artifacts/staging |

---

## 二、数据接入管线

### 2.1 管线 A：PDF 年报（已运行）

```
PDF 年报 (MinIO documents/)
    │
    ↓ Docling (GPU OCR) — 已完成，脚本离线运行
Markdown 文件 → data/pdf_to_md/ (19,776 个)
    │
    ↓ import_local_md.py (Phase 2) — ✅ 完成
    │   四级切块: Heading → Paragraph → Sentence → Hard
    ↓
PG: documents (19,776) + chunks (1,509,899)
    │
    ↓ embed_to_qdrant.py (Phase 4) — 🔄 进行中 (43%)
    │   Embedding :8001, batch=256
    ↓
Qdrant: documents_cn (647K/1,505K) + documents_hk (2.3K/4.5K)
```

**Phase 4 实时进度：**

| Collection | 总数 | 已嵌入 | 进度 |
|-----------|-----:|-------:|-----:|
| documents_cn | 1,505,434 | 647,224 | 43.0% |
| documents_hk | 4,465 | 2,283 | 51.1% |
| **合计** | **1,509,899** | **649,507** | **43.0%** |

### 2.2 管线 B：结构化数据 AkShare（已完成）

```
AkShare API (东方财富/同花顺/申万)
    │
    ↓ akshare_p1_data.py — ✅ 完成
    ↓ 全量接口 + 逐股采集
    ↓
PG: 6 张业务表
```

| 表 | 行数 | 数据来源 | 说明 |
|---|-----:|---------|------|
| analyst_ratings | 1,206 | 机构评级 | 研报评级明细 |
| institutional_holdings | 41 | 机构持仓 | 基金重仓 |
| financials | 210 | 财务指标 | 核心财务数据 |
| industry_pe | 31 | 申万行业 | 31 个一级行业 PE/PB/股息率 |
| earnings_forecast | 9,338 | 东方财富 | EPS 一致预期 + 评级分布 |
| performance_forecast | 7,447 | 东方财富 | 业绩预告 + 成长预期 |

### 2.3 管线 C：网页爬取（规划中）

```
Crawl4AI (:11235) → MD → MinIO (website/) → import_web_md.py → PG → Qdrant (documents_web)
```

目标：上市公司 IR 页面、监管公告、财经新闻

---

## 三、处理脚本清单

| 脚本 | 功能 | 阶段 | 状态 |
|------|------|------|------|
| `import_local_md.py` | MD → PG documents + chunks（四级切块） | Phase 2 | ✅ 完成 |
| `pg_migrate.py` | 数据迁移到统一 schema | Phase 3 | ✅ 完成 |
| `embed_to_qdrant.py` | PG chunks → Embedding → Qdrant | Phase 4 | 🔄 运行中 |
| `akshare_p1_data.py` | P1 数据采集（行业PE/盈利预测/业绩预告） | 数据补充 | ✅ 完成 |
| `akshare_fetch.py` | AkShare 综合数据采集 | 数据补充 | ✅ 完成 |
| `docling_parse.py` | PDF → MD 解析 | Phase 1 | ✅ 完成 |
| `minio_import.py` | 文件导入 MinIO | 基础设施 | ✅ 完成 |
| `akshare_market_data.py` | 市场行情数据 | 数据补充 | 待用 |

脚本路径：`/mnt/e/Value_capitalism/scripts/migrate_to_platform/`

---

## 四、端到端数据流

```
                        数据源
                          │
         ┌────────────────┼────────────────┐
         ↓                ↓                ↓
    PDF 年报         AkShare API       网页 (规划)
    (MinIO)          (东方财富等)       (Crawl4AI)
         │                │                │
         ↓                ↓                ↓
    Docling 解析     清洗+入库         MD 解析
         │                │                │
         ↓                ↓                ↓
    四级切块          PG 业务表         PG chunks
    (import_local_md)  (6 张表)            │
         │                │                │
         ↓                │                ↓
    PG chunks ←───────────┴────────────────┘
    (1,509,899 条)
         │
         ↓ Embedding (:8001)
         ↓ batch=256, 2560-dim
         ↓
    Qdrant (:6333)
    documents_cn + documents_hk
         │
         ↓ RAG 检索
         ↓
    Reranker (:8002) → Top-K 重排
         │
         ↓
    LLM 生成回答 → OpenWebUI (:3000)
         │
         ↓ 知识沉淀
    Obsidian Vault (via MCP)
```

---

## 五、存储层详情

### 5.1 PostgreSQL（业务真相源）

| 表 | 行数 | 类别 |
|---|-----:|------|
| documents | 19,776 | 文档元数据 |
| chunks | 1,509,899 | 文档切块（含 embedded 标记） |
| collections | 3 | collection 配置 |
| analyst_ratings | 1,206 | 市场数据 |
| earnings_forecast | 9,338 | 市场数据 |
| performance_forecast | 7,447 | 市场数据 |
| financials | 210 | 市场数据 |
| industry_pe | 31 | 市场数据 |
| institutional_holdings | 41 | 市场数据 |
| agents | 0 | 预留 |
| tasks | 0 | 预留 |

### 5.2 Qdrant（语义检索索引）

| Collection | Points | 向量维度 | 距离 |
|-----------|-------:|---------:|------|
| documents_cn | 356,847 | 2560 | Cosine |
| documents_hk | 2,283 | 2560 | Cosine |

### 5.3 MinIO（文件真相源）

| Bucket | 内容 |
|--------|------|
| documents/ | PDF 年报原文 (cn/600519/2024/...) |
| knowledge/ | Agent 生成的知识文档 |
| datasets/ | 数据集 (akshare/tushare/wind) |
| artifacts/ | Agent 输出 (research/summary) |
| staging/ | 处理中间态 (pending/processing/failed) |

---

## 六、当前状态与下一步

### 已完成

- [x] Phase 1: PDF → MD（19,776 份）
- [x] Phase 2: MD → Chunks（1,509,899 条，四级切块）
- [x] Phase 3: Chunks → PG（全量入库）
- [x] P1 数据采集: 行业PE + 盈利预测 + 业绩预告（18,273 条）
- [x] documents_hk collection 创建 + 失败数据修复

### 进行中

- [ ] **Phase 4: Embedding → Qdrant（43%，ETA ~28h）**

### 待启动

- [ ] Phase 6: Vault Generator → Obsidian
- [ ] Phase 7: Research Agent → artifacts/
- [ ] Phase 9: 自动化流水线
- [ ] Crawl4AI 部署（网页数据通道）
- [ ] LangGraph Agent 部署

---

## 七、端口规划

| 服务 | 端口 | 状态 |
|------|------|------|
| Open WebUI | 3000 | ✅ 运行 |
| Docling | 5001 | 🔲 未部署 |
| PostgreSQL | 5433 | ✅ 运行 |
| Qdrant API | 6333 | ✅ 运行 |
| Qdrant gRPC | 6334 | ✅ 运行 |
| Embedding | 8001 | ✅ 运行 |
| Reranker | 8002 | ✅ 运行 |
| LangGraph | 8100 | 🔲 未部署 |
| MinIO API | 9000 | ✅ 运行 |
| MinIO Console | 9001 | ✅ 运行 |
| Crawl4AI | 11235 | 🔲 未部署 |

---

## 八、文档索引

| 文档 | 内容 |
|------|------|
| `sys_architecture.md` | 系统架构设计稿（分层架构、Agent 设计、演进路线） |
| `sys_web_pipline.md` | **本文档** — 数据管线实际运行状态 |
| `sys_postgre.md` | PostgreSQL 详细设计 |
| `sys_qdrant.md` | Qdrant 详细设计 |
| `sys_Minio.md` | MinIO 详细设计 |
| `sys_embeding_reranker.md` | Embedding / Reranker 配置 |
| `sys_docling.md` | Docling 文档解析 |
| `sys_obsidian.md` | Obsidian 知识库 |
| `AI-Platform-System-Design/01~24_*.md` | 完整系统设计（24 篇） |
| `akshare_em_api_reference.md` | 东方财富接口技术参考 |
