# Apache AGE Production Cypher Query Library

> **Research Agent 标准化 Graph Query 查询模板库**
> 让 Agent 不直接生成任意 Cypher，而是调用经过验证的查询模板

---

## 推荐架构

```
Research Agent
      |
Knowledge MCP Server
      |
Graph Query Library
      |
Apache AGE
      |
Investment Knowledge Graph
```

---

## 1. 设计原则

**生产环境不要让 LLM 直接生成任意 Cypher：**

```cypher
-- ❌ 禁止：LLM 自由生成
MATCH (n)-[r]->(m)
RETURN n, r, m
```

**原因：**

| 风险 | 说明 |
|------|------|
| 错误查询 | LLM 容易生成语法错误或语义偏差的 Cypher |
| 无权限控制 | 任意查询可能越权访问敏感数据 |
| 性能不可控 | 全图扫描、无深度限制、缺少 LIMIT |
| 难以审计 | 无法追踪 Agent 查询意图和访问模式 |

**采用 Intent → Template → Parameter Binding 模式：**

```
Intent（意图识别）
    ↓
Query Template（查询模板）
    ↓
Parameter Binding（参数绑定）
    ↓
Apache AGE
    ↓
Structured Result（结构化结果）
```

**示例：**

> 用户：*美国 AI 芯片限制影响 NVIDIA 吗？*

```
Agent 识别 Intent：POLICY_IMPACT_ANALYSIS
    ↓
调用：query_policy_company_impact()
    ↓
参数：{ "company": "NVIDIA", "policy": "AI Chip Export Control" }
    ↓
返回结构化结果
```

---

## 2. Query Library 目录设计

```
knowledge/
└── graph_queries/
    ├── company/
    │   ├── company_profile.cypher      # 公司基本信息
    │   ├── company_relationship.cypher  # 上下游生态关系
    │   └── company_risk.cypher          # 公司风险分析
    ├── event/
    │   ├── event_impact.cypher          # 事件影响链
    │   ├── event_history.cypher         # 事件演变路径
    │   └── similar_events.cypher        # 历史类似事件
    ├── policy/
    │   ├── policy_effect.cypher         # 政策直接影响
    │   └── regulation_chain.cypher      # 政策传导链
    ├── industry/
    │   ├── industry_map.cypher          # 行业公司地图
    │   └── industry_risk.cypher         # 行业风险分析
    └── research/
        ├── investment_analysis.cypher   # 投资论点验证
        └── thesis_validation.cypher     # 多因素影响分析
```

---

## 3. Company 查询模板

### 3.1 查询公司基本信息

> **场景：** Research Agent — *"NVIDIA 是什么公司？"*
>
> **文件：** `company_profile.cypher`

**Cypher：**

```cypher
MATCH (c:Company)
WHERE c.name = $company

OPTIONAL MATCH (c)-[:BELONGS_TO]->(i:Industry)
OPTIONAL MATCH (c)-[:LOCATED_IN]->(country:Country)

RETURN {
    company: c.name,
    ticker:  c.ticker,
    industry: i.name,
    country: country.name
}
```

**参数：**

```json
{ "company": "NVIDIA" }
```

**返回：**

```json
{
    "company":  "NVIDIA",
    "ticker":   "NVDA",
    "industry": "Semiconductor",
    "country":  "USA"
}
```

---

### 3.2 查询公司生态关系

> **场景：** *"NVIDIA 上下游有哪些？"*
>
> **文件：** `company_relationship.cypher`

**Cypher：**

```cypher
MATCH (c:Company)-[r]-(entity)
WHERE c.name = $company
RETURN type(r), labels(entity), entity.name
```

**返回示例：**

```
NVIDIA  | suppliers   | TSMC
NVIDIA  | competitors | AMD
NVIDIA  | customers   | Microsoft
```

---

### 3.3 公司风险分析

> **场景：** *"NVIDIA 当前风险有哪些？"*
>
> **文件：** `company_risk.cypher`

**Cypher：**

```cypher
MATCH (e:Event)-[:IMPACTS]->(c:Company)
WHERE c.name = $company
RETURN e.name, e.event_time, e.impact, e.confidence
ORDER BY e.event_time DESC
```

**返回字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `e.name` | string | 事件名称 |
| `e.event_time` | date | 事件时间 |
| `e.impact` | string | 影响方向（positive/negative/neutral） |
| `e.confidence` | float | 置信度（0~1） |

---

## 4. Event 查询模板

> **事件是投资系统核心。**

### 4.1 查询事件影响链

> **场景：** *"AI 芯片出口限制影响哪些对象？"*
>
> **文件：** `event_impact.cypher`

**Cypher：**

```cypher
MATCH (e:Event)-[:IMPACTS]->(target)
WHERE e.name = $event
RETURN target.name, labels(target), target.industry
```

**结果示例：**

```
AI Export Restriction
    ↓ impacts
  NVIDIA
    ↓ impacts
  TSMC
    ↓ impacts
  Semiconductor Industry
```

---

### 4.2 查询历史类似事件

> **场景：** *"历史有没有类似情况？"*
>
> **文件：** `similar_events.cypher`
>
> **策略：** Event Embedding（Qdrant）+ Graph 联合查询

**Cypher：**

```cypher
MATCH (e:Event)
WHERE e.event_type = $type
RETURN e.name, e.event_time, e.impact
ORDER BY e.event_time DESC
LIMIT 10
```

**联合检索流程：**

```
Qdrant: Event Description Embedding
    ↓ Similar Event Retrieval
Apache AGE: Graph Relationship Enrichment
    ↓
完整历史事件链
```

---

### 4.3 查询事件演变

> **场景：** *"事件后续发展如何？"*
>
> **文件：** `event_history.cypher`

**Cypher：**

```cypher
MATCH path = (e:Event)-[:FOLLOWED_BY*1..5]->(next:Event)
WHERE e.event_id = $event_id
RETURN path
```

**结果示例：**

```
Export Restriction
    ↓ FOLLOWED_BY
License Requirement
    ↓ FOLLOWED_BY
Production Adjustment
    ↓ FOLLOWED_BY
Revenue Impact
```

---

## 5. Policy 查询模板

### 5.1 政策影响分析

> **场景：** *"美国政策影响哪些公司？"*
>
> **文件：** `policy_effect.cypher`

**Cypher：**

```cypher
MATCH (p:Policy)-[:AFFECTS]->(c:Company)
WHERE p.name = $policy
RETURN c.name, c.ticker, c.industry
```

---

### 5.2 政策传导链

> **投资研究重点 — 追踪政策从宏观到微观的完整传导路径。**
>
> **文件：** `regulation_chain.cypher`

**传导路径：**

```
Policy → Market → Industry → Company → Stock
```

**Cypher：**

```cypher
MATCH path = (p:Policy)-[*1..5]->(target)
WHERE p.name = $policy
RETURN path
```

**示例：**

```
Interest Rate Cut
    ↓ affects
  Bond Market
    ↓ impacts
  Real Estate Industry
    ↓ impacts
  Vanke (000002)
    ↓
  Stock Price Impact
```

---

## 6. Industry 查询模板

### 6.1 行业地图

> **场景：** *"AI Semiconductor 有哪些公司？"*
>
> **文件：** `industry_map.cypher`

**Cypher：**

```cypher
MATCH (i:Industry)<-[:BELONGS_TO]-(c:Company)
WHERE i.name = $industry
RETURN c.name, c.ticker
```

---

### 6.2 行业风险分析

> **文件：** `industry_risk.cypher`

**Cypher：**

```cypher
MATCH (e:Event)-[:IMPACTS]->(i:Industry)
WHERE i.name = $industry
RETURN e.name, e.impact, e.confidence
```

---

## 7. 投资研究高级 Query

### 7.1 Investment Thesis Validation

> **场景：** *"AI 产业链是否支持 NVIDIA 长期增长？"*
>
> **文件：** `investment_analysis.cypher`

**查询维度：**

```
Company → Industry → Demand Driver → Event → Financial Metric
```

**Cypher：**

```cypher
MATCH (c:Company)-[:BELONGS_TO]->(i:Industry)
MATCH (i)<-[:IMPACTS]-(e:Event)
MATCH (c)-[:REPORTS]->(m:Metric)
WHERE c.name = $company
RETURN i, e, m
```

---

### 7.2 风险传播分析

> **文件：** `thesis_validation.cypher`
>
> **场景：** 追踪地缘事件的多级传播路径

**传播链示例：**

```
Taiwan Conflict
    ↓ impacts
  TSMC
    ↓ supplies
  NVIDIA
    ↓ impacts
  AI Industry
    ↓ impacts
  Market
```

**Cypher：**

```cypher
MATCH path = (e:Event)-[*1..6]->(target)
WHERE e.name = $event
RETURN path
```

---

### 7.3 多因素影响分析

> **场景：** *"NVIDIA 当前面临哪些维度的投资风险？"*
>
> **组合维度：** Policy Risk + Supply Risk + Competition Risk + Demand Risk

**Cypher：**

```cypher
MATCH (c:Company)
WHERE c.name = $company

OPTIONAL MATCH (c)<-[:IMPACTS]-(policy:Event)
OPTIONAL MATCH (c)-[:COMPETES_WITH]-(competitor)
OPTIONAL MATCH (c)<-[:SUPPLIES]-(supplier)

RETURN policy, competitor, supplier
```

---

## 8. Research MCP Tool 设计

> **核心原则：MCP Tool 不暴露 Cypher，Agent 通过意图调用。**

```
Agent 调用 MCP Tool
        |
analyze_company_risk(company="NVIDIA")
        |
内部加载 company_risk.cypher
        |
参数绑定 → Apache AGE
        |
返回结构化结果
```

**MCP Tool 定义示例：**

```json
{
    "name": "analyze_company_risk",
    "description": "Analyze company investment risks from knowledge graph",
    "parameters": {
        "company": "NVIDIA"
    }
}
```

---

## 9. Query Result 标准格式

所有 Graph Query 返回统一结构，便于 LLM 推理：

```json
{
    "query_type": "POLICY_IMPACT",

    "entities": [
        "NVIDIA",
        "TSMC"
    ],

    "relations": [
        "restricted_by",
        "supply_dependency"
    ],

    "events": [
        "AI Export Control"
    ],

    "confidence": 0.86
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `query_type` | string | 查询意图类型枚举 |
| `entities` | list[string] | 涉及的实体列表 |
| `relations` | list[string] | 涉及的关系列表 |
| `events` | list[string] | 涉及的事件列表 |
| `confidence` | float | 结果整体置信度（0~1） |

---

## 10. Query Registry

> 类似 MCP Provider Registry，统一管理所有查询模板的元数据。

**目录：**

```
registry/
└── graph_queries.yaml
```

**示例：**

```yaml
queries:
  - id: company_risk_analysis
    file: company/company_risk.cypher
    intent:
      - risk_analysis
    parameters:
      - company
    permission: research_agent

  - id: policy_impact_analysis
    file: policy/policy_effect.cypher
    intent:
      - policy_analysis
      - impact_analysis
    parameters:
      - policy
    permission: research_agent

  - id: event_chain
    file: event/event_impact.cypher
    intent:
      - event_analysis
    parameters:
      - event
    permission: research_agent
```

---

## 11. 性能优化

### 11.1 Index 策略

**Company 索引：**

```cypher
CREATE INDEX FOR (c:Company) ON (c.name);
CREATE INDEX FOR (c:Company) ON (c.ticker);
```

**Event 索引：**

```cypher
CREATE INDEX FOR (e:Event) ON (e.event_time);
CREATE INDEX FOR (e:Event) ON (e.event_type);
```

---

### 11.2 查询限制

**禁止无限制全图扫描：**

```cypher
-- ❌ 禁止
MATCH (n) RETURN n

-- ✅ 必须带 LIMIT
MATCH (n) RETURN n LIMIT 100
```

---

### 11.3 Graph Traversal 深度限制

| 场景 | 推荐深度 | 禁止 |
|------|----------|------|
| 直接关系查询 | 1 hop | — |
| 影响链分析 | 1~3 hops | — |
| 传导链分析 | 1~5 hops | — |
| 全图探索 | — | `[*]` 无限制 |

**推荐写法：**

```cypher
-- ✅ 限制深度
MATCH path = (a)-[*1..5]->(b)

-- ❌ 禁止无限制
MATCH path = (a)-[*]->(b)
```

---

## 12. 最终 Research Agent Workflow

```
User Question
      |
Intent Classification（意图识别）
      |
Query Planner Agent（查询规划）
      |
Graph Query Library（模板调用）
      |
Apache AGE（图查询执行）
      |
Knowledge Result（图知识结果）
      |
Qdrant Document Retrieval（语义文档检索）
      |
Market Data MCP（实时行情数据）
      |
Research Agent（综合推理）
      |
Investment Report（投资研究报告）
```

---

## 总结

### 各组件在投研中的职责

| 组件 | 核心作用 |
|------|----------|
| **Qdrant** | 找到相关资料（语义相似度检索） |
| **Apache AGE** | 理解关系和因果（图遍历 + 关系推理） |
| **PostgreSQL** | 保存事实（结构化业务真相源） |
| **Query Library** | 控制 Agent 查询能力（模板化 + 权限 + 性能） |
| **Research Agent** | 生成投资判断（综合多源知识推理） |

### 最终价值公式

```
Semantic Memory（Qdrant）
    +
Graph Memory（Apache AGE）
    +
Financial Facts（PostgreSQL）
    ↓
Institutional-grade Research Agent
```

> **Apache AGE Query Library** 是 Knowledge MCP Server 的核心能力层，将图查询能力从"自由 Cypher"升级为"受控、可审计、高性能的模板化查询"，是生产级 AI 投研平台的必要基础设施。
