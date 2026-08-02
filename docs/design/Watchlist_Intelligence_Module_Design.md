# Watchlist Intelligence Module Design

> Version: v1.0
> Module: Watchlist Intelligence Center
> Status: Design
> Author: AI Investment Research Platform

---

# 1. Overview

Watchlist Intelligence（自选股智能监控）是 AI Investment Research Platform 的核心业务模块之一。

该模块负责：

- 管理用户收藏股票
- 每日自动监控相关新闻
- 自动监控行业动态
- 自动监控上市公司公告
- 自动分析产业链事件
- AI 判断事件影响程度
- 自动生成每日研究报告
- 向 Research Agent 提供股票监控能力

该模块不是行情系统，而是**智能研究入口（Research Entry Point）**。

---

# 2. Goals

建立一套完整的：

```

Watchlist
↓

Daily Monitoring

↓

Knowledge Organization

↓

AI Analysis

↓

Research Report

↓

Alert

```

帮助用户：

> 每天快速了解自己关注股票发生的重要事件。

---

# 3. System Architecture

```

                        User

                          │

                  Watchlist Center

                          │

      ┌───────────────────┼─────────────────────┐

      │                   │                     │

Watchlist Manager   Monitoring Engine     Alert Engine

      │                   │                     │

      │           News / Industry / Policy      │

      │                   │                     │

      └──────────────┬────┘                     │

                     │

           Knowledge Ingestion Agent

                     │

            Investment Knowledge Graph

                     │

             Knowledge MCP Server

                     │

              Research Agent

                     │

            Daily Research Report

```

---

# 4. Module Components

## 4.1 Watchlist Manager

负责：

- 收藏股票
- 删除股票
- 股票分组
- 标签管理
- 导入导出

例如：

```

科技

消费

新能源

港股

观察名单

```

---

## 4.2 Monitoring Engine

每天自动执行：

```

Scheduler

↓

Load Watchlist

↓

Collect News

↓

Collect Announcements

↓

Collect Industry News

↓

Collect Policy News

↓

Collect Macro Events

↓

Knowledge Organization

↓

AI Analysis

↓

Generate Daily Report

```

---

## 4.3 Intelligence Agent

负责：

- 新闻去重
- 事件抽取
- Entity Linking
- Event Classification
- Industry Mapping
- Impact Analysis
- AI Summary

最终输出：

```

Importance

Sentiment

Confidence

Impact Horizon

```

---

## 4.4 Alert Engine

负责：

实时提醒。

例如：

```

重大公告

重大政策

重大行业事件

财报发布

龙虎榜

机构评级变化

```

支持：

- Web Notification
- Email
- 企业微信
- Telegram
- Discord
- Slack

---

# 5. Monitoring Scope

每支股票每天监控：

## Company

- 公司新闻
- 公司公告
- 财报
- 高管变动
- 股权变动
- 并购重组

---

## Industry

- 行业新闻
- 行业指数
- 产业政策
- 技术突破
- 原材料价格

---

## Supply Chain

例如：

```

英伟达

↓

GPU

↓

光模块

↓

中际旭创

↓

新易盛

```

产业链事件自动关联。

---

## Policy

例如：

```

国务院政策

证监会政策

财政部

工信部

商务部

```

---

## Macro

例如：

- 美联储
- CPI
- PPI
- PMI
- GDP
- 汇率
- 利率

---

## Market

例如：

- 龙虎榜
- 大宗交易
- 融资融券
- 北向资金
- 南向资金

---

# 6. AI Event Analysis

AI 自动分析每条新闻。

输出：

## Importance

```

★★★★★

★★★★☆

★★★☆☆

★★☆☆☆

★☆☆☆☆

```

---

## Sentiment

```

Bullish

Bearish

Neutral

```

---

## Confidence

```

Official

High

Medium

Low

Rumor

```

---

## Impact Horizon

```

Short-term

Mid-term

Long-term

```

---

## Related Stocks

自动识别：

```

新闻

↓

Entity Extraction

↓

Knowledge Graph

↓

Affected Stocks

```

例如：

```

AI芯片出口政策

↓

英伟达

↓

光模块

↓

中际旭创

↓

新易盛

↓

天孚通信

```

即使新闻没有直接提到股票，也能自动关联。

---

# 7. Watchlist Database

## watchlist

| Field | Type |
|----------|----------|
| id | UUID |
| user_id | UUID |
| stock_code | varchar |
| stock_name | varchar |
| market | varchar |
| industry | varchar |
| tags | jsonb |
| created_at | timestamp |

---

## watchlist_events

记录每天发现的重要事件。

| Field | Type |
|----------|----------|
| id | UUID |
| stock_code | varchar |
| news_id | UUID |
| importance | int |
| sentiment | varchar |
| confidence | varchar |
| summary | text |
| created_at | timestamp |

---

## daily_watchlist_report

每天生成研究报告。

---

# 8. Knowledge Integration

所有新闻统一进入：

```

Collector

↓

Raw News Store

↓

Knowledge Ingestion Agent

↓

Knowledge Graph

↓

Knowledge MCP Server

↓

Watchlist Intelligence

```

避免重复分析。

---

# 9. Daily Workflow（建窗口让我输入指定时间，可以选择开启、关闭自动运行功能，有个按钮可以手动开始）

每天：

```

07:00

↓

Load Watchlist

↓

Collect Latest News

↓

Collect Industry Events

↓

Collect Company Announcements

↓

Entity Extraction

↓

Knowledge Graph Update

↓

AI Impact Analysis

↓

Generate Daily Report

↓

Push Notification

```

---

# 10. Daily Report

例如：

```

Watchlist Daily Report

2026-08-02

====================================

★★★★★ 今日重点

美国出台 AI 芯片出口新政策

影响：

★★★★★

涉及：

中际旭创

新易盛

工业富联

--------------------------------

★★★★☆

贵州茅台发布半年报

AI：

略超市场预期

--------------------------------

★★★☆☆

锂矿价格上涨

涉及：

天齐锂业

赣锋锂业

```

随后针对每支股票输出：

```

贵州茅台

相关新闻：

……

公告：

……

行业动态：

……

AI总结：

……

--------------------------------

腾讯

相关新闻：

……

AI总结：

……

```

---

# 11. MCP Interface

Watchlist MCP Server 提供统一能力。

```

get_watchlist()

get_watchlist_news()

get_watchlist_events()

get_stock_monitoring()

get_daily_watchlist_report()

get_stock_related_news()

get_stock_industry_events()

get_stock_alerts()

```

Research Agent 不直接访问数据库。

全部通过 MCP 获取。

---

# 12. Dashboard

Web UI

```

Watchlist

-----------------------------------

★★★★★ 今日重点（4）

★★★★ 今日重要（8）

★★★ 一般（16）

-----------------------------------

贵州茅台

2 条新闻

1 条公告

AI：

偏利好

-----------------------------------

腾讯

1 条行业新闻

AI：

中性

-----------------------------------

中际旭创

产业链重大事件

★★★★★

-----------------------------------

今日建议重点阅读：

5 篇

```

---

# 13. Future Extensions

未来可扩展：

- AI 自动生成投资日志
- AI 自动更新投资 Thesis
- 自选股风险评分
- 自选股估值跟踪
- AI 自动生成周报
- AI 自动生成月报
- 多账户 Watchlist
- AI Portfolio Manager
- 自选股之间关联分析
- 行业热度排行榜
- 产业链事件传播分析

---

# 14. Module Deployment

建议新增目录：

```

modules/

└── watchlist/
    ├── api/
    ├── scheduler/
    ├── collectors/
    ├── monitoring/
    ├── intelligence/
    ├── alerts/
    ├── reports/
    ├── models/
    ├── mcp/
    └── tests/

```

---

# 15. Dependencies

该模块依赖以下已有系统：

| Module | Purpose |
|---------|---------|
| News Intelligence Agent | 新闻采集 |
| Knowledge Ingestion Agent | 新闻结构化与知识抽取 |
| PostgreSQL | Watchlist 数据存储 |
| Qdrant | 向量检索 |
| Knowledge Graph | 股票、行业、事件关联 |
| Knowledge MCP Server | 统一查询接口 |
| Research Agent | 智能研究与报告生成 |
| Scheduler | 定时任务调度 |
| Notification Service | 消息推送 |

---

# 16. Design Principles

- Watchlist 仅作为用户关注对象管理，不直接承担分析逻辑。
- 所有新闻、公告、政策统一进入 Knowledge Ingestion Agent，避免重复处理。
- 行业事件、产业链事件通过 Knowledge Graph 自动关联至相关股票。
- 所有 AI 分析结果应具备可追溯的 Evidence（新闻、公告、政策等）。
- Research Agent、Web UI 和 Alert Engine 均通过 Watchlist MCP Server 获取数据，避免直接访问底层数据库。
- 模块设计保持可扩展，可支持多用户、多市场（A 股、港股、美股）及多资产类型（股票、ETF、基金、债券等）。
