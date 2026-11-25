"""
bot/integrations/ai_client.py

Client for the AI Assistant module's underlying LLM provider. Supports
Anthropic (Claude), OpenAI, and OpenRouter so administrators can use
whichever provider key they already have configured.

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
_OPENAI_API_BASE = "https://api.openai.com/v1/chat/completions"
_OPENROUTER_API_BASE = "https://openrouter.ai/api/v1/chat/completions"


@async_retry(attempts=2, base_delay=1.5, exceptions=(ExternalServiceError,), retry_if=is_transient_service_error)
async def complete(system_prompt: str, user_prompt: str, *, max_tokens: int = 1024) -> str:
    provider = (settings.ai_provider or "anthropic").strip().lower()
    if provider not in {"anthropic", "openai", "openrouter"}:
        raise ConfigurationError(f"Unsupported AI_PROVIDER: {settings.ai_provider}")
    if not settings.ai_api_key:
        raise ConfigurationError("AI_API_KEY is not configured")

    if provider == "anthropic":
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
        url = _ANTHROPIC_API_BASE
    else:
        headers = {
            "Authorization": f"Bearer {settings.ai_api_key}",
            "content-type": "application/json",
        }
        payload = {
            "model": settings.ai_model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        url = _OPENROUTER_API_BASE if provider == "openrouter" else _OPENAI_API_BASE

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if provider == "anthropic":
                return "".join(block.get("text", "") for block in data.get("content", []))
            choices = data.get("choices") or []
            if choices:
                return str((choices[0].get("message") or {}).get("content") or "")
            return ""
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                "AI Provider", f"{exc.response.status_code}: {exc.response.text}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError("AI Provider", str(exc)) from exc
