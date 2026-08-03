"""Skill Registry - Skill 注册、发现与调用"""

import logging
from typing import Any

from skills.base_skill import BaseSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Skill 注册表（单例）"""

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """注册 Skill"""
        if skill.name in self._skills:
            logger.warning("Skill '%s' already registered, overwriting", skill.name)
        self._skills[skill.name] = skill
        logger.info("Registered skill: %s v%s", skill.name, skill.version)

    def unregister(self, name: str) -> None:
        """注销 Skill"""
        self._skills.pop(name, None)

    def get(self, name: str) -> BaseSkill | None:
        """获取 Skill 实例"""
        return self._skills.get(name)

    def list_all(self) -> list[dict[str, str]]:
        """列出所有已注册 Skill"""
        return [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "tags": s.tags,
            }
            for s in self._skills.values()
        ]

    def find_by_tag(self, tag: str) -> list[BaseSkill]:
        """按标签搜索 Skill"""
        return [s for s in self._skills.values() if tag in s.tags]

    async def execute(self, name: str, **kwargs) -> dict[str, Any]:
        """按名称执行 Skill"""
        skill = self._skills.get(name)
        if skill is None:
            return {"success": False, "error": f"Skill '{name}' not found"}

        errors = skill.validate_params(**kwargs)
        if errors:
            return {"success": False, "error": "; ".join(errors)}

        try:
            return await skill.execute(**kwargs)
        except Exception as e:
            logger.exception("Skill '%s' execution failed", name)
            return {"success": False, "error": str(e)}


# 全局单例
_registry = SkillRegistry()


def get_skill(name: str) -> BaseSkill | None:
    """获取 Skill"""
    return _registry.get(name)


def list_skills() -> list[dict[str, str]]:
    """列出所有 Skill"""
    return _registry.list_all()


def register_skill(skill: BaseSkill) -> None:
    """注册 Skill"""
    _registry.register(skill)


def get_registry() -> SkillRegistry:
    """获取全局 Registry"""
    return _registry
