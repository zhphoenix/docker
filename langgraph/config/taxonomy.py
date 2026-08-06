"""Taxonomy 加载器 - 从 specs/ontology.yaml 读取统一类型枚举

KOC-A2 规定实体类型合法性以 taxonomy.entity_types 为权威来源。
本模块提供带缓存的 ontology.yaml 读取，避免各节点重复硬编码白名单。

权威来源：specs/ontology.yaml（唯一权威定义，见该文件头部注释）。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# 定位 specs/ontology.yaml：从 langgraph 仓库根（含 config/ 的父目录）向上找 ai-platform/specs
_LANGGRAPH_ROOT = Path(__file__).resolve().parent.parent
_SPECS_CANDIDATES = [
    _LANGGRAPH_ROOT.parent / "specs" / "ontology.yaml",  # ai-platform/specs/ontology.yaml
]

_cache: dict[str, Any] = {}
_mtime: float = 0


def _resolve_ontology_path() -> Path:
    """解析 ontology.yaml 绝对路径（按候选顺序查找第一个存在者）"""
    for cand in _SPECS_CANDIDATES:
        if cand.exists():
            return cand
    # 兜底：允许通过环境变量覆盖
    env = os.environ.get("ONTOLOGY_PATH")
    if env and Path(env).exists():
        return Path(env)
    return _SPECS_CANDIDATES[0]


def load_taxonomy() -> dict[str, Any]:
    """读取 ontology.yaml 全部内容（带 mtime 缓存，文件变更自动重载）

    Returns:
        ontology.yaml 的 dict；文件缺失或解析失败返回 {}
    """
    global _cache, _mtime
    path = _resolve_ontology_path()
    if not path.exists():
        logger.warning("Taxonomy: ontology.yaml not found at %s, using empty", path)
        return {}
    try:
        mtime = path.stat().st_mtime
        if mtime != _mtime or not _cache:
            with open(path, "r", encoding="utf-8") as f:
                _cache = yaml.safe_load(f) or {}
            _mtime = mtime
            logger.debug("Taxonomy loaded from %s", path)
        return _cache
    except Exception as e:  # noqa: BLE001
        logger.warning("Taxonomy: load failed: %s", e)
        return {}


def get_entity_types() -> set[str]:
    """返回合法实体类型 id 集合（taxonomy.entity_types 的 id 字段）"""
    tax = load_taxonomy()
    return {item.get("id") for item in tax.get("entity_types", []) if item.get("id")}


def get_relation_types() -> set[str]:
    """返回合法关系类型 id 集合（taxonomy.relation_types 的 id/canonical 字段）"""
    tax = load_taxonomy()
    return {
        item.get("id") for item in tax.get("relation_types", [])
        if item.get("id")
    }