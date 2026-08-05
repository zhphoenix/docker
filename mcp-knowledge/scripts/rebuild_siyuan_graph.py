"""全量重建 SiYuan 知识图谱文档。

将 PostgreSQL 中所有 active 实体的 SiYuan 文档强制重建，使实体文档包含
"相关实体"链接（[[邻居]]），从而让 SiYuan 内置关系图能基于文档链接
自动生成关联图谱。

设计红线：PG 为唯一 SoT，SiYuan 仅展示。本脚本只读 PG、只写 SiYuan，
不写入任何业务状态（不触碰 sync_version 等同步元数据）。

用法（mcp-knowledge 根目录下执行）：
    python scripts/rebuild_siyuan_graph.py --limit 50        # 抽样重建
    python scripts/rebuild_siyuan_graph.py --dry-run          # 仅列出，不写入
    python scripts/rebuild_siyuan_graph.py                    # 全量重建
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 保证从任意工作目录运行都能 import server 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.adapters.siyuan.client import SiYuanClient  # noqa: E402
from server.adapters.siyuan.mapper import (  # noqa: E402
    entity_to_path,
    entity_to_template_context,
    notebook_for,
)
from server.adapters.siyuan.templates import renderer  # noqa: E402
from server.storage.postgres import pg_storage  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("rebuild_siyuan_graph")


async def rebuild(limit: int | None = None, dry_run: bool = False) -> None:
    """遍历所有 active 实体，强制重建 SiYuan 文档（含邻居链接）。"""
    entities = await pg_storage.query(
        """
        SELECT id, entity_type, canonical_name, name, description,
               aliases, confidence, properties, updated_at
        FROM core.entities
        WHERE status = 'active'
        ORDER BY id
        """
    )
    if limit:
        entities = entities[:limit]

    logger.info("待重建实体数: %d (dry_run=%s)", len(entities), dry_run)
    if not entities:
        logger.info("无待重建实体")
        return

    client = SiYuanClient()
    ok = fail = 0
    for e in entities:
        name = e.get("canonical_name") or e.get("name") or "untitled"
        try:
            etype = e.get("entity_type", "Company")
            # 注入一跳邻居链接，供 SiYuan 关系图生成实体间关联
            neighbors = await pg_storage.get_entity_neighbors_for_render(str(e["id"]))
            context = entity_to_template_context(e, neighbors=neighbors)
            markdown = renderer.render(etype, context)
            notebook = notebook_for(etype)
            path = entity_to_path(e)

            if dry_run:
                logger.info("[dry-run] %s → %s/%s", name, notebook, path)
                ok += 1
                continue

            result = await client.upsert_doc(notebook, path, markdown)
            logger.info("[ok] %s → %s/%s (%s)", name, notebook, path, result.get("action"))
            ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("[fail] %s: %s", name, exc)
            fail += 1

    logger.info("重建完成: ok=%d fail=%d", ok, fail)


def main() -> None:
    parser = argparse.ArgumentParser(description="全量重建 SiYuan 知识图谱文档")
    parser.add_argument("--limit", type=int, default=None, help="抽样数量")
    parser.add_argument("--dry-run", action="store_true", help="仅列出实体，不写入")
    args = parser.parse_args()

    asyncio.run(rebuild(limit=args.limit, dry_run=args.dry_run))


if __name__ == "__main__":
    main()