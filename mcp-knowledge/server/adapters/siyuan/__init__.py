"""SiYuan Knowledge Workspace 适配器

将 PostgreSQL 中的知识对象渲染为 SiYuan 文档并增量同步。
遵循设计红线：SiYuan 仅展示层，PG 为唯一 SoT。

对外暴露：
  - SiYuanClient      : HTTP 客户端（限流 / 幂等 / 重试）
  - render_templates  : Jinja2 模板渲染
  - SiYuanSync        : 增量同步 + 版本 Diff
"""

from server.adapters.siyuan.client import SiYuanClient
from server.adapters.siyuan.config import SiYuanConfig, get_siyuan_config
from server.adapters.siyuan.sync import SiYuanSync

__all__ = [
    "SiYuanClient",
    "SiYuanConfig",
    "get_siyuan_config",
    "SiYuanSync",
]