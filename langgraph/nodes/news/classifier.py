"""Node 3: News Classifier — 新闻分类 + 重要性评分

职责：
- 调用 LLM 对每篇文章进行分类（macro/stock/company/geopolitics/policy/technology）
- 评估重要性分数（0~1）
- 标记市场/行业关联

使用 prompts/news/classification.md 模板。
"""

import asyncio
import logging

from tools.llm import llm_tool
from prompts.loader import load_prompt
from config.policy_loader import get_policy
from nodes.news.utils import extract_json_array

logger = logging.getLogger(__name__)

# 合法分类（对应 ontology.yaml news_category）
VALID_CATEGORIES = {"macro", "stock", "company", "geopolitics", "policy", "technology"}

# 单批次最大文章数（防止 LLM 过载）
MAX_BATCH_SIZE = 50


def _score_to_tier(score: float) -> int:
    """DLM 分级策略：根据 importance_score 映射 Tier

    Tier 1: 永久保存 + 进入 Knowledge Graph（美联储/政策/战争/并购/财报/技术突破）
    Tier 2: 长期保存 3-5 年（公司新闻/行业新闻/分析文章）
    Tier 3: 短期保存 30-90 天（市场快讯/重复报道/转载）
    """
    if score >= 0.8:
        return 1
    if score >= 0.5:
        return 2
    return 3


async def news_classifier(state: dict) -> dict:
    """新闻分类节点

    输入: unique_articles
    输出: classified_articles（含 category, importance, market, sector）
    """
    articles = state.get("unique_articles", [])
    new_errors: list[str] = []

    if not articles:
        return {"classified_articles": [], "errors": new_errors}

    # S-4: 批量大小限制
    if len(articles) > MAX_BATCH_SIZE:
        logger.warning("Classifier: truncating %d articles to %d", len(articles), MAX_BATCH_SIZE)
        articles = articles[:MAX_BATCH_SIZE]

    max_concurrent = get_policy("news.classification.max_concurrent_llm", 3)
    sem = asyncio.Semaphore(max_concurrent)
    prompt_template = load_prompt("news/classification")

    async def classify_one(article: dict) -> dict:
        """对单篇文章进行分类"""
        async with sem:
            title = article.get("title", "")
            content = article.get("content", "")[:2000]
            prompt = prompt_template.replace("{title}", title).replace("{content}", content)

            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "请对这篇新闻进行分类和重要性评估。"},
            ]

            try:
                result = await llm_tool.chat(messages, temperature=0.2, max_tokens=512)
                response = result["choices"][0]["message"]["content"]
                parsed = extract_json_array(response)
                if parsed:
                    info = parsed[0] if isinstance(parsed, list) else parsed
                    category = info.get("category", "macro")
                    if category not in VALID_CATEGORIES:
                        category = "macro"
                    article["category"] = category
                    article["importance"] = float(info.get("importance", 0.5))
                    article["market"] = info.get("market", [])
                    article["sector"] = info.get("sector", [])
                else:
                    article["category"] = "macro"
                    article["importance"] = 0.5
                    article["market"] = []
                    article["sector"] = []
            except Exception as e:
                logger.warning("Classifier: LLM failed for '%s': %s", title[:50], e)
                article["category"] = "macro"
                article["importance"] = 0.5
                article["market"] = []
                article["sector"] = []

            return article

    # 并发分类
    tasks = [classify_one(a) for a in articles]
    classified = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for i, r in enumerate(classified):
        if isinstance(r, Exception):
            new_errors.append(f"Classifier: article {i} failed: {r}")
            # 保留文章，使用默认分类
            articles[i]["category"] = "macro"
            articles[i]["importance"] = 0.5
            articles[i]["market"] = []
            articles[i]["sector"] = []
            results.append(articles[i])
        else:
            results.append(r)

    logger.info("Classifier: %d articles classified", len(results))

    # DLM Tier 分级：根据 importance 映射 tier
    for art in results:
        art["tier"] = _score_to_tier(art.get("importance", 0.5))

    # C-3 修复：重编号 article_idx 为 classified_articles 中的位置索引
    # 去重后原始 article_idx 已失效，下游节点(entity/event/publisher)依赖此索引
    for idx, art in enumerate(results):
        art["article_idx"] = idx

    return {"classified_articles": results, "errors": new_errors}
