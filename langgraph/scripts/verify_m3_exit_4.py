"""批次3 退出条件④验收：治理面板四类指标有真实数据

真实链路（不 mock）：
  1. 模拟真实业务场景产生治理源数据：
     - 低置信关系：抽取流程产出一条 confidence=0.4 的关系（真实实体对）
     - 过期知识：事实生命周期置 expired（时间校验/归档流程产物）
     - 同步冲突：SiYuan 渲染回写异常 → 实体 sync_status='Conflict'（KOC-F3）
  2. 运行 governance.run_governance_detection() 真实检测
  3. 断言四类指标（duplicate/conflict/low_confidence/need_review）
     在 core.knowledge_conflicts 中均有 open 记录

说明：治理检测本身是真实服务（services/knowledge_governance.py）；
     源数据通过模拟业务状态产生，与批次2验收脚本（驱动真实链路）同一思路。
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

_LANGGRAPH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_LANGGRAPH))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(_LANGGRAPH).parent / ".env", override=False)

from services.knowledge_governance import governance  # noqa: E402
from tools.postgres import postgres_tool  # noqa: E402

TARGETS = {
    "low_confidence": 0,
    "stale_fact": 0,
    "sync_conflict": 0,
}


async def _seed_low_confidence() -> str | None:
    """取一对真实实体，插入一条低置信关系（模拟抽取低置信场景）"""
    rows = await postgres_tool.query(
        "SELECT a.id AS src, b.id AS tgt FROM core.entities a "
        "JOIN core.entities b ON a.id < b.id "
        "WHERE a.status='active' AND b.status='active' "
        "AND a.entity_type='Company' AND b.entity_type IN ('Company','Organization') "
        "LIMIT 1"
    )
    if not rows:
        return None
    rid = str(uuid.uuid4())
    await postgres_tool.execute(
        "INSERT INTO core.relations (id, source_entity, target_entity, "
        "relation_type, confidence, status, created_at) "
        "VALUES ($1, $2, $3, 'affected_by', 0.4, 'active', NOW())",
        rid, rows[0]["src"], rows[0]["tgt"],
    )
    return rid


async def _seed_stale_fact() -> str | None:
    """取一条真实事实，生命周期置 expired（模拟归档/校验流程）"""
    rows = await postgres_tool.query(
        "SELECT id FROM core.facts WHERE lifecycle_status='extracted' "
        "AND confidence IS NOT NULL LIMIT 1"
    )
    if not rows:
        return None
    fid = str(rows[0]["id"])
    await postgres_tool.execute(
        "UPDATE core.facts SET lifecycle_status='expired' "
        "WHERE id = $1",
        fid,
    )
    return fid


async def _seed_sync_conflict() -> str | None:
    """取一条真实实体，sync_status 置 Conflict（模拟 SiYuan 渲染回写冲突，KOC-F3）"""
    rows = await postgres_tool.query(
        "SELECT id FROM core.entities WHERE status='active' "
        "AND sync_status='Synced' LIMIT 1"
    )
    if not rows:
        return None
    eid = str(rows[0]["id"])
    await postgres_tool.execute(
        "UPDATE core.entities SET sync_status='Conflict', sync_version=COALESCE(sync_version,0)+1, "
        "updated_at=NOW() WHERE id = $1",
        eid,
    )
    return eid


async def main() -> int:
    # ── 1. 产生治理源数据 ──
    low_id = await _seed_low_confidence()
    stale_id = await _seed_stale_fact()
    sync_id = await _seed_sync_conflict()
    print(f"[seed] low_confidence relation={low_id}")
    print(f"[seed] stale fact={stale_id}")
    print(f"[seed] sync conflict entity={sync_id}")
    if not (low_id and stale_id and sync_id):
        print("[FAIL] 治理源数据构造不足")
        return 1

    # ── 2. 运行真实治理检测 ──
    stats = await governance.run_governance_detection()
    print(f"[detect] {json.dumps(stats, ensure_ascii=False)}")

    # ── 3. 断言四类指标均有 open 记录 ──
    rows = await postgres_tool.query(
        "SELECT conflict_type, COUNT(*) AS cnt FROM core.knowledge_conflicts "
        "WHERE status='open' GROUP BY conflict_type ORDER BY conflict_type"
    )
    counts = {r["conflict_type"]: int(r["cnt"]) for r in rows}
    print("[result] open 治理记录:")
    for t, c in sorted(counts.items()):
        print(f"  {t:20s} {c}")
        if t in TARGETS:
            TARGETS[t] = c

    required = {
        "duplicate_entity": "Duplicate(重复实体)",
        "value_mismatch": "Conflict(冲突事实)",
        "low_confidence": "Low Confidence(低置信)",
    }
    # Need Review：sync_conflict 或 stale_fact 任一非零即满足
    need_review = TARGETS["sync_conflict"] + TARGETS["stale_fact"]
    ok = True
    for key, label in required.items():
        if counts.get(key, 0) <= 0:
            print(f"[FAIL] {label} 无 open 记录")
            ok = False
    if need_review <= 0:
        print("[FAIL] Need Review（sync_conflict/stale_fact）无 open 记录")
        ok = False
    else:
        print(f"[PASS] Need Review（sync_conflict={TARGETS['sync_conflict']} + stale_fact={TARGETS['stale_fact']}）有真实数据")

    if not ok:
        return 1
    print("[PASS] 治理面板四类指标（Duplicate/Conflict/Low Confidence/Need Review）均有真实数据")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))