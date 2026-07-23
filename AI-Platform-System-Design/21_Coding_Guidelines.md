# Coding Guidelines

## 一、编码规范

### 1.1 Python 版本

- Python 3.11+
- 使用 `async/await` 异步编程
- 使用类型注解（Type Hints）

### 1.2 代码风格

- 遵循 PEP 8
- 行宽 100 字符
- 使用 4 空格缩进
- 函数/类添加 docstring

### 1.3 导入顺序

```python
# 1. 标准库
import os
import uuid
from typing import Optional

# 2. 第三方库
from fastapi import FastAPI
from pydantic import BaseModel
import httpx

# 3. 本地模块
from config.settings import settings
from tools.qdrant import QdrantTool
from nodes.planner import planner
```

---

## 二、目录约定

| 目录 | 用途 | 内容 |
|------|------|------|
| `app/` | FastAPI 应用 | main.py、中间件、生命周期 |
| `api/` | 路由层 | chat.py、models.py、health.py |
| `graph/` | LangGraph 核心 | builder.py、graph.py、state.py |
| `agents/` | Agent 定义 | base_agent.py、research_agent.py |
| `nodes/` | Node 定义 | planner.py、retrieve.py、reason.py |
| `tools/` | Tool 定义 | llm.py、qdrant.py、postgres.py |
| `prompts/` | Prompt 模板 | planner.md、reason.md |
| `schemas/` | 数据模型 | chat.py、state.py |
| `memory/` | Memory 管理 | checkpoint.py |
| `config/` | 配置 | settings.py |
| `tests/` | 测试 | unit/、integration/、api/ |

---

## 三、命名约定

| 类型 | 规范 | 示例 |
|------|------|------|
| 文件名 | snake_case | `retrieve.py` |
| 类名 | PascalCase | `QdrantTool`、`AgentState` |
| 函数名 | snake_case | `def search()`、`def planner()` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT = 3` |
| 变量 | snake_case | `user_question`、`search_results` |
| 私有成员 | 前缀 `_` | `_internal_method()` |

---

## 四、异步约定

```python
# ✅ 正确：异步函数使用 async def
async def retrieve(state: AgentState) -> dict:
    results = await qdrant_tool.search(...)
    return {"documents": results}

# ❌ 错误：同步函数中调用异步
def retrieve(state: AgentState) -> dict:
    results = asyncio.run(qdrant_tool.search(...))  # 不要这样做
```

---

## 五、错误处理

```python
# ✅ 正确：明确的错误处理
try:
    results = await qdrant_tool.search(collection, vector)
except httpx.ConnectError:
    logger.error(f"Qdrant unavailable: {collection}")
    raise ServiceUnavailableError("Qdrant service is down")

# ❌ 错误：吞掉异常
try:
    results = await qdrant_tool.search(collection, vector)
except Exception:
    pass  # 不要这样做
```

---

## 六、MinIO 文件命名

| 规则 | 说明 |
|------|------|
| 永远不用中文 | 文件名、目录名全部英文 |
| 用公司代码不用公司名 | `600519` 而非 `贵州茅台` |
| 目录已含上下文，文件名不重复 | `report.pdf` 而非 `600519_2025_年报.pdf` |
| 路径格式 | `{bucket}/{market}/{symbol}/{doc_type}/{year}/{file}` |

---

## 七、Git 约定

| 规则 | 说明 |
|------|------|
| 提交信息 | 中文，简洁描述变更 |
| 分支 | feature/xxx、fix/xxx |
| .env | 不提交，提供 .env.example |
| 模型文件 | 不提交，通过文档说明来源 |