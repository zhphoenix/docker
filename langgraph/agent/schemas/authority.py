"""权威度映射 - providers.yaml source_provider → AuthorityLevel

复用 providers.yaml 中已有的 official + status 字段组合，
将数据源 ID 映射到权威度级别。
"""

from schemas.financial import AuthorityLevel

# providers.yaml source_provider (id) → authority level 映射
# 映射规则:
#   official=true  & status=verified  → very_high
#   official=true  & status=limited   → high
#   official=false & status=verified  → medium
#   其他                              → low
AUTHORITY_SOURCE_MAP: dict[str, str] = {
    # --- very_high: official=true & status=verified ---
    "cninfo": "very_high",
    "hkexnews": "very_high",
    "sec_edgar": "very_high",
    "qiushi": "very_high",
    "gov_cn": "very_high",
    "sse": "very_high",
    "szse": "very_high",
    "csrc": "very_high",
    "safe": "very_high",
    "csindex": "very_high",
    "xinhua": "very_high",
    "people_daily": "very_high",
    "sec_xbrl": "very_high",
    "fred": "very_high",

    # --- high: official=true & status=limited ---
    "reuters": "high",
    "nbs": "high",
    "pboc": "high",
    "chinabond": "high",
    "customs": "high",
    "cls": "high",
    "nyse": "high",
    "cboe": "high",
    "google_trends": "high",
    "reddit": "high",
    "stocktwits": "high",
    "oecd": "high",

    # --- medium: official=false & status=verified ---
    "akshare": "medium",
    "yfinance": "medium",
    "eastmoney_news": "medium",
    "sina_finance": "medium",
    "yahoo_news": "medium",
    "beike": "medium",

    # --- low: 其他 ---
    "_default": "medium",
}

# 权威度数值映射（用于比较）
AUTHORITY_ORDER: dict[str, int] = {
    "very_high": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def get_authority_level(source_provider: str) -> str:
    """获取数据源的权威度级别

    Args:
        source_provider: providers.yaml 中的数据源 ID

    Returns:
        权威度级别字符串 ("very_high" / "high" / "medium" / "low")
    """
    return AUTHORITY_SOURCE_MAP.get(source_provider, AUTHORITY_SOURCE_MAP["_default"])


def filter_by_authority(
    items: list[dict],
    min_authority: str,
    authority_key: str = "authority",
) -> list[dict]:
    """按权威度过滤结果列表

    Args:
        items: 含 authority 字段的结果列表
        min_authority: 最低权威度级别
        authority_key: authority 字段的 key 名

    Returns:
        过滤后的结果列表
    """
    min_level = AUTHORITY_ORDER.get(min_authority, 0)
    return [
        item
        for item in items
        if AUTHORITY_ORDER.get(item.get(authority_key, "medium"), 2) >= min_level
    ]
