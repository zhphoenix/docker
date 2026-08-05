# LangGraph 目录架构重组计划

## Summary

将 `langgraph/agent/` 下的全部代码重组到 `langgraph/` 根目录，采用建议的分层架构（graphs / nodes / state / tools / agents / memory / runtime / api），并扩展增设 `pipelines/ storage/ collectors/ skills/ services/ schemas/` 目录容纳未被建议结构覆盖的模块。一次性 `git mv` 重组 + 批量修正 import，不改变任何运行时行为。

关键决策（已确认）：
- 一次性全量重组，通过 git 提交分阶段回滚兜底
- 保留所有现有功能模块，扩展目录结构
- 代码平铺于 `langgraph/` 根目录，**不创建名为 `langgraph` 的可安装包**（避免与 pip 的 langgraph 库冲突），`pyproject.toml` 仅承载项目元数据与工具配置，导入方式维持现有 cwd 根导入模式

## 目录映射总表（旧 → 新，均相对 langgraph/）

### 核心重组
| 旧路径 (agent/ 下) | 新路径 |
|---|---|
| `main.py` | `main.py`（uvicorn 目标改为 `api.server:app`）|
| `app/main.py` | `api/server.py` |
| `api/*.py`（13 个路由 + path_utils） | `api/*.py` 原地不动 |
| `graph/graph.py` | `graphs/research_graph.py` |
| `graph/builder.py` | 拆分：graph 缓存 → `graphs/__init__.py`；执行封装 → `runtime/executor.py`（新建）|
| `graph/state.py` | 删除（纯 re-export，直接改指向 state/）|
| `schemas/state.py` | `state/research_state.py` |
| `news_agent/state.py` | `state/news_state.py` |
| `knowledge_agent/state.py` | `state/knowledge_state.py` |
| `rag_nodes/*.py`（8 个节点） | `nodes/research/*.py` |
| `news_agent/nodes/*.py`（8 个节点） | `nodes/news/*.py`（含 `utils.py`）|
| `knowledge_agent/nodes/*.py`（6 个节点） | `nodes/knowledge/*.py` |
| `news_agent/graph.py` | `graphs/news_analysis_graph.py` |
| `knowledge_agent/graph.py` | `graphs/knowledge_graph.py` |
| `memory/memory.py` | `memory/memory_store.py` |
| `services/checkpoint.py` | `memory/checkpoint.py` |
| `services/task_queue.py` | `runtime/queue.py` |
| `scheduler/scheduler.py` | `runtime/scheduler.py`（保持导出 `start_scheduler`/`stop_scheduler`）|
| `scheduler/worker.py` | `runtime/worker.py` |
| `services/pipeline.py` | `pipelines/document_pipeline.py` |
| `services/web_pipeline.py` | `pipelines/web_pipeline.py` |
| `ingestion/web/*.py`（6 个文件） | `pipelines/web/*.py` |
| `news_agent/collector/*.py` | `collectors/*.py` |
| `news_agent/storage/postgres.py` | `storage/news/postgres.py` |
| `knowledge_agent/storage/postgres.py` | `storage/knowledge/postgres.py` |
| `knowledge_agent/storage/qdrant.py` | `storage/knowledge/qdrant.py` |
| `knowledge_agent/storage/age.py` | `storage/knowledge/age.py` |
| `tools/financial_data.py` | `tools/market_tools.py` |
| `tools/` 其余（llm/embedding/qdrant/postgres/minio/docling/reranker/chunker） | `tools/` 原地不动 |

### 原地保留（不改名）
- `agents/`（base_agent、chat_agent、research_agent、kb_agent、investment_agent，共 5 个；`investment_agent` 不更名为 portfolio_agent，因 policies.yaml 与前端均以 `investment` 名称引用，改名属破坏性变更）
- `config/settings.py`、`config/policy_loader.py`、`config/policies.yaml`、`config/mcp_servers.yaml`
- `prompts/**`（现有目录结构已符合建议）
- `skills/**`、`providers/**`
- `services/` 剩余文件：`router.py`、`approval.py`、`lifecycle.py`、`batch_embed.py`、`news_storage.py`
- `schemas/chat.py`、`schemas/financial.py`、`schemas/authority.py`（API 请求模型，保留根级 `schemas/` 包）
- `tests/**` → 移至 `langgraph/tests/`

### 新建文件
- `pyproject.toml`：项目元数据 + pytest/ruff 配置，不定义 package（避免 langgraph 命名冲突）
- `config/agents.yaml`：Agent 注册表配置（从 `services/router.py` 的 `AGENT_REGISTRY` 与 policies.yaml 路由规则抽出声明式定义）
- `config/workflows.yaml`：4 条 Graph 工作流的声明式注册表（名称、模块路径、入口说明），供 `graphs/__init__.py` 读取
- `graphs/document_graph.py`：文档处理 StateGraph，节点委托调用 `pipelines/document_pipeline.py` 现有 `doc_pipeline` 各阶段方法，不重写业务逻辑
- `state/document_state.py`：DocumentState TypedDict（document_id、stage、chunks、error 等字段）
- `memory/thread_manager.py`：从 `api/chat.py` 提取 thread_id/config 组装逻辑
- `runtime/executor.py`：统一 Graph 执行入口（`astream`/`ainvoke` 封装 + checkpointer 装配），吸收 `graph/builder.py` 缓存逻辑
- `tools/knowledge_tools.py`：封装 MCP Knowledge Server 调用（`settings.MCP_KNOWLEDGE_URL`）
- `tools/search_tools.py`：检索语义封装（qdrant_tool + reranker_tool 组合检索）
- `tools/document_tools.py`：文档处理语义封装（docling + minio + chunker）
- `langgraph/scripts/`：收纳 `clear_minio.py`、`_clean_qdrant.py`、`_mi_probe.py`、`_setup_probe.py`、`_verify_code.py`
- `.dockerignore`：排除 tests/、__pycache__/、scripts/ 等

### 删除
- 空目录 `ingestion/api/`、`ingestion/documents/`、`ingestion/scheduler/`
- `agent/graph/state.py`、`agent/app/`、`agent/graph/`（内容迁移后）

## Import 批量改写规则

对所有 `.py` 文件执行以下替换（sed 批处理 + 人工抽查）：

```
from schemas.state import        → from state.research_state import
from graph.state import          → from state.research_state import
from graph.graph import          → from graphs.research_graph import
from graph.builder import        → from graphs import
from rag_nodes.<m> import        → from nodes.research.<m> import
from news_agent.graph import     → from graphs.news_analysis_graph import
from news_agent.state import     → from state.news_state import
from news_agent.nodes.<m> import → from nodes.news.<m> import
from news_agent.collector.<m> import → from collectors.<m> import
from news_agent.storage.postgres import → from storage.news.postgres import
from knowledge_agent.graph import → from graphs.knowledge_graph import
from knowledge_agent.state import → from state.knowledge_state import
from knowledge_agent.nodes.<m> import → from nodes.knowledge.<m> import
from knowledge_agent.storage.<m> import → from storage.knowledge.<m> import
from services.checkpoint import  → from memory.checkpoint import
from services.task_queue import  → from runtime.queue import
from services.pipeline import    → from pipelines.document_pipeline import
from services.web_pipeline import → from pipelines.web_pipeline import
from scheduler import            → from runtime.scheduler import
from scheduler.worker import     → from runtime.worker import
from memory.memory import        → from memory.memory_store import
from ingestion.web.<m> import    → from pipelines.web.<m> import
from tools.financial_data import → from tools.market_tools import
uvicorn "app.main:app"           → "api.server:app"
```

每个新目录补 `__init__.py`（state/、graphs/、nodes/{research,news,knowledge}/、runtime/、pipelines/、pipelines/web/、storage/{news,knowledge}/、collectors/）。

## 部署配置变更

- `compose.yml`：volume `./agent:/app` → `.:/app`
- `Dockerfile.dev`：同步挂载/工作目录调整
- `Dockerfile`（生产）：`COPY agent/ .` → `COPY . .` + `.dockerignore`
- `compose.prod.yml`：同步检查
- `main.py`：uvicorn 模块路径 `app.main:app` → `api.server:app`，`reload_dirs` 不变
- vite 代理、前端、根目录 `scripts/`（如 `sync_to_age.py`、`web_scheduler.py`）均走 HTTP 8100，无需改动

## 执行顺序（分阶段提交，便于回滚）

1. 分支 `refactor/langgraph-restructure`，提交 1：新建目录骨架与全部 `__init__.py`、新文件（pyproject.toml、config yaml、document_state、thread_manager、executor、tools 封装、document_graph）
2. 提交 2：`git mv` 核心模块（graphs/state/nodes/memory/runtime）+ import 改写
3. 提交 3：`git mv` pipelines/storage/collectors/tools 改名 + import 改写
4. 提交 4：api/server.py、main.py、prompts/tests/scripts 迁移 + import 改写
5. 提交 5：Dockerfile/compose 更新、删除空目录与旧 agent/ 残留
6. 提交 6：README.md 更新为新架构说明

## Test Plan

1. 静态检查：容器内 `python -m compileall api graphs nodes state tools agents memory runtime pipelines storage collectors skills services config schemas`
2. 导入检查：`python -c "import api.server"`（容器内）
3. 单测：容器内 `pytest tests/ -x`
4. 服务启动：`cd langgraph && docker compose up -d --build`，`curl http://127.0.0.1:8100/health` 返回 200，`/v1/models` 正常列出 agents
5. Graph 冒烟：触发一次 research chat 请求验证 research graph；确认 scheduler 日志中 news/knowledge graph 编译成功
6. 前端冒烟：3001 端口页面加载、对话功能正常

## Assumptions

- `investment_agent` 保留原名，不改为 `portfolio_agent`（前端与 policies.yaml 引用 `investment`）
- 用户建议中的 `nodes/researcher.py`、`extractor.py`、`analyzer.py` 等泛化命名不采用，保留现有具体节点文件名并归入 `nodes/research/ news/ knowledge/` 子目录，避免大规模语义重写
- `graphs/document_graph.py` 只做编排封装，文档处理实际逻辑仍在 `pipelines/document_pipeline.py`
- `tools/python_tools.py` 不创建（当前无 Python 执行工具需求）
