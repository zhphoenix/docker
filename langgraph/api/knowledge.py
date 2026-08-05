"""Knowledge API - 知识库管理（Collection 统计 + 知识图谱查询 + Hybrid 检索）"""

import asyncio
import json
import logging
import os
import uuid as uuid_mod
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config.settings import settings
from tools.postgres import postgres_tool
from tools.llm import llm_tool
from config.policy_loader import get_policy
from storage.knowledge.postgres import knowledge_storage
from storage.knowledge.qdrant import knowledge_qdrant
from runtime.queue import task_queue
from pipelines.document_pipeline import doc_pipeline
from api.path_utils import normalize_path, get_volume_mapping_info

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/collections")
async def list_collections():
    """知识库 Collection 列表

    合并 collections 表元数据 + chunks 实际计数 + Qdrant points 统计。
    Qdrant 不可达时 qdrant_points 字段为 null（降级）。
    """
    try:
        rows = await postgres_tool.query(
            """
            SELECT c.id, c.name, c.description, c.vector_size, c.distance, c.domain,
                   COUNT(ch.id) AS chunk_count,
                   COUNT(ch.qdrant_point_id) AS embedded_count
            FROM collections c
            LEFT JOIN chunks ch ON ch.collection_name = c.name
            GROUP BY c.id, c.name, c.description, c.vector_size, c.distance, c.domain
            ORDER BY c.name
            """
        )
    except Exception as e:
        logger.exception("Failed to query collections")
        raise HTTPException(status_code=500, detail=str(e))

    # Qdrant points 统计（独立降级，不影响主数据）
    # 并行查询避免 collection 数量多时串行等待拖慢接口
    qdrant_stats: dict[str, int] = {}
    try:
        async def _query_points(name: str) -> tuple[str, int | None]:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(
                        f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}/collections/{name}"
                    )
                    if resp.status_code == 200:
                        return name, resp.json().get("result", {}).get("points_count", 0)
            except Exception:
                pass  # 单个 collection 查询失败不影响其他
            return name, None

        results = await asyncio.gather(*[_query_points(r["name"]) for r in rows])
        qdrant_stats = {name: cnt for name, cnt in results if cnt is not None}
    except Exception:
        logger.warning("Qdrant unreachable, qdrant_points will be null")

    collections = []
    for r in rows:
        collections.append({
            "id": str(r["id"]),
            "name": r["name"],
            "description": r.get("description"),
            "vector_size": r["vector_size"],
            "distance": r.get("distance"),
            "domain": r.get("domain"),
            "chunk_count": r["chunk_count"],
            "embedded_count": r["embedded_count"],
            "qdrant_points": qdrant_stats.get(r["name"]),  # None 表示不可用
        })

    return {"collections": collections, "total": len(collections)}


@router.get("/stats")
async def knowledge_stats():
    """Knowledge Hub 聚合统计 - 一次返回 Dashboard 全部数据

    各子查询独立 try/catch，单故障不影响整体返回（对应字段降级为 0/空）。
    """
    stats: dict = {}

    # documents / chunks / embedded
    try:
        rows = await postgres_tool.query(
            "SELECT "
            "(SELECT COUNT(*) FROM documents) AS documents, "
            "(SELECT COUNT(*) FROM chunks) AS chunks, "
            "(SELECT COUNT(*) FROM chunks WHERE qdrant_point_id IS NOT NULL) AS embedded"
        )
        r = rows[0]
        stats["documents"] = r["documents"]
        stats["chunks"] = r["chunks"]
        stats["embedded"] = r["embedded"]
    except Exception:
        logger.warning("stats: documents/chunks query failed, degraded")
        stats["documents"] = stats["chunks"] = stats["embedded"] = 0

    # entities / facts（显式 schema 前缀，与现有代码一致）
    try:
        rows = await postgres_tool.query(
            "SELECT "
            "(SELECT COUNT(*) FROM core.entities WHERE status='active') AS entities, "
            "(SELECT COUNT(*) FROM core.facts) AS facts"
        )
        r = rows[0]
        stats["entities"] = r["entities"]
        stats["facts"] = r["facts"]
    except Exception:
        logger.warning("stats: entities/facts query failed, degraded")
        stats["entities"] = stats["facts"] = 0

    # 任务队列（按状态分组）
    try:
        rows = await postgres_tool.query(
            "SELECT status, COUNT(*) AS cnt FROM tasks GROUP BY status"
        )
        counts = {r["status"]: r["cnt"] for r in rows}
        stats["task_queue"] = {
            "pending": counts.get("pending", 0),
            "running": counts.get("running", 0),
            "done": counts.get("done", 0),
            "failed": counts.get("failed", 0),
        }
    except Exception:
        logger.warning("stats: task_queue query failed, degraded")
        stats["task_queue"] = {"pending": 0, "running": 0, "done": 0, "failed": 0}

    # 最近任务
    try:
        rows = await postgres_tool.query(
            "SELECT id, title, task_type, status, progress, created_at "
            "FROM tasks ORDER BY created_at DESC LIMIT 8"
        )
        stats["recent_tasks"] = [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "task_type": r["task_type"],
                "status": r["status"],
                "progress": float(r["progress"] or 0),
                "created_at": str(r["created_at"]) if r.get("created_at") else None,
            }
            for r in rows
        ]
    except Exception:
        logger.warning("stats: recent_tasks query failed, degraded")
        stats["recent_tasks"] = []

    # 最近更新文档
    try:
        rows = await postgres_tool.query(
            "SELECT id, market, symbol, company, status, chunk_count, updated_at "
            "FROM documents ORDER BY updated_at DESC LIMIT 8"
        )
        stats["recent_updates"] = [
            {
                "id": str(r["id"]),
                "market": r["market"],
                "symbol": r["symbol"],
                "company": r.get("company"),
                "status": r["status"],
                "chunk_count": r["chunk_count"],
                "updated_at": str(r["updated_at"]) if r.get("updated_at") else None,
            }
            for r in rows
        ]
    except Exception:
        logger.warning("stats: recent_updates query failed, degraded")
        stats["recent_updates"] = []

    # 知识质量：chunk 平均长度 / embedding 覆盖率 / 实体置信度
    try:
        rows = await postgres_tool.query(
            "SELECT AVG(token_count) AS avg_token_count, "
            "COUNT(qdrant_point_id)::float / NULLIF(COUNT(*), 0) AS embed_coverage "
            "FROM chunks"
        )
        r = rows[0]
        avg_token = r["avg_token_count"]
        coverage = r["embed_coverage"]
        stats["quality"] = {
            "avg_chunk_length": round(float(avg_token), 1) if avg_token is not None else None,
            "embedding_coverage": round(float(coverage) * 100, 1) if coverage is not None else None,
            "entity_confidence": None,
        }
        # 实体置信度（独立降级，失败不影响其他质量指标）
        try:
            erows = await postgres_tool.query(
                "SELECT AVG(confidence) AS avg_confidence FROM core.entities WHERE status='active'"
            )
            ec = erows[0]["avg_confidence"]
            stats["quality"]["entity_confidence"] = round(float(ec) * 100, 1) if ec is not None else None
        except Exception:
            logger.warning("stats: entity_confidence query failed, degraded")
    except Exception:
        logger.warning("stats: quality query failed, degraded")
        stats["quality"] = {
            "avg_chunk_length": None,
            "embedding_coverage": None,
            "entity_confidence": None,
        }

    # Collections 概览（复用 list_collections 逻辑）
    try:
        coll_data = await list_collections()
        stats["collections"] = coll_data["collections"]
    except Exception:
        logger.warning("stats: collections query failed, degraded")
        stats["collections"] = []

    return stats


# ============================================================
# 知识图谱查询 API
# ============================================================


@router.get("/entities")
async def list_entities(
    name: str = Query("", description="实体名称搜索"),
    entity_type: str = Query("", description="实体类型过滤"),
    limit: int = Query(20, ge=1, le=100),
):
    """查询实体（by name/type）"""
    try:
        entities = await knowledge_storage.search_entities(
            name=name, entity_type=entity_type, limit=limit
        )
        return {
            "entities": [
                {
                    "id": str(e["id"]),
                    "name": e["name"],
                    "entity_type": e["entity_type"],
                    "description": e.get("description"),
                    "canonical_name": e.get("canonical_name"),
                    "confidence": e.get("confidence"),
                    "source_count": e.get("source_count", 0),
                }
                for e in entities
            ],
            "total": len(entities),
        }
    except Exception as e:
        logger.exception("Failed to query entities")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities/{entity_id}")
async def get_entity_detail(entity_id: str):
    """实体详情（含 aliases、properties）"""
    try:
        import uuid as _uuid
        rows = await postgres_tool.query(
            """
            SELECT id, name, entity_type, description, canonical_name,
                   confidence, source_count, aliases, properties,
                   status, created_at, updated_at
            FROM core.entities
            WHERE id = $1 AND status = 'active'
            """,
            _uuid.UUID(entity_id),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Entity not found")
        e = rows[0]
        return {
            "id": str(e["id"]),
            "name": e["name"],
            "entity_type": e["entity_type"],
            "description": e.get("description"),
            "canonical_name": e.get("canonical_name"),
            "confidence": e.get("confidence"),
            "source_count": e.get("source_count", 0),
            "aliases": e.get("aliases") or [],
            "properties": e.get("properties") or {},
            "created_at": str(e["created_at"]) if e.get("created_at") else None,
            "updated_at": str(e["updated_at"]) if e.get("updated_at") else None,
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entity ID format")
    except Exception as e:
        logger.exception("Failed to get entity detail")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities/{entity_id}/neighbors")
async def get_entity_neighbors(
    entity_id: str,
    depth: int = Query(1, ge=1, le=2, description="遍历深度（最大 2）"),
):
    """图遍历：获取实体的关联实体"""
    try:
        neighbors = await knowledge_storage.get_entity_neighbors(entity_id, depth=depth)
        return {
            "entity_id": entity_id,
            "depth": depth,
            "neighbors": [
                {
                    "source_entity": str(n["source_entity"]),
                    "target_entity": str(n["target_entity"]),
                    "relation_type": n["relation_type"],
                    "depth": n["depth"],
                }
                for n in neighbors
            ],
            "total": len(neighbors),
        }
    except Exception as e:
        logger.exception("Failed to get neighbors")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/facts")
async def list_facts(
    subject: str = Query("", description="主体实体 ID"),
    predicate: str = Query("", description="谓词过滤"),
    limit: int = Query(50, ge=1, le=200),
):
    """查询事实（by subject/predicate）"""
    if not subject:
        raise HTTPException(status_code=400, detail="subject parameter required")

    try:
        facts = await knowledge_storage.get_facts_by_subject(
            subject_entity=subject,
            predicate=predicate or None,
            limit=limit,
        )
        return {
            "facts": [
                {
                    "id": str(f["id"]),
                    "predicate": f["predicate"],
                    "object_value": f["object_value"],
                    "unit": f.get("unit"),
                    "time_start": str(f["time_start"]) if f.get("time_start") else None,
                    "time_end": str(f["time_end"]) if f.get("time_end") else None,
                    "confidence": f.get("confidence"),
                    "verification_status": f.get("verification_status"),
                }
                for f in facts
            ],
            "total": len(facts),
        }
    except Exception as e:
        logger.exception("Failed to query facts")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Hybrid 检索 API
# ============================================================


class HybridSearchRequest(BaseModel):
    query: str
    entity_name: str = ""
    limit: int = 10


@router.post("/search")
async def hybrid_search(request: HybridSearchRequest):
    """混合检索：图查询 + 向量检索 + RRF 合并"""
    try:
        # 1. 图查询（结构化）
        graph_results = []
        entity_ids = []

        if request.entity_name:
            entities = await knowledge_storage.find_entity_by_name(
                request.entity_name, limit=1
            )
            if entities:
                entity_id = str(entities[0]["id"])
                entity_ids = [entity_id]
                graph_results = await knowledge_storage.get_entity_neighbors(
                    entity_id, depth=2
                )

        # 2. 向量检索（语义）
        vector_results = await knowledge_qdrant.hybrid_search(
            query=request.query,
            entity_ids=entity_ids if entity_ids else None,
            limit=request.limit,
        )

        # 3. 合并结果
        return {
            "query": request.query,
            "graph_results": [
                {
                    "source_entity": str(r["source_entity"]),
                    "target_entity": str(r["target_entity"]),
                    "relation_type": r["relation_type"],
                    "depth": r["depth"],
                }
                for r in graph_results
            ],
            "vector_results": vector_results,
            "entity_ids_used": entity_ids,
        }
    except Exception as e:
        logger.exception("Hybrid search failed")
        raise HTTPException(status_code=500, detail=str(e))


class GraphRAGRequest(BaseModel):
    query: str = Field(..., min_length=1, description="自然语言查询")
    entity_name: str = ""
    limit: int = Field(10, ge=1, le=30)


def _build_rag_context(
    query: str,
    graph_results: list[dict],
    vector_results: dict,
    entity_ids: list[str],
) -> dict:
    """组装 GraphRAG 上下文（图证据 + 向量证据）

    Returns:
        {"graph_evidence": [...], "vector_evidence": [...]}
    """
    # 图证据：关系边（含实体 id，供引用）
    graph_evidence = [
        {
            "source_entity": str(r["source_entity"]),
            "target_entity": str(r["target_entity"]),
            "relation_type": r["relation_type"],
            "depth": r["depth"],
        }
        for r in graph_results
    ]

    # 向量证据：实体描述 + 事实
    vector_evidence: list[dict] = []
    for ent in vector_results.get("entities", []):
        payload = ent.get("payload", {}) or {}
        vector_evidence.append({
            "kind": "entity",
            "name": payload.get("name", ""),
            "entity_type": payload.get("entity_type", ""),
            "description": (payload.get("description") or "")[:600],
        })
    for fact in vector_results.get("facts", []):
        payload = fact.get("payload", {}) or {}
        vector_evidence.append({
            "kind": "fact",
            "subject": payload.get("subject_name", ""),
            "predicate": payload.get("predicate", ""),
            "value": (payload.get("object_value") or "")[:400],
            "time_start": payload.get("time_start", ""),
        })

    # 限制上下文量，避免超出模型 context
    graph_evidence = graph_evidence[:30]
    vector_evidence = vector_evidence[:30]

    return {"graph_evidence": graph_evidence, "vector_evidence": vector_evidence}


@router.post("/search/rag")
async def graphrag_search(request: GraphRAGRequest):
    """GraphRAG 增强检索：图遍历 + 向量检索 + LLM 融合推理

    与 /search 的区别：在混合检索基础上叠加 LLM 推理，
    产出带引用（图证据 + 向量证据）的可解释答案段落。
    """
    try:
        # 1. 结构化图检索
        graph_results = []
        vector_results = []
        entity_ids = []

        if request.entity_name:
            entities = await knowledge_storage.find_entity_by_name(
                request.entity_name, limit=1
            )
            if entities:
                entity_id = str(entities[0]["id"])
                entity_ids = [entity_id]
                graph_results = await knowledge_storage.get_entity_neighbors(
                    entity_id, depth=2
                )

        # 2. 语义向量检索
        vector_results = await knowledge_qdrant.hybrid_search(
            query=request.query,
            entity_ids=entity_ids if entity_ids else None,
            limit=request.limit,
        )

        # 3. 组装推理上下文
        context = _build_rag_context(
            request.query, graph_results, vector_results, entity_ids
        )

        graph_txt = "\n".join(
            f"- [{e['relation_type']}] {e['source_entity'][:8]} → {e['target_entity'][:8]} (depth={e['depth']})"
            for e in context["graph_evidence"]
        ) or "(无图证据)"
        vec_txt = "\n".join(
            f"- ({e['kind']}) "
            + (
                f"{e.get('name', '')}({e.get('entity_type', '')}): {e.get('description', '')}"
                if e["kind"] == "entity"
                else f"{e.get('subject', '')} - {e.get('predicate', '')}: {e.get('value', '')} @ {e.get('time_start', '')}"
            )
            for e in context["vector_evidence"]
        ) or "(无向量证据)"

        prompt = (
            "你是投资研究知识问答助手，基于以下证据回答用户问题。\n"
            "要求：\n"
            "1. 只能基于给出的证据推理，不得编造；证据不足时明确说明。\n"
            "2. 输出纯 JSON（不要 markdown 代码块）：{\"summary\": "
            "\"一段完整、连贯的中文答案\", \"key_findings\": [{\"finding\": "
            "\"结论要点\", \"cited_evidence\": [\"对应证据原文片段\"]}]}.\n\n"
            f"## 用户问题\n{request.query}\n\n"
            f"## 图证据（结构化关系，entity_id 唯一标识）\n{graph_txt}\n\n"
            f"## 向量证据（实体/事实描述）\n{vec_txt}\n"
            "## 输出\n"
        )

        messages = [
            {"role": "system", "content": "你是严谨的投资知识图谱推理助手，支持证据引用，输出结构化 JSON。"},
            {"role": "user", "content": prompt},
        ]

        temperature = get_policy("knowledge.rag.temperature", 0.1)

        # 4. LLM 融合推理（失败时降级为原始检索结果）
        fusion = {"summary": "", "key_findings": []}
        try:
            result = await llm_tool.chat(messages, temperature=temperature)
            raw = (result.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
            # 去除可能的代码围栏
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
            try:
                import json as _json
                parsed = _json.loads(raw)
                if isinstance(parsed, dict):
                    fusion = {
                        "summary": str(parsed.get("summary", "")),
                        "key_findings": parsed.get("key_findings", []) or [],
                    }
            except Exception:
                fusion = {"summary": raw, "key_findings": []}
        except Exception as e:
            logger.warning("GraphRAG LLM fusion failed (degraded): %s", e)
            fusion = {"summary": "", "key_findings": []}

        return {
            "query": request.query,
            "fusion": fusion,
            "entity_ids_used": entity_ids,
            "evidence": {
                "graph": context["graph_evidence"],
                "vector": context["vector_evidence"],
            },
            "degraded": fusion["summary"] == "",
        }
    except Exception as e:
        logger.exception("GraphRAG search failed")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 知识提取任务 API
# ============================================================


class ExtractRequest(BaseModel):
    document_ids: list[str]
    raw_texts: dict[str, str] = {}  # 可选：直接传入文本


@router.post("/extract")
async def trigger_extraction(request: ExtractRequest):
    """触发知识提取任务（创建 task → worker 处理）"""
    if not request.document_ids:
        raise HTTPException(status_code=400, detail="document_ids required")

    try:
        task_id = await task_queue.create_task(
            task_type="knowledge_extraction",
            title=f"知识提取 ({len(request.document_ids)} docs)",
            total_items=len(request.document_ids),
            params={
                "document_ids": request.document_ids,
                "raw_texts": request.raw_texts,
            },
        )
        return {
            "task_id": task_id,
            "status": "pending",
            "document_count": len(request.document_ids),
        }
    except Exception as e:
        logger.exception("Failed to create extraction task")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 目录浏览 API
# ============================================================


# 允许浏览的根路径白名单（安全限制）
ALLOWED_BROWSE_ROOTS = ["/data", "/app"]


@router.get("/browse-dirs")
async def browse_dirs(path: str = Query("/data/minio/documents", description="要浏览的目录路径（支持 Windows/WSL/容器格式）")):
    """浏览服务器目录结构（仅返回目录，用于目录选择器）

    自动转换 Windows (E:\\...) 和 WSL (/mnt/e/...) 路径为容器路径。
    """
    # 路径转换：Windows/WSL → 容器路径
    path = normalize_path(path)
    target = Path(path).resolve()

    # 安全检查：路径必须在允许的根目录下
    if not any(str(target).startswith(root) for root in ALLOWED_BROWSE_ROOTS):
        raise HTTPException(
            status_code=403,
            detail=f"路径不在允许范围内，允许的根路径: {', '.join(ALLOWED_BROWSE_ROOTS)}"
        )

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"路径不存在: {path}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"不是目录: {path}")

    # 获取子目录列表
    subdirs = []
    try:
        for item in sorted(target.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                subdirs.append({
                    "name": item.name,
                    "path": str(item),
                })
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"无权限访问: {path}")

    # 计算父级路径
    parent = target.parent
    can_go_up = any(str(parent).startswith(root) for root in ALLOWED_BROWSE_ROOTS) and parent != target

    return {
        "current_path": str(target),
        "parent_path": str(parent) if can_go_up else None,
        "can_go_up": can_go_up,
        "directories": subdirs,
        "total": len(subdirs),
    }


@router.get("/path-mapping")
async def path_mapping():
    """返回卷映射信息，帮助前端用户理解路径转换关系"""
    return {
        "description": "路径映射关系：Windows → WSL → 容器",
        "examples": {
            "windows": "E:\\ai-platform\\data\\stock_a",
            "wsl": "/mnt/e/ai-platform/data/stock_a",
            "container": "/data/stock_a",
        },
        "volume_mounts": get_volume_mapping_info(),
        "tip": "建议使用目录浏览器选择路径，或手动输入容器路径（/data/... 格式）",
    }


# ============================================================
# MD 文件手动导入 API
# ============================================================


class MinioIngestRequest(BaseModel):
    bucket: str = Field("documents", description="MinIO bucket")
    prefix: str = Field("", description="对象前缀，如 cn/000002")
    market: str = Field("", description="市场过滤（cn/hk/us），空=全部")
    trigger: bool = Field(False, description="注册后是否立即入队 doc_pipeline")


@router.post("/ingest-minio")
async def trigger_ingest_minio(req: MinioIngestRequest):
    """从 MinIO 采集年报对象并注册为 pending documents（异步任务，支持进度/暂停/取消）

    调用 register_pending_from_minio 扫描 bucket 下的对象，识别
    /annual_report/{year}/report.{pdf|md} 形态的路径，写入 documents 表（幂等）。
    可选触发 doc_pipeline worker 处理。
    """
    task_id = await task_queue.create_task(
        task_type="ingest_minio",
        title=f"MinIO 导入: {req.bucket}/{req.prefix or '*'}"
        + (f" [{req.market}]" if req.market else ""),
        params={
            "bucket": req.bucket, "prefix": req.prefix,
            "market": req.market, "trigger": req.trigger,
        },
        created_by="api",
    )
    logger.info("[IngestMinio] async task created: %s | bucket=%s prefix=%r", task_id[:8], req.bucket, req.prefix)
    return {
        "status": "ok",
        "task_id": task_id,
        "async_mode": True,
    }


async def _run_ingest_minio_async(task_id: str, req: MinioIngestRequest) -> None:
    """异步任务：扫描 MinIO 并注册 pending 文档，支持暂停/恢复/终止"""
    try:
        result = await doc_pipeline.register_pending_from_minio(
            bucket=req.bucket, prefix=req.prefix, market=req.market,
            task_id=task_id,
        )
        if result.get("cancelled"):
            await task_queue.fail_task(
                task_id, "任务已终止（用户取消，部分文档可能已注册）"
            )
            await task_queue.log_task(
                task_id, "warn",
                f"MinIO 导入已终止，已注册 {result.get('added', 0)} 个文档",
            )
            return

        await task_queue.update_progress(
            task_id, result.get("found", 0),
            stage=f"完成 · 新增{result.get('added', 0)} 跳过{result.get('skipped', 0)} 重置{result.get('reset', 0)}",
            current_name="",
        )
        await task_queue.complete_task(task_id)
        await task_queue.log_task(
            task_id, "info",
            f"MinIO 导入完成: found={result.get('found', 0)} added={result.get('added', 0)} "
            f"skipped={result.get('skipped', 0)} reset={result.get('reset', 0)}",
        )

        if req.trigger and result.get("found", 0) > 0:
            # 只要扫描到对象即触发处理（已存在 pending 文档也会由
            # process_pending_documents 原子认领处理，避免因 added=0 永不触发）
            pipeline_task_id = await task_queue.create_task(
                task_type="doc_pipeline",
                title=f"文档处理 Pipeline ({result['found']} docs, MinIO)",
                params={"limit": result["found"]},
                total_items=result["found"],
                created_by="api",
            )
            await task_queue.log_task(task_id, "info", f"已触发 Pipeline: {pipeline_task_id}")
    except asyncio.CancelledError:
        logger.info("[IngestMinio] %s terminated", task_id[:8])
        await task_queue.fail_task(task_id, "任务已终止（用户取消）")
    except Exception as e:
        logger.exception("[IngestMinio] %s failed", task_id[:8])
        await task_queue.fail_task(task_id, str(e))
    finally:
        task_queue.purge_control(task_id)


class IngestRequest(BaseModel):
    path: str = Field(..., min_length=1, description="文件或目录路径")
    collection: str = Field("documents_cn", description="目标 Qdrant collection")


async def _run_ingest(path: str, collection: str, task_id: str = "") -> dict[str, int]:
    """后台执行 MD 文件导入处理管线（task_id 非空时同步更新任务队列进度）

    Returns:
        {"found": N, "added": M, "skipped": K}
    """
    from tools.chunker import chunk_markdown
    from tools.embedding import embedding_tool
    from tools.qdrant import qdrant_tool

    logger.info("[Ingest] Start | path=%s | collection=%s", path, collection)
    if task_id:
        await task_queue.start_task(task_id)

    stats = {"found": 0, "added": 0, "skipped": 0}

    try:
        target = Path(path)
        md_files: list[Path] = []

        if target.is_file() and target.suffix == ".md":
            md_files = [target]
        elif target.is_dir():
            md_files = sorted(target.rglob("*.md"))
        else:
            logger.warning("[Ingest] Invalid path: %s", path)
            if task_id:
                await task_queue.fail_task(task_id, f"Invalid path: {path}")
            return stats

        stats["found"] = len(md_files)

        if not md_files:
            logger.info("[Ingest] No .md files found at %s", path)
            if task_id:
                await task_queue.fail_task(task_id, f"No .md files found at {path}")
            return stats

        embed_batch_size = 16

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8")
                if not content.strip():
                    stats["skipped"] += 1
                    continue

                # 去重检查：基于 source_path
                source_path_str = str(md_file)
                exists = await postgres_tool.query(
                    "SELECT 1 FROM documents WHERE metadata->>'source_path' = $1",
                    source_path_str,
                )
                if exists:
                    logger.info("[Ingest] Skip duplicate | %s", md_file.name)
                    stats["skipped"] += 1
                    continue

                # Chunking
                chunks = chunk_markdown(content)
                if not chunks:
                    stats["skipped"] += 1
                    continue

                # 创建 document 记录
                doc_id = str(uuid_mod.uuid4())
                file_name = md_file.stem
                await postgres_tool.execute(
                    """
                    INSERT INTO documents (id, market, symbol, company, year,
                                           document_type, status, parser,
                                           chunk_count, metadata)
                    VALUES ($1, 'cn', $2, '', 0, 'markdown', 'indexing',
                            'direct', $3, $4::jsonb)
                    """,
                    doc_id, file_name, len(chunks),
                    json.dumps({"source_path": source_path_str, "ingest": "manual"}),
                )

                # Embedding（分批）
                all_vectors: list[list[float]] = []
                for batch_start in range(0, len(chunks), embed_batch_size):
                    batch = chunks[batch_start:batch_start + embed_batch_size]
                    texts = [c["content"][:2000] for c in batch]
                    vectors = await embedding_tool.embed(texts)
                    all_vectors.extend(vectors)

                # 写入 Qdrant + PostgreSQL chunks
                points = []
                for i, (chunk, vector) in enumerate(zip(chunks, all_vectors)):
                    point_id = str(uuid_mod.uuid4())
                    points.append({
                        "id": point_id,
                        "vector": vector,
                        "payload": {
                            "content": chunk["content"],
                            "heading": chunk.get("heading", ""),
                            "symbol": file_name,
                            "market": "cn",
                            "document_type": "markdown",
                            "document_id": doc_id,
                            "chunk_index": i,
                            "source_path": source_path_str,
                        },
                    })
                    await postgres_tool.execute(
                        """
                        INSERT INTO chunks (document_id, chunk_index, content,
                                            heading, collection_name, qdrant_point_id)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (document_id, chunk_index) DO NOTHING
                        """,
                        doc_id, i, chunk["content"],
                        chunk.get("heading", ""), collection, point_id,
                    )

                # Upsert Qdrant
                for batch_start in range(0, len(points), 100):
                    batch = points[batch_start:batch_start + 100]
                    await qdrant_tool.upsert(collection, batch)

                # 更新文档状态
                await postgres_tool.execute(
                    "UPDATE documents SET status = 'indexed' WHERE id = $1",
                    doc_id,
                )

                stats["added"] += 1
                logger.info(
                    "[Ingest] Processed | %s | chunks=%d", md_file.name, len(chunks)
                )
                if task_id:
                    await task_queue.update_progress(
                        task_id,
                        current_item=stats["added"] + stats["skipped"],
                        stage="embedding",
                        current_name=md_file.name,
                    )

            except Exception as e:
                logger.error("[Ingest] File failed | %s | %s", md_file, e)
                stats["skipped"] += 1
                if task_id:
                    await task_queue.update_progress(
                        task_id,
                        current_item=stats["added"] + stats["skipped"],
                        stage="failed_file",
                        current_name=md_file.name,
                    )

        logger.info(
            "[Ingest] Complete | found=%d added=%d skipped=%d | collection=%s",
            stats["found"], stats["added"], stats["skipped"], collection,
        )

        # 更新任务标题包含最终统计
        if task_id:
            await postgres_tool.execute(
                "UPDATE tasks SET title = $1 WHERE id = $2",
                f"文档导入 {path} (found={stats['found']}, added={stats['added']}, skipped={stats['skipped']})",
                task_id,
            )
            await task_queue.complete_task(task_id)

    except Exception as e:
        logger.error("[Ingest] Fatal error: %s", e)
        if task_id:
            await task_queue.fail_task(task_id, str(e))

    return stats


@router.post("/ingest")
async def trigger_ingest(req: IngestRequest):
    """手动导入 MD 文件并执行处理管线（异步执行，立即返回）"""
    # 基本路径验证
    target = Path(req.path)
    if not target.exists():
        raise HTTPException(status_code=400, detail=f"路径不存在：{req.path}")

    # 只接受目录路径
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="请选择目录，而不是单个文件")

    # 快速检测是否存在 .md 文件（避免大目录全量递归扫描）
    file_count = 0
    for _ in target.rglob("*.md"):
        file_count += 1
        if file_count >= 9999:
            break

    if file_count == 0:
        raise HTTPException(status_code=400, detail=f"目录下无 .md 文件：{req.path}")

    # 创建任务队列记录，供「处理详情」页展示进度
    task_id = await task_queue.create_task(
        task_type="doc_pipeline",
        title=f"文档导入 {req.path} ({file_count} files)",
        params={"path": req.path, "collection": req.collection},
        total_items=file_count,
        created_by="api",
    )
    asyncio.create_task(_run_ingest(req.path, req.collection, task_id))
    count_label = f"{file_count}+" if file_count >= 9999 else str(file_count)
    return {
        "status": "accepted",
        "message": f"导入任务已启动（{count_label} 个文件 → {req.collection}）",
        "found": file_count,
        "collection": req.collection,
        "task_id": task_id,
    }
