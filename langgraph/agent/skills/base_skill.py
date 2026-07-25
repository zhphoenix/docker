"""Skill 基类 - 定义可复用能力的标准接口

每个 Skill 封装一个独立的分析/处理能力，可被任意 Agent 调用。
新增 Skill 只需：
  1. 继承 BaseSkill
  2. 实现 execute() 方法
  3. 在 registry 中注册
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseSkill(ABC):
    """Skill 基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Skill 唯一标识名"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Skill 功能描述（用于 Agent 选择）"""
        ...

    @property
    def version(self) -> str:
        """版本号"""
        return "1.0.0"

    @property
    def tags(self) -> list[str]:
        """标签（用于分类检索）"""
        return []

    @abstractmethod
    async def execute(self, **kwargs) -> dict[str, Any]:
        """执行 Skill

        Args:
            **kwargs: Skill 特定参数

        Returns:
            结构化结果字典，至少包含 {"success": bool, "data": ...}
        """
        ...

    def validate_params(self, **kwargs) -> list[str]:
        """参数校验（可选覆写）

        Returns:
            错误信息列表，空列表表示通过
        """
        return []

    def __repr__(self) -> str:
        return f"<Skill: {self.name} v{self.version}>"
