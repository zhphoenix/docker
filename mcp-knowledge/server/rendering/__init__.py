"""Knowledge Rendering Engine

消费 core.knowledge_render_jobs，将 PostgreSQL 知识对象渲染为 Markdown
并经 SiYuan Adapter 增量同步到 SiYuan 展示层。

设计红线：PG 为唯一 SoT，渲染源只读 PG；SiYuan 仅展示。
性能：按 Section 增量渲染 + 版本 Diff + 队列背压 + 限流。
"""

from server.rendering.engine import render_engine
from server.rendering.worker import RenderWorker

__all__ = ["render_engine", "RenderWorker"]