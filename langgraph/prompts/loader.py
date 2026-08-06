"""Prompt Hub - 从 agent_prompts 表加载 Prompt 模板（DB 为唯一事实源）

设计:
    - 启动时通过 load_all_from_db() 将全部生效 prompt 载入进程内 dict。
    - load_prompt() 为纯同步读取（graph 节点在 async 上下文调用，避免嵌套事件循环）。
    - DB 编辑后通过 refresh_prompt() / invalidate() 更新内存缓存。
    - 未找到时抛 FileNotFoundError（reason.py 等依赖该异常做回退）。

键映射:
    - DB 行 (agent_id=chat, name=system)  → 调用名 "chat/system"
    - DB 行 (agent_id=common, name=reason) → 调用名 "reason"
"""

import logging
import random
from collections import defaultdict
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# 内存缓存：{调用名: 内容}（单版本 / 多版本的默认选中版本）
_store: dict[str, str] = {}
# A/B 分流池：{调用名: [{"version": int, "content": str, "weight": int}]}
# 仅当同一 (agent_id, name) 存在多个 is_active=true 且 traffic_weight>0 的版本时填充
_variant_pool: dict[str, list[dict]] = {}
# 当前运行命中 variant：{调用名: {"version": int, "content": str}} —— 用于埋点打标
_variant_ctx: ContextVar[dict] = ContextVar("prompt_variant", default={})
_loaded = False


def _make_key(agent_id: str, name: str) -> str:
    """DB 行 → 调用名（与 scripts/migrate_prompts_to_db.py 的映射互逆）"""
    return name if agent_id == "common" else f"{agent_id}/{name}"


def _weighted_choice(variants: list[dict]) -> dict:
    """按 traffic_weight 概率随机选择一个 variant"""
    total = sum(v["weight"] for v in variants)
    r = random.uniform(0, total)
    upto = 0.0
    for v in variants:
        upto += v["weight"]
        if upto >= r:
            return v
    return variants[-1]


def get_resolved_variants() -> dict:
    """返回当前运行（context）内命中的全部 variant：{调用名: version}，未命中返回 {}"""
    return dict(_variant_ctx.get())


def reset_variant_context() -> None:
    """清空当前运行（context）的 variant 打标"""
    _variant_ctx.set({})

def variant_label() -> str | None:
    """将当前命中的第一个 variant 格式化为对比标签（如 'v2'），未命中返回 None"""
    resolved = _variant_ctx.get()
    if not resolved:
        return None
    first = next(iter(resolved.values()))
    version = first.get("version") if isinstance(first, dict) else first
    return f"v{version}"


async def load_all_from_db() -> int:
    """从 agent_prompts 表加载全部生效 Prompt 到内存，返回加载条数"""
    global _store, _variant_pool, _loaded
    from tools.postgres import postgres_tool

    rows = await postgres_tool.query(
        "SELECT agent_id, name, content, version, traffic_weight "
        "FROM agent_prompts WHERE is_active = true"
    )
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        key = _make_key(r["agent_id"], r["name"])
        groups[key].append(
            {
                "version": int(r.get("version") or 1),
                "content": r["content"],
                "weight": int(r.get("traffic_weight") or 0),
            }
        )

    new_store: dict[str, str] = {}
    new_pool: dict[str, list[dict]] = {}
    for key, variants in groups.items():
        pool = [v for v in variants if v["weight"] > 0]
        if len(variants) > 1 and len(pool) > 1:
            # A/B：多个生效版本且都有权重 → 加入分流池，默认选中最高权重版本
            new_pool[key] = pool
            new_store[key] = max(pool, key=lambda v: v["weight"])["content"]
        else:
            # 单版本或无人参与分流 → 取最新版本
            new_store[key] = max(variants, key=lambda v: v["version"])["content"]

    _store = new_store
    _variant_pool = new_pool
    _loaded = True
    logger.info(
        "Prompt Hub loaded %d prompts (incl. %d A/B pools) from DB",
        len(_store),
        len(_variant_pool),
    )
    return len(_store)


async def refresh_prompt(agent_id: str, name: str, content: str | None = None) -> None:
    """刷新单个 Prompt 到内存（content 为 None 时从 DB 读取）"""
    global _store, _variant_pool
    key = _make_key(agent_id, name)
    if content is not None:
        _store[key] = content
        return
    from tools.postgres import postgres_tool

    rows = await postgres_tool.query(
        "SELECT content, version, traffic_weight FROM agent_prompts "
        "WHERE agent_id=$1 AND name=$2 AND is_active=true",
        agent_id, name,
    )
    _variant_pool.pop(key, None)
    if not rows:
        _store.pop(key, None)
        return
    variants = [
        {
            "version": int(r.get("version") or 1),
            "content": r["content"],
            "weight": int(r.get("traffic_weight") or 0),
        }
        for r in rows
    ]
    pool = [v for v in variants if v["weight"] > 0]
    if len(variants) > 1 and len(pool) > 1:
        _variant_pool[key] = pool
        _store[key] = max(pool, key=lambda v: v["weight"])["content"]
    else:
        _store[key] = max(variants, key=lambda v: v["version"])["content"]


def invalidate(agent_id: str, name: str) -> None:
    """从内存缓存移除该 Prompt（下次 load 需重新加载）"""
    key = _make_key(agent_id, name)
    _store.pop(key, None)
    _variant_pool.pop(key, None)


def get_prompt(name: str) -> str | None:
    """获取原始 Prompt 内容（不做变量替换），未找到返回 None"""
    return _store.get(name)


def load_prompt(name: str, **kwargs) -> str:
    """加载 Prompt 模板

    Args:
        name: Prompt 调用名，如 "planner"、"chat/system"、"knowledge/entity_extraction"
        **kwargs: 模板变量替换，如 question="...", context="..."

    Returns:
        替换变量后的 Prompt 文本

    Raises:
        FileNotFoundError: 该 Prompt 在 DB 中不存在
    """
    content = None
    if name in _variant_pool:
        # A/B 分流：同一次运行内对同一 prompt 复用已命中的 variant
        ctx = _variant_ctx.get()
        entry = ctx.get(name)
        if entry is None:
            chosen = _weighted_choice(_variant_pool[name])
            new_ctx = dict(ctx)
            new_ctx[name] = {"version": chosen["version"]}
            _variant_ctx.set(new_ctx)
            entry = new_ctx[name]
        content = next(
            v["content"] for v in _variant_pool[name] if v["version"] == entry["version"]
        )
    else:
        content = _store.get(name)
    if content is None:
        raise FileNotFoundError(f"Prompt not found in DB: {name}")

    # 变量替换（使用安全替换，忽略缺失变量）
    if kwargs:
        for key, value in kwargs.items():
            content = content.replace("{" + key + "}", str(value))

    logger.debug("Loaded prompt '%s' (%d chars)", name, len(content))
    return content


def list_prompts(subdir: str = "") -> list[str]:
    """列出所有 Prompt 调用名（可选按目录前缀过滤）"""
    names = list(_store.keys())
    if subdir:
        prefix = f"{subdir}/"
        names = [n for n in names if n.startswith(prefix)]
    return sorted(names)