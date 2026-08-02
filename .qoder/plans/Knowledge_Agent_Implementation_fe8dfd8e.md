# Knowledge Graph Productionization + 术语统一

## 定位修正（检查结论）

**Apache AGE 已实现并接入（情况 B），项目已进入 "Knowledge Graph Productionization + GraphRAG" 阶段**，不是"建设 KG"。

### 完成度矩阵（基于只读代码检查）

| 能力 | 状态 | 证据 |
|------|------|------|
| Apache AGE 集成 | ✅ 已实现 | postgres/init/08-age-init.sql、mcp-knowledge/server/storage/age.py(409行)、knowledge_agent/storage/age.py |
| Graph Schema（10实体+10关系） | 🟡 不对齐 | specs/ontology.yaml + known_issues |
| Entity Resolution | 🟡 部分（ON CONFLICT + existing_id 合并） | knowledge_agent/storage/postgres.py、nodes/merger.py |
| Relation Confidence | ✅ 已带 confidence | nodes/relation.py、sync_relation |
| Temporal KG | 🟡 部分（facts 有时间段，图关系无时间戳） | nodes/merger.py |
| Graph Query Library | ✅ 已实现 | langgraph/agent/api/knowledge.py |
| Graph MCP Server | ✅ 完整 16 工具 (:8200) | mcp-knowledge/server/main.py 注册 6 模块 |
| GraphRAG | 🟡 混合检索有，缺 RAG 增强推理 | api/knowledge.py hybrid_search |
| Research Agent Workflow | ✅ Rerank 已接入 | agents/research_agent.py、graph/graph.py |
| 前端 Phase 1 UI | ✅ 已完成 | KnowledgePage.tsx + 4 组件 |

### 关键 Bug（术语统一根因）

[relation.py](file:///mnt/e/ai-platform/langgraph/agent/knowledge_agent/nodes/relation.py) 让 LLM 输出动词（`supplies`/`competes_with`），[merger.py](file:///mnt/e/ai-platform/langgraph/agent/knowledge_agent/nodes/merger.py) 不映射直接写库；而 [age.py](file:///mnt/e/ai-platform/mcp-knowledge/server/storage/age.py) 的 `sync_relation` 对非 `valid_types`(名词)会 fallback 为 `depends_on`，导致关系错误降级。

---

## 阶段 A：术语统一（本轮核心，改动最小、风险可控）

决策：**Prompt 直接输出名词**，ontology 新增 **partner（合作方）/ belongs_to（归属：Company→Industry）**。

### A1. specs/ontology.yaml 新增关系

在 `relation_types` 追加两个对象（名词 canonical）：

```yaml
- id: partner
  label: 合作
  canonical: true
  prompt_alias: "partners_with"
  description: "A 与 B 建立合作关系"
  direction: "bidirectional"
  examples: ["NVIDIA ↔ TSMC (AI 芯片合作)"]

- id: belongs_to
  label: 归属
  canonical: true
  prompt_alias: "belongs_to"
  description: "A 属于 B（如 Company → Industry）"
  direction: "source → target"
  examples: ["NVIDIA → AI Semiconductor"]
```

同时清理 `known_issues`：将"Prompt 使用动词"与"缺 customer"标记为待同步项（在 A2 完成后改为已解决）。

### A2. 重写 relation_extraction.md 为名词形式

文件：`/mnt/e/ai-platform/langgraph/agent/prompts/kb/relation_extraction.md`

关系类型改为名词（与 AGE/PG/ontology 完全对齐），新增 `customer/partner/belongs_to`：

```md
- supplier: 供应（TSMC → NVIDIA）
- customer: 客户（NVIDIA → TSMC，与 supplier 方向相反）
- competitor: 竞争（NVIDIA ↔ AMD，双向）
- depends_on: 依赖
- owns: 拥有
- uses: 使用
- invests_in: 投资
- located_in: 位于
- impacts: 影响
- causes: 导致
- partner: 合作（双向）
- belongs_to: 归属（Company → Industry）
```

同步更新示例 JSON 中的 `relation_type` 为名词，并加"方向注意"（supplier 方向：source 是供应商）。

### A3. relation.py 增加白名单校验

文件：`/mnt/e/ai-platform/langgraph/agent/knowledge_agent/nodes/relation.py`

在返回前过滤非法 `relation_type`（对齐 `VALID_EDGE_LABELS` 并加入 partner/belongs_to）：

```python
VALID_RELATION_TYPES = {
    "supplier", "customer", "competitor", "depends_on", "owns",
    "uses", "invests_in", "located_in", "impacts", "causes",
    "partner", "belongs_to",
}
# 提取结果中 relation_type 不在集合内 → 记录 warning 并丢弃该条
```

### A4. 同步 AGE edge labels（两处 age.py + sync_to_age.py）

- `/mnt/e/ai-platform/langgraph/agent/knowledge_agent/storage/age.py`：`VALID_EDGE_LABELS` 加入 `"partner", "belongs_to"`
- `/mnt/e/ai-platform/mcp-knowledge/server/storage/age.py`：`sync_relation` 的 `valid_types` 元组加入 `"partner", "belongs_to"`
- `/mnt/e/ai-platform/scripts/sync_to_age.py`：同步白名单（若有硬编码关系集合）

### A5. mcp-knowledge/server/tools/write.py docstring 同步

更新 `write.py` 中关系类型列表注释，新增 `customer/partner/belongs_to`（ontology 变更流程要求同步 docstring）。

### A6. 验证

1. `py_compile` 检查所有改动 Python 文件
2. grep 确认无残留动词形式（`supplies`/`competes_with`/`partners_with`）在 prompt/写入路径
3. 冒烟：调用 `mcp-knowledge` `sync_relation` 验证 partner 不再 fallback；如环境可用触发一次抽取任务验证入库 relation_type

---

## 阶段 B：Knowledge Intelligence Layer 生产化（后续迭代，登记方向）

聚焦完成度矩阵中的 🟡 缺口，按优先级：

- **B1 GraphRAG 增强**：`hybrid_search` 在图+向量结果上叠加 LLM 融合推理，产出带引用的图证据段落（改动 `api/knowledge.py` + 新增 `knowledge_agent` GraphRAG node）。
- **B2 Temporal KG**：为 AGE 关系边补充 `valid_from`/`valid_to` 属性，`sync_to_age.py` 与 `sync_relation` 写入时间戳；`trace_event_impact` 支持时间过滤。
- **B3 Entity Resolution 加固**：`bulk_upsert` 的嵌入式消歧核对（向量相似 + 名称模糊），输出合并报告。
- **B4 Graph MCP 多跳库**：新增 `query_company_relationship` / `find_related_companies(depth)` 工具（基于 `get_entity_graph`）+ GraphRAG 融合 MCP 工具。
- **B5 前端图谱可视化**：启用 KnowledgePage 的 Graph tab，用 React Flow 渲染 `entities/{id}/neighbors`（对应 atomic 的 `EntityBrowser` 增强，独立迭代）。

> B1-B5 不在本轮术语统一范围内，仅作登记，避免本轮范围膨胀。

---

## 关键文件清单（本轮阶段 A 改动）

| 文件 | 操作 | 职责 |
|------|------|------|
| `specs/ontology.yaml` | 修改 | 新增 partner/belongs_to，更新 known_issues |
| `langgraph/agent/prompts/kb/relation_extraction.md` | 重写 | 关系类型改名词 + customer/partner/belongs_to |
| `langgraph/agent/knowledge_agent/nodes/relation.py` | 修改 | relation_type 白名单校验过滤 |
| `langgraph/agent/knowledge_agent/storage/age.py` | 修改 | VALID_EDGE_LABELS + partner/belongs_to |
| `mcp-knowledge/server/storage/age.py` | 修改 | sync_relation valid_types + partner/belongs_to |
| `scripts/sync_to_age.py` | 修改（视情况） | 关系白名单同步 |
| `mcp-knowledge/server/tools/write.py` | 修改 | docstring 关系列表同步 |

## 风险与注意事项

1. **Prompt 改名词后抽取质量**：需重新验证 `supplier`（动词直觉是"供应动作"，名词"供应商"可能让 LLM 困惑方向）。在 example 中明确 direction（source=供应商）。
2. **存量数据**：已入库的动词型 `relation_type` 不会自动修复。若 PG 中已存在 `supplies` 等值，需在 A6 附一个一次性 SQL 迁移（`UPDATE core.relations SET relation_type=...`），或调用 sync_to_age.py 重建。在本轮计划中作为可选步骤，需确认存量规模后决定。
3. **白名单过滤会丢弃非法类型**：关系数量可能下降，属预期（更干净）；写入 A6 冒烟确认无严重损失。