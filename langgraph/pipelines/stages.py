"""Pipeline 阶段抽象 - 八阶段枚举与阶段记录追踪

DP-B1 定义 acquire/routing/parse/chunk/extraction/embedding/package/publish
八个流水线阶段，以及阶段记录追踪抽象。

每个阶段「进入 / 完成 / 失败」都会：
  1. 写入 task_logs（stage 字段 = 阶段名，level = info/error）
  2. 写入 documents.metadata.processing（JSONB，含 stages 数组与处理元信息）

与 DP-A1 的 ProcessingStage / ProcessingMetadata 模型字段一一对应，
供后续 DP-B4 把 parser/embedding_model/routing_strategy 等落库复用。
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_ms(started_iso: str | None, finished_iso: str | None) -> int | None:
    """由 ISO 时间戳计算耗时（毫秒）。任一缺失返回 None。"""
    if not started_iso or not finished_iso:
        return None
    try:
        start = datetime.fromisoformat(started_iso)
        end = datetime.fromisoformat(finished_iso)
        return int((end - start).total_seconds() * 1000)
    except (ValueError, TypeError):
        return None


class Stage(str, Enum):
    """八阶段流水线阶段枚举"""

    ACQUIRE = "acquire"
    ROUTING = "routing"
    PARSE = "parse"
    CHUNK = "chunk"
    EXTRACTION = "extraction"
    EMBEDDING = "embedding"
    PACKAGE = "package"
    PUBLISH = "publish"

    @property
    def label(self) -> str:
        return {
            Stage.ACQUIRE: "采集",
            Stage.ROUTING: "路由",
            Stage.PARSE: "解析",
            Stage.CHUNK: "分块",
            Stage.EXTRACTION: "知识抽取",
            Stage.EMBEDDING: "向量化",
            Stage.PACKAGE: "打包",
            Stage.PUBLISH: "发布",
        }[self]

    @classmethod
    def from_value(cls, value: str) -> "Stage":
        return cls(value)


class StageStatus(str, Enum):
    """阶段状态"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


# 阶段顺序（用于校验 / 展示 / 排序）
STAGE_ORDER: list[str] = [s.value for s in Stage]

# 阶段名 -> 中文标签（便捷映射）
STAGE_LABELS: dict[str, str] = {s.value: s.label for s in Stage}


class StageTracker:
    """单文档阶段追踪器

    维护 documents.metadata.processing 的内存视图，每一次「进入 / 完成 / 失败」
    都会同步写回 documents.metadata.processing，并（若存在 task_id）写一条
    task_logs（stage 字段 = 阶段名）。

    支持断点续传：从已有 metadata.processing 加载，继续追加/更新阶段记录。
    """

    def __init__(self, document_id: str, task_id: str | None = None):
        self.document_id = document_id
        self.task_id = task_id
        self._processing: dict[str, Any] = {
            "parser": None,
            "parser_version": None,
            "chunk_strategy": None,
            "embedding_model": None,
            "embedding_version": None,
            "routing_strategy": None,
            "llm_model": None,
            "ocr_engine": None,
            "processing_time": None,
            "stages": [],
        }
        self._stage_index: dict[str, int] = {}

    # ------------------------------------------------------------------
    # 加载 / 持久化
    # ------------------------------------------------------------------
    async def load(self, postgres_tool: Any) -> None:
        """从 documents.metadata.processing 加载已存在的处理记录（断点续传）"""
        try:
            rows = await postgres_tool.query(
                "SELECT COALESCE(metadata->'processing', '{}'::jsonb) AS processing "
                "FROM documents WHERE id = $1",
                self.document_id,
            )
        except Exception as e:
            logger.warning("StageTracker.load failed | doc=%s | %s", self.document_id[:8], e)
            return
        if not rows:
            return
        existing = rows[0].get("processing")
        if isinstance(existing, str):
            # asyncpg 把 jsonb 返回为 str，需反序列化
            try:
                existing = json.loads(existing)
            except (ValueError, TypeError):
                existing = None
        if existing:
            self._processing.update(existing)
            stages = self._processing.get("stages")
            if isinstance(stages, list):
                for i, st in enumerate(stages):
                    if isinstance(st, dict) and st.get("stage"):
                        self._stage_index[st["stage"]] = i

    async def _persist(self, postgres_tool: Any) -> None:
        """把 processing 视图写回 documents.metadata.processing（非关键路径）"""
        try:
            await postgres_tool.execute(
                "UPDATE documents SET metadata = jsonb_set("
                "COALESCE(metadata, '{}'::jsonb), '{processing}', $2::jsonb) "
                "WHERE id = $1",
                self.document_id, json.dumps(self._processing, ensure_ascii=False),
            )
        except Exception as e:
            logger.warning("StageTracker._persist failed | doc=%s | %s", self.document_id[:8], e)

    # ------------------------------------------------------------------
    # processing 元字段
    # ------------------------------------------------------------------
    def set_metadata(self, **kwargs: Any) -> None:
        """设置 processing 元字段（parser / embedding_model / routing_strategy 等）"""
        for k, v in kwargs.items():
            if k in self._processing and v is not None:
                self._processing[k] = v

    @property
    def processing(self) -> dict[str, Any]:
        return self._processing

    def stage_records(self) -> list[dict[str, Any]]:
        return list(self._processing.get("stages", []))

    # ------------------------------------------------------------------
    # 阶段记录主流程
    # ------------------------------------------------------------------
    def _ensure_stage(self, stage: str) -> int:
        """返回阶段在 stages 列表中的索引（不存在则追加 pending 记录）"""
        if stage in self._stage_index:
            return self._stage_index[stage]
        idx = len(self._processing["stages"])
        self._processing["stages"].append({
            "stage": stage,
            "status": StageStatus.PENDING.value,
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "error": None,
        })
        self._stage_index[stage] = idx
        return idx

    def _mark(self, stage: str, status: str, error: str = "") -> None:
        """更新内存中某阶段状态（不落库）"""
        idx = self._ensure_stage(stage)
        rec = self._processing["stages"][idx]
        now = _utcnow_iso()
        rec["status"] = status
        if status == StageStatus.RUNNING.value:
            rec["started_at"] = now
            rec["error"] = None
        else:
            rec["finished_at"] = now
            started = rec.get("started_at")
            rec["duration_ms"] = _duration_ms(started, now)
            rec["error"] = (error[:500] or None) if error else None

    async def _log_task(self, stage: str, level: str, message: str) -> None:
        """写 task_logs（延迟导入 task_queue，避免模块级循环依赖；失败不阻塞）"""
        if not self.task_id:
            return
        try:
            from runtime.queue import task_queue
            await task_queue.log_task(self.task_id, level, message, stage)
        except Exception as e:
            logger.warning("StageTracker._log_task failed | %s", e)

    async def enter(self, postgres_tool: Any, stage: Stage, message: str = "") -> None:
        """进入阶段：置 running、写 started_at、落库 + task_logs"""
        self._mark(stage.value, StageStatus.RUNNING.value)
        await self._persist(postgres_tool)
        await self._log_task(stage.value, "info", f"[{stage.label}] {message or '进入阶段'}")

    async def complete(self, postgres_tool: Any, stage: Stage, message: str = "") -> None:
        """完成阶段：置 success、写 finished_at/duration_ms、落库 + task_logs"""
        self._mark(stage.value, StageStatus.SUCCESS.value)
        await self._persist(postgres_tool)
        await self._log_task(stage.value, "info", f"[{stage.label}] 完成 {message}")

    async def fail(self, postgres_tool: Any, stage: Stage, error: str = "") -> None:
        """失败阶段：置 failed、写 error、落库 + task_logs"""
        self._mark(stage.value, StageStatus.FAILED.value, error)
        await self._persist(postgres_tool)
        await self._log_task(stage.value, "error", f"[{stage.label}] 失败 {error}")


@asynccontextmanager
async def track_stage(
    tracker: StageTracker,
    postgres_tool: Any,
    stage: Stage,
    message: str = "",
) -> AsyncIterator[None]:
    """阶段上下文管理器：进入 → 执行 → 完成/失败

    用法：
        async with track_stage(tracker, postgres_tool, Stage.PARSE, f"{symbol} 解析"):
            md_content = await docling_tool.convert_file(pdf_data, filename)
    """
    await tracker.enter(postgres_tool, stage, message)
    try:
        yield
    except Exception as e:
        await tracker.fail(postgres_tool, stage, str(e))
        raise
    else:
        await tracker.complete(postgres_tool, stage, message)