"""bot/utils/formatting.py — shared Telegram message formatting helpers."""

from __future__ import annotations

import html

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


def format_table(rows: list[dict], columns: list[str], *, max_col_width: int = 18) -> str:
    """Renders a clean monospace table for Telegram (HTML-escaped inside <pre>)."""
    def _cell(val: object) -> str:
        text = str(val if val is not None else "-").replace("\n", " ").strip()
        if len(text) > max_col_width:
            return text[: max_col_width - 1] + "…"
        return text

    str_rows = [{c: _cell(r.get(c)) for c in columns} for r in rows]
    widths = [
        max(len(c), *(len(r[c]) for r in str_rows)) if str_rows else len(c)
        for c in columns
    ]
    header = " | ".join(c.ljust(w) for c, w in zip(columns, widths))
    sep = "-+-".join("-" * w for w in widths)
    lines = [header, sep]
    for r in str_rows:
        lines.append(" | ".join(r[c].ljust(w) for c, w in zip(columns, widths)))
    return "<pre>" + html.escape("\n".join(lines), quote=False) + "</pre>"
