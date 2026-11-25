"""
bot/db/repositories/platform_repo.py

Read-only telemetry repository querying Quiz Space's application tables
(users, quizzes, completions, guest_quiz_attempts, premium_requests,
ai_performance_logs, extraction_jobs, web_vitals, user_sessions,
classrooms, cosmo_conversations) via `target_db()`.

Every query degrades gracefully (logs and returns None / empty defaults)
when an optional application table or column is absent in a given
environment, so a single missing table never breaks /dashboard, /pulse,
or scheduled reports.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from bot.integrations.supabase_client import target_db

logger = logging.getLogger("repositories.platform")

_CORE_TABLES = (
    "users",
    "quizzes",
    "completions",
    "guest_quiz_attempts",
    "premium_requests",
    "classrooms",
    "ai_performance_logs",
    "extraction_jobs",
    "cosmo_conversations",
    "monitoring_logs",
    "incidents",
)


def _cutoff_iso(*, hours: int = 0, minutes: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours, minutes=minutes)).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return ordered[idx]


def _safe_count(
    table: str,
    *,
    column: str = "*",
    since_iso: str | None = None,
    since_col: str = "created_at",
    eq_filters: dict[str, Any] | None = None,
    in_filters: dict[str, list[Any]] | None = None,
) -> int | None:
    try:
        query = target_db().table(table).select(column, count="exact").limit(1)
        if since_iso is not None:
            query = query.gte(since_col, since_iso)
        for key, val in (eq_filters or {}).items():
            query = query.eq(key, val)
        for key, vals in (in_filters or {}).items():
            query = query.in_(key, vals)
        res = query.execute()
        if res.count is not None:
            return int(res.count)
        return len(res.data or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed counting table=%s: %s", table, exc)
        return None


async def get_core_table_counts() -> dict[str, int | None]:
    return {table: _safe_count(table) for table in _CORE_TABLES}


async def get_quiz_activity_summary(*, hours: int = 24) -> dict[str, Any]:
    cutoff = _cutoff_iso(hours=hours)
    total_quizzes = _safe_count("quizzes", column="id")
    quizzes_recent = _safe_count("quizzes", column="id", since_iso=cutoff)
    total_completions = _safe_count("completions", column="id")
    completions_recent = _safe_count("completions", column="id", since_iso=cutoff)
    guest_attempts_recent = _safe_count("guest_quiz_attempts", column="id", since_iso=cutoff)
    total_classrooms = _safe_count("classrooms", column="id")
    cosmo_recent = _safe_count("cosmo_conversations", column="id", since_iso=cutoff)

    avg_score_pct: float | None = None
    try:
        res = (
            target_db()
            .table("completions")
            .select("score,total_questions")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
        ratios = [
            (row["score"] / row["total_questions"]) * 100.0
            for row in (res.data or [])
            if isinstance(row.get("score"), (int, float))
            and isinstance(row.get("total_questions"), (int, float))
            and row["total_questions"] > 0
        ]
        if ratios:
            avg_score_pct = round(sum(ratios) / len(ratios), 1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed calculating avg completion score: %s", exc)

    top_quizzes: list[dict[str, Any]] = []
    try:
        res = (
            target_db()
            .table("quizzes")
            .select("id,title,total_plays,avg_rating,category")
            .order("total_plays", desc=True)
            .limit(5)
            .execute()
        )
        top_quizzes = list(res.data or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed fetching top quizzes: %s", exc)

    return {
        "hours": hours,
        "total_quizzes": total_quizzes,
        "quizzes_recent": quizzes_recent,
        "total_completions": total_completions,
        "completions_recent": completions_recent,
        "guest_attempts_recent": guest_attempts_recent,
        "avg_score_pct": avg_score_pct,
        "total_classrooms": total_classrooms,
        "cosmo_conversations_recent": cosmo_recent,
        "top_quizzes": top_quizzes,
    }


async def get_payment_requests_summary(*, limit: int = 10) -> dict[str, Any]:
    pending_count = _safe_count("premium_requests", column="id", eq_filters={"status": "pending"})
    needs_info_count = _safe_count("premium_requests", column="id", eq_filters={"status": "needs_info"})
    cutoff_7d = _cutoff_iso(hours=24 * 7)
    approved_7d = _safe_count(
        "premium_requests", column="id", since_iso=cutoff_7d, eq_filters={"status": "approved"}
    )
    rejected_7d = _safe_count(
        "premium_requests", column="id", since_iso=cutoff_7d, eq_filters={"status": "rejected"}
    )

    pending_items: list[dict[str, Any]] = []
    try:
        # Select strictly non-PII columns (no email or payment_screenshot).
        res = (
            target_db()
            .table("premium_requests")
            .select("id,plan_name,status,created_at")
            .in_("status", ["pending", "needs_info"])
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        pending_items = list(res.data or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed fetching pending premium_requests: %s", exc)

    return {
        "pending_count": pending_count,
        "needs_info_count": needs_info_count,
        "approved_7d": approved_7d,
        "rejected_7d": rejected_7d,
        "pending_items": pending_items,
    }


async def get_ai_health_summary(*, hours: int = 24, error_limit: int = 5) -> dict[str, Any]:
    cutoff = _cutoff_iso(hours=hours)
    rows: list[dict[str, Any]] = []
    available = True
    try:
        res = (
            target_db()
            .table("ai_performance_logs")
            .select("operation,provider,model,status,latency_ms,error_category,error_message,created_at")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
        rows = list(res.data or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed fetching ai_performance_logs: %s", exc)
        available = False

    total_calls = len(rows)
    success_count = sum(1 for r in rows if r.get("status") == "success")
    error_count = sum(1 for r in rows if r.get("status") == "error")
    success_rate_pct = round((success_count / total_calls) * 100.0, 1) if total_calls else None

    latencies = [
        int(r["latency_ms"])
        for r in rows
        if isinstance(r.get("latency_ms"), (int, float)) and r["latency_ms"] >= 0
    ]
    avg_latency_ms = round(sum(latencies) / len(latencies)) if latencies else None
    p95_latency_ms = _percentile(latencies, 95.0)

    by_provider: dict[str, dict[str, Any]] = {}
    by_operation: dict[str, dict[str, int]] = {}
    recent_errors: list[dict[str, Any]] = []

    for row in rows:
        prov = str(row.get("provider") or "unknown")
        op = str(row.get("operation") or "unknown")
        is_err = row.get("status") == "error"

        prov_entry = by_provider.setdefault(prov, {"calls": 0, "errors": 0, "_latencies": []})
        prov_entry["calls"] += 1
        if is_err:
            prov_entry["errors"] += 1
        if isinstance(row.get("latency_ms"), (int, float)) and row["latency_ms"] >= 0:
            prov_entry["_latencies"].append(int(row["latency_ms"]))

        op_entry = by_operation.setdefault(op, {"calls": 0, "errors": 0})
        op_entry["calls"] += 1
        if is_err:
            op_entry["errors"] += 1

        if is_err and len(recent_errors) < error_limit:
            recent_errors.append(
                {
                    "user_id": row.get("user_id"),
                    "operation": op,
                    "provider": prov,
                    "model": row.get("model"),
                    "latency_ms": row.get("latency_ms"),
                    "error_category": row.get("error_category"),
                    "error_message": (row.get("error_message") or "")[:300],
                    "created_at": row.get("created_at"),
                }
            )

    for prov_entry in by_provider.values():
        lats = prov_entry.pop("_latencies")
        prov_entry["avg_latency_ms"] = round(sum(lats) / len(lats)) if lats else None

    return {
        "available": available,
        "hours": hours,
        "total_calls": total_calls,
        "success_count": success_count,
        "error_count": error_count,
        "success_rate_pct": success_rate_pct,
        "avg_latency_ms": avg_latency_ms,
        "p95_latency_ms": p95_latency_ms,
        "by_provider": by_provider,
        "by_operation": by_operation,
        "recent_errors": recent_errors,
    }


async def get_extraction_jobs_summary(*, hours: int = 24, stuck_minutes: int = 20) -> dict[str, Any]:
    cutoff = _cutoff_iso(hours=hours)
    stuck_cutoff = datetime.now(timezone.utc) - timedelta(minutes=stuck_minutes)
    available = True

    active_rows: list[dict[str, Any]] = []
    recent_rows: list[dict[str, Any]] = []
    try:
        active_res = (
            target_db()
            .table("extraction_jobs")
            .select(
                "id,extraction_mode,status,progress_percentage,provider,"
                "error_message,processing_started_at,updated_at,created_at"
            )
            .in_("status", ["pending", "processing"])
            .order("created_at", desc=False)
            .limit(100)
            .execute()
        )
        active_rows = list(active_res.data or [])

        recent_res = (
            target_db()
            .table("extraction_jobs")
            .select("id,extraction_mode,status,provider,error_message,created_at,completed_at")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        recent_rows = list(recent_res.data or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed fetching extraction_jobs: %s", exc)
        available = False

    pending_count = sum(1 for r in active_rows if r.get("status") == "pending")
    processing_count = sum(1 for r in active_rows if r.get("status") == "processing")
    complete_recent = sum(1 for r in recent_rows if r.get("status") == "complete")
    error_recent = sum(1 for r in recent_rows if r.get("status") == "error")

    stuck_jobs: list[dict[str, Any]] = []
    for row in active_rows:
        if row.get("status") != "processing":
            continue
        ts = _parse_iso(row.get("updated_at")) or _parse_iso(row.get("processing_started_at"))
        if ts is not None and ts < stuck_cutoff:
            stuck_jobs.append(
                {
                    "id": row.get("id"),
                    "progress_percentage": row.get("progress_percentage", 0),
                    "provider": row.get("provider"),
                    "updated_at": row.get("updated_at") or row.get("processing_started_at"),
                }
            )

    recent_errors = [
        {
            "id": r.get("id"),
            "extraction_mode": r.get("extraction_mode"),
            "provider": r.get("provider"),
            "error_message": (r.get("error_message") or "")[:300],
            "created_at": r.get("created_at"),
        }
        for r in recent_rows
        if r.get("status") == "error"
    ][:10]

    return {
        "available": available,
        "hours": hours,
        "pending_count": pending_count,
        "processing_count": processing_count,
        "complete_recent": complete_recent,
        "error_recent": error_recent,
        "stuck_jobs": stuck_jobs,
        "recent_errors": recent_errors,
    }


async def get_web_vitals_summary(*, hours: int = 24) -> dict[str, dict[str, Any]]:
    cutoff = _cutoff_iso(hours=hours)
    metrics: dict[str, list[float]] = {}
    try:
        res = (
            target_db()
            .table("web_vitals")
            .select("metric_name,metric_value")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
        for row in res.data or []:
            name = row.get("metric_name")
            val = row.get("metric_value")
            if isinstance(name, str) and isinstance(val, (int, float)):
                metrics.setdefault(name, []).append(float(val))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed fetching web_vitals: %s", exc)
        return {}

    summary: dict[str, dict[str, Any]] = {}
    for name, vals in metrics.items():
        ordered = sorted(vals)
        p75_idx = max(0, min(len(ordered) - 1, math.ceil(0.75 * len(ordered)) - 1))
        avg_val = sum(vals) / len(vals)
        p75_val = ordered[p75_idx]
        if name == "CLS":
            summary[name] = {"samples": len(vals), "avg": round(avg_val, 3), "p75": round(p75_val, 3)}
        else:
            summary[name] = {"samples": len(vals), "avg": round(avg_val), "p75": round(p75_val)}
    return summary


async def get_active_sessions_summary() -> dict[str, int | None]:
    return {
        "active_1h": _safe_count("user_sessions", column="id", since_iso=_cutoff_iso(hours=1), since_col="last_active"),
        "active_24h": _safe_count(
            "user_sessions", column="id", since_iso=_cutoff_iso(hours=24), since_col="last_active"
        ),
    }
