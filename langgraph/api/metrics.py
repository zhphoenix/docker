"""Agent Metrics API — 按 agent 维度聚合运行指标（AC-P3-3）

规范 §12 六项指标：Today Runs / Success / Failed / Avg Latency / Avg Tokens / Avg Cost
+ 趋势序列（Runs / Latency / Tokens / Error Rate）。
数据源：agent_runs（批次1 AC-B3 埋点，status ∈ running/completed/failed）；
成本按 config/pricing.yaml 计价（无单价 → 置 0）。
"""

import logging
import math
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from config.policy_loader import get_agent_price
from tools.postgres import postgres_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["metrics"])

RANGE_DAYS = {"1d": 1, "7d": 7, "30d": 30}

# 参与时长统计的终态（running 无 duration_ms 语义）
# chat.py 用 success/failed；invoke_tracked 用 completed/failed
_FINISHED = ("success", "completed", "failed")


def _estimate_cost(agent_id: str, tokens_in: int, tokens_out: int) -> float:
    """估算 tokens 对应的 LLM 成本（美元）；无单价 → 置 0"""
    price = get_agent_price(agent_id)
    cost = (
        tokens_in * price["input_per_mtok"]
        + tokens_out * price["output_per_mtok"]
    ) / 1_000_000
    return round(cost, 6)


def _to_float(value) -> float:
    """asyncpg numeric → float（NaN/Inf 视为 0）"""
    try:
        f = float(value) if value is not None else 0.0
        return f if math.isfinite(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


@router.get("/{agent_id}/metrics")
async def get_agent_metrics(
    agent_id: str,
    range_days: str = Query("7d", alias="range", pattern="^(1d|7d|30d)$"),
):
    """Agent 运行指标（六项汇总 + 按天趋势）

    Args:
        agent_id: 规范 Agent 名（如 news_intelligence / knowledge_ingestion）
        range_days: 时间范围 1d / 7d / 30d，默认 7d
    """
    days = RANGE_DAYS.get(range_days, 7)

    # Agent 存在性校验（与 /api/agents/{agent_id} 一致；无数据也返回零值指标）
    from api.agents import list_agents

    all_agents = (await list_agents())["agents"]
    if not any(a["id"] == agent_id for a in all_agents):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    # ── 汇总指标 ──────────────────────────────────────────
    rows = await postgres_tool.query(
        "SELECT "
        "  COUNT(*) AS runs, "
        "  COUNT(*) FILTER (WHERE status = 'completed') AS success, "
        "  COUNT(*) FILTER (WHERE status = 'failed') AS failed, "
        "  COALESCE(AVG(duration_ms) FILTER (WHERE status = ANY($3)), 0) AS avg_latency_ms, "
        "  COALESCE(AVG(tokens_in + tokens_out), 0) AS avg_tokens, "
        "  COALESCE(SUM(tokens_in), 0) AS total_tokens_in, "
        "  COALESCE(SUM(tokens_out), 0) AS total_tokens_out "
        "FROM agent_runs "
        "WHERE agent_id = $1 AND created_at >= NOW() - make_interval(days => $2)",
        agent_id,
        days,
        list(_FINISHED),
    )
    row = rows[0] if rows else {}
    runs = int(row.get("runs") or 0)
    success = int(row.get("success") or 0)
    failed = int(row.get("failed") or 0)
    avg_latency_ms = _to_float(row.get("avg_latency_ms"))
    avg_tokens = _to_float(row.get("avg_tokens"))
    total_tokens_in = int(row.get("total_tokens_in") or 0)
    total_tokens_out = int(row.get("total_tokens_out") or 0)
    total_cost = _estimate_cost(agent_id, total_tokens_in, total_tokens_out)

    summary = {
        "runs": runs,
        "success": success,
        "failed": failed,
        "success_rate": round(100.0 * success / runs, 2) if runs else 0.0,
        "avg_latency_ms": round(avg_latency_ms, 1),
        "avg_tokens": round(avg_tokens, 1),
        "avg_cost": round(total_cost / runs, 6) if runs else 0.0,
        "total_cost": total_cost,
    }

    # ── 按天趋势 ──────────────────────────────────────────
    trend_rows = await postgres_tool.query(
        "SELECT "
        "  created_at::date AS date, "
        "  COUNT(*) AS runs, "
        "  COALESCE(AVG(duration_ms) FILTER (WHERE status = ANY($3)), 0) AS avg_latency_ms, "
        "  COALESCE(AVG(tokens_in + tokens_out), 0) AS avg_tokens, "
        "  ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'failed') "
        "        / NULLIF(COUNT(*), 0), 2) AS error_rate "
        "FROM agent_runs "
        "WHERE agent_id = $1 AND created_at >= NOW() - make_interval(days => $2) "
        "GROUP BY created_at::date ORDER BY created_at::date",
        agent_id,
        days,
        list(_FINISHED),
    )
    trend = []
    for tr in trend_rows:
        d = tr.get("date")
        trend.append(
            {
                "date": d.isoformat() if isinstance(d, date) else str(d),
                "runs": int(tr.get("runs") or 0),
                "avg_latency_ms": round(_to_float(tr.get("avg_latency_ms")), 1),
                "avg_tokens": round(_to_float(tr.get("avg_tokens")), 1),
                "error_rate": _to_float(tr.get("error_rate")),
            }
        )

    return {
        "agent_id": agent_id,
        "range": range_days,
        "summary": summary,
        "trend": trend,
    }


@router.get("/{agent_id}/prompt-variants")
async def get_prompt_variants(
    agent_id: str,
    range_days: str = Query("7d", alias="range", pattern="^(1d|7d|30d)$"),
):
    """A/B Prompt 变体对比（AC-P4-3）

    按 agent_runs.variant 分组聚合，对比各变体的运行次数 / 成功率 / 平均耗时。
    仅统计有 variant 打标的记录（未参与 A/B 的运行无 variant，不参与对比）。

    Args:
        agent_id: 规范 Agent 名（如 chat / research）
        range_days: 时间范围 1d / 7d / 30d，默认 7d
    """
    days = RANGE_DAYS.get(range_days, 7)

    rows = await postgres_tool.query(
        "SELECT "
        "  variant, "
        "  COUNT(*) AS runs, "
        "  COUNT(*) FILTER (WHERE status = 'success') AS success, "
        "  COUNT(*) FILTER (WHERE status = 'failed') AS failed, "
        "  COALESCE(AVG(duration_ms) FILTER (WHERE status = ANY($3)), 0) AS avg_latency_ms, "
        "  COALESCE(AVG(tokens_in + tokens_out), 0) AS avg_tokens "
        "FROM agent_runs "
        "WHERE agent_id = $1 AND created_at >= NOW() - make_interval(days => $2) "
        "  AND variant IS NOT NULL "
        "GROUP BY variant "
        "ORDER BY variant",
        agent_id,
        days,
        list(_FINISHED),
    )

    variants = []
    for r in rows:
        runs = int(r.get("runs") or 0)
        success = int(r.get("success") or 0)
        failed = int(r.get("failed") or 0)
        variants.append(
            {
                "variant": r.get("variant"),
                "runs": runs,
                "success": success,
                "failed": failed,
                "success_rate": round(100.0 * success / runs, 2) if runs else 0.0,
                "avg_latency_ms": round(_to_float(r.get("avg_latency_ms")), 1),
                "avg_tokens": round(_to_float(r.get("avg_tokens")), 1),
            }
        )

    return {
        "agent_id": agent_id,
        "range": range_days,
        "variants": variants,
        "total": len(variants),
    }