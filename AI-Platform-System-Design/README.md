# AI Platform System Design

本项目为完全离线、本地部署的 AI 投研平台，采用 FastAPI + LangGraph + Open WebUI 架构。

核心能力链路：`文档解析 → 向量化 → RAG 检索 → Agent 推理 → 知识沉淀`

---

## 文档导航

### 核心架构层

| 编号 | 文档 | 说明 |
|------|------|------|
| 01 | [总体架构](01_总体架构.md) | 系统分层、请求链路、设计原则、演进路线、四大存储 |
| 02 | [系统组件](02_系统组件.md) | 11 个组件详细说明、端口规划 |
| 03 | [项目目录设计](03_项目目录设计.md) | Agent 目录、Docker 目录、MinIO Bucket、Obsidian Vault |
| 04 | [Docker部署](04_Docker部署.md) | Docker Compose 配置、网络、数据卷 |

### API 与 Agent 编排层

| 编号 | 文档 | 说明 |
|------|------|------|
| 05 | [FastAPI设计](05_FastAPI设计.md) | API 网关层、OpenAI Compatible API |
| 06 | [LangGraph设计](06_LangGraph设计.md) | Workflow Engine、Graph 结构、部署方式 |
| 07 | [State设计](07_State设计.md) | AgentState 定义、数据载体 |
| 08 | [Node设计](08_Node设计.md) | Node 列表与职责 |
| 08a | [RerankNode设计规范](08a_RerankNode设计规范.md) | RerankNode 详细实现规范 |
| 09 | [Tool设计](09_Tool设计.md) | Tool 列表与接口契约 |
| 09a | [EmbeddingTool设计规范](09a_EmbeddingTool设计规范.md) | EmbeddingTool 详细实现规范 |
| 10 | [Memory设计](10_Memory设计.md) | Memory 三层分类（工作/情景/知识） |

### 能力与数据层

| 编号 | 文档 | 说明 |
|------|------|------|
| 11 | [RAG设计](11_RAG设计.md) | RAG 检索增强生成流程 |
| 12 | [数据库设计](12_数据库设计.md) | PostgreSQL 表结构 |
| 13 | [MCP设计](13_MCP设计.md) | MCP 协议集成（Obsidian 等） |
| 14 | [OpenAI兼容API](14_OpenAI兼容API.md) | OpenAI Compatible API 实现细节 |
| 15 | [配置体系设计](15_配置体系设计.md) | 四层配置体系（.env / YAML / Registry / Runtime DB） |

### 工程规范层

| 编号 | 文档 | 说明 |
|------|------|------|
| 16 | [开发规范](16_开发规范.md) | 分层架构规范、Layer 分离原则 |
| 17 | [日志监控](17_日志监控.md) | 五层日志体系 |
| 18 | [测试规范](18_测试规范.md) | 三层测试体系（单元/集成/API） |
| 19 | [部署流程](19_部署流程.md) | 部署步骤与验证 |
| 20 | [开发计划](20_开发计划.md) | 渐进式开发路线（Web UI → Tauri 2）+ Specification 方法论 |
| 21 | [Coding Guidelines](21_Coding_Guidelines.md) | Python 编码规范 |

### 参考与指南

| 编号 | 文档 | 说明 |
|------|------|------|
| 22 | [API Reference](22_API_Reference.md) | API 端点参考 |
| 23 | [Agent Development Guide](23_Agent_Development_Guide.md) | Agent/Node/Tool 开发指南 |
| 24 | [数据底座规范](24_数据底座规范.md) | MinIO/PostgreSQL/Qdrant 完整数据规范 |

### 新增领域规范

| 编号 | 文档 | 说明 |
|------|------|------|
| 25 | [UI设计规范](25_UI设计规范.md) | AI Platform UI Design System（Mac 风格） |
| 26 | [Crawl4AI集成设计规范](26_Crawl4AI集成设计规范.md) | Web Ingestion Layer 完整规范 |
| 27 | [数据访问层设计规范](27_数据访问层设计规范.md) | 统一数据访问层（DAL） |
| 28 | [图工程架构设计规范](28_图工程架构设计规范.md) | Graph Engineering 架构演进方向 |
| 29 | [文件生命周期管理规范](29_文件生命周期管理规范.md) | 文件分类、生命周期、清理策略 |

### 辅助资源

| 文件 | 说明 |
|------|------|
| [schemas/metadata.schema.json](schemas/metadata.schema.json) | 文档元数据 JSON Schema |

### 规范体系（项目根目录）

| 文件 | 说明 |
|------|------|
| [CLAUDE.md](../CLAUDE.md) | AI 行为宪法（工作原则与边界） |
| [specs/architecture.yaml](../specs/architecture.yaml) | 分层架构可执行约束（18 条规则） |

> 规范体系关系：`CLAUDE.md`（行为宪法）→ `specs/`（可执行约束）→ `AI-Platform-System-Design/`（设计解释源）。
> 规划状态跟踪见 [.qoder/plans/SPEC_SYSTEM_ROADMAP.md](../.qoder/plans/SPEC_SYSTEM_ROADMAP.md)。

---

## 文档治理规范

- **命名**：`{编号}_{中文标题}.md`，子文档用 `XXa_` 后缀
- **元信息**：每个文件头部包含 Version / Status / Last Updated / Scope
- **引用**：文件间使用相对路径 Markdown 链接
- **版本**：主版本 = 架构级修改，次版本 = 内容补充，各文件独立版本