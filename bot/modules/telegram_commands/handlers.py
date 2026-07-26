"""
bot/modules/telegram_commands/handlers.py — Telegram Commands

Registers every /command with bot/core/router.py via the @command
decorator. This file contains NO business logic itself — every handler
is a thin adapter that calls into the relevant module's service.py and
formats the result for Telegram. Importing this module (done once in
bot/main.py) is what populates the router's registry.

See: modules/17-telegram-commands.md
"""

from __future__ import annotations

import re

from bot.core.router import CommandContext, command, registered_commands
from bot.utils.formatting import status_line
from bot.utils.style import title


# --- General ------------------------------------------------------------

@command("start")
async def handle_start(ctx: CommandContext) -> str:
    from bot.modules.auth import service as auth_service

    await auth_service.authenticate(ctx.user_id, username=None)
    return (
        f"{title('Quiz Space DevOps Bot', 'wave')}\n\n"
        "I monitor, deploy, back up, and report on Quiz Space — right here in Telegram.\n\n"
        "Pick something below, or send /help for the full command list."
    )


# Grouped, in the order an admin actually reaches for them.
_HELP_GROUPS: list[tuple[str, list[str]]] = [
    ("Monitoring", ["status", "dashboard", "database", "storage", "system"]),
    ("Users", ["users", "user"]),
    ("Deployment", ["deploy", "build", "rollback"]),
    ("Backup & Restore", ["backup", "restore"]),
    ("Observability", ["logs", "errors", "security"]),
    ("Insights", ["analytics", "reports"]),
    ("Admin", ["settings", "setrole"]),
]


@command("help")
async def handle_help(ctx: CommandContext) -> str:
    known = set(registered_commands())
    lines = [title("Available Commands"), ""]
    seen: set[str] = set()
    for group_name, cmds in _HELP_GROUPS:
        present = [c for c in cmds if c in known]
        if not present:
            continue
        lines.append(f"<b>{group_name}</b>")
        lines.extend(f"/{c}" for c in present)
        lines.append("")
        seen.update(present)
    leftover = sorted(known - seen - {"start", "help"})
    if leftover:
        lines.append("<b>Other</b>")
        lines.extend(f"/{c}" for c in leftover)
    return "\n".join(lines).strip()


# --- Monitoring -----------------------------------------------------------

@command("status")
async def handle_status(ctx: CommandContext) -> str:
    from bot.modules.api_monitor import service as api_monitor
    from bot.modules.database_monitor import service as database_monitor
    from bot.modules.storage_monitor import service as storage_monitor
    from bot.modules.website_monitor import service as website_monitor

    website = await website_monitor.check_website()
    api = await api_monitor.check_api()
    database = await database_monitor.check_database()
    storage = await storage_monitor.check_storage()

    return (
        title("Quiz Space — System Status", "dashboard") + "\n"
        + status_line("Website", website["status"], f"{website['latency_ms']}ms") + "\n"
        + status_line("API", api["status"], f"{api['latency_ms']}ms") + "\n"
        + status_line("Database", database["status"]) + "\n"
        + status_line("Storage", storage["status"])
    )


@command("dashboard")
async def handle_dashboard(ctx: CommandContext) -> str:
    from bot.modules.analytics import service as analytics_service
    from bot.modules.deployment import service as deployment_service

    analytics = await analytics_service.get_analytics_summary()
    deployment = await deployment_service.get_deployment_status()
    return (
        title("Quiz Space — Dashboard", "reports") + "\n"
        f"Last deployment: {deployment.get('conclusion', deployment.get('status', 'unknown'))}\n"
        f"Errors (24h): {analytics.get('error_count', 'N/A')}"
    )


# --- Users -----------------------------------------------------------------

@command("users")
async def handle_users(ctx: CommandContext) -> str:
    from bot.modules.users import service as users_service

    summary = await users_service.get_user_summary()
    return (
        f"{title('Users', 'users')}\n"
        f"Total: {summary['total_users']}\n"
        f"Premium: {summary['premium_users']}\n"
        f"Recent signups: {len(summary['recent_signups'])}"
    )


# users.uid is `text` (a Supabase Auth UID stored as a string — see
# the RLS policies on the `users` table, which compare
# (auth.uid())::text = uid). It is not guaranteed to be a dashed UUID,
# so this only rejects obviously-invalid input (empty, whitespace,
# suspiciously long) rather than enforcing a specific ID format.
_UID_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@command("user")
async def handle_user(ctx: CommandContext) -> str:
    from bot.modules.users import service as users_service

    if not ctx.args:
        return "Usage: /user <uid_or_email>"
    identifier = ctx.args[0]
    if not (_UID_RE.match(identifier) or _EMAIL_RE.match(identifier)):
        return "Invalid identifier — expected a user uid or an email address."
    detail = await users_service.get_user_detail(identifier)
    if detail is None:
        return f"No user found matching '{identifier}'."
    lines = [f"{k}: {v}" for k, v in detail.items() if k not in ("uid",)]
    return f"{title('User', 'users')}\nuid: {detail.get('uid')}\n" + "\n".join(lines)


# --- Infrastructure ----------------------------------------------------------

@command("database")
async def handle_database(ctx: CommandContext) -> str:
    from bot.modules.database_monitor import service as database_monitor

    result = await database_monitor.check_database()
    return status_line("Database", result["status"], f"{result['latency_ms']}ms")


@command("storage")
async def handle_storage(ctx: CommandContext) -> str:
    from bot.modules.storage_monitor import service as storage_monitor

    result = await storage_monitor.check_storage()
    return status_line("Storage", result["status"], f"{result['bucket_count']} buckets")


@command("system")
async def handle_system(ctx: CommandContext) -> str:
    from bot.modules.cloudflare import service as cloudflare_service
    from bot.modules.firebase import service as firebase_service
    from bot.modules.github import service as github_service

    repo = await github_service.get_repo_status()
    cf = await cloudflare_service.get_deployment_status()
    fb = await firebase_service.get_status()
    return (
        "🖥️ <b>System Overview</b>\n"
        f"GitHub: {repo['latest_commit_sha']} — {repo['latest_commit_message']}\n"
        f"Cloudflare Pages: {cf.get('status', 'unknown')}\n"
        f"Firebase: {fb['status']}"
    )


# --- Deployment ----------------------------------------------------------------

@command("deploy")
async def handle_deploy(ctx: CommandContext) -> str:
    from bot.modules.deployment import service as deployment_service

    confirmed = "confirm" in ctx.args
    return await deployment_service.trigger_deploy(confirmed=confirmed)


@command("build")
async def handle_build(ctx: CommandContext) -> str:
    from bot.modules.deployment import service as deployment_service

    confirmed = "confirm" in ctx.args
    return await deployment_service.trigger_build(confirmed=confirmed)


@command("rollback")
async def handle_rollback(ctx: CommandContext) -> str:
    from bot.modules.deployment import service as deployment_service

    confirmed = "confirm" in ctx.args
    target_sha = next((a for a in ctx.args if a != "confirm"), None)
    return await deployment_service.trigger_rollback(confirmed=confirmed, target_sha=target_sha)


# --- Observability -----------------------------------------------------------

@command("logs")
async def handle_logs(ctx: CommandContext) -> str:
    from bot.modules.logging import service as logging_service

    logs = await logging_service.get_recent_command_logs(limit=10)
    lines = [f"/{log['command']} — {log['duration_ms']}ms" for log in logs]
    return "📜 <b>Recent Activity</b>\n" + "\n".join(lines) if lines else "No recent activity."


@command("errors")
async def handle_errors(ctx: CommandContext) -> str:
    from bot.integrations import sentry_client

    issues = await sentry_client.get_recent_issues(limit=10)
    if not issues:
        return "✅ No unresolved errors."
    lines = [f"• {issue.get('title', 'Unknown error')} ({issue.get('count', '?')}x)" for issue in issues]
    return "🐛 <b>Recent Errors</b>\n" + "\n".join(lines)


@command("security")
async def handle_security(ctx: CommandContext) -> str:
    from bot.modules.security import service as security_service

    overview = await security_service.get_security_overview()
    return (
        "🛡️ <b>Security Overview</b>\n"
        f"Open Dependabot alerts: {overview['dependabot']['total_open']}\n"
        f"Recent unauthorized attempts: {overview['recent_unauthorized_attempts']}"
    )


# --- Backup / Restore --------------------------------------------------------------

@command("backup")
async def handle_backup(ctx: CommandContext) -> str:
    from bot.modules.backup import service as backup_service

    if ctx.args and ctx.args[0] == "list":
        backups = await backup_service.list_backups()
        if not backups:
            return "No backups found yet."
        lines = [
            f"• {b['backup_id']} — {b['artifact_name']} ({b['created_at']})"
            for b in backups[:10]
        ]
        return f"{title('Available Backups', 'backup')}\n" + "\n".join(lines)

    confirmed = "confirm" in ctx.args
    return await backup_service.trigger_backup(confirmed=confirmed)


@command("restore")
async def handle_restore(ctx: CommandContext) -> str:
    from bot.modules.backup import service as backup_service

    if not ctx.args:
        return "Usage: /restore <backup_id> [confirm]\nSee /backup list for available backup IDs."
    backup_id = ctx.args[0]
    if not backup_id.isdigit():
        return f"Invalid backup_id '{backup_id}' — expected a numeric ID from /backup list."
    confirmed = "confirm" in ctx.args
    return await backup_service.trigger_restore(confirmed=confirmed, backup_id=backup_id)


# --- Analytics / Reports -------------------------------------------------------------

@command("analytics")
async def handle_analytics(ctx: CommandContext) -> str:
    from bot.modules.analytics import service as analytics_service

    summary = await analytics_service.get_analytics_summary()
    return f"📈 <b>Analytics</b>\nErrors (24h): {summary.get('error_count', 'N/A')}"


@command("reports")
async def handle_reports(ctx: CommandContext) -> str:
    from bot.modules.reports import service as reports_service

    report_type = ctx.args[0] if ctx.args else "daily"
    report = await reports_service.get_report(report_type)
    if report is None:
        return f"No '{report_type}' report has been generated yet."
    return report["content"]


# --- Settings -----------------------------------------------------------------------

# Matches the runtime settings table in docs/05-configuration.md §7 —
# keep the two in sync when adding a new setting.
# --- Access control (RBAC) ----------------------------------------------------------

@command("setrole")
async def handle_setrole(ctx: CommandContext) -> str:
    """Owner-only. Grants ADMIN or VIEWER to a Telegram user ID at
    runtime — see bot/core/permissions.py for why OWNER can never be
    granted this way (env-only, by design)."""
    from bot.db.repositories.users_repo import set_role

    if len(ctx.args) < 2:
        return "Usage: /setrole <telegram_user_id> <ADMIN|VIEWER>"

    try:
        target_user_id = int(ctx.args[0])
    except ValueError:
        return "telegram_user_id must be a number."

    role_str = ctx.args[1].upper()
    if role_str not in ("ADMIN", "VIEWER"):
        return "Role must be ADMIN or VIEWER. Owner can only be set via the OWNER_USER_IDS environment variable."

    await set_role(target_user_id, role_str)
    return f"✅ User {target_user_id} is now {role_str}."


# --- Runtime settings ----------------------------------------------------------------

_KNOWN_SETTINGS: dict[str, str] = {
    "maintenance_mode": "bool",
    "website_latency_warn_ms": "int",
    "api_latency_warn_ms": "int",
    "notify_on_new_user": "bool",
    "report_verbosity": "enum:brief,full",
}


def _parse_setting_value(kind: str, raw: str):
    if kind == "bool":
        if raw.lower() in ("true", "1", "yes", "on"):
            return True
        if raw.lower() in ("false", "0", "no", "off"):
            return False
        raise ValueError("expected true/false")
    if kind == "int":
        try:
            return int(raw)
        except ValueError:
            raise ValueError("expected a whole number") from None
    if kind.startswith("enum:"):
        options = kind.split(":", 1)[1].split(",")
        if raw not in options:
            raise ValueError(f"expected one of: {', '.join(options)}")
        return raw
    raise ValueError("unsupported setting type")  # pragma: no cover — guarded by _KNOWN_SETTINGS


@command("settings")
async def handle_settings(ctx: CommandContext) -> str:
    from bot.db.repositories.config_repo import get_all_settings, set_setting

    known_keys_hint = ", ".join(_KNOWN_SETTINGS)

    if not ctx.args:
        settings_map = await get_all_settings()
        if not settings_map:
            return f"No runtime settings configured yet.\nUsage: /settings <key> <value>\nKnown keys: {known_keys_hint}"
        return "⚙️ <b>Settings</b>\n" + "\n".join(f"{k}: {v}" for k, v in settings_map.items())

    if len(ctx.args) < 2:
        return f"Usage: /settings <key> <value>\nKnown keys: {known_keys_hint}"

    key, raw_value = ctx.args[0], " ".join(ctx.args[1:])
    if key not in _KNOWN_SETTINGS:
        return f"Unknown setting '{key}'.\nKnown keys: {known_keys_hint}"

    try:
        value = _parse_setting_value(_KNOWN_SETTINGS[key], raw_value)
    except ValueError as e:
        return f"Invalid value for '{key}': {e}"

    await set_setting(key, value)
    return f"⚙️ {key} set to {value}."
