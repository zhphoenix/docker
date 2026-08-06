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

logger = logging.getLogger(__name__)

# 内存缓存：{调用名: 内容}
_store: dict[str, str] = {}
_loaded = False


def _make_key(agent_id: str, name: str) -> str:
    """DB 行 → 调用名（与 scripts/migrate_prompts_to_db.py 的映射互逆）"""
    return name if agent_id == "common" else f"{agent_id}/{name}"


async def load_all_from_db() -> int:
    """从 agent_prompts 表加载全部生效 Prompt 到内存，返回加载条数"""
    global _store, _loaded
    from tools.postgres import postgres_tool

    rows = await postgres_tool.query(
        "SELECT agent_id, name, content FROM agent_prompts WHERE is_active = true"
    )
    new_store: dict[str, str] = {}
    for r in rows:
        key = _make_key(r["agent_id"], r["name"])
        new_store[key] = r["content"]
    _store = new_store
    _loaded = True
    logger.info("Prompt Hub loaded %d prompts from DB", len(_store))
    return len(_store)


async def refresh_prompt(agent_id: str, name: str, content: str | None = None) -> None:
    """刷新单个 Prompt 到内存（content 为 None 时从 DB 读取）"""
    global _store
    key = _make_key(agent_id, name)
    if content is not None:
        _store[key] = content
        return
    from tools.postgres import postgres_tool

    rows = await postgres_tool.query(
        "SELECT content FROM agent_prompts "
        "WHERE agent_id=$1 AND name=$2 AND is_active=true "
        "ORDER BY version DESC LIMIT 1",
        agent_id, name,
    )
    if rows:
        _store[key] = rows[0]["content"]
    else:
        _store.pop(key, None)


def invalidate(agent_id: str, name: str) -> None:
    """从内存缓存移除该 Prompt（下次 load 需重新加载）"""
    _store.pop(_make_key(agent_id, name), None)


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