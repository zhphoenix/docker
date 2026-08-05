"""Graph Tools - 事件影响链 / 事件搜索（Apache AGE Cypher）

Tools:
  16. trace_event_impact — 事件影响链追踪
  17. search_event       — 事件搜索 + 影响实体

依赖: Apache AGE 图存储（不可用时返回错误提示）
"""

import json
import logging

from fastmcp import FastMCP

from server.storage.age import age_storage
from server.storage.postgres import pg_storage
from server.storage.qdrant import (qdrant_storage, COLLECTION_ENTITIES, COLLECTION_FACTS)
from server.llm import llm_client

logger = logging.getLogger(__name__)

# 向量证据相似度下限：低于该分数的检索结果不作为 LLM 推理证据，
# 防止无关概念（如消费股查询混入"光模块"）被 LLM 幻觉关联。
VECTOR_EVIDENCE_MIN_SCORE = 0.5


async def _resolve_entity_name_map(entity_ids: list[str]) -> dict[str, str]:
    """批量解析实体 id → 名称（按输入顺序）"""
    if not entity_ids:
        return {}
    rows = await pg_storage.get_entities_by_ids(entity_ids)
    by_id: dict[str, dict] = {str(r["id"]): r for r in rows}
    ordered: dict[str, str] = {}
    for eid in entity_ids:
        r = by_id.get(eid)
        ordered[eid] = r["name"] if r else eid
    return ordered


async def _resolve_entity_names(entity_ids: list[str]) -> list[str]:
    """解析实体 id 列表为名称列表（保序）"""
    mapping = await _resolve_entity_name_map(entity_ids)
    return [mapping[eid] for eid in entity_ids]


def register_graph_tools(mcp: FastMCP) -> None:
    """注册 Graph 相关 MCP Tools（AGE + PG 多跳 + GraphRAG）"""

    @mcp.tool()
    async def trace_event_impact(
        event: str, depth: int = 3, date_from: str = "", date_to: str = ""
    ) -> dict:
        """事件影响链追踪

        从事件节点出发，追踪其对实体网络的影响传播路径。
        Event → Companies → Suppliers → Industries → Market Impact

        需要 Apache AGE 图数据库支持。

        Args:
            event: 事件名称或关键词（如 "AI Chip Export Restriction"、"台积电地震"）
            depth: 影响链追踪深度（1-4，默认 3）
            date_from: 事件最早日期（含，ISO yyyy-MM-dd），空=不限
            date_to: 事件最晚日期（含，ISO yyyy-MM-dd），空=不限

        Returns:
            {event, direct_entities, impact_chain: [{entity, entity_id, entity_type}], total_impacted}
        """
        if not age_storage.available:
            return {
                "error": "Apache AGE not available. Event impact tracing requires graph database.",
                "hint": "Ensure AGE is initialized (postgres/init/08-age-init.sql)",
            }

        try:
            return await age_storage.trace_event_impact(
                event, depth, date_from=date_from, date_to=date_to
            )
        except Exception as e:
            return {"error": f"Event impact trace failed: {str(e)}"}

    @mcp.tool()
    async def search_event(query: str, event_type: str = "", limit: int = 10) -> dict:
        """搜索事件 + 影响实体

        在知识图谱中搜索事件节点，并返回每个事件影响的实体列表。

        需要 Apache AGE 图数据库支持。

        Args:
            query: 搜索关键词（匹配事件名称和描述）
            event_type: 事件类型过滤（earnings/regulation/merger/acquisition/product_launch/macro_policy/geopolitical/supply_chain/technology）
            limit: 返回数量上限（默认 10）

        Returns:
            {count, events: [{name, event_type, description, date, impacted_entities}]}
        """
        if not age_storage.available:
            return {
                "error": "Apache AGE not available. Event search requires graph database.",
                "hint": "Ensure AGE is initialized (postgres/init/08-age-init.sql)",
            }

        try:
            events = await age_storage.search_events(query, event_type, limit)
            return {"count": len(events), "events": events}
        except Exception as e:
            return {"error": f"Event search failed: {str(e)}"}

    @mcp.tool()
    async def query_company_relationship(
        source: str, target: str, max_depth: int = 4, limit: int = 5
    ) -> dict:
        """查询两公司间的多跳关系路径（PG 双向递归 CTE）

        返回 source→target 的最短路径及路径上的关系类型，用于揭示关联链路。

        Args:
            source: 起点公司名称（如 "NVIDIA"）
            target: 终点公司名称（如 "台积电"）
            max_depth: 最大路径深度（1-6，默认 4）
            limit: 返回路径数上限（默认 5）

        Returns:
            {source, target, paths: [{path: [实体名...], relations: [...类型], depth}]}
        """
        try:
            srcs = await pg_storage.find_entity_by_name(source, limit=1)
            tgts = await pg_storage.find_entity_by_name(target, limit=1)
            if not srcs:
                return {"error": f"Source entity '{source}' not found"}
            if not tgts:
                return {"error": f"Target entity '{target}' not found"}

            src_id = str(srcs[0]["id"])
            tgt_id = str(tgts[0]["id"])
            rows = await pg_storage.find_path_between(
                src_id, tgt_id, max_depth=max_depth, limit=limit
            )

            paths = []
            for r in rows:
                # 解析路径上的实体 id，补查出名称
                entity_ids = [str(x) for x in (r.get("path_entities") or [])]
                # 双向遍历：目标可能经反向边命中，要求路径包含目标即可
                if not entity_ids or tgt_id not in entity_ids:
                    continue
                names = await _resolve_entity_names(entity_ids)
                paths.append({
                    "path": names,
                    "depth": r.get("depth"),
                })

            return {
                "source": source,
                "target": target,
                "paths": paths,
                "total": len(paths),
            }
        except ValueError as e:
            return {"error": f"Invalid entity: {str(e)}"}
        except Exception as e:
            return {"error": f"Relationship query failed: {str(e)}"}

    @mcp.tool()
    async def find_related_companies(
        entity: str, depth: int = 2, relation_types: str = "", limit: int = 50
    ) -> dict:
        """多跳关联公司检索（CTE，深度≤3）

        从目标公司出发按关系类型多跳展开，返回关联公司及关系。

        Args:
            entity: 公司名称（如 "NVIDIA"）
            depth: 最大跳数（1-3，默认 2）
            relation_types: 逗号分隔的关系类型过滤（如 "supplier,customer,partner"），空=全部
            limit: 返回关联数量上限（默认 50）

        Returns:
            {entity, count, related: [{id, name, type, relation, confidence, depth}]}
        """
        try:
            ents = await pg_storage.find_entity_by_name(entity, limit=1)
            if not ents:
                return {"error": f"Entity '{entity}' not found"}

            eid = str(ents[0]["id"])
            rel_types = (
                [t.strip() for t in relation_types.split(",") if t.strip()]
                if relation_types else None
            )
            rows = await pg_storage.find_related_companies(
                eid, depth=depth, relation_types=rel_types, limit=limit
            )

            ids = list({str(x) for r in rows for x in (r.get("source_entity"), r.get("target_entity"))})
            id_to_name = await _resolve_entity_name_map(ids)

            related = []
            seen: set[str] = set()
            for r in rows:
                src = str(r["source_entity"])
                tgt = str(r["target_entity"])
                # 以目标侧实体为关联节点（起点除外）
                neighbor = tgt if tgt != eid else src
                if neighbor == eid or neighbor in seen:
                    continue
                name = id_to_name.get(neighbor, neighbor)
                if name in seen:
                    continue
                seen.add(name)
                seen.add(neighbor)
                related.append({
                    "id": neighbor,
                    "name": name,
                    "type": r.get("relation_type"),
                    "relation": r.get("relation_type"),
                    "confidence": r.get("confidence"),
                    "depth": r.get("depth"),
                })

            return {
                "entity": {"id": eid, "name": ents[0]["name"]},
                "count": len(related),
                "related": related,
            }
        except Exception as e:
            return {"error": f"Related companies query failed: {str(e)}"}

    @mcp.tool()
    async def graphrag_search(
        query: str, entity_name: str = "", limit: int = 10
    ) -> dict:
        """GraphRAG 增强检索：图遍历 + 向量检索 + LLM 融合推理

        在混合检索基础上叠加 LLM 推理，产出带引用的可解释答案。
        LLM 不可用时自动降级返回原始检索证据。

        Args:
            query: 自然语言问题（如 "台积电的主要客户有哪些？"）
            entity_name: 可选，锚定实体（如 "台积电"）
            limit: 每类证据条数上限（默认 10）

        Returns:
            {query, fusion: {summary, key_findings}, evidence: {graph, vector}, degraded}
        """
        try:
            entity_ids: list[str] = []
            graph_results = []
            if entity_name:
                ents = await pg_storage.find_entity_by_name(entity_name, limit=1)
                if ents:
                    entity_ids = [str(ents[0]["id"])]
                    graph_results = await pg_storage.get_entity_graph(entity_ids[0], depth=2)

            vec = await qdrant_storage.parallel_search(
                query,
                [COLLECTION_ENTITIES, COLLECTION_FACTS],
                top_k=limit,
                score_threshold=VECTOR_EVIDENCE_MIN_SCORE,
            )

            # 组装证据
            graph_evidence = [
                {
                    "source_entity": str(r["source_entity"]),
                    "target_entity": str(r["target_entity"]),
                    "relation_type": r["relation_type"],
                    "depth": r["depth"],
                }
                for r in graph_results
            ][:30]
            vector_evidence = []
            for ent in vec.get(COLLECTION_ENTITIES, []):
                if ent.get("score", 0.0) < VECTOR_EVIDENCE_MIN_SCORE:
                    continue  # 双保险：低相似度实体不作为证据
                p = ent.get("payload") or {}
                vector_evidence.append({
                    "kind": "entity", "name": p.get("name", ""),
                    "entity_type": p.get("entity_type", ""),
                    "description": (p.get("description") or "")[:600],
                })
            for fact in vec.get(COLLECTION_FACTS, []):
                if fact.get("score", 0.0) < VECTOR_EVIDENCE_MIN_SCORE:
                    continue  # 双保险：低相似度事实不作为证据
                p = fact.get("payload") or {}
                vector_evidence.append({
                    "kind": "fact",
                    "subject": p.get("subject_name", ""),
                    "predicate": p.get("predicate", ""),
                    "value": (p.get("object_value") or "")[:400],
                    "time_start": p.get("time_start", ""),
                })
            vector_evidence = vector_evidence[:30]

            graph_txt = "\n".join(
                f"- [{e['relation_type']}] {e['source_entity'][:8]} -> {e['target_entity'][:8]} (depth={e['depth']})"
                for e in graph_evidence
            ) or "(无图证据)"
            vec_txt = "\n".join(
                f"- ({e['kind']}) " + (
                    f"{e.get('name', '')}({e.get('entity_type', '')}): {e.get('description', '')}"
                    if e["kind"] == "entity"
                    else f"{e.get('subject', '')} - {e.get('predicate', '')}: {e.get('value', '')} @ {e.get('time_start', '')}"
                )
                for e in vector_evidence
            ) or "(无向量证据)"

            prompt = (
                "你是投资研究知识问答助手，基于以下证据回答用户问题。\n"
                "要求：\n"
                "1. 只能基于给出的证据推理，不得编造；证据不足时明确说明。\n"
                "2. 输出纯 JSON（不要 markdown 代码块）：{\"summary\": "
                "\"一段完整、连贯的中文答案\", \"key_findings\": [{\"finding\": "
                "\"结论要点\", \"cited_evidence\": [\"对应证据原文片段\"]}]}.\n\n"
                f"## 用户问题\n{query}\n\n"
                f"## 图证据（结构化关系）\n{graph_txt}\n\n"
                f"## 向量证据（实体/事实描述）\n{vec_txt}\n"
                "## 输出\n"
            )
            messages = [
                {"role": "system", "content": "你是严谨的投资知识图谱推理助手，支持证据引用，输出结构化 JSON。"},
                {"role": "user", "content": prompt},
            ]

            fusion = {"summary": "", "key_findings": []}
            degraded = True
            try:
                result = await llm_client.chat(messages, temperature=0.1)
                raw = (result.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
                if raw.startswith("```"):
                    raw = raw.strip("`").strip()
                    if raw.startswith("json"):
                        raw = raw[4:].strip()
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        fusion = {
                            "summary": str(parsed.get("summary", "")),
                            "key_findings": parsed.get("key_findings", []) or [],
                        }
                except Exception:
                    fusion = {"summary": raw, "key_findings": []}
                degraded = fusion["summary"] == ""
            except Exception as e:
                logger.warning("GraphRAG LLM fusion failed (degraded): %s", e)

            return {
                "query": query,
                "fusion": fusion,
                "entity_ids_used": entity_ids,
                "evidence": {"graph": graph_evidence, "vector": vector_evidence},
                "degraded": degraded,
            }
        except Exception as e:
            logger.exception("GraphRAG search failed")
            return {"error": f"GraphRAG search failed: {str(e)}"}
