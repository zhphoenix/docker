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
        ├── sisyphus       :8080
        ├── langgraph      :8100
        ├── obsidian       :3002 (Web UI) / :27123 (REST API)
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

### 3.9 Obsidian（容器化，obsidian-remote）

Obsidian 知识层通过 `ghcr.io/sytone/obsidian-remote` 镜像容器化部署：容器内运行完整 Obsidian + KasmVNC，通过浏览器访问；安装 Local REST API 插件后对内外暴露 REST API。

```yaml
services:
  obsidian:
    image: ghcr.io/sytone/obsidian-remote:latest
    container_name: obsidian
    ports:
      - "3002:8080"      # Web UI（KasmVNC 浏览器访问）
      - "27123:27123"    # Local REST API - HTTP（需在插件内启用）
    environment:
      PUID: "1000"
      PGID: "1000"
      TZ: Asia/Shanghai
    volumes:
      - /mnt/e/ai-platform/data/obsidian_vault:/vaults/ai-platform
      - obsidian-config:/config
    deploy:
      resources:
        limits: { cpus: "2.0", memory: 4G }
```

**首次使用需在 Web UI（http://localhost:3002）内安装并启用 Local REST API 插件**：

1. Settings → Community plugins → 关闭 Safe mode
2. Browse → 搜索 "Local REST API" → Install → Enable
3. 插件设置：启用 "Enable Non-encrypted (HTTP) Server"（端口 27123）
4. 插件设置：允许非本地接口访问（绑定 `0.0.0.0`，否则仅容器内回环可达）
5. 复制插件生成的 API Key，更新到 `.env` 的 `OBSIDIAN_API_KEY`

**验证连接**：

```bash
# 宿主机（经端口映射）
curl http://127.0.0.1:27123/
# langgraph 容器内（经 ai-platform 网络以容器名访问）
docker exec langgraph curl http://obsidian:27123/
```

**注意**：
- Vault 目录与 langgraph 容器共享同一宿主机路径（`data/obsidian_vault`），Vault 即共享知识空间
- Agent 容器通过容器名 `http://obsidian:27123` 访问（见 `settings.py` 的 `OBSIDIAN_URL`）
- 插件必须绑定 `0.0.0.0`，否则其他容器与宿主机均无法访问（默认仅绑定 127.0.0.1）

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
OPENAI_BASE_URL=http://sisyphus:8080/v1
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
8. LLM (sisyphus)  docker compose up -d
9. LangGraph Agent  docker compose up -d（依赖上述所有服务）
10. Open WebUI      docker compose up -d
11. Obsidian        docker compose up -d（Web UI :3002，首次需进容器内安装 REST API 插件）
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
| Obsidian | 2.0 | 4G | - |