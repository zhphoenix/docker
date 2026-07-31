"""Node 2: Entity Extractor - 实体提取

并发从每个 chunk 提取实体（Semaphore 限流），内存去重。
"""

import asyncio
import json
import logging
import re

from tools.llm import llm_tool
from prompts.loader import load_prompt
from config.policy_loader import get_policy

logger = logging.getLogger(__name__)


async def entity_extractor(state: dict) -> dict:
    """实体提取节点

    对每个 chunk 并发调用 LLM 提取实体，
    使用 Semaphore 限制并发（尊重 LLM rate limit）。
    """
    chunks = state.get("chunks", [])
    errors = list(state.get("errors", []))

    if not chunks:
        errors.append("EntityExtractor: no chunks to process")
        return {"entities": [], "errors": errors}

    max_concurrent = get_policy("knowledge.extraction.max_concurrent_llm", 4)
    chunk_max_chars = get_policy("knowledge.extraction.chunk_max_chars", 3000)
    sem = asyncio.Semaphore(max_concurrent)

    prompt_template = load_prompt("knowledge/entity_extraction")

    async def extract_from_chunk(chunk: dict) -> list[dict]:
        """从单个 chunk 提取实体"""
        async with sem:
            content = chunk["content"][:chunk_max_chars]
            prompt = prompt_template.replace("{content}", content)

            try:
                result = await llm_tool.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                text = result["choices"][0]["message"]["content"]
                return _parse_entities(text)
            except Exception as e:
                logger.warning(
                    "Entity extraction failed for chunk %d: %s",
                    chunk.get("chunk_index", -1), e,
                )
                return []

    # 并发提取
    tasks = [extract_from_chunk(c) for c in chunks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 扁平化 + 去重 by (name.lower(), entity_type)
    all_entities: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for r in results:
        if isinstance(r, Exception):
            errors.append(f"EntityExtractor: chunk error: {r}")
            continue
        for e in r:
            key = (e.get("name", "").lower().strip(), e.get("entity_type", ""))
            if key[0] and key not in seen:
                seen.add(key)
                all_entities.append(e)

    logger.info("EntityExtractor: %d entities from %d chunks", len(all_entities), len(chunks))
    return {"entities": all_entities, "errors": errors}


def _parse_entities(text: str) -> list[dict]:
    """从 LLM 输出中解析实体 JSON

    支持 markdown code block 包裹和纯 JSON。
    """
    # 尝试提取 ```json ... ``` 块
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        text = match.group(1)

    # 尝试找到 JSON 数组
    text = text.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        text = text[start:end + 1]

    try:
        entities = json.loads(text)
        if not isinstance(entities, list):
            return []

        # 校验必填字段
        valid = []
        for e in entities:
            if isinstance(e, dict) and e.get("name") and e.get("entity_type"):
                valid.append({
                    "name": e["name"].strip(),
                    "entity_type": e["entity_type"].strip(),
                    "description": e.get("description", ""),
                    "aliases": e.get("aliases", []),
                    "properties": e.get("properties", {}),
                })
        return valid
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse entity JSON: %s", text[:200])
        return []
