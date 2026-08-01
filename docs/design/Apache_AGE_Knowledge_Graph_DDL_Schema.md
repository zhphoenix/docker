# Apache AGE 实际数据库 Schema 设计（DDL）

> **状态：IMPLEMENTED（已集成）**
>
> Apache AGE 1.5.0 已通过自建 Docker 镜像集成（PG17 + pgvector + AGE）。
> 图遍历已迁移至 Cypher 查询，PostgreSQL CTE 作为 Fallback。
>
> **实现状态**：已完成（参见 `postgres/Dockerfile` + `postgres/init/08-age-init.sql`）

---

## 1. 设计目标

本 Schema 面向 AI Investment Research Platform：

核心目标：

    新闻
    +
    金融数据
    +
    公司信息
    +
    事件
    +
    政策
    +
    行业关系

    ↓

    Knowledge Graph

    ↓

    Research Agent 推理

采用：

    PostgreSQL

    +

    Apache AGE

    +

    pgvector

架构。

------------------------------------------------------------------------

# 2. 数据库分层设计

推荐：

    PostgreSQL

    ├── relational schema

    │
    ├── stock_data
    │
    ├── financial_data
    │
    ├── news
    │
    ├── knowledge
    │
    └── graph namespace (Apache AGE)

职责：

  层                 用途
  ------------------ ----------------
  PostgreSQL Table   结构化事实数据
  Apache AGE Graph   实体关系
  pgvector           语义检索

------------------------------------------------------------------------

# 3. 初始化 Apache AGE

## 创建扩展

``` sql
CREATE EXTENSION IF NOT EXISTS age;
```

加载 AGE：

``` sql
LOAD 'age';
```

设置搜索路径：

``` sql
SET search_path = ag_catalog, "$user", public;
```

------------------------------------------------------------------------

# 4. 创建 Knowledge Graph

Graph 名称：

    investment_knowledge_graph

创建：

``` sql
SELECT create_graph(
    'investment_knowledge_graph'
);
```

------------------------------------------------------------------------

# 5. Entity 节点设计

## 5.1 Company 公司节点

Label:

    Company

属性：

``` json
{
entity_id,
name,
ticker,
exchange,
country,
industry,
market_cap,
created_at
}
```

示例：

``` cypher
CREATE
(c:Company {
entity_id:'company_00001',
name:'NVIDIA',
ticker:'NVDA',
country:'USA',
industry:'Semiconductor'
})
```

------------------------------------------------------------------------

# 5.2 Industry 行业节点

Label:

    Industry

属性：

``` json
{
industry_id,
name,
category
}
```

示例：

    AI Semiconductor

    Cloud Computing

    Energy

------------------------------------------------------------------------

# 5.3 Country 国家节点

Label:

    Country

属性：

``` json
{
country_id,
name,
region
}
```

------------------------------------------------------------------------

# 5.4 Government 政府节点

Label:

    Government

属性：

``` json
{
government_id,
name,
country
}
```

示例：

    US Government

    China Government

------------------------------------------------------------------------

# 5.5 Person 人物节点

Label:

    Person

属性：

``` json
{
person_id,
name,
role,
organization
}
```

例如：

    Jensen Huang

    Jerome Powell

------------------------------------------------------------------------

# 5.6 Product 产品节点

Label:

    Product

属性：

``` json
{
product_id,
name,
category,
company
}
```

例如：

    H100 GPU

    Blackwell GPU

------------------------------------------------------------------------

# 5.7 Policy 政策节点

Label:

    Policy

属性：

``` json
{
policy_id,
name,
type,
issuer,
date
}
```

例如：

    AI Chip Export Control

------------------------------------------------------------------------

# 5.8 Event 事件节点

Event 是投资研究核心。

Label:

    Event

属性：

``` json
{
event_id,
name,
event_type,
event_time,
impact,
confidence
}
```

示例：

``` json
{
event_id:"event_001",

name:
"US AI Chip Export Restriction",

event_type:
"regulation",

impact:
"negative",

confidence:
0.87
}
```

------------------------------------------------------------------------

# 5.9 News 新闻节点

Label:

    News

属性：

``` json
{
news_id,
title,
source,
url,
publish_time,
embedding_id
}
```

------------------------------------------------------------------------

# 5.10 Metric 指标节点

用于连接财务数据。

Label:

    Metric

属性：

``` json
{
metric_id,
name,
value,
unit,
period
}
```

例如：

    Revenue

    EPS

    Gross Margin

------------------------------------------------------------------------

# 6. Relationship 设计

------------------------------------------------------------------------

## Company belongs_to Industry

关系：

    Company

     |
    belongs_to

     |

    Industry

Cypher：

``` cypher
MATCH
(c:Company),
(i:Industry)

CREATE
(c)-[:BELONGS_TO]->(i)
```

------------------------------------------------------------------------

## Company located_in Country

    Company

     |
    located_in

     |

    Country

------------------------------------------------------------------------

## Government creates Policy

    Government

     |
    creates

     |

    Policy

------------------------------------------------------------------------

## Policy affects Company

    Policy

     |
    affects

     |

    Company

例如：

    AI Export Control

            |

         NVIDIA

------------------------------------------------------------------------

## Company manufactures Product

    Company

     |
    manufactures

     |

    Product

例如：

    TSMC

     |

    GPU Chip

------------------------------------------------------------------------

## Company competes_with Company

    NVIDIA

     |
    competes_with

     |

    AMD

------------------------------------------------------------------------

## Event impacts Company

最重要关系：

    Event

     |
    impacts

     |

    Company

属性：

``` json
{
impact_type:
"negative",

strength:
0.85,

time_range:
"6_months"
}
```

------------------------------------------------------------------------

## Event impacts Industry

    Event

     |

    impacts

     |

    Industry

------------------------------------------------------------------------

## Event mentioned_in News

    Event

     |

    mentioned_in

     |

    News

------------------------------------------------------------------------

# 7. 完整事件案例

事件：

    US AI Chip Export Restriction

Graph:

                     Event

                        |

                     impacts

                        |

                   NVIDIA

                        |

                   depends_on

                        |

                      TSMC

                        |

                   belongs_to

                        |

              Semiconductor Industry

------------------------------------------------------------------------

# 8. PostgreSQL 关系表设计

虽然关系存在 Graph 中，但是部分查询适合 SQL。

## entity_registry

``` sql
CREATE TABLE entity_registry (

id UUID PRIMARY KEY,

entity_type VARCHAR(50),

entity_name TEXT,

external_id TEXT,

created_at TIMESTAMP

);
```

------------------------------------------------------------------------

## event_fact

``` sql
CREATE TABLE event_fact (

id UUID PRIMARY KEY,

event_id TEXT,

fact_type TEXT,

fact_value JSONB,

source TEXT,

confidence FLOAT

);
```

------------------------------------------------------------------------

## entity_alias

用于 Entity Linking：

``` sql
CREATE TABLE entity_alias (

id UUID PRIMARY KEY,

entity_id UUID,

alias TEXT,

language VARCHAR(20)

);
```

------------------------------------------------------------------------

# 9. Entity Linking 支持

例如：

不同名称：

    Apple

    Apple Inc.

    苹果公司

    NASDAQ:AAPL

统一：

    entity_id

    company_00001

查询：

``` sql
SELECT *

FROM entity_alias

WHERE alias='苹果公司';
```

------------------------------------------------------------------------

# 10. Research Agent 查询案例

问题：

    美国限制 AI 芯片出口，对 NVIDIA 有什么影响？

Graph Query：

``` cypher
MATCH

(policy:Policy)

-[:AFFECTS]->

(company:Company)

WHERE company.name='NVIDIA'

RETURN policy,company
```

继续：

``` cypher
MATCH

(event:Event)

-[:IMPACTS]->

(industry:Industry)

RETURN event,industry
```

------------------------------------------------------------------------

# 11. Graph + Vector Hybrid Retrieval

推荐架构：

    User Query

         |

    Intent Agent

         |

    +------------+

    |            |

    Graph Query Vector Search

    |            |

    AGE          Qdrant

    |            |

    Relations   Documents

    +------------+

         |

    Research Agent

------------------------------------------------------------------------

# 12. 推荐最终数据库结构

    PostgreSQL

    ├── stock_data

    ├── financial_data

    ├── news

    ├── facts

    ├── entity_registry

    ├── entity_alias


    ├── AGE Graph

    │
    └── investment_knowledge_graph

            ├── Company

            ├── Industry

            ├── Event

            ├── Policy

            ├── Person

            ├── Product

            └── Relations


    └── pgvector

            └── embeddings

------------------------------------------------------------------------

# 13. 设计原则

## Graph 保存：

    谁影响谁

    为什么影响

    关系链

------------------------------------------------------------------------

## PostgreSQL 保存：

    事实

    指标

    时间序列数据

------------------------------------------------------------------------

## Qdrant 保存：

    文本语义

    研究报告

    新闻内容

------------------------------------------------------------------------

# 14. 对 AI Investment Research Platform 的意义

最终形成：

    Database

    保存事实


    +

    Vector DB

    理解文本


    +

    Knowledge Graph

    理解世界

Research Agent 可以进行：

-   事件追踪
-   因果分析
-   行业影响分析
-   公司关联分析
-   历史事件类比

这才接近机构投资研究系统的知识基础设施。
