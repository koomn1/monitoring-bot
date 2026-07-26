"""
bot/modules/cloudflare/service.py — Cloudflare Module

Wraps bot/integrations/cloudflare_client.py with domain logic: latest
Pages deployment status, rollback orchestration.

See: modules/10-cloudflare-module.md
"""

from __future__ import annotations

from typing import Any

from bot.integrations import cloudflare_client


async def get_deployment_status() -> dict[str, Any]:
    deployment = await cloudflare_client.get_latest_pages_deployment()
    if deployment is None:
        return {"status": "unknown"}
    return {
        "id": deployment.get("id"),
        "status": deployment.get("latest_stage", {}).get("status"),
        "url": deployment.get("url"),
        "created_on": deployment.get("created_on"),
    }


async def rollback(deployment_id: str) -> dict[str, Any]:
    return await cloudflare_client.rollback_to_deployment(deployment_id)
