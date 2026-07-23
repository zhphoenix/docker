# Docker 部署

## 一、部署概览

所有服务通过 Docker Compose 管理，共享 `ai-platform` 外部网络。

```text
Docker Desktop
└── WSL2 (Ubuntu)
    └── Docker Network: ai-platform (external)
        ├── open-webui     :3000
        ├── docling        :5001
        ├── postgres       :5432
        ├── qdrant         :6333 / :6334
        ├── embedding      :8001
        ├── reranker       :8002
        ├── qwythos-9b     :8080
        ├── langgraph      :8100
        └── minio          :9000 / :9001
```

---

## 二、网络配置

所有容器加入同一个外部网络 `ai-platform`：

```yaml
networks:
  ai-platform:
    external: true
```

创建网络命令：

```bash
docker network create ai-platform
```

容器间通过**容器名**互相访问（如 `http://postgres:5432`、`http://qdrant:6333`）。

---

## 三、各服务 compose.yml 要点

### 3.1 PostgreSQL

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg17
    container_name: postgres
    ports: ["5432:5432"]
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: ai
    volumes:
      - pg_data:/var/lib/postgresql/data      # named volume（WSL2 NTFS 不支持 chmod）
      - ./init:/docker-entrypoint-initdb.d:ro
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 1G }
    command:
      - "postgres"
      - "-c" "shared_buffers=256MB"
      - "-c" "effective_cache_size=512MB"
      - "-c" "max_connections=50"
```

**初始化 SQL**（`init/01-init.sql`）：
- 创建 `langgraph` 数据库
- 启用 `pgvector` 扩展
- 创建 `documents`、`chunks`、`tasks`、`agents`、`collections` 表

> 完整表结构见 [24_数据底座规范](24_数据底座规范.md) 第四章。

### 3.2 Qdrant

```yaml
services:
  qdrant:
    image: qdrant/qdrant
    container_name: qdrant
    ports: ["6333:6333", "6334:6334"]
    volumes:
      - ./data:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334
      - QDRANT__STORAGE__ON_DISK_PAYLOAD=true
      - QDRANT__STORAGE__HNSW_INDEX__ON_DISK=true
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 2G }
```

### 3.3 MinIO

```yaml
services:
  minio:
    image: quay.io/minio/minio:RELEASE.2025-07-23T15-54-02Z
    container_name: minio
    ports: ["9000:9000", "9001:9001"]
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - /mnt/d/minio/data:/data
    command: server /data --console-address ":9001"
    deploy:
      resources:
        limits: { cpus: "0.5", memory: 512M }
```

### 3.4 Embedding

```yaml
services:
  embedding:
    image: ghcr.io/ggml-org/llama.cpp:server-cuda13
    container_name: embedding
    ports: ["8001:8080"]
    volumes:
      - /mnt/g/models:/models:ro
    command:
      - -m /models/unsloth/Qwen3-Embedding-4B-f16.gguf
      - --embedding
      - --host 0.0.0.0
      - --port "8080"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

### 3.5 Reranker

```yaml
services:
  reranker:
    image: ghcr.io/ggml-org/llama.cpp:server
    container_name: reranker
    ports: ["8002:8080"]
    volumes:
      - /mnt/g/models:/models:ro
    command:
      - -m /models/unsloth/Qwen3-Reranker-0.6B-Q8_0.gguf
      - --reranking
      - --embedding
      - --pooling rank
      - --ctx-size "4096"
      - --host 0.0.0.0
      - --port "8080"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

### 3.6 Docling

```yaml
services:
  docling:
    image: quay.io/docling-project/docling-serve-cu128:latest
    container_name: docling
    ports: ["5001:5001"]
    environment:
      DOCLING_SERVE_ENABLE_UI: "true"
      UVICORN_WORKERS: "1"
    volumes:
      - docling-models:/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

### 3.7 Open WebUI

```yaml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:v0.10.2-cuda
    container_name: open-webui
    ports: ["3000:8080"]
    environment:
      OPENAI_API_BASE_URL: http://host.docker.internal:8100/v1
      OPENAI_API_KEY: dummy
    volumes:
      - open-webui:/app/backend/data
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

### 3.8 LangGraph Agent 服务（自定义 FastAPI）

```yaml
services:
  langgraph:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: langgraph
    ports: ["8100:8100"]
    env_file:
      - ../.env
    networks:
      - ai-platform
    extra_hosts:
      - "host.docker.internal:host-gateway"
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 4G
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

### 3.9 Obsidian（Windows 侧，非 Docker）

Obsidian 不是 Docker 容器，而是 Windows 桌面应用。通过 MCP 协议与 Docker 内的 Agent 通信。

**前置条件**：

1. Windows 侧安装 Obsidian，打开 `E:\Knowledge\Vault` 作为 Vault
2. 安装 Local REST API 插件（端口 27123）
3. 确认插件设置中启用 HTTPS

**验证连接**：

```bash
# 从 WSL2 访问 Windows 侧 Obsidian MCP
curl -k https://host.docker.internal:27123/api/v1/search?q=test
```

**注意**：
- MCP 服务依赖 Obsidian 桌面端运行，关闭 Obsidian 则 MCP 不可用
- Vault 路径必须匹配（`E:\Knowledge\Vault`）
- Agent 容器通过 `host.docker.internal` 访问 Windows 侧服务

---

## 四、环境变量管理

全局 `.env` 文件位于 `/mnt/e/docker/.env`，各 compose.yml 通过 `env_file` 引用：

```ini
# ===== PostgreSQL =====
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=ai

# ===== MinIO =====
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# ===== LangGraph Agent =====
LANGGRAPH_PORT=8100
OPENAI_API_KEY=EMPTY
OPENAI_BASE_URL=http://qwythos-9b:8080/v1
MODEL_NAME=qwen3
```

**注意事项**：
- `.env` 文件分隔线必须以 `#` 开头注释，不能用其他符号
- 不要在 `.env` 中使用 `export` 前缀
- 敏感信息不要提交到版本控制，提供 `.env.example` 作为模板

---

## 五、部署顺序

```
1. 创建网络         docker network create ai-platform
2. PostgreSQL       docker compose up -d（基础设施优先）
3. Qdrant           docker compose up -d
4. MinIO            docker compose up -d
5. Embedding        docker compose up -d
6. Reranker         docker compose up -d
7. Docling          docker compose up -d
8. LLM (qwythos-9b)  docker compose up -d
9. LangGraph Agent  docker compose up -d（依赖上述所有服务）
10. Open WebUI      docker compose up -d（最后启动）
11. Obsidian        Windows 侧启动 + 确认 MCP 可用
```

---

## 六、资源限制汇总

| 服务 | CPU 限制 | 内存限制 | GPU |
|------|---------|---------|-----|
| PostgreSQL | 1.0 | 1G | - |
| Qdrant | 1.0 | 2G | - |
| MinIO | 0.5 | 512M | - |
| Embedding | 2.0 | 8G | 全部 |
| Reranker | 2.0 | 4G | 全部 |
| Docling | 2.0 | 4G | 全部 |
| Open WebUI | 1.0 | 2G | 全部 |
| LangGraph | 2.0 | 4G | - |

> **注意**：Obsidian 运行在 Windows 侧，不占用 Docker 资源。