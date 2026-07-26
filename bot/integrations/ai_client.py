"""
bot/integrations/ai_client.py

Client for the AI Assistant module's underlying LLM provider. Defaults to
the Anthropic API (Claude) but is written behind a minimal provider-agnostic
interface so AI_PROVIDER could be swapped later.

See: docs/04-environment-variables.md, modules/18-ai-assistant.md
"""

from __future__ import annotations

import logging

import httpx

from bot.config import settings
from bot.core.exceptions import ConfigurationError, ExternalServiceError
from bot.utils.retry import async_retry, is_transient_service_error

logger = logging.getLogger("integrations.ai")

_ANTHROPIC_API_BASE = "https://api.anthropic.com/v1/messages"


@async_retry(attempts=2, base_delay=1.5, exceptions=(ExternalServiceError,), retry_if=is_transient_service_error)
async def complete(system_prompt: str, user_prompt: str, *, max_tokens: int = 1024) -> str:
    if settings.ai_provider != "anthropic":
        raise ConfigurationError(f"Unsupported AI_PROVIDER: {settings.ai_provider}")
    if not settings.ai_api_key:
        raise ConfigurationError("AI_API_KEY is not configured")

    headers = {
        "x-api-key": settings.ai_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": settings.ai_model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(_ANTHROPIC_API_BASE, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return "".join(block.get("text", "") for block in data.get("content", []))
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                "AI Provider", f"{exc.response.status_code}: {exc.response.text}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError("AI Provider", str(exc)) from exc
