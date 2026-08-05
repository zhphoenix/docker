# 知识平台架构术语规范

> 来源：`docs/design/SiYuan/统一术语.md`
> **上位权威**：Agent/Service 命名以 `specs/agent-registry.yaml` 为准；类型枚举以 `specs/ontology.yaml` 为准。

## 核心概念

| 推荐名称 | 中文说明 | 所属组件/存储 | 推荐写法 | 不建议写法 |
| --- | --- | --- | --- | --- |
| Knowledge Object | 知识对象 | PostgreSQL | `Knowledge Object` | Knowledge Item, Knowledge Entity, 知识条目 |
| Knowledge Schema | 知识模型 | 规范层 | `Knowledge Schema` | Knowledge Model, Data Model |
| Knowledge Database | 长期结构化知识库 | PostgreSQL | `Knowledge Database` | Knowledge Store, 知识库 |
| Knowledge Graph | 知识图谱 | Apache AGE | `Knowledge Graph` | Graph DB, 关系数据库 |
| Vector Index | 语义检索索引 | Qdrant | `Vector Index` | Vector DB, Vector Store, 向量数据库 |
| Knowledge Workspace | 知识工作台 | SiYuan | `Knowledge Workspace` | Knowledge Human Interface, Human Knowledge UI, Human Knowledge Layer, 知识界面 |
| Knowledge Rendering Engine | 知识渲染引擎 | 独立服务 | `Knowledge Rendering Engine` | Knowledge Rendering Pipeline, Page Generator, 页面生成器 |
| Knowledge Platform | 知识平台 | 整体系统 | `Knowledge Platform` | AI Knowledge Operating System, Knowledge OS |

## Agent 与 Service

| 推荐名称 | 中文说明 | 类型 | 推荐写法 | 不建议写法 |
| --- | --- | --- | --- | --- |
| Knowledge Ingestion Agent | 知识摄取 Agent | Pipeline Agent | `Knowledge Ingestion Agent` | Knowledge Organization Agent, Knowledge Extraction Agent, knowledge_graph_agent |
| News Intelligence Agent | 新闻智能 Agent | Pipeline Agent | `News Intelligence Agent` | News Collector, News Agent, news_ingestion_agent |
| Research Agent | 研究 Agent | Chat Agent | `Research Agent` | — |
| Knowledge Review Agent | 知识审核 Agent | Pipeline Agent（规划） | `Knowledge Review Agent` | Review Agent |
| Knowledge MCP Server | 知识 MCP 服务 | MCP Server | `Knowledge MCP Server` | MCP Knowledge Server, Knowledge Server, MCP Server |
| Knowledge Rendering Engine | 知识渲染引擎 | Service（规划） | `Knowledge Rendering Engine` | Rendering Pipeline, Page Renderer |

## Worker 与 Service 命名

源自 Workflow 页面优化建议文档，用于后台任务与监控展示：

| 推荐名称 | 中文说明 | 类型 | 推荐写法 | 不建议写法 |
| --- | --- | --- | --- | --- |
| Embedding Worker | 向量化 Worker | Worker | `Embedding Worker` | Embed Worker |
| Graph Worker | 图 Worker | Worker | `Graph Worker` | — |
| Embedding Service | 向量化服务 | Service | `Embedding Service` | — |
| Graph Service | 图服务 | Service | `Graph Service` | 知识图谱服务 |

## 操作动词补充

| 中文 | 英文 | 用途 |
| --- | --- | --- |
| 重建 | Rebuild | 用于 `Rebuild Embedding` / `Rebuild Graph` 等重建操作 |

## 功能模块

| 推荐名称 | 中文说明 | 所属组件 | 推荐写法 | 不建议写法 |
| --- | --- | --- | --- | --- |
| SiYuan Adapter | 思源适配器 | Knowledge MCP Server | `SiYuan Adapter` | SiYuan MCP Adapter, SiYuan Plugin |
| Knowledge Inbox | 知识收件箱 | PostgreSQL | `Knowledge Inbox` | Draft Queue, Staging Area |
| Knowledge Review Center | 知识审核中心 | Web UI | `Knowledge Review Center` | Review Panel, Approval UI |
| Knowledge Governance | 知识治理 | 规则引擎 | `Knowledge Governance` | Quality Control, Data Governance |
| Trusted Knowledge | 可信知识 | PostgreSQL + AGE + Qdrant | `Trusted Knowledge` | Verified Knowledge, Final Knowledge |
| Template Engine | 模板引擎 | Knowledge Rendering Engine | `Template Engine` | Markdown Generator |
| Render Queue | 渲染队列 | Knowledge Rendering Engine | `Render Queue` | Job Queue |

## 存储组件

| 推荐名称 | 中文说明 | 角色定位 | 推荐写法 | 不建议写法 |
| --- | --- | --- | --- | --- |
| PostgreSQL | 结构化事实源 | Source of Truth，存储 entity/fact/relation/event 等结构化数据 | `PostgreSQL` | Knowledge DB（架构图中可简写） |
| Apache AGE | 图存储引擎 | 知识图谱存储与 Cypher 查询 | `Apache AGE` | AGE, Graph Database |
| Qdrant | 向量存储引擎 | 语义检索（6 Collections） | `Qdrant` | Vector Database |
| MinIO | 文档存储 | 原始文件归档（HTML/PDF/图片/JSON） | `MinIO` | Document Store, File Storage, Object Storage |
| SiYuan | 知识工作台 | 人工交互层（浏览/审核/编辑/研究笔记） | `SiYuan` | 知识数据库, 最终知识库 |

## 历史名称 → 规范名称映射

以 `specs/agent-registry.yaml` §4 为权威来源：

| 历史名称 | 规范名称 | 说明 |
| --- | --- | --- |
| Knowledge Organization Agent | **Knowledge Ingestion Agent** | SiYuan 全部 5 篇文档均使用旧名，需全量替换 |
| Knowledge Extraction Agent | **Knowledge Ingestion Agent** | 不是独立 Agent，是 Ingestion Agent 的内部节点（entity_extractor, fact_extractor, relation_extractor） |
| News Collector | **News Intelligence Agent** | 实施计划中使用的旧名 |
| MCP Knowledge Server | **Knowledge MCP Server** | 词序颠倒 |
| Research Agent | **Research Agent** | ✅ 已一致 |
| Knowledge Review Agent | **Knowledge Review Agent** | 规划中，名称可保留，待实现后注册 |
| Knowledge Rendering Pipeline | **Knowledge Rendering Engine** | 统一为 Engine |
| SiYuan MCP Adapter | **SiYuan Adapter** | 它是 MCP Server 内部的适配层，不是独立 MCP |
| Template Engine / Jinja2 Template | **Template Engine**（实现：Jinja2） | 逻辑名与实现技术分开表述 |
| Document Store | **MinIO** | 直接使用组件名 |
| Knowledge Human Interface | **Knowledge Workspace** | SiYuan 的唯一定位名称 |

## 禁止创造的新名称

以下名称不得在文档中新增使用：

- ~~Knowledge Writing Agent~~（写入由 Knowledge Ingestion Agent 的 merger 节点完成）
- ~~Knowledge Sync Agent~~（同步由 Knowledge Rendering Engine 完成）
- ~~SiYuan Agent~~（SiYuan 通过 SiYuan Adapter 访问，无需独立 Agent）
- ~~Knowledge Display Agent~~（展示由 Knowledge Rendering Engine 完成）
- ~~Page Generation Agent~~（页面生成是程序行为，不是 Agent）

## 架构图存储标注规范

在架构流程图中，存储组件统一采用「组件名 + 角色」标注：

```
PostgreSQL (Source of Truth)
Apache AGE (Knowledge Graph)
Qdrant (Vector Index)
MinIO (Document Storage)
SiYuan (Knowledge Workspace)
```

不应使用：`Knowledge DB`、`Graph DB`、`Vector DB`、`Document Store`、`Human Knowledge UI` 等非标标注。

## 修订红线（不得违反）

1. **PostgreSQL 是唯一结构化事实源（Source of Truth）**，SiYuan 不是。
2. **Apache AGE 负责知识图谱查询**，SiYuan 不维护图谱。
3. **Qdrant 负责语义检索**，搜索不依赖 SiYuan 内置搜索。
4. **MinIO 负责文档存储**，PostgreSQL 仅存元数据引用。
5. **SiYuan 仅是知识工作台（Knowledge Workspace）**，不能被称为"知识数据库"、"最终知识库"或"唯一事实源"。
6. **所有对 SiYuan 的访问通过 Knowledge MCP Server（统一知识访问层）完成**，Agent 不直接调用 SiYuan API。
7. **页面生成由 Knowledge Rendering Engine 通过模板渲染驱动**，LLM 不直接拼接 Markdown。
8. **Agent 命名以 `specs/agent-registry.yaml` 为唯一权威**，不得随意创造新 Agent 名称。
9. **类型枚举以 `specs/ontology.yaml` 为唯一权威**，文档中出现的类型列表必须与之对齐。