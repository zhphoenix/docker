"""Node 4a: News Entity Extractor — 新闻实体识别

职责：
- 从分类后的文章中提取金融实体
- 实体类型引用 ontology.yaml 10 种 Entity Types
- 并发处理多篇文章（Semaphore 限流）
- 同时提取实体间关系

使用 prompts/news/entity_extraction.md 模板。
"""

import asyncio
import logging

from tools.llm import llm_tool
from prompts.loader import load_prompt
from config.policy_loader import get_policy
from nodes.news.utils import extract_json_array

logger = logging.getLogger(__name__)

# ontology.yaml 10 种实体类型
VALID_ENTITY_TYPES = {
    "Company", "Person", "Product", "Technology", "Industry",
    "Country", "Organization", "Event", "Metric", "Concept",
}

# ontology.yaml 10 种关系类型
VALID_RELATION_TYPES = {
    "supplier", "customer", "competitor", "depends_on", "owns",
    "uses", "invests_in", "located_in", "impacts", "causes",
}


async def news_entity_extractor(state: dict) -> dict:
    """新闻实体提取节点

    输入: classified_articles
    输出: entities, relations
    """
    articles = state.get("classified_articles", [])
    new_errors: list[str] = []

    if not articles:
        return {"entities": [], "relations": [], "errors": new_errors}

    max_concurrent = get_policy("news.extraction.max_concurrent_llm", 4)
    chunk_max_chars = get_policy("news.extraction.article_max_chars", 3000)
    sem = asyncio.Semaphore(max_concurrent)

    prompt_template = load_prompt("news/entity_extraction")

    async def extract_from_article(article: dict) -> tuple[list[dict], list[dict]]:
        """从单篇文章提取实体和关系"""
        async with sem:
            title = article.get("title", "")
            content = article.get("content", "")[:chunk_max_chars]
            article_id = article.get("article_idx", 0)

            prompt = prompt_template.replace("{title}", title).replace("{content}", content)

            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "请提取这篇新闻中的实体和关系。"},
            ]

            try:
                result = await llm_tool.chat(messages, temperature=0.2, max_tokens=2048)
                response = result["choices"][0]["message"]["content"]

                # 解析实体
                entities_raw = extract_json_array(response)
                entities = []
                relations = []

                for ent in entities_raw:
                    if not isinstance(ent, dict):
                        continue
                    name = ent.get("name", "").strip()
                    entity_type = ent.get("entity_type", "Concept")
                    if not name:
                        continue
                    if entity_type not in VALID_ENTITY_TYPES:
                        entity_type = "Concept"

                    entities.append({
                        "name": name,
                        "entity_type": entity_type,
                        "description": ent.get("description", ""),
                        "confidence": float(ent.get("confidence", 0.8)),
                        "article_idx": article_id,
                        "aliases": ent.get("aliases", []),
                    })

                    # 提取内嵌关系
                    for rel in ent.get("relations", []):
                        rel_type = rel.get("relation_type", "")
                        if rel_type in VALID_RELATION_TYPES and rel.get("target"):
                            relations.append({
                                "source_name": name,
                                "target_name": rel["target"],
                                "relation_type": rel_type,
                                "confidence": float(rel.get("confidence", 0.7)),
                                "article_idx": article_id,
                            })

                return entities, relations

            except Exception as e:
                logger.warning("EntityExtractor: failed for '%s': %s", title[:50], e)
                return [], []

    # 并发提取
    tasks = [extract_from_article(a) for a in articles]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_entities: list[dict] = []
    all_relations: list[dict] = []

    for i, r in enumerate(results):
        if isinstance(r, Exception):
            new_errors.append(f"EntityExtractor: article {i} failed: {r}")
        else:
            ents, rels = r
            all_entities.extend(ents)
            all_relations.extend(rels)

    # 内存去重（同名同类型实体合并）
    seen = set()
    unique_entities = []
    for ent in all_entities:
        key = (ent["name"].lower(), ent["entity_type"])
        if key not in seen:
            seen.add(key)
            unique_entities.append(ent)

    logger.info(
        "EntityExtractor: %d entities, %d relations from %d articles",
        len(unique_entities), len(all_relations), len(articles),
    )

    return {"entities": unique_entities, "relations": all_relations, "errors": new_errors}
