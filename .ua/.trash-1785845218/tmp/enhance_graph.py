#!/usr/bin/env python3
"""Phase 3 enhancements: fix missing fields + add package/serves/depends_on edges."""
import json, os

UA = "/mnt/e/ai-platform/.ua/intermediate"
gp = os.path.join(UA, "assembled-graph.json")
g = json.load(open(gp))
nodes, edges = g["nodes"], g["edges"]
by_id = {n["id"]: n for n in nodes}

def add_edge(src, tgt, etype, desc, weight=0.7):
    for e in edges:
        if e["source"] == src and e["target"] == tgt and e["type"] == etype:
            return
    edges.append({"source": src, "target": tgt, "type": etype,
                  "direction": "forward", "weight": weight, "description": desc})

# --- 1) Fix missing fields ---
fixes = {
    "config:.env.example": {
        "summary": "环境变量示例文件，定义项目所需的占位环境变量（数据库连接、API 密钥、服务地址等），供开发时复制为 .env 使用。",
        "tags": ["env", "配置", "环境变量"],
    },
    "document:CLAUDE.md": {
        "summary": "AI 编码助手协作规范，定义项目开发约定、常用命令与对话流程，指导 IDE 内 AI 工具的协作方式。",
        "tags": ["ai", "规范", "协作"],
    },
    "resource:compose.yml": {
        "summary": "根 Docker Compose 编排文件，通过 include 引入 14 个子服务栈（postgres/minio/qdrant/docling/embedding/reranker/paddleocr/sisyphus/openwebui/langgraph/crawl4ai/obsidian/mcp-knowledge/mcp-news），统一启动 AI 投研平台。",
        "tags": ["docker", "compose", "编排", "部署"],
    },
}
for nid, f in fixes.items():
    if nid in by_id:
        by_id[nid]["summary"] = f["summary"]
        by_id[nid]["tags"] = f["tags"]

# --- 2) __init__.py package contains edges ---
# Each __init__.py is a package marker; add contains edge to same-dir and subdir files
init_nodes = [n for n in nodes if n["id"].endswith("__init__.py")]
for n in init_nodes:
    nid = n["id"]
    prefix = nid.replace("file:", "").replace("__init__.py", "")
    for other in nodes:
        oid = other["id"]
        if oid == nid:
            continue
        if not oid.startswith("file:"):
            continue
        op = oid.replace("file:", "")
        # same directory or direct subdirectory
        if op.startswith(prefix) and op != n["id"].replace("file:", ""):
            # only direct children (one level) to keep it meaningful
            rel = op[len(prefix):]
            if "/" not in rel and rel.endswith(".py"):
                add_edge(nid, oid, "contains", "包包含模块", 0.7)

# --- 3) Dockerfile serves edges ---
# Dockerfile (resource) serves the service entry in the same module dir
docker_services = {
    "resource:langgraph/Dockerfile": "file:langgraph/main.py",
    "resource:mcp-knowledge/Dockerfile": "file:mcp-knowledge/server/main.py",
    "resource:mcp-news/Dockerfile": "file:mcp-news/server/main.py",
}
for src, tgt in docker_services.items():
    if src in by_id and tgt in by_id and not any(e["source"]==src and e["target"]==tgt for e in edges):
        add_edge(src, tgt, "serves", "镜像构建服务", 0.5)

# --- 4) config depends_on edges ---
config_deps = [
    ("config:langgraph/pyproject.toml", "file:langgraph/main.py"),
    ("config:frontend/package.json", "file:frontend/src/main.tsx"),
    ("config:frontend/vite.config.ts", "file:frontend/src/main.tsx"),
]
for src, tgt in config_deps:
    if src in by_id and tgt in by_id:
        add_edge(src, tgt, "depends_on", "依赖配置", 0.6)

# --- 5) postgres init SQL resource -> postgres service (defines_schema) ---
pg_init = [n for n in nodes if n["id"].startswith("resource:postgres/init/")]
pg_compose = "resource:postgres/compose.yml" if "resource:postgres/compose.yml" in by_id else None
for n in pg_init:
    if pg_compose and not any(e["source"]==n["id"] and e["target"]==pg_compose for e in edges):
        add_edge(n["id"], pg_compose, "defines_schema", "初始化数据库模式", 0.8)

g["nodes"] = nodes
g["edges"] = edges
json.dump(g, open(gp, "w"), ensure_ascii=False, indent=1)
print("Total nodes:", len(nodes), "Total edges:", len(edges))

# --- report orphan count after enhancement ---
with_edges = set()
for e in edges:
    with_edges.add(e["source"]); with_edges.add(e["target"])
orphans = [n["id"] for n in nodes if n["id"] not in with_edges]
print("Orphans after enhancement:", len(orphans))