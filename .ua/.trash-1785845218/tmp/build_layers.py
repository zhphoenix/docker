#!/usr/bin/env python3
"""Phase 4: assign file-level nodes to architectural layers."""
import json, os

UA = "/mnt/e/ai-platform/.ua/intermediate"
g = json.load(open(os.path.join(UA, "assembled-graph.json")))
nodes = g["nodes"]

LAYERS = [
    {"id": "layer:frontend", "name": "前端应用", "description": "React 前端界面，包含页面、组件、状态管理、API 客户端与样式。", "nodeIds": []},
    {"id": "layer:backend-core", "name": "后端核心", "description": "LangGraph 后端核心：API 路由、图工作流、节点、工具、Agent、状态、存储、管线、服务、运行时与入口。", "nodeIds": []},
    {"id": "layer:mcp-services", "name": "MCP 服务", "description": "模型上下文协议服务：mcp-knowledge（知识库）与 mcp-news（新闻）的服务端实现。", "nodeIds": []},
    {"id": "layer:infrastructure", "name": "基础设施", "description": "数据库、向量库、模型服务与容器编排：PostgreSQL、MinIO、Qdrant、Docling、Embedding、Reranker、PaddleOCR、Sisyphus、Crawl4AI、Obsidian 及 Docker Compose。", "nodeIds": []},
    {"id": "layer:config", "name": "配置与规格", "description": "服务配置、注册表、架构规格与 schema 定义文件。", "nodeIds": []},
    {"id": "layer:docs", "name": "文档与提示词", "description": "项目文档、架构决策、提示词模板、技能与协作规范。", "nodeIds": []},
    {"id": "layer:scripts", "name": "运维脚本", "description": "数据导入、同步、初始化与架构检查脚本。", "nodeIds": []},
    {"id": "layer:tests", "name": "测试", "description": "单元测试、接口测试与集成测试。", "nodeIds": []},
]

def layer_index(lid):
    for i, l in enumerate(LAYERS):
        if l["id"] == lid:
            return i
    return None

def assign(n):
    nid = n["id"]
    fp = n.get("filePath", "")
    t = n["type"]
    fp_head = fp.split("/")[0] if fp else ""

    # frontend
    if fp.startswith("frontend/"):
        return "layer:frontend"
    # mcp services
    if fp.startswith("mcp-knowledge/") or fp.startswith("mcp-news/"):
        if fp.endswith("__init__.py") or "tests" in fp:
            return "layer:tests" if "tests" in fp else "layer:mcp-services"
        return "layer:mcp-services"
    # tests
    if "/tests/" in fp or fp.startswith("tests/"):
        return "layer:tests"
    # prompts
    if fp.startswith("langgraph/prompts/"):
        return "layer:docs"
    # scripts
    if fp.startswith("scripts/") or fp.startswith("langgraph/scripts/"):
        return "layer:scripts"
    # backend core
    if fp.startswith("langgraph/"):
        return "layer:backend-core"
    # infrastructure
    infra_dirs = ["postgres","minio","qdrant","docling","embedding","reranker",
                  "paddleocr","sisyphus","openwebui","crawl4ai","obsidian","siyuan"]
    if fp_head in infra_dirs:
        return "layer:infrastructure"
    if fp in ("compose.yml",) or fp.endswith("Dockerfile") or fp.endswith("Dockerfile.dev") or fp.endswith("Dockerfile.cuda13"):
        return "layer:infrastructure"
    # config
    if fp_head in ("config","registry","specs") or fp.startswith("AI-Platform-System-Design/"):
        return "layer:config"
    if t == "config":
        return "layer:config"
    # docs
    if fp_head in ("docs",".qoder",".sisi","skills") or fp in ("CLAUDE.md","README.md") or fp.endswith(".md"):
        return "layer:docs"
    if t == "document":
        return "layer:docs"
    # fallback config
    return "layer:config"

for n in nodes:
    lid = assign(n)
    idx = layer_index(lid)
    LAYERS[idx]["nodeIds"].append(n["id"])

# produce output
out = LAYERS
json.dump(out, open(os.path.join(UA, "layers.json"), "w"), ensure_ascii=False, indent=2)
total = sum(len(l["nodeIds"]) for l in LAYERS)
print("Total assigned:", total, "of", len(nodes))
for l in LAYERS:
    print(f"{l['id']:28s} {len(l['nodeIds']):4d}  {l['name']}")