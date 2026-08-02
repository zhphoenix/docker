# Knowledge MCP Server 权限控制设计规范

> **ARCH 编号**：ARCH-005（附属）
> **状态**：Draft
> **最后更新**：2026-08-01

---

## 1. 设计目标

为 Knowledge MCP Server 的 15 个 Tools 定义访问控制策略，确保：

- 写操作（create/update）仅限授权调用方
- 读操作可分级开放
- 所有调用可审计追踪
- 最小权限原则

---

## 2. 调用方分类

| 调用方 | 身份标识 | 信任级别 | 说明 |
|---|---|---|---|
| **Research Agent** | `agent:research` | 高 | 内部 Agent，只读查询 |
| **Knowledge Ingestion Agent** | `agent:knowledge` | 高 | 内部 Agent，读写（通过 Merger 节点） |
| **Investment Agent** | `agent:investment` | 高 | 内部 Agent，只读查询 |
| **Chat Agent** | `agent:chat` | 中 | 内部 Agent，受限只读 |
| **Frontend API** | `api:frontend` | 中 | 通过 langgraph API 层转发 |
| **External MCP Client** | `ext:*` | 低 | 外部 MCP 客户端（未来） |

---

## 3. Tool 权限矩阵

| Tool | 模块 | research | knowledge | investment | chat | frontend | external |
|---|---|---|---|---|---|---|---|
| `search_entity` | Entity | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `get_entity` | Entity | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `get_entity_graph` | Entity | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `search_facts` | Fact | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `get_fact_history` | Fact | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| `get_timeline` | Fact | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `semantic_search` | Semantic | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `similar_documents` | Semantic | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `create_entity` | Write | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `create_fact` | Write | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `create_relation` | Write | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `update_knowledge` | Write | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `get_company_profile` | Analysis | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `get_supply_chain` | Analysis | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| `get_risk_factors` | Analysis | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |

**原则**：
- Write Tools 仅限 `knowledge` 身份（Knowledge Ingestion Agent 的 Merger 节点）
- 图遍历和分析类 Tools 不对低信任级别开放
- Chat Agent 仅开放基础搜索（防止 prompt injection 触发复杂查询）

---

## 4. 认证方案

### 4.1 内部 Agent（当前阶段）

内部 Agent 通过 **API Key + Scope** 认证：

```python
# MCP Server 中间件
class AuthMiddleware:
    API_KEYS = {
        "key-research-xxx": {"caller": "agent:research", "scopes": ["read"]},
        "key-knowledge-xxx": {"caller": "agent:knowledge", "scopes": ["read", "write"]},
        "key-investment-xxx": {"caller": "agent:investment", "scopes": ["read"]},
        "key-chat-xxx": {"caller": "agent:chat", "scopes": ["read:basic"]},
    }
```

**传递方式**：HTTP Header

```
Authorization: Bearer key-research-xxx
X-Caller-ID: agent:research
```

### 4.2 外部客户端（未来阶段）

OAuth 2.0 Client Credentials Flow：

```
POST /oauth/token
  grant_type=client_credentials
  client_id=xxx
  client_secret=xxx
  scope=read
```

---

## 5. Scope 定义

| Scope | 允许的 Tools | 说明 |
|---|---|---|
| `read` | 所有非 Write Tools | 完整只读访问 |
| `read:basic` | search_entity, get_entity, search_facts, semantic_search, get_timeline | 基础只读（Chat Agent） |
| `write` | create_entity, create_fact, create_relation, update_knowledge | 知识写入 |
| `admin` | health_check + 缓存管理 | 运维操作 |

---

## 6. 审计日志

所有 Tool 调用记录审计日志：

```python
audit_record = {
    "timestamp": "2026-08-01T12:00:00Z",
    "caller": "agent:research",
    "tool": "get_entity_graph",
    "params": {"entity": "NVIDIA", "depth": 2},
    "duration_ms": 145,
    "result_status": "success",  # success / denied / error
    "request_id": "uuid",
}
```

**存储**：PostgreSQL `audit.mcp_access_log` 表

**保留期**：90 天

---

## 7. 速率限制

| 调用方 | 限制 | 窗口 |
|---|---|---|
| 内部 Agent | 100 req/min | 滑动窗口 |
| Frontend API | 30 req/min | 滑动窗口 |
| External | 10 req/min | 滑动窗口 |
| Write Tools | 20 req/min | 固定窗口（全局） |

**超限响应**：

```json
{"error": "Rate limit exceeded", "retry_after": 30}
```

---

## 8. 实现路径

### Phase 1（当前）

- [x] 内部网络隔离（MCP Server 仅 Docker 内网可达）
- [x] 无认证（信任内网）
- [ ] 添加 `X-Caller-ID` Header 日志记录

### Phase 2（近期）

- [ ] API Key 认证中间件
- [ ] Tool 级权限检查装饰器
- [ ] 审计日志表 + 写入

### Phase 3（外部开放前）

- [ ] OAuth 2.0 认证
- [ ] 速率限制（Redis 滑动窗口）
- [ ] 权限管理 API

---

## 9. 与现有代码的对接

```python
# 建议实现：Tool 权限装饰器
def require_scope(scope: str):
    """Tool 级权限检查"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            caller = get_current_caller()  # 从 context 获取
            if scope not in caller.scopes:
                return {"error": f"Permission denied: requires '{scope}' scope"}
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# 使用示例
@mcp.tool()
@require_scope("write")
async def create_entity(...):
    ...
```

---

## 10. 安全约束总结

| 约束 | 级别 | 说明 |
|---|---|---|
| Write Tools 仅限 knowledge 身份 | MUST | 防止未授权写入 |
| 所有调用记录审计日志 | MUST | 可追溯 |
| 外部客户端禁止 Write 权限 | MUST_NOT | 最小权限 |
| Chat Agent 限制为基础只读 | SHOULD | 防 prompt injection |
| 速率限制 | SHOULD | 防滥用 |
| API Key 定期轮换 | SHOULD | 安全 hygiene |
