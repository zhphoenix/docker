"""Node 4: Fact Extractor - 事实提取

提取结构化事实 (subject/predicate/object/time) + 证据。
"""

import asyncio
import json
import logging
import re

from tools.llm import llm_tool
from prompts.loader import load_prompt
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)


async def fact_extractor(state: dict) -> dict:
    """事实提取节点

    从 chunks 中提取结构化事实和证据引用。
    """
    entities = state.get("entities", [])
    chunks = state.get("chunks", [])
    new_errors: list[str] = []

    if not chunks:
        new_errors.append("FactExtractor: no chunks to process")
        return {"facts": [], "evidence": [], "errors": new_errors}

    max_concurrent = get_policy("knowledge.extraction.max_concurrent_llm", 4)
    chunk_max_chars = get_policy("knowledge.extraction.chunk_max_chars", 3000)
    sem = asyncio.Semaphore(max_concurrent)

    # 实体名称列表
    entity_names = json.dumps(
        [e["name"] for e in entities],
        ensure_ascii=False,
    )

    prompt_template = load_prompt("kb/fact_extraction")
    prompt_base = prompt_template.replace("{entities}", entity_names)

    # 实体名称集合（校验用）
    valid_names = {e["name"].lower() for e in entities}

    async def extract_from_chunk(chunk: dict) -> list[dict]:
        """从单个 chunk 提取事实"""
        async with sem:
            content = chunk["content"][:chunk_max_chars]
            prompt = prompt_base.replace("{content}", content)

            try:
                result = await llm_tool.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                text = result["choices"][0]["message"]["content"]
                return _parse_facts(text, valid_names, chunk)
            except Exception as e:
                logger.warning(
                    "Fact extraction failed for chunk %d: %s",
                    chunk.get("chunk_index", -1), e,
                )
                return []

    # 并发提取
    tasks = [extract_from_chunk(c) for c in chunks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 扁平化 + 分离 facts 和 evidence
    all_facts: list[dict] = []
    all_evidence: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for r in results:
        if isinstance(r, Exception):
            new_errors.append(f"FactExtractor: chunk error: {r}")
            continue
        for item in r:
            fact = item.get("fact", {})
            evidence = item.get("evidence", {})

            # 去重 by (subject, predicate, object_value str)
            key = (
                fact.get("subject", "").lower(),
                fact.get("predicate", "").lower(),
                str(fact.get("object_value", "")),
            )
            if key[0] and key[1] and key not in seen:
                seen.add(key)
                all_facts.append(fact)
                if evidence:
                    all_evidence.append(evidence)

    logger.info("FactExtractor: %d facts from %d chunks", len(all_facts), len(chunks))
    return {"facts": all_facts, "evidence": all_evidence, "errors": new_errors}


def _parse_facts(text: str, valid_names: set[str], chunk: dict) -> list[dict]:
    """从 LLM 输出中解析事实 JSON

    Returns:
        [{"fact": {...}, "evidence": {...}}, ...]
    """
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        text = match.group(1)

    text = text.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        text = text[start:end + 1]

    try:
        facts_raw = json.loads(text)
        if not isinstance(facts_raw, list):
            return []

        results = []
        for f in facts_raw:
            if not isinstance(f, dict):
                continue

            subject = f.get("subject", "").strip()
            predicate = f.get("predicate", "").strip()

            if not subject or not predicate:
                continue

            # 校验 subject 在已识别实体中
            if subject.lower() not in valid_names:
                continue

            fact = {
                "subject": subject,
                "predicate": predicate,
                "object_value": f.get("object_value", {}),
                "unit": f.get("unit"),
                "time_start": f.get("time_start"),
                "time_end": f.get("time_end"),
                "confidence": f.get("confidence", 0.8),
            }

            evidence = {}
            quote = f.get("evidence_quote", "")
            if quote:
                evidence = {
                    "location": f"chunk_{chunk.get('chunk_index', 0)}",
                    "quote": quote[:500],
                    "confidence": f.get("confidence", 0.8),
                }

            results.append({"fact": fact, "evidence": evidence})

        return results
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse fact JSON: %s", text[:200])
        return []
