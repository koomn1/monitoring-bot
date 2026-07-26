"""
bot/modules/ai_assistant/service.py — AI Assistant

Answers free-form operational questions ("why is the API slow today?",
"summarize this week's incidents") by combining recent monitoring/log
data with an LLM call. Never given write access to any system — it can
only read via the other modules' service functions and respond in text.

See: modules/18-ai-assistant.md
"""

from __future__ import annotations

from bot.integrations import ai_client
from bot.modules.logging import service as logging_service
from bot.modules.security import service as security_service

_SYSTEM_PROMPT = (
    "You are the Quiz Space DevOps AI Assistant, operating inside a Telegram "
    "bot. You help administrators understand the current state of the Quiz "
    "Space infrastructure. Be concise, use the operational data provided, "
    "and never invent numbers you were not given. If the data is insufficient, "
    "say so plainly and suggest which command would provide it."
)


async def answer_question(question: str) -> str:
    recent_logs = await logging_service.get_recent_command_logs(limit=10)
    security = await security_service.get_security_overview()

    context = f"Recent command logs: {recent_logs}\nSecurity overview: {security}\n"
    prompt = f"{context}\nAdministrator question: {question}"

    return await ai_client.complete(_SYSTEM_PROMPT, prompt)
