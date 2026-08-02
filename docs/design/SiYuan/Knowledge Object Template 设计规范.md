# Knowledge Object Template 设计规范
## AI Investment Research Platform

---

# 1. 设计原则

对于整个 AI Investment Research Platform，**Knowledge Object Template（知识对象模板）不应直接照搬 SiYuan 页面模板**。

模板应该先来源于平台统一的 **Knowledge Schema**，再映射到 SiYuan（或未来其他知识工作台）。

这样即使未来从 SiYuan 迁移到其他系统，**Knowledge Schema、Knowledge Graph、Knowledge MCP Server、Knowledge Ingestion Agent** 都无需重写。

推荐采用三层模板架构：

```text
Knowledge Schema（平台统一模型）
        │
        ▼
Knowledge Object Template（业务模板）
        │
        ▼
SiYuan Template（页面模板）
```

---

# 2. Knowledge Object 分类

建议控制在 **12 种核心 Knowledge Object** 以内。

| 类型 | 核心程度 | 数据来源 |
|------|---------|----------|
| Company | ⭐⭐⭐⭐⭐ | 企业资料、财报 |
| Industry | ⭐⭐⭐⭐⭐ | 行业分析 |
| Security（股票） | ⭐⭐⭐⭐⭐ | 行情、交易 |
| Person | ⭐⭐⭐⭐ | CEO、管理层 |
| Event | ⭐⭐⭐⭐⭐ | 新闻、公告 |
| Fact | ⭐⭐⭐⭐⭐ | AI 抽取 |
| Metric | ⭐⭐⭐⭐ | 财务指标 |
| Document | ⭐⭐⭐⭐⭐ | PDF、研报 |
| Research Report | ⭐⭐⭐⭐⭐ | Agent 输出 |
| Theme | ⭐⭐⭐ | AI、机器人等投资主题 |
| Country / Region | ⭐⭐ | 宏观分析 |
| Watchlist | ⭐⭐⭐⭐ | 用户关注标的 |

---

## 第一阶段必须完成的模板

- Company
- Event
- Document
- Research Report

---

# 3. Company Template

Company 是整个知识体系中最核心的对象。

## 3.1 对象结构

```text
Company
│
├── Metadata
├── Profile
├── Business
├── Financial
├── Industry
├── Products
├── Competitors
├── Management
├── Events
├── Risks
├── Opportunities
├── Documents
├── Timeline
└── Relations
```

---

## 3.2 Metadata

```
Entity ID
Entity Type

Company Name
Ticker
Exchange

Country
Industry
Sector

Created Time
Updated Time
Status
```

---

## 3.3 Profile

```
Business Description
Website
Founded
Employees
Market Cap
Listing Date
```

---

## 3.4 Business

```
Revenue Sources
Business Segments
Major Customers
Major Suppliers
Competitive Advantage
Economic Moat
```

---

## 3.5 Financial

```
Revenue
Gross Margin
Operating Margin
ROE
ROIC
FCF
Debt
Cash
Valuation
Growth
Consensus
```

---

## 3.6 Relations

Relations 不是普通文本，而是知识图谱关系。

```
Competitor
Supplier
Customer
Subsidiary
Holding
Partner
Management
Industry
Theme
Country
```

---

# 4. Industry Template

```
Industry

Metadata

Definition
Market Size
Growth
Lifecycle

Key Companies

Drivers
Risks
Policies

Events

Research
```

---

# 5. Security（股票）Template

```
Ticker
Exchange
Currency

Company
Industry

Price
Market Cap

PE
PB
PS

Dividend

Liquidity

Institution Holding

Analyst Rating
```

说明：

- 与 Company 一对一关联。

---

# 6. Person Template

```
Name

Role
Company

Education
Experience

Holding

Compensation

Speech

News

Relations
```

---

# 7. Event Template

建议将 **Event** 作为新闻组织中心。

```
Event

Metadata

Summary

Source

Date

Importance

Category

Related Companies

Related Industries

Related Countries

Facts

Evidence

Impact

Timeline
```

示例：

```text
NVIDIA 发布 Blackwell
        │
        ▼
Company
        │
        ▼
NVIDIA
        │
        ▼
Industry
        │
        ▼
AI GPU
        │
        ▼
Impact
        │
        ▼
Positive
```

---

# 8. Fact Template

Fact 是知识库中的最小知识单元。

```
Fact

Subject

Predicate

Object

Confidence

Evidence

Source

Time

Extractor

Status
```

示例：

```
Apple

acquired

Beats
```

或者：

```
NVIDIA

Revenue Growth

56%
```

> Fact 将写入 PostgreSQL 和 Knowledge Graph，而不仅仅保存到 SiYuan 页面。

---

# 9. Metric Template

```
Metric

Name

Value

Unit

Period

Company

Industry

Source

Confidence

Updated Time
```

示例：

```
Revenue

120B

USD

FY2025
```

---

# 10. Document Template

```
Document

Title

Document Type

Company

Industry

Author

Publisher

Publish Date

Language

Pages

Storage Location

Embedding ID

Summary

Keywords

Evidence

Chunks
```

说明：

Document 对应 MinIO 中的真实文件，仅保存元数据和引用。

---

# 11. Research Report Template

所有 Research Agent 输出均应采用统一结构。

```
Research Report

Metadata

Executive Summary

Investment Thesis

Business Analysis

Industry Analysis

Financial Analysis

Valuation

Catalysts

Risks

Scenario

Recommendation

Evidence

References

Appendix
```

要求：

所有结论必须关联：

- Fact
- Event
- Document

---

# 12. Watchlist Template

```
Watchlist

Ticker

Company

Reason

Expected Catalyst

Risk

Target Price

Priority

Review Date

Status
```

说明：

由 Research Agent 每日自动更新。

---

# 13. Knowledge Inbox Template

AI 新抽取的知识不得直接进入正式知识库。

```
Knowledge Inbox

New Entity

New Fact

New Event

Duplicate

Need Review

Approved

Rejected
```

推荐流程：

```text
News
        │
        ▼
Knowledge Ingestion Agent
        │
        ▼
Knowledge Inbox
        │
        ▼
人工审核
        │
        ▼
Knowledge Graph
        │
        ▼
Company / Event / Fact
```

---

# 14. 模板之间的关系

建议建立统一对象关系，而不是孤立页面。

```text
Company
├── Security
├── Industry
├── Person
├── Event
├── Fact
├── Metric
├── Document
└── Research Report

Industry
├── Company
├── Event
├── Theme
└── Report

Event
├── Company
├── Fact
├── Evidence
└── Timeline

Research Report
├── Company
├── Event
├── Fact
├── Metric
└── Document
```

---

# 15. 推荐实施顺序

结合当前平台已有能力（News Pipeline、Knowledge Ingestion Agent、Knowledge Graph、Knowledge MCP Server），建议按依赖关系逐步建设。

---

## Phase 1：核心对象（Priority P1）

完成以下模板：

1. Company
2. Document
3. Event
4. Fact

目标：

- 建立 Knowledge Object 基础模型
- 支撑 Knowledge Ingestion Agent
- 建立知识图谱核心节点

---

## Phase 2：分析能力（Priority P2）

继续建设：

5. Metric
6. Industry
7. Security
8. Research Report

目标：

- 支撑投资分析
- 建立行业知识体系
- 支撑 Agent 自动生成研究报告

---

## Phase 3：扩展对象（Priority P3）

最后完成：

9. Person
10. Theme
11. Watchlist
12. Knowledge Inbox

目标：

- 完善知识生态
- 支撑用户自选股
- 支撑人工审核流程

---

# 16. 最终 Knowledge Object 架构

```text
                     Knowledge Schema
                            │
                            ▼
                Knowledge Object Template
                            │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
   Company         Industry          Security
        │               │                │
        ├──────┐        │                │
        ▼      ▼        ▼                ▼
     Event   Metric   Theme          Watchlist
        │
        ▼
      Fact
        │
        ▼
    Document
        │
        ▼
Research Report
        │
        ▼
Knowledge Inbox
```

---

# 17. 设计原则总结

## 核心原则

- Knowledge Schema 是平台唯一统一模型（Source of Truth）。
- Knowledge Object Template 是业务对象定义，不依赖具体知识管理工具。
- SiYuan Template 仅作为页面展示模板，可随时替换。
- 所有 Knowledge Object 都应支持：
  - 唯一 ID
  - Metadata
  - Version
  - Evidence
  - Graph Relation
  - MCP Tool
  - AI 自动生成
  - 人工审核

最终形成：

```text
Knowledge Schema
        │
        ▼
Knowledge Object
        │
        ├── PostgreSQL（结构化知识）
        ├── Apache AGE（知识图谱）
        ├── Qdrant（语义检索）
        └── SiYuan（知识工作台）
```

这一架构能够保证知识模型独立于具体 UI，实现平台长期可维护、可扩展和可迁移。