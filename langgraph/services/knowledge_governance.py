"""KOC-B1 知识治理检测服务

检测五类治理问题并写入 core.knowledge_conflicts：
  1. duplicate_entity   重复实体（trgm 名称相似度 ≥ 阈值 或 别名重叠）
  2. value_mismatch     冲突事实（同 subject+predicate+时间，不同 object_value）
  3. low_confidence     低置信关系/事实（confidence < 阈值）
  4. stale_fact         过期知识（facts.lifecycle_status ∈ expired/archived）
  5. sync_conflict      同步冲突（KOC-F3：core.entities.sync_status ∈ Pending Review / Conflict）

设计原则（KOC 计划书风险 #3）：阈值走 policy 配置（governance.*），
先只写 conflicts 不自动动作，由 Governance 面板人工处理后回写状态。

幂等：同一冲突主体（entity_id 或 fact 对）已有 open 记录时不重复写。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from config.policy_loader import get_policy
from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)

# 冲突类型常量（与 core.knowledge_conflicts.conflict_type 对应）
CONFLICT_DUPLICATE_ENTITY = "duplicate_entity"
CONFLICT_VALUE_MISMATCH = "value_mismatch"
CONFLICT_LOW_CONFIDENCE = "low_confidence"
CONFLICT_STALE_FACT = "stale_fact"
CONFLICT_SYNC_CONFLICT = "sync_conflict"


class KnowledgeGovernance:
    """知识治理检测器（KOC-B1）"""

    async def detect_duplicate_entities(self) -> int:
        """重复实体检测：trgm 名称相似度 ≥ 阈值 或 别名重叠

        对每个重复对写两条冲突记录（各实体一条），resolution 记录对方 id 与相似度，
        供 Governance 面板执行合并/保留/驳回。
        """
        threshold = float(get_policy("governance.duplicate_threshold", 0.85))
        rows = await postgres_tool.query(
            """
            SELECT a.id AS id_a, a.name AS name_a, b.id AS id_b, b.name AS name_b,
                   similarity(a.name, b.name) AS sim
            FROM core.entities a
            JOIN core.entities b ON a.id < b.id
            WHERE a.status = 'active' AND b.status = 'active'
              AND (
                  similarity(a.name, b.name) >= $1
                  OR EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements_text(a.aliases) x
                      INNER JOIN jsonb_array_elements_text(b.aliases) y ON x = y
                  )
              )
            """,
            threshold,
        )
        written = 0
        for r in rows:
            sim = float(r.get("sim") or 0.0)
            for entity_id, other_id, other_name in (
                (r["id_a"], r["id_b"], r["name_b"]),
                (r["id_b"], r["id_a"], r["name_a"]),
            ):
                ok = await self._insert_conflict(
                    conflict_type=CONFLICT_DUPLICATE_ENTITY,
                    entity_id=entity_id,
                    resolution={
                        "kind": "duplicate_pair",
                        "duplicate_of": str(other_id),
                        "duplicate_name": other_name,
                        "similarity": round(sim, 3),
                    },
                )
                written += 1 if ok else 0
        if written:
            logger.info("[Governance] duplicate_entities | written=%d | threshold=%.2f", written, threshold)
        return written

    async def detect_conflicting_facts(self) -> int:
        """冲突事实检测：同 subject+predicate+时间区间、不同 object_value

        同一实体同一指标在不同时间点取值不同属正常（time_start/time_end 不同则跳过）。
        """
        rows = await postgres_tool.query(
            """
            SELECT f1.id AS fact_a, f2.id AS fact_b, f1.subject_entity,
                   f1.predicate, f1.object_value AS object_a, f2.object_value AS object_b
            FROM core.facts f1
            JOIN core.facts f2
              ON f1.subject_entity = f2.subject_entity
             AND f1.predicate = f2.predicate
             AND f1.id < f2.id
             AND f1.time_start IS NOT DISTINCT FROM f2.time_start
             AND f1.time_end IS NOT DISTINCT FROM f2.time_end
            WHERE f1.lifecycle_status = 'extracted'
              AND f2.lifecycle_status = 'extracted'
              AND f1.object_value::text IS DISTINCT FROM f2.object_value::text
            """,
        )
        written = 0
        for r in rows:
            ok = await self._insert_conflict(
                conflict_type=CONFLICT_VALUE_MISMATCH,
                entity_id=r["subject_entity"],
                fact_a=r["fact_a"],
                fact_b=r["fact_b"],
                resolution={
                    "predicate": r["predicate"],
                    "object_a": r["object_a"],
                    "object_b": r["object_b"],
                },
            )
            written += 1 if ok else 0
        if written:
            logger.info("[Governance] value_mismatch | written=%d", written)
        return written

    async def detect_low_confidence(self) -> int:
        """低置信检测：relations / facts 的 confidence < 阈值"""
        threshold = float(get_policy("governance.low_confidence_threshold", 0.6))
        written = 0

        rel_rows = await postgres_tool.query(
            """
            SELECT id, source_entity, target_entity, relation_type, confidence
            FROM core.relations
            WHERE status = 'active' AND confidence IS NOT NULL AND confidence < $1
            """,
            threshold,
        )
        for r in rel_rows:
            ok = await self._insert_conflict(
                conflict_type=CONFLICT_LOW_CONFIDENCE,
                entity_id=r["source_entity"],
                resolution={
                    "kind": "relation",
                    "ref": str(r["id"]),
                    "relation_type": r["relation_type"],
                    "target_entity": str(r["target_entity"]) if r["target_entity"] else None,
                    "confidence": r["confidence"],
                },
            )
            written += 1 if ok else 0

        fact_rows = await postgres_tool.query(
            """
            SELECT id, subject_entity, predicate, confidence
            FROM core.facts
            WHERE lifecycle_status = 'extracted'
              AND confidence IS NOT NULL AND confidence < $1
            """,
            threshold,
        )
        for r in fact_rows:
            ok = await self._insert_conflict(
                conflict_type=CONFLICT_LOW_CONFIDENCE,
                entity_id=r["subject_entity"],
                resolution={
                    "kind": "fact",
                    "ref": str(r["id"]),
                    "predicate": r["predicate"],
                    "confidence": r["confidence"],
                },
            )
            written += 1 if ok else 0

        if written:
            logger.info("[Governance] low_confidence | written=%d | threshold=%.2f", written, threshold)
        return written

    async def detect_stale_facts(self) -> int:
        """过期知识检测：facts.lifecycle_status = expired / archived"""
        rows = await postgres_tool.query(
            """
            SELECT id, subject_entity, predicate, lifecycle_status
            FROM core.facts
            WHERE lifecycle_status IN ('expired', 'archived')
            """,
        )
        written = 0
        for r in rows:
            ok = await self._insert_conflict(
                conflict_type=CONFLICT_STALE_FACT,
                entity_id=r["subject_entity"],
                fact_a=r["id"],
                resolution={
                    "predicate": r["predicate"],
                    "lifecycle_status": r["lifecycle_status"],
                },
            )
            written += 1 if ok else 0
        if written:
            logger.info("[Governance] stale_facts | written=%d", written)
        return written

    async def detect_sync_conflicts(self) -> int:
        """同步冲突检测（KOC-F3）：core.entities.sync_status 待审/冲突态

        SiYuan 渲染回写异常或多次编辑冲突时，实体进入 Pending Review / Conflict。
        结果写 knowledge_conflicts（类型 sync_conflict），由 Governance 面板
        人工处理后重置 sync_status='Synced'（keep/dismiss 均回写）。
        """
        rows = await postgres_tool.query(
            """
            SELECT id, name, entity_type, sync_status, sync_version
            FROM core.entities
            WHERE status = 'active'
              AND sync_status IN ('Pending Review', 'Conflict')
            """,
        )
        written = 0
        for r in rows:
            ok = await self._insert_conflict(
                conflict_type=CONFLICT_SYNC_CONFLICT,
                entity_id=r["id"],
                resolution={
                    "kind": "sync_status",
                    "sync_status": r["sync_status"],
                    "sync_version": r["sync_version"],
                },
            )
            written += 1 if ok else 0
        if written:
            logger.info("[Governance] sync_conflicts | written=%d", written)
        return written

    async def run_governance_detection(self) -> dict[str, int]:
        """运行全部治理检测（scheduler job 入口）"""
        stats: dict[str, int] = {}
        stats["duplicate_entities"] = await self.detect_duplicate_entities()
        stats["conflicting_facts"] = await self.detect_conflicting_facts()
        stats["low_confidence"] = await self.detect_low_confidence()
        stats["stale_facts"] = await self.detect_stale_facts()
        stats["sync_conflicts"] = await self.detect_sync_conflicts()
        stats["total"] = sum(stats.values())
        logger.info("[Governance] detection done | %s", stats)
        return stats

    async def resolve_conflict(self, conflict_id: str, action: str, note: str = "") -> bool:
        """处理治理项（KOC-B2）：回写 status='resolved' + resolution.action

        action:
          - merge   合并重复实体（duplicate_entity 专用）：当前实体并入
                    resolution.duplicate_of 保留实体（name 入 aliases，自身置 merged）
          - keep    保留（确认无冲突，直接关闭）
          - dismiss 驳回（确认误报，关闭）

        Returns:
            True 处理成功；False 记录不存在或已处理
        """
        if action not in ("merge", "keep", "dismiss"):
            raise ValueError(f"action must be merge/keep/dismiss, got {action}")

        row = await postgres_tool.query(
            "SELECT conflict_type, entity_id, resolution FROM core.knowledge_conflicts "
            "WHERE id = $1 AND status = 'open'",
            conflict_id,
        )
        if not row:
            return False
        conflict = row[0]

        # merge 动作：真实合并重复实体（别名并入保留实体，自身置 merged）
        if (
            action == "merge"
            and conflict["conflict_type"] == CONFLICT_DUPLICATE_ENTITY
            and conflict.get("entity_id")
        ):
            resolution: dict = {}
            try:
                resolution = json.loads(conflict["resolution"] or "{}")
            except (json.JSONDecodeError, TypeError):
                pass
            target_id = resolution.get("duplicate_of")
            if target_id:
                ent = await postgres_tool.query(
                    "SELECT name FROM core.entities WHERE id = $1", conflict["entity_id"]
                )
                if ent:
                    name = ent[0]["name"]
                    await postgres_tool.execute(
                        "UPDATE core.entities SET aliases = aliases || jsonb_build_array($2::text), "
                        "status = 'merged', updated_at = NOW() WHERE id = $1 AND status = 'active'",
                        target_id, name,
                    )
                    await postgres_tool.execute(
                        "UPDATE core.entities SET status = 'merged', updated_at = NOW() "
                        "WHERE id = $1",
                        conflict["entity_id"],
                    )
                    logger.info(
                        "[Governance] merge | %s -> %s | alias=%s",
                        str(conflict["entity_id"])[:8], str(target_id)[:8], name,
                    )

        # sync_conflict 处理（KOC-F3）：重置实体同步状态为 Synced
        # keep/dismiss 均视为人工确认，同步冲突解除后回写 Synced。
        if (
            conflict["conflict_type"] == CONFLICT_SYNC_CONFLICT
            and conflict.get("entity_id")
        ):
            await postgres_tool.execute(
                "UPDATE core.entities SET sync_status = 'Synced', "
                "sync_version = sync_version + 1, last_synced_at = NOW(), "
                "updated_at = NOW() WHERE id = $1",
                conflict["entity_id"],
            )
            logger.info(
                "[Governance] sync_conflict resolved | %s -> Synced",
                str(conflict["entity_id"])[:8],
            )

        result = await postgres_tool.execute(
            """
            UPDATE core.knowledge_conflicts
            SET status = 'resolved',
                resolution = (COALESCE(resolution, '{}')::jsonb || jsonb_build_object(
                    'action', $2::text, 'note', $3::text, 'resolved_at', NOW()::text))::text,
                resolved_at = NOW()
            WHERE id = $1 AND status = 'open'
            """,
            conflict_id, action, note[:500],
        )
        return "UPDATE 1" in result

    async def _insert_conflict(
        self,
        conflict_type: str,
        entity_id: Any = None,
        fact_a: Any = None,
        fact_b: Any = None,
        resolution: dict | None = None,
    ) -> bool:
        """幂等写入冲突记录：同类型同主体已有 open 记录则跳过

        - value_mismatch：按 (fact_a, fact_b) 无序对去重
        - 其余类型：按 entity_id 或 fact_a 去重
        """
        if conflict_type == CONFLICT_VALUE_MISMATCH and fact_a and fact_b:
            dedup = "((fact_a = $3 AND fact_b = $4) OR (fact_a = $4 AND fact_b = $3))"
        elif fact_a:
            dedup = "(fact_a = $3)"
        else:
            dedup = "(entity_id = $2)"

        result = await postgres_tool.execute(
            f"""
            INSERT INTO core.knowledge_conflicts (conflict_type, entity_id, fact_a, fact_b, resolution)
            SELECT $1, $2, $3, $4, $5::jsonb
            WHERE NOT EXISTS (
                SELECT 1 FROM core.knowledge_conflicts
                WHERE conflict_type = $1 AND status = 'open' AND {dedup}
            )
            """,
            conflict_type, entity_id, fact_a, fact_b,
            json.dumps(resolution or {}, ensure_ascii=False, default=str),
        )
        # 解析受影响行数区分“已插入”与“幂等跳过”（"INSERT 0 1" vs "INSERT 0 0"）
        try:
            inserted = int(str(result).split()[-1])
        except (ValueError, IndexError):
            inserted = 1  # 无法解析时保守视为已插入
        return inserted > 0


# 模块级单例
governance = KnowledgeGovernance()