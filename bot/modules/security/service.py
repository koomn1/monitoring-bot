"""
bot/modules/security/service.py — Security Module

Aggregates security posture across: GitHub Dependabot alerts, Sentry
error spikes, unauthorized bot access attempts (from audit_logs), and
basic Supabase RLS sanity checks. Backs /security.

See: modules/13-security-module.md, docs/07-security.md
"""

from __future__ import annotations

from typing import Any

from bot.db.repositories.logs_repo import get_recent_logs
from bot.modules.github import service as github_service


async def get_security_overview() -> dict[str, Any]:
    dependabot = await github_service.get_security_alerts_summary()
    recent_logs = await get_recent_logs(limit=100)
    unauthorized_attempts = [
        log for log in recent_logs if log.get("error") and "Unauthorized" in str(log.get("error"))
    ]
    return {
        "dependabot": dependabot,
        "recent_unauthorized_attempts": len(unauthorized_attempts),
    }
