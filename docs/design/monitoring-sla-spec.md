# Knowledge Pipeline 监控告警 SLA 设计规范

## 1. 设计目标

为 Knowledge Ingestion Agent 和 Knowledge MCP Server 定义可量化的 SLA 指标、监控方案和告警规则。

> 本规范填补审查报告中 W8（监控告警缺失）的空白。

---

## 2. 核心 SLA 指标

### 2.1 Knowledge Ingestion Agent 节点级指标

| 节点 | 指标 | P50 目标 | P99 目标 | 告警阈值 |
|---|---|---|---|---|
| `parser` | 处理延迟 | < 500ms | < 2s | > 5s |
| `entity_extractor` | 处理延迟 | < 3s | < 10s | > 15s |
| `relation_extractor` | 处理延迟 | < 5s | < 15s | > 20s |
| `fact_extractor` | 处理延迟 | < 5s | < 15s | > 20s |
| `validator` | 处理延迟 | < 2s | < 8s | > 10s |
| `merger` | 处理延迟 | < 3s | < 10s | > 15s |
| **全链路** | 端到端延迟 | < 20s | < 60s | > 90s |

> 当前代码已通过 `_timed` 装饰器采集节点耗时，需对接 Prometheus metrics。

### 2.2 Knowledge MCP Server 工具级指标

| 工具模块 | 指标 | P95 目标 | 告警阈值 |
|---|---|---|---|
| Entity Tools | 查询延迟 | < 500ms | > 2s |
| Fact Tools | 查询延迟 | < 800ms | > 3s |
| Semantic Tools | 查询延迟（Qdrant） | < 1s | > 5s |
| Analysis Tools | 查询延迟 | < 2s | > 8s |
| Write Tools | 写入延迟 | < 1s | > 5s |

### 2.3 质量指标

| 指标 | 定义 | 告警阈值 |
|---|---|---|
| 实体提取召回率 | 提取实体 / 标注实体 | < 80% |
| 事实准确率 | 验证通过事实 / 总提取事实 | < 70% |
| 冲突率 | conflicts 数量 / 总 facts 数量 | > 15% |
| 低置信度比例 | confidence < 0.5 的 fact 占比 | > 30% |

---

## 3. 监控采集方案

### 3.1 节点耗时（已有基础）

```python
# 当前 graph.py 已有 _timed 装饰器
# 需要增加：
from prometheus_client import Histogram

NODE_LATENCY = Histogram(
    "knowledge_agent_node_latency_seconds",
    "Knowledge Ingestion Agent node processing time",
    labelnames=["node_name"]
)
```

### 3.2 MCP Tool 耗时

```python
TOOL_LATENCY = Histogram(
    "mcp_knowledge_tool_latency_seconds",
    "Knowledge MCP Server tool execution time",
    labelnames=["tool_name", "module"]
)
```

### 3.3 错误计数

```python
ERRORS_TOTAL = Counter(
    "knowledge_pipeline_errors_total",
    "Total errors in knowledge pipeline",
    labelnames=["stage", "error_type"]
)
```

---

## 4. 告警规则

### 4.1 延迟告警

```yaml
# Prometheus Alerting Rules
groups:
  - name: knowledge_pipeline_latency
    rules:
      - alert: KnowledgeAgentE2EHighLatency
        expr: histogram_quantile(0.99, knowledge_agent_node_latency_seconds) > 90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Knowledge Ingestion Agent 端到端延迟超过 90s"

      - alert: MCPToolHighLatency
        expr: histogram_quantile(0.95, mcp_knowledge_tool_latency_seconds) > 5
        for: 3m
        labels:
          severity: warning
        annotations:
          summary: "MCP Tool {{ $labels.tool_name }} 延迟过高"
```

### 4.2 错误率告警

```yaml
      - alert: KnowledgeAgentHighErrorRate
        expr: |
          rate(knowledge_pipeline_errors_total[5m])
          / rate(knowledge_agent_runs_total[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Knowledge Ingestion Agent 错误率超过 10%"
```

### 4.3 质量告警

```yaml
      - alert: KnowledgeQualityDegradation
        expr: knowledge_agent_conflict_ratio > 0.15
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "知识冲突率超过 15%，可能需要人工审核"
```

---

## 5. Dashboard 建议

使用 Grafana 建立以下 Dashboard：

| Dashboard | 核心面板 |
|---|---|
| Knowledge Ingestion Agent Overview | 全链路延迟、节点耗时热力图、错误率趋势 |
| MCP Server Health | Tool 延迟分布、QPS、缓存命中率 |
| Knowledge Quality | 实体/事实/关系提取数量趋势、置信度分布、冲突率 |
| Storage Health | PostgreSQL 连接池、Qdrant Collection 大小、查询延迟 |

---

## 6. 错误处理策略

### 6.1 重试策略

| 阶段 | 重试次数 | 退避策略 | 降级方案 |
|---|---|---|---|
| LLM 调用 | 3 次 | 指数退避 1s/2s/4s | 降级为保守提取（仅高置信度结果） |
| PostgreSQL 写入 | 2 次 | 固定间隔 1s | 写入 DLQ（Dead Letter Queue） |
| Qdrant 写入 | 2 次 | 固定间隔 1s | 跳过向量索引，标记为待补 |

### 6.2 Dead Letter Queue

```python
# 处理失败的文档进入 DLQ
DLQ_TABLE = "knowledge_agent_dlq"
# 字段: document_id, stage, error_message, raw_state, retry_count, created_at
# 超过 3 次重试的文档由 Knowledge Maintenance Agent 定期清理
```

---

## 7. 与现有代码的对接点

| 现有代码 | 对接方式 |
|---|---|
| `graph.py` `_timed` 装饰器 | 增加 Prometheus Histogram 采集 |
| `state.py` `errors: Annotated[list[str], operator.add]` | 增加 `ERRORS_TOTAL` Counter |
| `state.py` `confidence_score` | 增加质量指标采集 |
| `cache.py` | 增加缓存命中率 Counter |
| `scheduler.py` | 定时触发质量报告生成 |
