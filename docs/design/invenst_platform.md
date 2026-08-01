ARCH-001
News Intelligence Platform Design

ARCH-002
Knowledge Graph Schema (Apache AGE) — **已集成**（PG17 + AGE 1.5.0），参见 `specs/agent-registry.yaml` §5

ARCH-003
Knowledge Graph Ingestion Agent — 规范名称：**Knowledge Agent**，参见 `specs/agent-registry.yaml`

ARCH-004
Knowledge Maintenance Agent — **规划中**，参见 `specs/agent-registry.yaml` §3

ARCH-005
Knowledge MCP Server — 参见 `specs/agent-registry.yaml` §2

ARCH-006
Research Agent Workflow — 参见 `specs/agent-registry.yaml` §1

ARCH-007
Knowledge Graph Query Library — **已实现**（Cypher 查询 + PG CTE Fallback），参见 `mcp-knowledge/server/storage/age.py`

ARCH-008
Knowledge Graph Ontology — 建议迁移为 `specs/ontology.yaml`

ARCH-009
Entity Resolution System — **规划中**，参见 `specs/agent-registry.yaml` §3

ARCH-010
Event Intelligence Engine — **规划中**

---

> **命名权威来源**：所有 Agent/Service 命名以 `specs/agent-registry.yaml` 为准。
> 设计文档中出现的历史名称（如 Knowledge Graph Ingestion Agent、news_ingestion_agent）请参考注册表 §4 映射。

---

建议不要停留在目前的 v1.0。

目前这份设计属于典型的 LLM → Graph 流程，但对于生产级投资研究平台，还建议升级为 Knowledge Intelligence Pipeline v2.0，增加以下能力：

News Deduplication Agent：Hash + Embedding 去重，避免重复新闻污染知识图谱。
Entity Resolution Agent：统一实体注册、别名管理、Ticker 映射（如 Apple → Apple Inc. → NASDAQ:AAPL）。
Fact Verification Agent：多来源交叉验证，降低幻觉和错误关系写入风险。
Ontology Enforcement Agent：所有实体类型、关系类型、事件类型严格遵循 Ontology，禁止自由生成。
Graph Merge Agent：自动合并重复 Entity、Relation、Event，避免图谱膨胀。
Knowledge Maintenance Agent：生命周期管理、置信度更新、过期关系衰减（Relation Decay）、事件版本管理（Event Versioning）。
Research Memory Builder：将多个事件自动沉淀为长期 Investment Thesis，而不仅仅保存单个新闻事件。
Graph Quality Monitor：持续检测孤立节点、重复关系、低置信度事实和异常图结构。

这一套能力可以把当前的 Ingestion Pipeline 从信息抽取流水线升级为真正的生产级 Knowledge Intelligence Pipeline，更适合作为长期运行的 AI 投资研究平台核心。
