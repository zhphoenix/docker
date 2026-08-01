"""Node 5: News Impact Analyzer — 投资影响分析

职责：
- 综合实体 + 事件信息，评估投资影响
- 对高重要性文章（importance >= 0.7）进行深度影响分析
- 输出结构化的影响评估（影响方向、程度、时间范围、受益/受损标的）

使用 prompts/news/impact_analysis.md 模板。
Fan-in 节点：等待 Entity Extractor 和 Event Extractor 都完成后执行。
"""

import asyncio
import json
import logging

from tools.llm import llm_tool
from prompts.loader import load_prompt
from config.policy_loader import get_policy
from news_agent.utils import extract_json_array

logger = logging.getLogger(__name__)

# 重要性阈值：只对高重要性文章做深度影响分析
IMPACT_ANALYSIS_THRESHOLD = 0.7


async def news_impact_analyzer(state: dict) -> dict:
    """投资影响分析节点

    输入: classified_articles, entities, events
    输出: impact_assessments
    """
    articles = state.get("classified_articles", [])
    entities = state.get("entities", [])
    events = state.get("events", [])
    new_errors: list[str] = []

    if not articles:
        return {"impact_assessments": [], "errors": new_errors}

    # 筛选需要深度分析的高重要性文章
    high_importance = [a for a in articles if a.get("importance", 0) >= IMPACT_ANALYSIS_THRESHOLD]

    if not high_importance:
        logger.info("ImpactAnalyzer: no high-importance articles, skipping deep analysis")
        # 为所有事件生成简单影响评估
        simple_assessments = []
        for evt in events:
            simple_assessments.append({
                "source": "event",
                "title": evt.get("title", ""),
                "impact_direction": evt.get("impact_direction", "neutral"),
                "impact_score": evt.get("impact_score", 0.0),
                "market": evt.get("market", []),
                "sector": evt.get("sector", []),
                "entities": evt.get("entities", []),
            })
        return {"impact_assessments": simple_assessments, "errors": new_errors}

    max_concurrent = get_policy("news.impact.max_concurrent_llm", 2)
    sem = asyncio.Semaphore(max_concurrent)
    prompt_template = load_prompt("news/impact_analysis")

    # 构建实体/事件摘要供 prompt 使用
    entity_summary = json.dumps(
        [{"name": e["name"], "type": e["entity_type"]} for e in entities[:20]],
        ensure_ascii=False,
    )
    event_summary = json.dumps(
        [{"title": ev["title"], "type": ev["event_type"], "direction": ev["impact_direction"]}
         for ev in events[:10]],
        ensure_ascii=False,
    )

    async def analyze_one(article: dict) -> list[dict]:
        """对单篇高重要性文章进行影响分析"""
        async with sem:
            title = article.get("title", "")
            content = article.get("content", "")[:2500]

            prompt = (
                prompt_template
                .replace("{title}", title)
                .replace("{content}", content)
                .replace("{entities}", entity_summary)
                .replace("{events}", event_summary)
            )

            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "请分析这篇新闻的投资影响。"},
            ]

            try:
                result = await llm_tool.chat(messages, temperature=0.3, max_tokens=1024)
                response = result["choices"][0]["message"]["content"]

                assessments_raw = extract_json_array(response)
                assessments = []
                for a in assessments_raw:
                    if not isinstance(a, dict):
                        continue
                    assessments.append({
                        "source": "article",
                        "article_title": title,
                        "target_entity": a.get("target_entity", ""),
                        "impact_direction": a.get("impact_direction", "neutral"),
                        "impact_score": float(a.get("impact_score", 0.0)),
                        "time_horizon": a.get("time_horizon", "medium"),
                        "reasoning": a.get("reasoning", ""),
                        "market": a.get("market", []),
                        "sector": a.get("sector", []),
                    })
                return assessments

            except Exception as e:
                logger.warning("ImpactAnalyzer: failed for '%s': %s", title[:50], e)
                return []

    # 并发分析
    tasks = [analyze_one(a) for a in high_importance]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_assessments: list[dict] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            new_errors.append(f"ImpactAnalyzer: article {i} failed: {r}")
        else:
            all_assessments.extend(r)

    # 补充事件级简单评估
    for evt in events:
        all_assessments.append({
            "source": "event",
            "title": evt.get("title", ""),
            "impact_direction": evt.get("impact_direction", "neutral"),
            "impact_score": evt.get("impact_score", 0.0),
            "market": evt.get("market", []),
            "sector": evt.get("sector", []),
            "entities": evt.get("entities", []),
        })

    logger.info("ImpactAnalyzer: %d assessments generated", len(all_assessments))
    return {"impact_assessments": all_assessments, "errors": new_errors}
