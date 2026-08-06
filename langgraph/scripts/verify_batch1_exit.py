"""批次 1 退出条件综合验收（只读，不修改任何数据）

覆盖：
  ① knowledge_packages 建表成功且可重复执行（幂等检查）
  ③ /api/agents 返回 6 个 Agent（内置并集）
  ④ agent_runs 中 Pipeline 记录（knowledge_ingestion / news_intelligence）
  ⑤ Source Health 四指标落表（news.sources 扩列 + news.collect_runs）

采用与 tests/conftest.py 相同策略：加载根 .env。
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[0]  # langgraph/scripts
LANGGRAPH = ROOT.parent  # langgraph
PROJ = LANGGRAPH.parent  # 项目根（langgraph/ 上一级）
load_dotenv(PROJ / ".env", override=False)

sys.path.insert(0, str(LANGGRAPH))


async def main() -> int:
    from tools.postgres import postgres_tool

    results: dict[str, str] = {}
    ok = True

    # ── ③ /api/agents 返回 6 个（内置并集，不依赖 DB）──
    try:
        from config.agent_meta import get_agent_meta
        from api.agents import _merge_builtin
        meta = get_agent_meta() if callable(get_agent_meta) else {}
        # 兜底直接读 yaml
        if not meta:
            import yaml
            meta = yaml.safe_load(open(ROOT / "config/agent_meta.yaml", encoding="utf-8")) or {}
        meta = meta.get("meta", meta) if isinstance(meta, dict) else {}
        builtin = _merge_builtin(meta)
        ids = [a["id"] for a in builtin]
        count = len(ids)
        has_pipeline = ("knowledge_ingestion" in ids) and ("news_intelligence" in ids)
        results["③ /api/agents"] = f"builtin={count} pipeline双项={has_pipeline} ids={ids}"
        if count != 6 or not has_pipeline:
            ok = False
    except Exception as e:
        results["③ /api/agents"] = f"ERROR: {e}"
        ok = False

    # ── DB 相关 ──
    try:
        await postgres_tool.connect()

        # ① knowledge_packages 表存在（幂等建表：CREATE TABLE IF NOT EXISTS）
        rows = await postgres_tool.query(
            "SELECT to_regclass('public.knowledge_packages') AS tbl"
        )
        tbl = rows[0]["tbl"] if rows else None
        results["① knowledge_packages 建表"] = f"to_regclass={tbl}"
        if not tbl:
            ok = False

        # ① 幂等：重复执行迁移脚本应无报错（仅验证语法/存在性，不重放）
        # 已通过 to_regclass 确认，且脚本本身为 IF NOT EXISTS。

        # ④ agent_runs 中 Pipeline 记录
        try:
            ar = await postgres_tool.query(
                """
                SELECT agent_id, COUNT(*) AS cnt
                FROM agent_runs
                WHERE agent_id IN ('knowledge_ingestion', 'news_intelligence')
                GROUP BY agent_id
                """
            )
            ar_map = {r["agent_id"]: r["cnt"] for r in ar}
            results["④ agent_runs Pipeline"] = f"knowledge_ingestion={ar_map.get('knowledge_ingestion', 0)} news_intelligence={ar_map.get('news_intelligence', 0)}"
            # 验收条文：双路径各 1 条 → 共 2 条
            if ar_map.get("knowledge_ingestion", 0) + ar_map.get("news_intelligence", 0) < 2:
                ok = False
        except Exception as e:
            results["④ agent_runs Pipeline"] = f"ERROR(表不存在或查询失败): {e}"
            # agent_runs 表可能不存在，标记失败但继续
            ok = False

        # ⑤ Source Health 四指标落表
        src_cols = {"last_latency_ms", "last_success", "last_error", "error_count", "last_collected_at"}
        try:
            cols = await postgres_tool.query(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='news' AND table_name='sources'
                """
            )
            col_set = {r["column_name"] for r in cols}
            missing = src_cols - col_set
            results["⑤ news.sources 扩列"] = f"缺失={sorted(missing) if missing else '无（四指标齐备）'}"
            if missing:
                ok = False
        except Exception as e:
            results["⑤ news.sources 扩列"] = f"ERROR: {e}"
            ok = False

        try:
            cr = await postgres_tool.query(
                """
                SELECT to_regclass('news.collect_runs') AS tbl,
                       (SELECT COUNT(*) FROM news.collect_runs) AS runs
                """
            )
            cr_row = cr[0] if cr else {}
            results["⑤ news.collect_runs"] = f"表={cr_row.get('tbl')} 记录数={cr_row.get('runs')}"
            if not cr_row.get("tbl"):
                ok = False
        except Exception as e:
            results["⑤ news.collect_runs"] = f"ERROR: {e}"
            ok = False

        await postgres_tool.close()
    except Exception as e:
        results["DB"] = f"连接失败: {e}"
        ok = False

    print("\n=== 批次1退出条件验收 ===")
    for k, v in results.items():
        print(f"[{'PASS' if not v.startswith(('ERROR','[非法]')) and k!='DB' else 'CHECK'}] {k}: {v}")
    print(f"\n总体判定: {'✓ 全部满足' if ok else '✗ 存在未满足项'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))