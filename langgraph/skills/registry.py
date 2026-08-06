"""Skill Registry - Skill 注册、发现与调用"""

import logging
from typing import Any

from skills.base_skill import BaseSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Skill 注册表（单例）

    enabled 状态与已注册实例分离存储，避免修改 BaseSkill 接口。
    """

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}
        self._enabled: dict[str, bool] = {}

    def register(self, skill: BaseSkill) -> None:
        """注册 Skill（默认启用）"""
        if skill.name in self._skills:
            logger.warning("Skill '%s' already registered, overwriting", skill.name)
        self._skills[skill.name] = skill
        # 新注册默认启用；已存在则保留原状态
        self._enabled.setdefault(skill.name, True)
        logger.info("Registered skill: %s v%s", skill.name, skill.version)

    def unregister(self, name: str) -> None:
        """注销 Skill"""
        self._skills.pop(name, None)
        self._enabled.pop(name, None)

    def get(self, name: str) -> BaseSkill | None:
        """获取 Skill 实例"""
        return self._skills.get(name)

    def is_enabled(self, name: str) -> bool:
        """查询 Skill 是否启用"""
        return self._enabled.get(name, False)

    async def set_enabled(self, name: str, enabled: bool) -> bool:
        """启用/禁用 Skill（更新内存 + 持久化到 DB），返回是否成功"""
        if name not in self._skills:
            return False
        self._enabled[name] = enabled
        try:
            from tools.postgres import postgres_tool
            await postgres_tool.execute(
                "INSERT INTO agent_skills (name, enabled) VALUES ($1, $2) "
                "ON CONFLICT (name) DO UPDATE SET enabled=EXCLUDED.enabled, "
                "updated_at=NOW()",
                name,
                enabled,
            )
        except Exception as e:
            logger.warning("persist skill '%s' enabled=%s failed: %s", name, enabled, e)
        logger.info("Skill '%s' set enabled=%s", name, enabled)
        return True

    async def sync_from_db(self) -> None:
        """从 agent_skills 表加载各 Skill 的持久化启用状态（启动时调用）

        对 DB 中尚无记录的 Skill 以默认启用写入（seed），保持注册表与库一致。
        """
        try:
            from tools.postgres import postgres_tool
            rows = await postgres_tool.query("SELECT name, enabled FROM agent_skills")
            db_state = {r["name"]: bool(r["enabled"]) for r in rows}
            for name in list(self._skills.keys()):
                if name in db_state:
                    self._enabled[name] = db_state[name]
                else:
                    self._enabled.setdefault(name, True)
                    try:
                        await postgres_tool.execute(
                            "INSERT INTO agent_skills (name, enabled) VALUES ($1, $2) "
                            "ON CONFLICT (name) DO NOTHING",
                            name,
                            self._enabled[name],
                        )
                    except Exception as e:
                        logger.warning("seed skill '%s' failed: %s", name, e)
            logger.info("Skill enabled state synced from DB (%d)", len(self._skills))
        except Exception as e:
            logger.warning("Skill sync_from_db failed: %s", e)

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有已注册 Skill（含 enabled / tags / version）"""
        return [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "tags": s.tags,
                "enabled": self._enabled.get(s.name, False),
            }
            for s in self._skills.values()
        ]

    async def reload(self) -> list[dict[str, Any]]:
        """重新加载全部 Skill（保留各 Skill 的启用状态）

        通过重新导入并注册模块，使代码改动在运行中生效。
        """
        from importlib import import_module, reload as reload_module

        modules = {
            "rag_search": "skills.rag_search",
            "master_analysis": "skills.master_analysis",
            "web_article_summary": "skills.web_article_summary",
            "investment_research": "skills.investment_research",
        }
        prev = dict(self._enabled)
        for mod in modules.values():
            try:
                m = import_module(mod)
                reload_module(m)
                # 找出模块内所有 BaseSkill 子类并重新注册
                import inspect
                from skills.base_skill import BaseSkill
                for _, obj in inspect.getmembers(m, inspect.isclass):
                    if issubclass(obj, BaseSkill) and obj is not BaseSkill:
                        self.register(obj())
            except Exception as e:
                logger.warning("Skill reload '%s' failed: %s", mod, e)
        # 恢复原启用状态
        self._enabled.update({k: v for k, v in prev.items() if k in self._skills})
        return self.list_all()

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
