# Docker 开发规范

## LangGraph / AI Agent 项目开发环境规范

版本：v1.0

---

# 1. 核心原则

Docker 在 AI Agent 项目中的职责：

* 固化运行环境
* 管理依赖版本
* 保证部署一致性

Docker **不是开发代码编辑环境**。

开发阶段不应该：

```
修改代码
    ↓
docker build
    ↓
重新生成镜像
    ↓
重新启动容器
```

正确方式：

```
修改代码
    ↓
Volume 自动同步
    ↓
LangGraph Reload
    ↓
立即测试
```

---

# 2. Docker 镜像与代码分离原则

## 错误方式

将代码 COPY 到镜像：

```dockerfile
FROM python:3.12

WORKDIR /app

COPY . /app

RUN pip install -r requirements.txt

CMD ["python","main.py"]
```

结果：

```
Docker Image

├── Python
├── Dependencies
└── Application Code
```

代码被固化到 Image 中。

修改代码后：

必须重新：

```
docker build
docker run
```

开发效率低。

---

# 3. 推荐开发模式

## 镜像只保存运行环境

Docker Image：

```
Image

├── Python Runtime
├── LangGraph
├── LangChain
├── System Dependencies
└── Python Packages
```

代码通过 Volume 挂载：

```
Host

AI-Platform
│
├── agents
├── workflows
├── skills
├── prompts
└── configs


        ↓ Volume


Container

/app

├── agents
├── workflows
├── skills
├── prompts
└── configs
```

---

# 4. Docker Compose 开发规范

示例：

```yaml
services:

  langgraph:

    image: langgraph-dev

    volumes:

      - ./agents:/app/agents
      - ./workflows:/app/workflows
      - ./skills:/app/skills
      - ./prompts:/app/prompts
      - ./configs:/app/configs

    ports:

      - "8100:8100"

    command:

      langgraph dev
```

效果：

修改：

```
agents/research_agent.py
```

无需：

```
docker build
```

直接：

```
LangGraph Reload
```

---

# 5. LangGraph 开发规范

推荐：

```
langgraph dev
```

而不是：

```
python main.py
```

标准项目：

```
research-agent/

├── langgraph.json
├── requirements.txt
│
└── src/

    └── agent/

        ├── graph.py
        ├── nodes.py
        ├── tools.py
        └── state.py
```

---

# 6. Docker 三层架构规范

AI Platform 推荐：

```
                Docker Image

        ┌────────────────────┐
        │ Python Runtime     │
        │ LangGraph          │
        │ LangChain          │
        │ Dependencies       │
        └────────────────────┘


                Volume

        ┌────────────────────┐
        │ Agent Code         │
        │ Skills             │
        │ Prompts            │
        │ Workflow           │
        │ Config             │
        └────────────────────┘


                Services

        ┌────────────────────┐
        │ PostgreSQL         │
        │ Qdrant             │
        │ MinIO              │
        │ Redis              │
        │ MCP Server         │
        └────────────────────┘
```

---

# 7. 项目目录规范

推荐：

```
AI-Platform/

├── docker/

│   ├── langgraph/
│   ├── postgres/
│   └── mcp/


├── agents/

│   ├── research/
│   ├── analyst/
│   └── critic/


├── skills/

├── prompts/

├── workflows/

├── mcp/

├── configs/

├── services/

└── docker-compose.yml
```

---

# 8. 需要重新 Build 的情况

以下情况需要重新构建 Docker Image：

## 8.1 Python 依赖变化

例如：

requirements.txt：

```
langgraph-checkpoint-postgres
langchain-openai
qdrant-client
```

执行：

```
docker build
```

---

## 8.2 系统依赖变化

例如：

新增：

```
apt install poppler-utils
```

需要重新 build。

---

## 8.3 基础镜像变化

例如：

```
python:3.12

↓

python:3.13
```

需要重新 build。

---

# 9. 不需要 Build 的修改

以下修改直接通过 Volume 生效：

| 修改内容               | 是否需要 Build |
| ------------------ | ---------- |
| Agent逻辑            | 否          |
| LangGraph Workflow | 否          |
| Tool代码             | 否          |
| Prompt             | 否          |
| Skill文件            | 否          |
| YAML配置             | 否          |
| MCP配置              | 否          |
| 测试代码               | 否          |

---

# 10. 开发环境与生产环境区别

## 开发环境

目标：

快速迭代。

采用：

```
Docker Container

+

Volume Mount

+

Hot Reload

+

langgraph dev
```

特点：

* 修改代码立即生效
* 不重复构建镜像
* 方便调试

---

## 生产环境

目标：

稳定部署。

流程：

```
Git Commit

↓

Docker Build

↓

Version Image

↓

Deploy
```

例如：

```
research-agent:v1.2.0
```

特点：

* 镜像不可变
* 版本可追踪
* 易回滚

---

# 11. AI Agent 平台推荐架构

```
                 User

                  |

             Research Agent

                  |

             LangGraph Runtime

                  |

             MCP Client

                  |

        +---------+----------+

        |                    |

 Knowledge MCP        Data MCP


        |                    |

PostgreSQL             AKShare
Qdrant                 TuShare
Neo4j                  APIs
MinIO                  Crawlers

```

---

# 12. MCP / Skill / Prompt 管理原则

不要将以下内容打包进 Docker Image：

```
skills/
prompts/
agents/
configs/
```

原因：

* 修改频繁
* 需要动态更新
* 需要版本管理
* Agent 运行时需要读取

推荐：

```
Git Repository

+

Volume Mount

+

Registry Management
```

---

# 13. 最终开发规范总结

## 开发阶段

```
代码
 ↓
Volume Mount
 ↓
LangGraph Reload
 ↓
测试
```

不要：

```
代码
 ↓
Docker Build
 ↓
重新部署
```

## 发布阶段

```
代码冻结

↓

Docker Build

↓

生成版本镜像

↓

部署
```

---

## 核心原则

> Docker 管环境，不管业务代码。

> Image 管依赖，Volume 管变化。

> 开发追求快速迭代，生产追求稳定交付。

对于 LangGraph + MCP + AI Agent 平台，应采用“开发热更新 + 生产镜像固化”的双模式架构。
