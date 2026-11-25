"""bot/utils/time_utils.py — timezone-aware time helpers used across modules."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def humanize_delta(dt: datetime) -> str:
    delta = utc_now() - dt
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return f"منذ {seconds} ث"
    if seconds < 3600:
        return f"منذ {seconds // 60} د"
    if seconds < 86400:
        return f"منذ {seconds // 3600} س"
    return f"منذ {seconds // 86400} ي"
