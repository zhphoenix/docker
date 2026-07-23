# Memory 设计

## 一、定位

Memory 系统为 Agent 提供短期和长期记忆能力。

---

## 二、Memory 三层分类

| 记忆类型 | 存储位置 | 说明 | 生命周期 |
|---------|---------|------|---------|
| **工作记忆** | PostgreSQL / Redis（未来） | 当前任务的短期上下文 | 任务级 |
| **情景记忆（Episodic）** | PostgreSQL | Agent 的思考过程、任务执行记录 | 持久 |
| **知识记忆** | Qdrant + Obsidian | 语义检索知识 + 长期研究沉淀 | 持久 |

---

## 三、Checkpoint（工作记忆）

### 3.1 实现方式

使用 LangGraph 的 `AsyncPostgresSaver` 将 State 持久化到 PostgreSQL。

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def get_checkpointer():
    return await AsyncPostgresSaver.from_conn_string(
        "postgresql+asyncpg://postgres:postgres@postgres:5432/langgraph"
    )
```

### 3.2 作用

- **任务恢复**：Agent 中断后可从 Checkpoint 恢复
- **状态回溯**：可查看任意历史 State
- **Human-in-the-loop**：支持人工介入后继续执行

### 3.3 数据库

使用独立的 `langgraph` 数据库（在 `01-init.sql` 中创建）。

### 3.4 注意事项

- `AsyncPostgresSaver.from_conn_string()` 必须用 `async with`
- `langgraph-checkpoint-postgres` 需显式添加 `psycopg[binary]` 依赖
- Redis 非必需，当前方案不使用 Redis

---

## 四、情景记忆

### 4.1 存储位置

PostgreSQL `research_tasks` 表。

### 4.2 内容

- 研究任务执行记录
- Agent 思考过程
- 工具调用历史

### 4.3 用途

- 避免重复执行相同任务
- 回顾历史分析结论
- 经验沉淀

---

## 五、知识记忆

### 5.1 语义检索知识（Qdrant）

- 文档 Chunk 经 Embedding 后的向量
- 支持语义搜索
- 用于 RAG 检索

### 5.2 长期研究沉淀（Obsidian）

- 投资人的知识沉淀
- 研究结论、行业认知、投资逻辑
- 通过 MCP 协议与 Agent 交互
- AI 写入 Vault，Obsidian 负责展示和编辑

### 5.3 Agent 共享知识空间（Vault）

Obsidian Vault 不仅是人读写的工具，也是 Agent 间异步协作的媒介：

| 角色 | 操作 | 示例 |
|------|------|------|
| Research Agent | 写入研究报告 | `03_Investment/Reports/600519/2026-07-17.md` |
| Investment Agent | 读取报告 + 写入 DCF | 读取报告 → 写入 `Companies/600519/dcf.md` |
| Knowledge Agent | 维护索引 | 更新标签、frontmatter、双向链接 |
| 投资人 | 编辑/标注 | 修改结论、补充认知 |
| 所有 Agent | 读取投资人笔记 | `03_Investment/Research/` 作为上下文输入 |

---

## 六、Memory 数据流

```text
用户提问
    │
    ▼
Agent 执行
    │
    ├── Checkpoint（PostgreSQL）
    │   └── 保存当前 State，支持恢复
    │
    ├── RAG 检索（Qdrant）
    │   └── 读取语义知识记忆
    │
    ├── 任务记录（PostgreSQL）
    │   └── 保存情景记忆
    │
    ├── 知识沉淀（Obsidian Vault）
    │   └── 研究报告/结论写入 Vault
    │
    └── 知识闭环
        └── 投资人编辑 → Agent 下次读取作为上下文
```

### 双向闭环数据流

```text
Agent 写入报告 → Obsidian Vault → 投资人编辑/标注
                                       │
                        Agent 读取投资人笔记 ←┘
```

---

## 七、未来扩展

| 扩展 | 说明 |
|------|------|
| Redis | 高性能工作记忆，支持 TTL 自动过期 |
| 向量化的情景记忆 | 将历史任务 Embedding 到 Qdrant，支持相似任务检索 |
| 跨 Agent 记忆共享 | 多个 Agent 共享同一 Memory 层 |