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


def format_cards(
    rows: list[dict],
    fields: list[tuple[str, str]],
    *,
    title_key: str = "title",
    max_value_len: int = 80,
) -> str:
    """Render records as readable RTL-friendly Telegram cards.

    Monospace tables are difficult to scan in Arabic because mixed RTL/LTR
    columns lose their alignment on mobile. Cards keep each label/value pair
    on its own line and are safe for HTML parse mode.
    """
    cards: list[str] = []
    for row in rows:
        title_value = row.get(title_key) or row.get("id") or "سجل"
        lines = [f"<b>{html.escape(str(title_value)[:max_value_len], quote=False)}</b>"]
        for label, key in fields:
            raw = row.get(key)
            value = "—" if raw is None or raw == "" else str(raw)
            value = value.replace("\n", " ").strip()[:max_value_len]
            lines.append(
                f"• {html.escape(label, quote=False)}: "
                f"<b>{html.escape(value, quote=False)}</b>"
            )
        cards.append("\n".join(lines))
    return "\n\n────────────\n\n".join(cards)
