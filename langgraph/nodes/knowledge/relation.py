"""Node 3: Relation Extractor - 关系提取

基于已识别实体 + 原文，提取实体间关系。
"""

import asyncio
import json
import logging
import re

from tools.llm import llm_tool
from prompts.loader import load_prompt
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)


# 合法的关系类型白名单（与 specs/ontology.yaml / AGE VALID_EDGE_LABELS 对齐）
VALID_RELATION_TYPES = {
    "supplier", "customer", "competitor", "depends_on", "owns",
    "uses", "invests_in", "located_in", "impacts", "causes",
    "partner", "belongs_to",
}


async def relation_extractor(state: dict) -> dict:
    """关系提取节点

    将实体列表和 chunks 组合后调用 LLM 提取关系。
    对 chunks 分波处理避免上下文过长。
    """
    entities = state.get("entities", [])
    chunks = state.get("chunks", [])
    new_errors: list[str] = []

    if not entities or not chunks:
        new_errors.append("RelationExtractor: missing entities or chunks")
        return {"relations": [], "errors": new_errors}

    max_concurrent = get_policy("knowledge.extraction.max_concurrent_llm", 4)
    chunk_max_chars = get_policy("knowledge.extraction.chunk_max_chars", 3000)
    sem = asyncio.Semaphore(max_concurrent)

    # 构建实体名称列表（供 prompt 使用）
    entity_names = json.dumps(
        [{"name": e["name"], "type": e["entity_type"]} for e in entities],
        ensure_ascii=False,
    )

    prompt_template = load_prompt("kb/relation_extraction")
    # 预填实体列表
    prompt_base = prompt_template.replace("{entities}", entity_names)

    # 构建实体名称集合（用于校验）
    valid_names = {e["name"].lower() for e in entities}

    async def extract_from_chunk(chunk: dict) -> list[dict]:
        """从单个 chunk 提取关系"""
        async with sem:
            content = chunk["content"][:chunk_max_chars]
            prompt = prompt_base.replace("{content}", content)

            try:
                result = await llm_tool.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                text = result["choices"][0]["message"]["content"]
                return _parse_relations(text, valid_names)
            except Exception as e:
                logger.warning(
                    "Relation extraction failed for chunk %d: %s",
                    chunk.get("chunk_index", -1), e,
                )
                return []

    # 并发提取
    tasks = [extract_from_chunk(c) for c in chunks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 扁平化 + 去重 by (source, relation_type, target)
    all_relations: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for r in results:
        if isinstance(r, Exception):
            new_errors.append(f"RelationExtractor: chunk error: {r}")
            continue
        for rel in r:
            key = (
                rel["source"].lower(),
                rel["relation_type"],
                rel["target"].lower(),
            )
            if key not in seen:
                seen.add(key)
                all_relations.append(rel)

    logger.info("RelationExtractor: %d relations from %d chunks", len(all_relations), len(chunks))
    return {"relations": all_relations, "errors": new_errors}


def _parse_relations(text: str, valid_names: set[str]) -> list[dict]:
    """从 LLM 输出中解析关系 JSON"""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        text = match.group(1)

    text = text.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        text = text[start:end + 1]

    try:
        relations = json.loads(text)
        if not isinstance(relations, list):
            return []

        valid = []
        for r in relations:
            if not isinstance(r, dict):
                continue
            source = r.get("source", "").strip()
            target = r.get("target", "").strip()
            rtype = r.get("relation_type", "").strip()

            # 校验：source/target 必须在已识别实体中
            if source and target and rtype:
                if source.lower() in valid_names and target.lower() in valid_names:
                    # 校验：relation_type 必须在白名单内（过滤动词残留等非法值）
                    if rtype not in VALID_RELATION_TYPES:
                        logger.warning(
                            "RelationExtractor: skip invalid relation_type=%r (from %s → %s)",
                            rtype, source, target,
                        )
                        continue
                    valid.append({
                        "source": source,
                        "target": target,
                        "relation_type": rtype,
                        "confidence": r.get("confidence", 0.8),
                        "properties": r.get("properties", {}),
                    })
        return valid
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse relation JSON: %s", text[:200])
        return []
