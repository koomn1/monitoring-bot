"""
bot/modules/ai_assistant/service.py — AI Assistant

Answers free-form operational questions ("why is the API slow today?",
"summarize this week's incidents", "how is AI extraction performing?")
by combining live Quiz Space telemetry, uptime/incidents, logs, and
security posture with an LLM call. Strictly read-only.

See: modules/18-ai-assistant.md
"""

from __future__ import annotations

import json
import logging
from typing import Any

from bot.core.exceptions import ConfigurationError
from bot.integrations import ai_client
from bot.modules.logging import service as logging_service
from bot.modules.platform_insights import service as insights_service
from bot.modules.security import service as security_service

logger = logging.getLogger("modules.ai_assistant")

_SYSTEM_PROMPT = (
    "You are the Quiz Space DevOps & Platform Operations AI Assistant inside "
    "Telegram. You help administrators understand the live health, usage, AI "
    "pipeline performance, pending payments, and incidents of Quiz Space. "
    "Reply in the same language as the administrator's question (Arabic or English). "
    "Be concise, cite concrete metrics from the telemetry provided, and never "
    "invent numbers. If a data source is missing or not configured, say so plainly."
)


async def _safe(coro: Any, default: Any) -> Any:
    try:
        return await coro
    except ConfigurationError as exc:
        return {"not_configured": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI assistant context degraded: %s", exc)
        return default


async def answer_question(question: str) -> str:
    pulse = await _safe(insights_service.get_live_pulse(hours=24), {})
    uptime = await _safe(insights_service.get_uptime_and_incidents(hours=24), {})
    recent_logs = await _safe(logging_service.get_recent_command_logs(limit=10), [])
    security = await _safe(security_service.get_security_overview(), {})

    context_payload = {
        "live_pulse_24h": pulse,
        "uptime_and_incidents_24h": uptime,
        "recent_bot_commands": recent_logs,
        "security_overview": security,
    }
    prompt = (
        f"Operational Telemetry JSON:\n{json.dumps(context_payload, default=str, ensure_ascii=False)}\n\n"
        f"Administrator question: {question}"
    )

    return await ai_client.complete(_SYSTEM_PROMPT, prompt)
