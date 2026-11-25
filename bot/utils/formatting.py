"""bot/utils/formatting.py — shared Telegram message formatting helpers."""

from __future__ import annotations

STATUS_EMOJI = {"up": "🟢", "down": "🔴", "degraded": "🟡", "unknown": "⚪"}
STATUS_AR = {
    "up": "يعمل",
    "down": "متوقف",
    "degraded": "بطيء",
    "unknown": "غير معروف",
    "not configured": "غير مهيأ",
}


def status_line(label: str, status: str, extra: str = "") -> str:
    low = status.lower()
    emoji = STATUS_EMOJI.get(low, "⚪")
    status_text = STATUS_AR.get(low, status.capitalize())
    suffix = f" ({extra})" if extra else ""
    return f"{emoji} {label}: {status_text}{suffix}"


def format_duration_ms(ms: int) -> str:
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.2f}s"


def format_table(rows: list[dict], columns: list[str]) -> str:
    """Renders a simple monospace table for Telegram (wrapped in <pre>)."""
    widths = [max(len(str(r.get(c, ""))) for r in [dict(zip(columns, columns))] + rows) for c in columns]
    lines = ["  ".join(c.ljust(w) for c, w in zip(columns, widths))]
    for r in rows:
        lines.append("  ".join(str(r.get(c, "")).ljust(w) for c, w in zip(columns, widths)))
    return "<pre>" + "\n".join(lines) + "</pre>"
