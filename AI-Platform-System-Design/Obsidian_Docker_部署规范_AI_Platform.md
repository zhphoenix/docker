# Obsidian Docker 部署规范（AI Platform）

## 定位

Obsidian 作为 AI Platform 的 Knowledge Center，提供知识管理、AI 输出沉淀、Prompt 管理能力。

---

## 部署配置

配置文件：`/obsidian/compose.yml`

```yaml
services:

  obsidian:

    image: lscr.io/linuxserver/obsidian:v1.12.7-ls140

    container_name: obsidian

    restart: unless-stopped

    ports:
      # Web UI (KasmVNC)
      - "3002:3000"
      # Local REST API (HTTPS)
      - "27124:27124"

    # Electron shared memory
    shm_size: "2gb"

    # 资源限制
    mem_limit: 4g
    cpus: "2.0"

    environment:
      PUID: "1000"
      PGID: "1000"
      TZ: Asia/Shanghai
      ENABLE_AUDIO: "false"
      DOCKER_MODS: ""

    volumes:
      # Vault 数据（WSL ext4，高性能 I/O）
      - /home/putinking/ai-platform/data/obsidian_vault:/vaults/obsidian_vault
      # 应用配置（命名卷）
      - obsidian-config:/config

    logging:
      driver: json-file
      options:
        max-size: "20m"
        max-file: "3"

volumes:
  obsidian-config:

networks:
  default:
    name: ai-platform
    external: true
```

---

## 访问方式

| 服务 | 地址 |
|------|------|
| Web UI | `http://192.168.3.37:3002` |
| REST API | `https://127.0.0.1:27124` |
| 容器内 API | `https://obsidian:27124` |

Windows 桌面 Obsidian 通过 WSL 网络路径访问同一 Vault：

```
\\wsl.localhost\Ubuntu\home\putinking\ai-platform\data\obsidian_vault
```

---

## 数据路径

| 用途 | 宿主机路径 | 容器内路径 |
|------|-----------|-----------|
| Vault | `/home/putinking/ai-platform/data/obsidian_vault` | `/vaults/obsidian_vault` |
| Config | Docker named volume `obsidian-config` | `/config` |

Vault 存储在 WSL ext4 文件系统，相比 `/mnt/e/`（NTFS 挂载）I/O 性能更优。

---

## Vault 结构

```text
obsidian_vault/
├── companies/       # 公司笔记（7800+）
├── queries/         # 查询笔记
├── skills/          # 技能笔记
├── templates/       # 模板
└── .obsidian/       # 插件与配置
```

---

## 核心插件

| 插件 | 用途 |
|------|------|
| Local REST API | Agent 通过 HTTPS API 读写 Vault |

---

## 运维命令

```bash
# 启动
cd /mnt/e/ai-platform/obsidian && docker compose up -d

# 重建
docker rm -f obsidian && docker compose up -d

# 日志
docker logs -f obsidian

# 状态
docker ps --filter name=obsidian
```

---

## 设计决策

- **镜像版本锁定** `v1.12.7-ls140`，避免 latest 引入不兼容变更
- **shm_size 2gb**：Electron/Chromium 需要较大共享内存
- **禁用音频**：服务器环境无需音频流
- **DOCKER_MODS 置空**：禁用 GPU 加速等不必要修改
- **日志轮转 20m×3**：防止日志无限增长
- **命名卷存 config**：应用配置与数据分离，vault 可独立迁移
# Obsidian Docker 部署规范（AI Platform）

## 目标

将 Obsidian 作为 AI Platform 的 Knowledge Center，提供统一的知识管理、AI 输出沉淀、Prompt 管理和项目文档能力。

---

## 推荐架构

```text
AI Platform
├── Open WebUI
├── LangGraph
├── Docling
├── Embedding
├── Reranker
├── PostgreSQL
├── Qdrant
├── MinIO
├── Crawl4AI
├── MCP Server
└── Obsidian
```

---

## 前提条件

- Docker Desktop
- Docker Compose
- 已创建 ai-platform 网络（可选）
- 建议准备独立目录：

```text
AI-Platform/
└── obsidian/
    ├── docker-compose.yml
    ├── config/
    └── vault/
```

---

## Docker Compose 示例

```yaml
services:
  obsidian:
    image: lscr.io/linuxserver/obsidian:latest
    container_name: obsidian

    security_opt:
      - seccomp:unconfined

    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Asia/Singapore

    volumes:
      - ./config:/config
      - ./vault:/vault

    ports:
      - "3000:3000"

    restart: unless-stopped

    shm_size: "1gb"

    networks:
      - ai-platform

networks:
  ai-platform:
    external: true
```

---

## 启动

```bash
docker compose up -d
```

查看状态：

```bash
docker ps
```

查看日志：

```bash
docker logs -f obsidian
```

浏览器访问：

```
http://localhost:3000
```

---

## Vault 建议结构

```text
vault/
├── 00_Inbox
├── 01_Daily
├── 02_Research
├── 03_Project
├── 04_Prompts
├── 05_Knowledge
├── 06_AI_Output
├── 07_Meeting
├── Assets
├── Templates
└── Canvas
```

---

## 推荐插件

| 插件 | 用途 |
|------|------|
| Local REST API | Agent 读写 Vault |
| Dataview | 查询 Markdown |
| Templater | 模板 |
| Tasks | 任务 |
| QuickAdd | 快速创建 |
| Omnisearch | 全文搜索 |
| Excalidraw | 架构图 |
| Canvas | 知识组织 |
| Git | 版本管理 |

---

## Local REST API

安装插件后建议：

- API Key
- CORS 白名单
- 启用写入权限
- HTTPS（反向代理时）

常用接口：

```
POST /vault/create
POST /vault/append
POST /vault/update
POST /search
GET  /active-file
```

---

## 与 AI Platform 集成

### OCR

```
PDF
 ↓
Docling
 ↓
Markdown
 ↓
Obsidian
```

### Research Agent

```
Research Agent
 ↓
Markdown
 ↓
02_Research
```

### Embedding

```
Markdown
 ↓
Chunk
 ↓
Embedding
 ↓
Qdrant
```

### 图片

```
图片
 ↓
MinIO
 ↓
Markdown 引用
```

### 元数据

PostgreSQL 保存：

- Document Metadata
- Hash
- Source
- Tags
- Embedding ID
- Chunk ID

正文仍保存在 Markdown。

---

## 维护建议

- Vault 使用 Git 管理版本。
- 每日自动备份到 MinIO。
- AI 写入统一通过 Local REST API。
- 文档更新后自动触发 Embedding 更新。
- Canvas 与 Excalidraw 文件纳入版本控制。

---

## 最终定位

Obsidian 作为 AI Platform 的 Knowledge Center：

- 知识库
- Prompt Library
- Research Center
- Daily Notes
- AI 输出中心
- 项目文档中心
- Agent Workspace
