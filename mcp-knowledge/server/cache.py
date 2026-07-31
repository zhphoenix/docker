"""TTL 缓存层 - 进程内热数据缓存

策略：
- get_entity / get_entity_graph: 缓存（实体变更频率低）
- get_company_profile / get_supply_chain: 缓存（聚合查询代价高）
- search_* / semantic_search: 不缓存（查询组合多）
- create_* / update_*: 触发失效
"""

import logging
from functools import wraps
from typing import Callable

from cachetools import TTLCache

from server.config import settings

logger = logging.getLogger(__name__)


class KnowledgeCache:
    """进程内 TTL 缓存"""

    def __init__(self):
        self._cache: TTLCache = TTLCache(
            maxsize=settings.CACHE_MAX_SIZE,
            ttl=settings.CACHE_TTL_SECONDS,
        )
        self._stats = {"hits": 0, "misses": 0}

    def cached(self, prefix: str, key_builder: Callable) -> Callable:
        """装饰器：自动缓存异步函数结果

        Args:
            prefix: 缓存 key 前缀（用于按类失效）
            key_builder: 从函数参数构建 cache key 的函数
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                if not settings.CACHE_ENABLED:
                    return await func(*args, **kwargs)

                cache_key = f"{prefix}:{key_builder(*args, **kwargs)}"

                # 快速路径（读）
                if cache_key in self._cache:
                    self._stats["hits"] += 1
                    return self._cache[cache_key]

                self._stats["misses"] += 1
                result = await func(*args, **kwargs)
                self._cache[cache_key] = result
                return result

            return wrapper
        return decorator

    def invalidate(self, prefix: str) -> int:
        """按前缀失效缓存（写操作后调用）

        Returns:
            失效的 key 数量
        """
        keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._cache[k]
        if keys_to_delete:
            logger.debug("Cache invalidated %d keys with prefix '%s'", len(keys_to_delete), prefix)
        return len(keys_to_delete)

    def invalidate_all(self) -> None:
        """清空全部缓存"""
        self._cache.clear()

    @property
    def stats(self) -> dict:
        """缓存统计"""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0.0
        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": round(hit_rate, 3),
            "size": len(self._cache),
        }


# 模块级单例
knowledge_cache = KnowledgeCache()
