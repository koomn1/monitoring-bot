"""
bot/config.py

Loads and validates all environment variables used across the Quiz Space
Telegram DevOps Bot. This is the single source of truth for configuration —
no module should call os.environ directly; everything goes through the
`settings` object exported from this file.

See: docs/04-environment-variables.md
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


def _get(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"See docs/04-environment-variables.md for the full list."
        )
    return value


def _get_int_list(name: str) -> List[int]:
    raw = os.environ.get(name, "")
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # --- Core / Environment -------------------------------------------------
    environment: str = field(default_factory=lambda: _get("ENVIRONMENT", "development"))
    log_level: str = field(default_factory=lambda: _get("LOG_LEVEL", "INFO"))

    # --- Telegram -------------------------------------------------------------
    telegram_bot_token: Optional[str] = field(default_factory=lambda: _get("TELEGRAM_BOT_TOKEN"))
    telegram_webhook_url: Optional[str] = field(default_factory=lambda: _get("TELEGRAM_WEBHOOK_URL"))
    telegram_use_webhook: bool = field(default_factory=lambda: _get_bool("TELEGRAM_USE_WEBHOOK", False))
    telegram_alert_channel_id: Optional[str] = field(default_factory=lambda: _get("TELEGRAM_ALERT_CHANNEL_ID"))
    telegram_error_channel_id: Optional[str] = field(default_factory=lambda: _get("TELEGRAM_ERROR_CHANNEL_ID"))

    # --- Admin / Access control -----------------------------------------------
    owner_user_ids: List[int] = field(default_factory=lambda: _get_int_list("OWNER_USER_IDS"))
    admin_user_ids: List[int] = field(default_factory=lambda: _get_int_list("ADMIN_USER_IDS"))
    viewer_user_ids: List[int] = field(default_factory=lambda: _get_int_list("VIEWER_USER_IDS"))

    # --- Supabase ---------------------------------------------------------------
    supabase_url: Optional[str] = field(default_factory=lambda: _get("SUPABASE_URL"))
    supabase_anon_key: Optional[str] = field(default_factory=lambda: _get("SUPABASE_ANON_KEY"))
    supabase_service_role_key: Optional[str] = field(default_factory=lambda: _get("SUPABASE_SERVICE_ROLE_KEY"))

    # --- GitHub -------------------------------------------------------------------
    github_token: Optional[str] = field(default_factory=lambda: _get("GITHUB_TOKEN"))
    github_repo: Optional[str] = field(default_factory=lambda: _get("GITHUB_REPO"))  # "owner/repo"
    github_webhook_secret: Optional[str] = field(default_factory=lambda: _get("GITHUB_WEBHOOK_SECRET"))

    # --- Cloudflare ------------------------------------------------------------
    cloudflare_api_token: Optional[str] = field(default_factory=lambda: _get("CLOUDFLARE_API_TOKEN"))
    cloudflare_account_id: Optional[str] = field(default_factory=lambda: _get("CLOUDFLARE_ACCOUNT_ID"))
    cloudflare_project_name: Optional[str] = field(default_factory=lambda: _get("CLOUDFLARE_PROJECT_NAME"))

    # --- Firebase ----------------------------------------------------------------
    firebase_project_id: Optional[str] = field(default_factory=lambda: _get("FIREBASE_PROJECT_ID"))
    firebase_service_account_json: Optional[str] = field(
        default_factory=lambda: _get("FIREBASE_SERVICE_ACCOUNT_JSON")
    )

    # --- Sentry ---------------------------------------------------------------------
    sentry_dsn: Optional[str] = field(default_factory=lambda: _get("SENTRY_DSN"))
    sentry_auth_token: Optional[str] = field(default_factory=lambda: _get("SENTRY_AUTH_TOKEN"))
    sentry_org_slug: Optional[str] = field(default_factory=lambda: _get("SENTRY_ORG_SLUG"))
    sentry_project_slug: Optional[str] = field(default_factory=lambda: _get("SENTRY_PROJECT_SLUG"))
    sentry_webhook_secret: Optional[str] = field(default_factory=lambda: _get("SENTRY_WEBHOOK_SECRET"))

    # --- Analytics ------------------------------------------------------------------
    ga_measurement_id: Optional[str] = field(default_factory=lambda: _get("GA_MEASUREMENT_ID"))
    ga_api_secret: Optional[str] = field(default_factory=lambda: _get("GA_API_SECRET"))
    umami_api_url: Optional[str] = field(default_factory=lambda: _get("UMAMI_API_URL"))
    umami_api_key: Optional[str] = field(default_factory=lambda: _get("UMAMI_API_KEY"))
    umami_website_id: Optional[str] = field(default_factory=lambda: _get("UMAMI_WEBSITE_ID"))

    # --- Monitored targets -----------------------------------------------------------
    website_url: Optional[str] = field(default_factory=lambda: _get("WEBSITE_URL"))
    api_base_url: Optional[str] = field(default_factory=lambda: _get("API_BASE_URL"))

    # --- AI Assistant ------------------------------------------------------------------
    ai_provider: str = field(default_factory=lambda: _get("AI_PROVIDER", "anthropic"))
    ai_api_key: Optional[str] = field(default_factory=lambda: _get("AI_API_KEY"))
    ai_model: str = field(default_factory=lambda: _get("AI_MODEL", "claude-sonnet-5"))

    # --- Automation intervals (seconds / cron) ------------------------------------------
    health_check_interval_seconds: int = field(
        default_factory=lambda: int(_get("HEALTH_CHECK_INTERVAL_SECONDS", "300"))
    )
    backup_cron: str = field(default_factory=lambda: _get("BACKUP_CRON", "0 3 * * *"))
    daily_report_cron: str = field(default_factory=lambda: _get("DAILY_REPORT_CRON", "0 8 * * *"))
    weekly_report_cron: str = field(default_factory=lambda: _get("WEEKLY_REPORT_CRON", "0 8 * * 1"))
    monthly_report_cron: str = field(default_factory=lambda: _get("MONTHLY_REPORT_CRON", "0 8 1 * *"))

    def validate(self) -> None:
        """
        Fail fast on missing critical configuration. Called once at startup
        in bot/main.py. Non-critical integrations (e.g. Firebase, Sentry) are
        allowed to be unset — the relevant modules must degrade gracefully
        (see each module's "Error Handling" section).
        """
        missing = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_service_role_key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
        if not (self.owner_user_ids or self.admin_user_ids):
            missing.append("OWNER_USER_IDS (at least one owner must be configured)")

        if missing:
            raise RuntimeError(
                "Missing required configuration: " + ", ".join(missing) +
                ". See docs/04-environment-variables.md."
            )


settings = Settings()
