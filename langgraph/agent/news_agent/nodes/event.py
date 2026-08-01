"""Node 4b: News Event Extractor — 新闻事件抽取

职责：
- 从分类后的文章中提取结构化事件
- 事件类型引用 ontology.yaml 9 种 Event Types
- 评估事件影响方向（positive/negative/neutral）
- 并发处理（与 Entity Extractor 并行执行）

使用 prompts/news/event_extraction.md 模板。
"""

import asyncio
import logging

from tools.llm import llm_tool
from prompts.loader import load_prompt
from config.policy_loader import get_policy
from news_agent.utils import extract_json_array

logger = logging.getLogger(__name__)

# ontology.yaml 9 种事件类型
VALID_EVENT_TYPES = {
    "earnings", "regulation", "merger", "acquisition",
    "product_launch", "macro_policy", "geopolitical",
    "supply_chain", "technology",
}

VALID_DIRECTIONS = {"positive", "negative", "neutral"}


async def news_event_extractor(state: dict) -> dict:
    """新闻事件抽取节点

    输入: classified_articles
    输出: events（含 event_type, impact_direction, entities 关联）
    """
    articles = state.get("classified_articles", [])
    new_errors: list[str] = []

    if not articles:
        return {"events": [], "errors": new_errors}

    max_concurrent = get_policy("news.extraction.max_concurrent_llm", 4)
    chunk_max_chars = get_policy("news.extraction.article_max_chars", 3000)
    sem = asyncio.Semaphore(max_concurrent)

    prompt_template = load_prompt("news/event_extraction")

    async def extract_from_article(article: dict) -> list[dict]:
        """从单篇文章提取事件"""
        async with sem:
            title = article.get("title", "")
            content = article.get("content", "")[:chunk_max_chars]
            article_id = article.get("article_idx", 0)

            prompt = prompt_template.replace("{title}", title).replace("{content}", content)

            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "请提取这篇新闻中的事件。"},
            ]

            try:
                result = await llm_tool.chat(messages, temperature=0.2, max_tokens=2048)
                response = result["choices"][0]["message"]["content"]

                events_raw = extract_json_array(response)
                events = []

                for evt in events_raw:
                    if not isinstance(evt, dict):
                        continue
                    evt_title = evt.get("title", "").strip()
                    event_type = evt.get("event_type", "")
                    if not evt_title:
                        continue
                    if event_type not in VALID_EVENT_TYPES:
                        event_type = "macro_policy"  # 中性默认值

                    direction = evt.get("impact_direction", "neutral")
                    if direction not in VALID_DIRECTIONS:
                        direction = "neutral"

                    events.append({
                        "title": evt_title,
                        "event_type": event_type,
                        "summary": evt.get("summary", ""),
                        "event_time": evt.get("event_time", ""),
                        "impact_direction": direction,
                        "impact_score": float(evt.get("impact_score", 0.0)),
                        "market": evt.get("market", []),
                        "sector": evt.get("sector", []),
                        "entities": evt.get("entities", []),
                        "confidence": float(evt.get("confidence", 0.8)),
                        "article_idx": article_id,
                    })

                return events

            except Exception as e:
                logger.warning("EventExtractor: failed for '%s': %s", title[:50], e)
                return []

    # 并发提取
    tasks = [extract_from_article(a) for a in articles]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_events: list[dict] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            new_errors.append(f"EventExtractor: article {i} failed: {r}")
        else:
            all_events.extend(r)

    logger.info("EventExtractor: %d events from %d articles", len(all_events), len(articles))
    return {"events": all_events, "errors": new_errors}
