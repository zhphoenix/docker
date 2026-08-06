#!/usr/bin/env python3
"""knowledge.* Schema 收口核对脚本

背景：
    knowledge schema（06-knowledge-schema.sql）已被 07-knowledge-database.sql 的
    多 Schema 架构取代：数据迁移至 core / document / taxonomy，
    knowledge.* 现为只读兼容视图（见 07 文件 §12）。

本脚本负责：
  1. 核对 knowledge.* 视图与正式表的数据计数是否一致（迁移正确性）
  2. 检查 knowledge schema 是否残留 BASE TABLE（应全部为视图）
  3. 扫描 langgraph / mcp-knowledge 代码库中 knowledge.* SQL 读写引用残留
  4. 输出迁移核对报告（--json 输出结构化结果，供 CI/验收使用）

用法：
  python3 scripts/migrate_knowledge_schema.py
  python3 scripts/migrate_knowledge_schema.py --json
  python3 scripts/migrate_knowledge_schema.py --skip-code-scan

环境变量：
  PG_HOST (default: localhost)
  PG_PORT (default: 5433)
  PG_USER (default: postgres)
  PG_PASS (default: postgres)
  PG_DB   (default: ai)
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import asyncpg

# ── 配置 ──────────────────────────────────────────────────────────────────────

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5433"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASS = os.environ.get("PG_PASS", "postgres")
PG_DB = os.environ.get("PG_DB", "ai")

# knowledge.* 视图 → 正式表映射（07 文件 §12 兼容视图）
VIEW_MAP = [
    # (knowledge 视图, 正式表, 说明)
    ("knowledge.entities", "core.entities", "实体"),
    ("knowledge.relations", "core.relations", "关系"),
    ("knowledge.facts", "core.facts", "事实"),
    ("knowledge.evidence", "core.evidence", "证据"),
    ("knowledge.documents", "document.documents", "来源文档"),
    ("knowledge.entity_types", "taxonomy.entity_types", "实体类型枚举"),
    ("knowledge.relation_types", "taxonomy.relation_types", "关系类型枚举"),
]

# 代码库扫描根目录（相对本脚本所在 scripts/ 的上一级）
CODE_ROOTS = [
    ("langgraph", Path(__file__).resolve().parent.parent / "langgraph"),
    ("mcp-knowledge", Path(__file__).resolve().parent.parent / "mcp-knowledge"),
]

# knowledge.* 表/视图名的 SQL 引用模式（排除 storage.knowledge 包路径）
_SQL_REF = re.compile(
    r"(?<!storage\.)knowledge\.(entities|relations|facts|evidence|documents|entity_types|relation_types)\b"
)
# 明确的 SQL 读写关键字上下文
_SQL_KW = re.compile(
    r"(FROM|INTO|JOIN|UPDATE|DELETE\s+FROM|TABLE|REFERENCES|ALTER\s+TABLE|CREATE\s+(VIEW|TABLE)|INSERT\s+INTO)\s+knowledge\.\w+",
    re.IGNORECASE,
)
# 扫描时忽略的行（注释/文档字符串/配置路径/README）
_IGNORE_LINE = re.compile(
    r"(^\s*#|^\s*--|^\s*\"\"\"|^\s*'''|storage\.knowledge|get_policy\(|policy\s*[=:]\s*[\"']|knowledge\.\*|knowledge\.%|knowledge\.\w+\s*\*|\.env|README|DEPRECATED|已废弃|兼容视图|07-knowledge|migrate_knowledge)",
    re.IGNORECASE,
)

# ── 数据核对 ──────────────────────────────────────────────────────────────────


async def count_rows(pool: asyncpg.Pool, table: str) -> int:
    """安全取表/视图行数（临时表不存在时返回 -1）。"""
    try:
        row = await pool.fetchval(f"SELECT COUNT(*) FROM {table}")
        return int(row or 0)
    except asyncpg.UndefinedTableError:
        return -1


async def check_schema_objects(pool: asyncpg.Pool) -> dict:
    """检查 knowledge schema 内对象类型分布。"""
    rows = await pool.fetch(
        """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = 'knowledge'
        ORDER BY table_name
        """
    )
    objects = [{"name": r["table_name"], "type": r["table_type"]} for r in rows]
    base_tables = [o["name"] for o in objects if o["type"] == "BASE TABLE"]
    views = [o["name"] for o in objects if o["type"] == "VIEW"]
    return {
        "total": len(objects),
        "views": views,
        "base_tables": base_tables,
        "ok": len(base_tables) == 0,
    }


async def verify_view_pair(pool: asyncpg.Pool, view: str, table: str) -> dict:
    """核对单个视图与正式表：计数一致 + 视图定义存在。"""
    view_exists = await pool.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.views
            WHERE table_schema = $1 AND table_name = $2
        )
        """,
        view.split(".")[0],
        view.split(".")[1],
    )
    view_cnt = await count_rows(pool, view)
    table_cnt = await count_rows(pool, table)
    return {
        "view": view,
        "table": table,
        "view_count": view_cnt,
        "table_count": table_cnt,
        "consistent": view_exists and view_cnt >= 0 and view_cnt == table_cnt,
    }


async def verify_all(pool: asyncpg.Pool) -> list[dict]:
    results = []
    for view, table, _label in VIEW_MAP:
        results.append(await verify_view_pair(pool, view, table))
    return results


# ── 代码引用扫描 ──────────────────────────────────────────────────────────────


def scan_code_references() -> list[dict]:
    """扫描代码库中 knowledge.* SQL 引用残留。"""
    findings: list[dict] = []
    for repo, root in CODE_ROOTS:
        if not root.exists():
            findings.append(
                {
                    "repo": repo,
                    "path": str(root),
                    "line": 0,
                    "content": "<目录不存在>",
                    "is_sql": False,
                }
            )
            continue
        for path in sorted(root.rglob("*.py")):
            if any(part.startswith(".") for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if _IGNORE_LINE.search(line):
                    continue
                if _SQL_REF.search(line) or _SQL_KW.search(line):
                    findings.append(
                        {
                            "repo": repo,
                            "path": str(path.relative_to(root)),
                            "line": lineno,
                            "content": line.strip()[:160],
                            "is_sql": bool(_SQL_KW.search(line)),
                        }
                    )
    return findings


# ── 主流程 ────────────────────────────────────────────────────────────────────


async def run() -> dict:
    report: dict = {
        "schema_status": None,
        "view_pairs": [],
        "code_scan": [],
        "summary": {},
    }

    pool = await asyncpg.create_pool(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, database=PG_DB
    )
    try:
        report["schema_status"] = await check_schema_objects(pool)
        report["view_pairs"] = await verify_all(pool)
    finally:
        await pool.close()

    if not args.skip_code_scan:
        report["code_scan"] = scan_code_references()

    # 汇总
    pairs = report["view_pairs"]
    consistent = [p for p in pairs if p["consistent"]]
    missing = [p for p in pairs if p["view_count"] < 0]
    mismatched = [p for p in pairs if not p["consistent"] and p["view_count"] >= 0]
    sql_refs = [f for f in report["code_scan"] if f.get("is_sql")]
    other_refs = [f for f in report["code_scan"] if not f.get("is_sql")]

    report["summary"] = {
        "schema_base_tables": len(report["schema_status"]["base_tables"]),
        "schema_views": len(report["schema_status"]["views"]),
        "view_pairs_total": len(pairs),
        "view_pairs_consistent": len(consistent),
        "view_pairs_missing": len(missing),
        "view_pairs_mismatched": len(mismatched),
        "sql_refs": len(sql_refs),
        "other_refs": len(other_refs),
        "ready": (
            report["schema_status"]["ok"]
            and len(mismatched) == 0
            and len(missing) == 0
            and len(sql_refs) == 0
        ),
    }
    return report


def render(report: dict) -> None:
    s = report["summary"]
    print("=" * 64)
    print("knowledge.* Schema 收口核对报告")
    print("=" * 64)

    print(f"\n[1] Schema 状态 (knowledge)")
    st = report["schema_status"]
    print(f"    视图: {len(st['views'])} 个  基表: {len(st['base_tables'])} 个  "
          f"→ {'✅ OK' if st['ok'] else '❌ 存在残留基表'}")
    if st["base_tables"]:
        print(f"    残留基表: {', '.join(st['base_tables'])}")

    print(f"\n[2] 视图 ↔ 正式表 数据核对")
    for p in report["view_pairs"]:
        mark = "✅" if p["consistent"] else ("⚠️ 缺失" if p["view_count"] < 0 else "❌ 不一致")
        print(f"    {mark} {p['view']:<26} → {p['table']:<28} "
              f"{p['view_count']} = {p['table_count']}")

    print(f"\n[3] 代码引用残留扫描")
    refs = report["code_scan"]
    if not args.skip_code_scan:
        sql_refs = [f for f in refs if f.get("is_sql")]
        other_refs = [f for f in refs if not f.get("is_sql")]
        print(f"    SQL 读写引用: {len(sql_refs)} 处  {'✅ 无残留' if not sql_refs else '❌ 需清理'}")
        for f in sql_refs:
            print(f"      - {f['repo']}/{f['path']}:{f['line']}  {f['content']}")
        print(f"    其他疑似引用: {len(other_refs)} 处")
        for f in other_refs[:20]:
            print(f"      - {f['repo']}/{f['path']}:{f['line']}  {f['content']}")
        if len(other_refs) > 20:
            print(f"      ... 其余 {len(other_refs) - 20} 处略")
    else:
        print("    已跳过（--skip-code-scan）")

    print(f"\n[4] 结论")
    ready = s["ready"]
    print(f"    视图对一致性: {s['view_pairs_consistent']}/{s['view_pairs_total']}  "
          f"缺失: {s['view_pairs_missing']}  不一致: {s['view_pairs_mismatched']}")
    print(f"    结论: {'✅ 迁移完成，knowledge.* 无新增读写，可进入废弃观察期' if ready else '❌ 存在问题，需人工处理'}")
    print("=" * 64)


def main() -> None:
    global args
    parser = argparse.ArgumentParser(description="knowledge.* Schema 收口核对脚本")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结构化结果")
    parser.add_argument("--skip-code-scan", action="store_true", help="跳过代码引用扫描")
    args = parser.parse_args()

    report = asyncio.run(run())

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        render(report)

    sys.exit(0 if report["summary"]["ready"] else 1)


if __name__ == "__main__":
    main()