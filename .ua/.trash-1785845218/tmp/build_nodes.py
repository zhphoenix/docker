#!/usr/bin/env python3
"""Build GraphNode + imports edges for all files, write per-batch JSON."""
import os, re, json, sys

ROOT = "/mnt/e/ai-platform"
UA = os.path.join(ROOT, ".ua", "intermediate")

scan = json.load(open(os.path.join(UA, "scan-result.json")))
batches = json.load(open(os.path.join(UA, "batches.json")))
fileinfo = json.load(open(os.path.join(UA, "file-info.json")))
# import-map: rel path -> list of module names (rel paths)
import_map = json.load(open(os.path.join(UA, "import-map.json")))

# Build set of all known rel paths for resolution
all_paths = [f["path"] for f in scan["files"]]
path_set = set(all_paths)

# Map from module-ish name to rel file path (for edge resolution)
def path_to_module(rel):
    """Convert a rel file path to its importable module name(s)."""
    base = os.path.dirname(rel).replace("/", ".")
    name = os.path.splitext(os.path.basename(rel))[0]
    ms = []
    if base:
        ms.append(f"{base}.{name}")
    ms.append(name)
    return ms

# Build lookup: module suffix -> rel path. For each file, register its module names.
module_to_path = {}
for rel in all_paths:
    if not rel.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
        continue
    for m in path_to_module(rel):
        module_to_path.setdefault(m, rel)

def resolve_import(module, source_rel):
    """Resolve an imported module name to a project rel path, or None."""
    # Skip external / stdlib singles (no dot and not a known project file)
    parts = module.split(".")
    # 0) Frontend @/ alias -> frontend/src/<module>
    if module.startswith("@/"):
        cand_rel = "frontend/src/" + module[2:]
        # try .ts/.tsx/.tsx
        for ext in (".ts", ".tsx", ".js", ".jsx"):
            if cand_rel + ext in path_set:
                return cand_rel + ext
    # 1) Exact match
    if module in module_to_path:
        return module_to_path[module]
    # 2) Project-root prefixes: try as <root>/<module>.py where root in {langgraph}
    for root in ("langgraph",):
        cand_rel = root + "/" + module.replace(".", "/") + ".py"
        if cand_rel in path_set and cand_rel != source_rel:
            return cand_rel
    # 3) Longest suffix match (e.g. 'api.chat' -> 'langgraph.api.chat')
    for i in range(len(parts)):
        suffix = ".".join(parts[i:])
        if suffix in module_to_path:
            cand = module_to_path[suffix]
            if cand != source_rel:
                return cand
    # 4) @/ alias for frontend (e.g. '@/services/x' -> frontend/src/services/x)
    return None

# Category -> node type / prefix
NODE_TYPE_MAP = {"docs":"document","config":"config","infra":"resource","data":"resource","script":"file","markup":"file"}
def node_type_for(fileCategory, rel):
    return NODE_TYPE_MAP.get(fileCategory, "file")

def prefix_for(nt):
    return {"file":"file","document":"document","config":"config","resource":"resource"}[nt]

def complexity_for(lines):
    if lines <= 20: return "simple"
    if lines <= 120: return "moderate"
    return "complex"

def langs_for(rel):
    ext = os.path.splitext(rel)[1]
    m = {"py":"Python","ts":"TypeScript","tsx":"TypeScript","js":"JavaScript","jsx":"JavaScript",
         "md":"Markdown","yaml":"YAML","yml":"YAML","json":"JSON","sql":"SQL","toml":"TOML",
         "sh":"Shell","dockerfile":"Dockerfile","html":"HTML","css":"CSS","txt":"Text"}.get(ext)
    return m or ""

def name_for(rel):
    return os.path.basename(rel)

def summary_for(rel, fileCategory, info):
    if info and info.get("doc"):
        return info["doc"]
    # fallback heuristics
    base = os.path.basename(rel)
    dir_ = os.path.dirname(rel)
    if fileCategory == "docs":
        return f"文档：{base}"
    if fileCategory == "config":
        return f"配置文件：{base}"
    return f"{base}（{dir_}）"

def tags_for(rel, fileCategory, info):
    tags = []
    dir_ = os.path.dirname(rel)
    segs = [s for s in dir_.split("/") if s]
    if segs: tags.append(segs[0])
    for s in segs:
        if s == "nodes": tags.append("node")
        elif s == "api": tags.append("api")
        elif s == "tools": tags.append("tool")
        elif s == "state": tags.append("state")
        elif s == "graphs": tags.append("graph")
        elif s == "storage": tags.append("storage")
        elif s == "collectors": tags.append("collector")
        elif s == "services": tags.append("service")
        elif s == "runtime": tags.append("runtime")
        elif s == "memory": tags.append("memory")
        elif s == "prompts": tags.append("prompt")
        elif s == "skills": tags.append("skill")
        elif s == "schemas": tags.append("schema")
        elif s == "config": tags.append("config")
        elif s == "frontend": tags.append("frontend")
        elif s == "components": tags.append("component")
        elif s == "pages": tags.append("page")
        elif s == "services": tags.append("service")
    if info:
        if info.get("classes"): tags.append("class")
        if info.get("funcs"): tags.append("function")
    tags = list(dict.fromkeys(tags))
    return tags[:6]

# Build nodes indexed by rel path
nodes_by_rel = {}
for f in scan["files"]:
    rel = f["path"]
    nt = node_type_for(f["fileCategory"], rel)
    info = fileinfo.get(rel, {})
    node = {
        "id": f"{prefix_for(nt)}:{rel}",
        "type": nt,
        "name": name_for(rel),
        "filePath": rel,
        "summary": summary_for(rel, f["fileCategory"], info),
        "tags": tags_for(rel, f["fileCategory"], info),
        "complexity": complexity_for(f["sizeLines"]),
        "languageNotes": langs_for(rel),
    }
    nodes_by_rel[rel] = node

# Build edges: imports
edges = []
seen_edges = set()
for rel, mods in import_map.items():
    if rel not in nodes_by_rel:
        continue
    src = nodes_by_rel[rel]["id"]
    for mod in mods:
        # skip external / stdlib-ish (no dot but not project) — resolve only
        tgt_rel = resolve_import(mod, rel)
        if not tgt_rel or tgt_rel == rel:
            continue
        if tgt_rel not in nodes_by_rel:
            continue
        tgt = nodes_by_rel[tgt_rel]["id"]
        key = (src, tgt, "imports")
        if key in seen_edges:
            continue
        seen_edges.add(key)
        edges.append({"source": src, "target": tgt, "type": "imports", "direction": "forward", "weight": 0.8, "description": "imports"})

# Write per-batch files
for b in batches["batches"]:
    idx = b["batchIndex"]
    out = {"nodes": [], "edges": []}
    for f in b["files"]:
        rel = f["path"]
        if rel in nodes_by_rel:
            out["nodes"].append(nodes_by_rel[rel])
    # edges whose source or target in this batch
    batch_ids = {n["id"] for n in out["nodes"]}
    for e in edges:
        if e["source"] in batch_ids:
            out["edges"].append(e)
    with open(os.path.join(UA, f"batch-{idx}.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

print("Total nodes:", len(nodes_by_rel))
print("Total edges:", len(edges))
print("Batches written:", len(batches["batches"]))