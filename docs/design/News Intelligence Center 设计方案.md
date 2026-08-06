新的 News Intelligence Center

建议改成：

News Intelligence Center
│
├── Live News Feed
├── Intelligence Queue
├── Event Monitor
├── Impact Monitor
├── Trend Discovery
├── Watchlist Monitor
├── Research Trigger
├── Source Health
└── Recent Activities
Live News Feed

展示：

最新新闻

高影响

热点

Breaking News

这里只负责：

浏览。

Intelligence Queue（新增）

展示：

News

↓

Processing

↓

Knowledge Package

↓

Published

用户可以看到：

Processing

Published

Failed

Waiting

这里和 Document Pipeline 联动。

Event Monitor

不是：

抽 Event。

而是：

查看：

Knowledge Operations

已经生成的：

Event

例如：

AI Chip Export

今天新增

12

影响：

37家公司
Impact Monitor

展示：

Knowledge Analytics

↓

Top Impact Events

例如：

美国限制AI芯片

影响：

★★★★★

不是重新分析。

而是：

展示。

Trend Discovery

例如：

过去24小时：

AI

+

GPU

+

Cloud

共同增长

来自：

Knowledge Analytics。

Watchlist Monitor

展示：

今天：

腾讯

命中

8条

相关新闻

这里：

调用：

Knowledge Services
Research Trigger

新增：

Create Research

Open Research

Compare

Generate Report

News：

负责：

触发。

不是：

生成。

Source Health

建议增加：

Reuters

Bloomberg

CNBC

SEC

港交所

巨潮

监控：

Latency

Errors

Articles

Duplicates

这个是：

News 独有。

Knowledge 没有。

数据流

建议改成：

News Sources
        │
        ▼
News Collector
        │
        ▼
Document Pipeline
        │
        ▼
Knowledge Package
        │
        ▼
Knowledge Operations Center
        │
        ├──────────────┐
        ▼              ▼
Knowledge Search   Knowledge Analytics
        │              │
        └──────┬───────┘
               ▼
News Intelligence Center
        │
        ├── Live Feed
        ├── Intelligence Queue
        ├── Event Monitor
        ├── Trend Discovery
        ├── Watchlist Monitor
        └── Research Trigger
与 Knowledge Operations 的边界
News Intelligence Center	Knowledge Operations Center
新闻浏览	Knowledge Inbox
实时新闻流	Validation
Breaking News	Merge
热点监控	Governance
Watchlist 命中	Knowledge Graph
Research Trigger	Search
Source Health	Analytics
Intelligence Queue	Knowledge Services
建议删除的功能

下面这些功能建议从 News Intelligence Center 中移除，因为已经被新的架构覆盖：

AI Summary（由 Document Pipeline 生成 Knowledge Package）
Entity Extraction（由 Document Pipeline 完成）
Event Extraction（由 Document Pipeline 完成）
Knowledge Graph Update（由 Knowledge Operations Center 完成）
AI Pipeline（由 Document Pipeline + Knowledge Operations Center 替代）
建议新增的功能

为了保持模块价值，建议增加更符合实时情报定位的能力：

Live News Feed：实时新闻流与热点。
Intelligence Queue：新闻进入 Document Pipeline、生成 Knowledge Package 的处理状态。
Event Monitor：展示已生成的重要事件及其演化。
Impact Monitor：基于 Knowledge Analytics 展示高影响事件。
Trend Discovery：热点趋势、主题聚类、跨行业联动。
Research Trigger：一键发起 Research Workflow。
Source Health：新闻源覆盖率、延迟、错误率、重复率监控。

这样，News Intelligence Center 就从“新闻处理中心”转变为“实时情报工作台”，与 Document Pipeline 和 Knowledge Operations Center 的职责边界完全一致。