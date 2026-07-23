# AI 投研平台 - 系统架构总览

## 一、系统目标

搭建一个本地化的 AI 投研平台，核心处理上市公司年报及各类研究资料。

核心能力链路：文档解析 -> 向量化 -> RAG 检索 -> Agent 推理 -> 知识沉淀

本系统定义为"本地 AI 操作系统"，运行在 Windows 11 + WSL2 + Docker Desktop 环境下，所有服务本地化部署，数据完全自控。

---

## 二、系统分层架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Windows 11 Host                                                         │
│                                                                         │
│  Chrome / Edge                                                          │
│                                                                         │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  Docker Desktop                                                         │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ WSL2 (Ubuntu)                                                    │   │
│  │                                                                   │   │
│  │  ① Presentation Layer                                            │   │
│  │  ┌───────────────────────────────────────────┐                   │   │
│  │  │ Open WebUI :3000                          │                   │   │
│  │  └───────────────────────────────────────────┘                   │   │
│  │               │ HTTP/OpenAI API                                  │   │
│  │               ▼                                                  │   │
│  │  ② AI Gateway                                                    │   │
│  │  ┌──────────────┐  ┌────────────────┐                           │   │
│  │  │ llama.cpp    │  │ Model Router   │                           │   │
│  │  │ :8080        │  │ (可选)         │                           │   │
│  │  └──────────────┘  └────────────────┘                           │   │
│  │               │ HTTP                                            │   │
│  │               ▼                                                  │   │
│  │  ③ Agent Layer                                                   │   │
│  │  ┌───────────────────────────────────────────┐                   │   │
│  │  │ LangGraph Service                         │                   │   │
│  │  └───────────────────────────────────────────┘                   │   │
│  │        ┌──────────┬──────────┬──────────┐                        │   │
│  │        ▼          ▼          ▼          ▼                        │   │
│  │  ④ Tool Layer                                                    │   │
│  │  PostgreSQL    MCP       Python     HTTP Search                  │   │
│  │        │                                                         │   │
│  │        ▼                                                         │   │
│  │  ⑤ RAG Layer                                                     │   │
│  │  Docling -> Chunk -> Embedding -> Reranker                       │   │
│  │        │                                                         │   │
│  │        ▼                                                         │   │
│  │  ⑥ Vector Layer                                                  │   │
│  │  Qdrant :6333                                                    │   │
│  │        │                                                         │   │
│  │        ▼                                                         │   │
│  │  ⑦ Structured Data Layer                                         │   │
│  │  PostgreSQL :5432                                                │   │
│  │        │                                                         │   │
│  │        ▼                                                         │   │
│  │  ⑧ Knowledge Layer                                               │   │
│  │  Obsidian Vault                                                  │   │
│  │        │                                                         │   │
│  │        ▼                                                         │   │
│  │  ⑨ Data Source Layer                                             │   │
│  │  PDF / TuShare / AKShare / RSS / Exchange                        │   │
│  │                                                                   │   │
│  │  ⑩ Storage Layer                                                 │   │
│  │  MinIO (文件存储) / Docker Volume / NAS                           │   │
│  │                                                                   │   │
│  │  ⑪ Monitoring Layer                                              │   │
│  │  Logs / Metrics                                                  │   │
│  │                                                                   │   │
│  │  ⑫ Scheduler Layer                                               │   │
│  │  Cron / APScheduler / 定时 Agent                                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 三、核心数据流

### 3.1 文档处理流水线

```
PDF / Word / HTML
        │
        ▼
   MinIO（原始文件存储，文件真相源）
        │
        ▼
   Docling Parser
        │
        ▼
   DoclingDocument（完整文档对象：标题、段落、表格、图片、页码）
        │
   ┌────┴────────────┐
   │                  │
   ▼                  ▼
HierarchicalChunker   导出 Markdown 到 MinIO
   │
   ▼
多个 Chunk
   │
   ├── 文本 Chunk ──> Embedding ──> Qdrant（语义检索）
   │
   └── 表格数据 ──> Extract ──> PostgreSQL（精确查询）
```

关键设计决策：
- 表格数据不进入 Qdrant，向量数据库不擅长精确数字查询、比较计算、财务建模
- Docling 先解析成文档对象（DoclingDocument），再 Chunk，最后可导出 Markdown
- MinIO 是"文件真相源（Source of Truth）"，PostgreSQL 是"业务真相源"，Qdrant 是"语义检索索引"

### 3.2 RAG 检索流程

```
用户提问
    │
    ▼
Embedding Model（Qwen3-Embedding-4B）
    │
    ▼
Qdrant（语义检索 Top-K Chunk）
    │
    ▼
Reranker（Qwen3-Reranker-0.6B，对 Top-K 重新排序）
    │
    ▼
LLM（llama.cpp，根据排序后的 Chunk 生成回答）
```

---

## 四、组件职责一览

| 组件 | 职责定位 | 核心说明 |
|------|---------|---------|
| **PostgreSQL** | 业务真相源 | 事实数据：股票行情、公司信息、Agent 任务、思考过程、文档处理状态 |
| **Qdrant** | 语义检索索引 | AI 可检索的知识：年报 Chunk 的 Embedding 向量 + 元数据 |
| **MinIO** | 文件真相源 | 原始文件存储：PDF、Markdown、图片、数据集、Agent 输出 |
| **Obsidian** | 第二大脑 | 投资人的知识沉淀：研究结论、行业认知、投资逻辑（不是数据库） |
| **Docling** | 文档解析 | PDF -> DoclingDocument -> Chunk -> Markdown |
| **llama.cpp (LLM)** | 本地 LLM 推理 | :8080，运行大语言模型，生成回答 |
| **llama.cpp (Embedding)** | 文本向量化 | :8001，Qwen3-Embedding-4B，Chunk → 向量 |
| **llama.cpp (Reranker)** | 重排序 | :8002，Qwen3-Reranker-0.6B，对 Top-K 结果重排 |
| **LangGraph** | Agent 编排 | 状态管理、多 Agent 协作、人工介入、任务恢复、Reflection |
| **Open WebUI** | 交互界面 | 用户入口，通过 HTTP/OpenAI API 与后端通信 |

### 4.1 三大存储的职责边界

- **PostgreSQL**：保存"事实数据" -- 结构化的股票数据、公司信息、Agent 任务状态、思考轨迹
- **Qdrant**：保存"理解后的知识" -- 文档 Chunk 经 Embedding 后的向量，支持语义检索
- **MinIO**：保存"原始文件" -- 按 market/company/document_type/year 组织的文档库
- **Obsidian**：保存"你的投资思想" -- 不是全部年报，而是研究结论和关联关系

### 4.2 Memory 三层分类

| 记忆类型 | 存储位置 | 说明 |
|---------|---------|------|
| 工作记忆 | PostgreSQL / Redis（未来） | 当前任务的短期上下文 |
| 情景记忆（Episodic） | PostgreSQL | Agent 的思考过程、任务执行记录 |
| 知识记忆 | Qdrant + Obsidian | 语义检索知识 + 长期研究沉淀 |

### 4.3 Obsidian 在系统中的定位

Obsidian 不是数据库，而是投资人的 Personal Knowledge Base：

```
            投资者
               │
               ▼
         Obsidian Vault
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
 行业认知   公司研究   投资逻辑
```

与 Agent 的连接方式：Obsidian Vault 作为 Markdown 源，通过 MCP 协议暴露给 AI。

---

## 五、Agent 架构

### 5.1 调度模型

Open WebUI 不直接调用工具，LangGraph 作为唯一调度中心：

```
Open WebUI
      │
      ▼
LangGraph（唯一调度中心）
      │
 ┌────┼────┬────┬────┬────┐
 ▼    ▼    ▼    ▼    ▼
RAG  PgSQL  MCP  Python  Search
 │
 ▼
llama.cpp
```

扩展性设计：新增工具（Bloomberg、Wind、回测系统、邮件发送）时，只需在 LangGraph 增加节点，Open WebUI 无需修改。

### 5.2 Agent 协作结构

```
              用户
               │
               ▼
       LangGraph Workflow
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
 Planner   Research   Coding
    │          │          │
    └──────────┼──────────┘
               ▼
       Knowledge Agent
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
  Qdrant   PostgreSQL  Obsidian
```

### 5.3 LangGraph 职责

- 状态管理
- 多 Agent 协作
- 人工介入（Human-in-the-loop）
- 任务恢复
- Reflection（反思与经验保存）

---

## 六、演进路线

| 阶段 | 重点 | 是否需要 LangGraph |
|------|------|-------------------|
| 第一阶段 | 本地 RAG（Docling + PostgreSQL + Qdrant + Embedding + Reranker） 
| 第二阶段 | 单 Agent（Research Agent） | 开始引入 |
| 第三阶段 | 多 Agent（投资、学习、知识管理等） | 成为系统核心 |

建议路径：
1. 先把文档处理和 RAG 打牢（Docling -> Chunk -> Embedding -> Qdrant -> PostgreSQL）
2. 完成一个能稳定工作的单 Agent
3. 当需要"规划、分支、状态管理、自动化工作流"时，再引入 LangGraph

---

## 附录：各组件详细文档索引

| 组件 | 详细文档 |
|------|---------|
| PostgreSQL | `sys_postgre.md` |
| Qdrant | `sys_qdrant.md` |
| MinIO | `sys_Minio.md` |
| Docling | `sys_docling.md` |
| Obsidian | `sys_obsidian.md` |
| Embedding / Reranker | `sys_embeding_reranker.md` |

---

## 附录：全局端口规划

| 服务 | 端口 |
|------|------|
| Open WebUI | 3000 |
| Docling | 5001 |
| PostgreSQL | 5432 |
| Qdrant | 6333 |
| Embedding (llama.cpp) | 8001 |
| Reranker (llama.cpp) | 8002 |
| LLM (llama.cpp) | 8080 |
| LangGraph | 8100 |
| MinIO API | 9000 |
| MinIO Console | 9001 |
