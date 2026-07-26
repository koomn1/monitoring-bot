"""
bot/utils/style.py

Single source of truth for the Bot's visual/text style: which emoji
means what, and how titles/messages are composed. Every module
formatting a Telegram message should import from here instead of
hardcoding an emoji inline, so the vocabulary stays consistent
Bot-wide — a 🔴 always means "down/failed", never anything else, and
no emoji is ever reused for two unrelated meanings.

Style rules:
  - One emoji per line, placed at the start of the line only.
  - Bold (<b>) for the message title only, never for body text.
  - No exclamation marks except for genuinely urgent alerts (service
    down, security alert) — routine confirmations stay calm.
  - Numbers and durations are always given units (ms, s, %) — never
    a bare number that could be misread.

See: modules/17-telegram-commands.md, modules/19-notifications.md
"""

from __future__ import annotations

EMOJI: dict[str, str] = {
    # states
    "up": "🟢",
    "down": "🔴",
    "degraded": "🟡",
    "unknown": "⚪",
    # actions
    "deploy": "🚀",
    "build": "🔨",
    "rollback": "⏪",
    "backup": "💾",
    "restore": "♻️",
    "refresh": "🔄",
    # domains
    "database": "🗄️",
    "storage": "📦",
    "security": "🛡️",
    "analytics": "📈",
    "reports": "📊",
    "logs": "📜",
    "errors": "🐛",
    "users": "👥",
    "system": "🖥️",
    "settings": "⚙️",
    "ai": "🤖",
    "dashboard": "📡",
    # outcomes
    "success": "✅",
    "failure": "❌",
    "warning": "⚠️",
    "confirm": "✅",
    "cancel": "❌",
    "wave": "👋",
    "premium": "⭐",
    "payment": "💰",
}


def title(text: str, emoji_key: str | None = None) -> str:
    """Renders a bold message title with an optional leading emoji,
    e.g. title("System Status", "dashboard") -> '📡 <b>System Status</b>'"""
    prefix = f"{EMOJI[emoji_key]} " if emoji_key else ""
    return f"{prefix}<b>{text}</b>"


def line(text: str, emoji_key: str | None = None) -> str:
    """Renders a single body line with an optional leading emoji."""
    prefix = f"{EMOJI[emoji_key]} " if emoji_key else ""
    return f"{prefix}{text}"
