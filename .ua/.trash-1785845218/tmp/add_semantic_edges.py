#!/usr/bin/env python3
"""Add semantic edges to assembled-graph: configures, deploys, documents, serves."""
import json, os

UA = "/mnt/e/ai-platform/.ua/intermediate"
gp = os.path.join(UA, "assembled-graph.json")
g = json.load(open(gp))

nodes = g["nodes"]
edges = g["edges"]
by_id = {n["id"]: n for n in nodes}

def add_edge(src, tgt, etype, desc, weight=0.7):
    for e in edges:
        if e["source"] == src and e["target"] == tgt and e["type"] == etype:
            return
    edges.append({"source": src, "target": tgt, "type": etype,
                  "direction": "forward", "weight": weight, "description": desc})

# Helper: find node by filepath suffix
def find(relpath):
    for n in nodes:
        if n.get("filePath") == relpath:
            return n["id"]
    return None

# 1) configures: config files configure their corresponding resource
#    agents.yaml/workflows.yaml/policies.yaml configure langgraph
configures = [
    ("config:langgraph/config/agents.yaml", "config:langgraph/config/workflows.yaml"),
    ("config:langgraph/config/agents.yaml", "config:langgraph/config/policies.yaml"),
    ("config:langgraph/config/mcp_servers.yaml", "config:langgraph/config/policies.yaml"),
    ("config:specs/agent-registry.yaml", "config:langgraph/config/agents.yaml"),
    ("config:specs/architecture.yaml", "config:langgraph/config/workflows.yaml"),
    ("config:specs/ontology.yaml", "config:langgraph/config/policies.yaml"),
]
for s, t in configures:
    if s in by_id and t in by_id:
        add_edge(s, t, "configures", "配置约束")

# 2) deploys: root compose deploys service modules
root_compose = find("compose.yml")
if root_compose:
    for sub in ["postgres/compose.yml","minio/compose.yml","qdrant/compose.yml",
                "docling/compose.yml","embedding/compose.yml","reranker/compose.yml",
                "paddleocr/compose.yml","sisyphus/compose.yml","openwebui/compose.yml",
                "langgraph/compose.yml","crawl4ai/compose.yml","obsidian/compose.yml",
                "mcp-knowledge/compose.yml","mcp-news/compose.yml"]:
        t = find(sub)
        if t:
            add_edge(root_compose, t, "deploys", "编排部署")

# 3) documents: docs describe code modules
documented = [
    ("document:langgraph/README.md", "file:langgraph/api/server.py"),
    ("document:docs/00_Architecture_Decisions.md", "file:langgraph/api/server.py"),
    ("document:docs/architecture/Backend_Architecture.md", "file:langgraph/graphs/research_graph.py"),
    ("document:docs/architecture/Agent_Architecture.md", "config:langgraph/config/agents.yaml"),
    ("document:frontend/README.md", "file:frontend/src/main.tsx"),
]
for s, t in documented:
    if s in by_id and t in by_id:
        add_edge(s, t, "documents", "文档说明")

# 4) serves: api routers serve graph workflows
serves = [
    ("file:langgraph/api/research.py", "file:langgraph/graphs/research_graph.py"),
    ("file:langgraph/api/news.py", "file:langgraph/graphs/news_analysis_graph.py"),
    ("file:langgraph/api/knowledge.py", "file:langgraph/graphs/knowledge_graph.py"),
    ("file:langgraph/api/documents.py", "file:langgraph/graphs/document_graph.py"),
]
for s, t in serves:
    if s in by_id and t in by_id:
        add_edge(s, t, "serves", "服务调用")

# 5) main.py entry serves the api server
main = find("langgraph/main.py")
server = find("langgraph/api/server.py")
if main and server:
    add_edge(main, server, "serves", "入口启动")

# 6) triggers: scheduler triggers collectors
sch = find("langgraph/runtime/scheduler.py")
for col in ["langgraph/collectors/rss_collector.py","langgraph/collectors/web_collector.py"]:
    c = find(col)
    if sch and c:
        add_edge(sch, c, "triggers", "调度触发")

# 7) tested_by: tests test production code
tested = [
    ("file:langgraph/tests/unit/test_planner.py", "file:langgraph/nodes/research/planner.py"),
    ("file:langgraph/tests/unit/test_retrieve.py", "file:langgraph/nodes/research/retrieve.py"),
    ("file:langgraph/tests/unit/test_qdrant_tool.py", "file:langgraph/tools/qdrant.py"),
    ("file:langgraph/tests/unit/test_embedding_tool.py", "file:langgraph/tools/embedding.py"),
    ("file:langgraph/tests/api/test_chat.py", "file:langgraph/api/chat.py"),
    ("file:langgraph/tests/integration/test_graph.py", "file:langgraph/graphs/research_graph.py"),
]
for s, t in tested:
    if s in by_id and t in by_id:
        add_edge(t, s, "tested_by", "被测试覆盖")

# 8) frontend pages serve backend apis
pages = ["frontend/src/app/pages/ResearchPage.tsx","frontend/src/app/pages/NewsPage.tsx",
         "frontend/src/app/pages/KnowledgePage.tsx","frontend/src/app/pages/DocumentsPage.tsx"]
apis = ["langgraph/api/research.py","langgraph/api/news.py","langgraph/api/knowledge.py","langgraph/api/documents.py"]
for p, a in zip(pages, apis):
    ps, a2 = find(p), find(a)
    if ps and a2:
        add_edge(ps, a2, "calls", "页面调用")

g["nodes"] = nodes
g["edges"] = edges
json.dump(g, open(gp, "w"), ensure_ascii=False, indent=1)
print("Total edges now:", len(edges))