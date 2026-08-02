# Human-in-the-Loop（HITL）知识审核与长期知识库设计规范
## AI Investment Research Platform

---

# 1. 设计目标

这是整个 AI Investment Research Platform 中最重要的一环。

如果没有 **Human-in-the-Loop（HITL）**，知识库最终会逐渐演变为：

> **AI 幻觉仓库（Hallucination Repository）**

对于投资研究平台而言，长期知识库必须保存的是：

> **Trusted Knowledge（可信知识）**

而不是：

> **AI Output（AI 输出结果）**

因此，不建议 AI 直接写入 Knowledge Graph，而应建立完整的知识审核与治理体系。

---

# 2. 知识生命周期（Knowledge Lifecycle）

建议采用 **五层知识生命周期模型**：

```text
                Raw Information
        (News / PDF / Filing / Web)
                     │
                     ▼
          Knowledge Ingestion Agent
                     │
                     ▼
             Draft Knowledge（草稿）
                     │
                     ▼
          Knowledge Review（人工审核）
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
      Approved              Rejected
          │                     │
          ▼                     ▼
   Trusted Knowledge      Feedback Dataset
          │
          ▼
 PostgreSQL + Apache AGE + Qdrant
          │
          ▼
      Research Agent
```

> **只有 Approved 的知识才能进入长期知识库。**

---

# 3. Knowledge Review Agent

当前平台已实现：

- News Intelligence Agent
- Knowledge Ingestion Agent
- Research Agent

建议新增：

> **Knowledge Review Agent**

---

## 职责

Knowledge Review Agent 不负责最终审批，而负责辅助审核人员：

- 重复实体检测
- 实体合并建议
- 冲突检测
- 缺失字段检测
- 自动补全建议
- 审核优先级排序

---

### 示例

输入：

```text
Apple Inc.
Apple
APPLE
```

Review Agent 输出：

```text
建议合并：

Apple Inc.
```

审核人员：

```
Approve
```

---

# 4. Knowledge Inbox

所有 AI 输出不得直接进入正式知识库。

建议新增：

```
Knowledge Inbox
```

作为草稿知识缓冲区。

---

## Inbox 数据结构

| 字段 | 说明 |
|------|------|
| id | 唯一标识 |
| type | Knowledge Object 类型 |
| status | 当前状态 |
| confidence | AI 置信度 |
| source | 数据来源 |
| created_time | 创建时间 |
| reviewer | 审核人 |
| review_time | 审核时间 |

---

## 状态建议

```
NEW

EXTRACTED

READY_REVIEW

APPROVED

REJECTED

ARCHIVED
```

所有 AI 生成知识必须先进入 Inbox。

---

# 5. 审核对象

审核对象不是 Markdown 页面，而是：

> **Knowledge Object**

例如：

```json
{
  "type":"Fact",
  "subject":"NVIDIA",
  "predicate":"Revenue Growth",
  "object":"56%",
  "source":"Annual Report",
  "confidence":0.98
}
```

审核人员只需：

- ✅ Approve
- ❌ Reject

即可完成审核。

---

# 6. 审核粒度

建议采用四级审核体系。

---

## Level 1：Document

审核文档来源。

例如：

```
Annual Report
```

判断：

```
可信
```

↓

```
Approve
```

---

## Level 2：Entity

审核实体。

例如：

```
NVIDIA
```

确认：

- 是否真实存在
- 是否重复
- 是否需要合并

---

## Level 3：Fact

审核事实。

例如：

```
Revenue Growth

56%
```

确认：

- 是否正确
- 是否有来源
- 是否可信

---

## Level 4：Relation

审核关系。

例如：

```text
NVIDIA

Partner

TSMC
```

确认关系是否正确。

---

# 7. Knowledge Review Center

不建议使用 SiYuan 作为审核界面。

建议在 Web UI 中新增：

> **Knowledge Review Center**

---

## 功能

```text
Pending（35）

Approve

Reject

Merge

Split

Edit

History
```

---

### 示例

左侧：

```
Revenue

120B
```

右侧：

```
Source

Annual Report

Confidence

99%

Evidence

......
```

审核：

```
Approve
```

---

# 8. Confidence（可信度）

所有 Knowledge Object 建议保存：

```
confidence
```

示例：

| 内容 | Confidence |
|------|-----------:|
| Revenue | 0.99 |
| Annual Report | 0.98 |
| AI 推理 | 0.52 |
| Rumor | 0.41 |

---

## 自动审核规则

建议：

```
confidence < 0.75
```

自动进入：

```
Need Review
```

---

# 9. Evidence（证据）

所有 Fact 必须至少关联一个 Evidence。

例如：

```text
Fact

↓

Revenue

↓

Evidence

↓

Annual Report
```

没有 Evidence：

> **禁止进入长期知识库。**

---

# 10. Conflict Detection（冲突检测）

示例：

数据库已有：

```
CEO

Jensen Huang
```

新闻抽取：

```
CEO

Lisa Su
```

Review Agent：

```
Conflict
```

审核人员：

```
Reject
```

不会直接覆盖已有知识。

---

# 11. Approval Workflow

推荐审批流程：

```text
AI

↓

Draft

↓

Review

↓

Approve

↓

Knowledge Graph
```

不要采用：

```text
AI

↓

Knowledge Graph
```

---

# 12. Knowledge Version（知识版本）

建议所有 Knowledge Object 保存版本。

例如：

```
Company

↓

Version

v15
```

修改：

```
v16
```

同时保留：

```
History
```

支持：

- 历史恢复
- 差异比较
- 回滚

---

# 13. Knowledge Audit（审计）

建议新增：

```
knowledge_audit
```

示例：

| 字段 | 示例 |
|------|------|
| Who | AI |
| What | Revenue |
| Old | 110B |
| New | 120B |
| When | 2026-08-02 |
| Approved By | Admin |

实现：

> **任何知识都可追溯是谁修改的。**

---

# 14. 自动审批策略

不是所有知识都需要人工审核。

例如：

```text
SEC Filing

Confidence

99%
```

↓

```
Auto Approve
```

而：

```text
Twitter

Confidence

45%
```

↓

```
Manual Review
```

---

## 建议建立审批策略表

| 来源 | 默认策略 | 示例 |
|------|---------|------|
| 官方公告、监管文件 | 自动审批（满足规则） | 年报、交易所公告 |
| 主流财经媒体 | 抽样审核或规则审批 | Reuters、Bloomberg 等 |
| AI 推理生成 | 人工审批 | 投资观点、风险判断 |
| 社交媒体、论坛 | 人工审批 | X、Reddit、雪球等 |

---

# 15. 长期知识库（Trusted Knowledge）

真正进入长期知识库的是：

```
Trusted Knowledge
```

存储位置：

- PostgreSQL（事实存储）
- Apache AGE（知识图谱）
- Qdrant（语义索引）

不是：

```
AI Output
```

---

# 16. 最终知识流

```text
                   News / PDF / Filing
                           │
                           ▼
             Knowledge Ingestion Agent
                           │
                           ▼
               Knowledge Inbox（草稿）
                           │
                           ▼
               Knowledge Review Agent
                           │
                           ▼
             Knowledge Review Center
                     │             │
             Approve │             │ Reject
                     ▼             ▼
         Trusted Knowledge     Feedback Dataset
                     │
        ┌────────────┼─────────────┐
        ▼            ▼             ▼
   PostgreSQL   Apache AGE     Qdrant
  (事实存储)     (关系图谱)     (语义检索)
        │
        ▼
 Knowledge Rendering Engine
        │
        ▼
      SiYuan（展示与人工协作）
        │
        ▼
 Research Agent（查询与分析）
```

---

# 17. 新增核心模块

相比简单的 "Approve / Reject" 按钮，建议新增两个独立模块。

---

## 17.1 Knowledge Review Center（审核中心）

负责人机交互。

### 功能

- 待审核队列
- 证据查看
- 冲突比较
- 批量审批
- 实体合并
- 实体拆分
- 编辑修正
- 审核历史

---

## 17.2 Knowledge Governance（知识治理）

负责规则管理与质量控制。

### 功能

- 自动审批规则
- 置信度阈值管理
- 来源可信度评分
- 重复检测
- 冲突检测
- 数据质量评分

---

## 建议增加质量维度

| 指标 | 说明 |
|------|------|
| Completeness | 完整性 |
| Consistency | 一致性 |
| Freshness | 时效性 |
| Traceability | 可追溯性 |

---

# 18. Trusted Knowledge 的四个核心属性

长期知识库中的每条知识都应具备以下能力：

## 1. 可追溯（Traceable）

- 来源明确
- Evidence 完整
- 审计记录完整

---

## 2. 可审核（Reviewable）

- 保留审批记录
- 支持再次审核
- 支持人工修正

---

## 3. 可版本化（Versioned）

- 支持历史版本
- 支持 Diff
- 支持回滚

---

## 4. 可量化可信度（Trust Scored）

每条 Knowledge Object 保存：

- Confidence
- Source Score
- Quality Score

形成统一可信度体系。

---

# 19. 推荐整体架构

```text
Raw Information
        │
        ▼
Knowledge Ingestion Agent
        │
        ▼
Knowledge Inbox
        │
        ▼
Knowledge Review Agent
        │
        ▼
Knowledge Review Center
        │
        ▼
Knowledge Governance
        │
        ▼
Trusted Knowledge
        │
 ┌──────┼───────────────┐
 ▼      ▼               ▼
PostgreSQL      Apache AGE      Qdrant
        │
        ▼
Knowledge Rendering Engine
        │
        ▼
SiYuan Knowledge Workspace
        │
        ▼
Research Agent
```

---

# 20. 设计总结

## 核心原则

- AI 输出不是长期知识。
- 所有知识必须经过 Knowledge Inbox。
- Human-in-the-Loop 是可信知识建设的核心。
- 审核对象是 Knowledge Object，而不是 Markdown 页面。
- 所有 Fact 必须关联 Evidence。
- 所有 Knowledge Object 必须支持 Version、Audit、Confidence。
- 长期知识库仅保存 Trusted Knowledge。

最终形成完整的知识治理闭环：

```text
AI Extraction
        │
        ▼
Knowledge Inbox
        │
        ▼
Human Review
        │
        ▼
Knowledge Governance
        │
        ▼
Trusted Knowledge
        │
        ▼
Research Agent
```

这种设计能够确保知识具备 **可追溯、可审核、可版本化、可量化可信度** 四项核心能力，对于投资研究平台而言，比 AI 自动入库更加可靠，也更适合作为 Research Agent 的长期知识基础。