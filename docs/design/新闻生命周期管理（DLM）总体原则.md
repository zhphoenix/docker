# News Data Lifecycle Management（DLM）设计规范

## AI Investment Research Platform 新闻生命周期管理

## 1. 设计目标

如果每天采集全球财经新闻，几年后会产生：

-   数百万篇 Raw News
-   数十亿字符文本
-   大量重复新闻
-   大量低价值信息
-   Knowledge Graph 节点膨胀
-   Embedding 存储增长

如果没有 Data Lifecycle Management（DLM），会影响：

-   检索速度
-   Agent 推理质量
-   存储成本
-   Knowledge Graph 可维护性

核心原则：

> 不要简单删除新闻，而应该分层管理。

新闻生命周期和知识生命周期必须分开。

------------------------------------------------------------------------

# 2. 数据分层架构

    Raw News Layer

            ↓

    Processed Knowledge Layer

            ↓

    Knowledge Graph Layer

            ↓

    Research Memory Layer

生命周期不同：

  层                   保存时间
  -------------------- ----------
  原始 HTML            30-180天
  清洗文本             1-3年
  Embedding            长期
  Entity               永久
  Event                永久
  Relation             永久
  Investment Insight   永久

------------------------------------------------------------------------

# 3. Raw News Archive

存储：

-   HTML
-   PDF
-   图片
-   原始 JSON

推荐：

    MinIO

目录：

    news-raw/

     └── 2026/

          └── 07/

              └──31/

                 article_xxx.html

生命周期：

    90-180 days

用途：

-   重新解析
-   模型升级
-   数据审计

------------------------------------------------------------------------

# 4. Normalized News

处理后的新闻进入 PostgreSQL。

表：

    news_article

示例：

``` sql
CREATE TABLE news_article
(
id UUID,
title TEXT,
content TEXT,
source TEXT,
publish_time TIMESTAMP,
language VARCHAR(10),
hash VARCHAR(64),
importance_score FLOAT,
created_at TIMESTAMP
);
```

保存：

    1-3年

------------------------------------------------------------------------

# 5. Embedding Memory

进入：

    Qdrant

保存：

-   News embedding
-   Chunk embedding
-   Event embedding

Collection：

    news_embedding

用途：

-   Similarity Search
-   Historical Comparison
-   Event Similarity

生命周期：

长期。

------------------------------------------------------------------------

# 6. Knowledge Graph Layer

进入：

    Apache AGE

原则：

> 不保存新闻全文，只保存结构化知识。

保存：

## Entity

例如：

    NVIDIA
    TSMC
    AI Semiconductor

永久。

## Event

例如：

    AI Chip Export Restriction
    2026-07-31

永久。

## Relation

例如：

    US Government

          |
       restricts

          |

    NVIDIA

永久。

------------------------------------------------------------------------

# 7. 新闻重要性评分

增加：

    News Intelligence Agent

示例：

``` json
{
"importance_score":0.92,
"category":"market_moving",
"impact":"high"
}
```

------------------------------------------------------------------------

# 8. 新闻分级策略

## Tier 1：永久保存

包括：

-   美联储政策
-   国家政策
-   战争
-   并购
-   财报
-   行业变化
-   技术突破

进入：

    Knowledge Graph

## Tier 2：长期保存

包括：

-   公司新闻
-   行业新闻
-   分析文章

保存：

    3-5年

## Tier 3：短期保存

包括：

-   市场快讯
-   重复报道
-   新闻转载

保存：

    30-90天

------------------------------------------------------------------------

# 9. 新闻去重机制

流程：

    News Article

    ↓

    Hash Deduplication

    ↓

    Embedding Similarity

    ↓

    Event Merge

    ↓

    Knowledge Update

Hash：

``` python
sha256(title + content)
```

Embedding：

    similarity > 0.92

合并：

    News Cluster

           |

          Event

------------------------------------------------------------------------

# 10. Event-centric Storage

推荐：

> 以事件为中心，而不是新闻为中心。

结构：

                 Event

                  |

          +-------+-------+

          |       |       |

        News1   News2   News3

例如：

    Fed Rate Cut July 2026

关联：

-   Reuters
-   Bloomberg
-   CNBC
-   WSJ

------------------------------------------------------------------------

# 11. Apache AGE Event 生命周期

Event 永久保存。

增加：

``` json
{
"created_at":"2026-07-31",
"last_updated":"2026-08-01",
"confidence":0.95,
"source_count":25
}
```

------------------------------------------------------------------------

# 12. Knowledge Graph 数据维护

## Entity Merge

统一：

    Apple
    Apple Inc
    Apple Computer

为：

    entity_id:

    company_00001

## Relation Decay

关系增加时间：

``` json
{
"start_date":"2026-01-01",
"end_date":"2028-01-01"
}
```

------------------------------------------------------------------------

# 13. 生命周期策略

## 新闻层

  数据         保存周期
  ------------ ----------
  Raw HTML     90-180天
  Clean Text   1-3年
  重要新闻     永久
  重复新闻     删除

## Knowledge 层

  数据                保存周期
  ------------------- ----------
  Entity              永久
  Event               永久
  Relation            永久
  Investment Thesis   永久

## Vector 层

  数据                 保存周期
  -------------------- ----------
  News Embedding       长期
  Event Embedding      永久
  Document Embedding   长期

------------------------------------------------------------------------

# 14. Knowledge Maintenance Agent

每日运行：

    Scheduler

        |

    Lifecycle Agent

        |

    +----------------+

    Duplicate Detection

    Importance Scoring

    Archive

    Graph Cleanup

    Embedding Cleanup

------------------------------------------------------------------------

# 15. AI Platform 模块

    ai-platform

    ├── agents
    │
    ├── news_ingestion_agent
    │
    ├── knowledge_graph_agent
    │
    └── knowledge_maintenance_agent

    ├── storage
    │
    ├── minio
    ├── postgres
    ├── qdrant
    └── apache-age

------------------------------------------------------------------------

# 16. 最终架构

    News Sources

         |

    News Collection（采集服务）

         |

    Raw News Storage (MinIO)

         |

    News Intelligence Agent

         |

    +-------------+-------------+

    |                           |

    Qdrant                  Apache AGE

    Embeddings              Knowledge Graph

    |                           |

    Similarity Search        World Model

    +-------------+-------------+

                  |

           Research Agent

                  |

           Investment Report

                  ↑

    Knowledge Maintenance Agent

------------------------------------------------------------------------

# 17. 结论

不建议：

    新闻保存几年后全部删除

正确方式：

    Raw News

    短生命周期

    ↓

    Knowledge Extraction

    ↓

    Entity / Event / Relation

    永久保存

    ↓

    Research Memory

    长期积累

目标不是建立新闻数据库。

目标是建立：

> 投资领域的长期演化知识图谱（Investment World Model）

生命周期管理的核心：

> 把短期信息不断压缩成长期知识。
