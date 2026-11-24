# Environment Variables

**Document:** `docs/04-environment-variables.md`
**Section:** Project Documentation
**Status:** Draft v1.0

---

## 1. Purpose

This document is the single authoritative reference for every environment variable the Bot reads, matching `bot/config.py` and `.env.example` exactly. Any variable not listed here should not exist in the codebase, and any variable listed here must exist in `bot/config.py`.

## 2. Responsibilities

- Enumerate every variable, its purpose, whether it is required, and its default
- Define which variables are secrets (never logged, never echoed in Telegram) vs. plain configuration
- Define where each variable is sourced from in each environment (local `.env` vs. GitHub Actions secrets vs. hosting provider's secret store)

## 3. Inputs

The running process's environment (`os.environ`), populated from `.env` locally or from the hosting platform's secret/environment configuration in production.

## 4. Outputs

A validated `Settings` object (`bot.config.settings`) consumed by every other module.

## 5. Dependencies

None — this is a foundational, dependency-free module.

---

## 6. Full Variable Reference

### Core

| Variable | Required | Default | Description |
|---|---|---|---|
| `ENVIRONMENT` | No | `development` | `development` \| `staging` \| `production` — used for log verbosity and safety gates (e.g. extra confirmation in production) |
| `LOG_LEVEL` | No | `INFO` | Standard Python logging level |

### Telegram

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | **Yes** | — | Bot token from [@BotFather](https://t.me/BotFather). **Secret.** |
| `TELEGRAM_USE_WEBHOOK` | No | `false` | If `true`, runs in webhook mode instead of long polling |
| `TELEGRAM_WEBHOOK_URL` | If webhook mode | — | Public HTTPS URL Telegram will POST updates to |
| `TELEGRAM_WEBHOOK_PORT` | No | `8080` | Port used by Telegram webhook mode; the HTTP receiver uses Railway's `PORT` when present, otherwise this value |
| `TELEGRAM_ADMIN_CHAT_ID` | No | — | Telegram user/chat ID for admin-only Supabase event notifications |
| `TELEGRAM_ALERT_CHANNEL_ID` | No | — | Chat/channel ID notifications are sent to; if unset, all Admin+ users are messaged individually |
| `TELEGRAM_ERROR_CHANNEL_ID` | No | — | Separate channel for Bot-internal error alerts |

### Access Control

| Variable | Required | Default | Description |
|---|---|---|---|
| `OWNER_USER_IDS` | **Yes*** | — | Comma-separated Telegram numeric user IDs with Owner role. At least one of Owner/Admin required. |
| `ADMIN_USER_IDS` | No | — | Comma-separated Admin-role user IDs |
| `VIEWER_USER_IDS` | No | — | Comma-separated Viewer-role user IDs |

### Supabase

| Variable | Required | Default | Description |
|---|---|---|---|
| `SUPABASE_URL` | **Yes** | — | Project URL, e.g. `https://xxxx.supabase.co` |
| `SUPABASE_ANON_KEY` | No | — | Public anon key (not used server-side by the Bot today; reserved) |
| `SUPABASE_SERVICE_ROLE_KEY` | **Yes** | — | Service-role key, bypasses RLS. **Secret — highest sensitivity.** |
| `SUPABASE_WEBHOOK_SECRET` | For Supabase database webhooks | — | Shared secret checked against the `X-Webhook-Secret` request header. **Secret.** |

### GitHub

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_TOKEN` | For deploy/backup/security features | — | Fine-grained PAT with `actions:write`, `contents:read`, `security_events:read`. **Secret.** |
| `GITHUB_REPO` | For deploy/backup/security features | — | `owner/repo` |
| `GITHUB_WEBHOOK_SECRET` | For inbound GitHub webhooks | — | HMAC secret to verify webhook signatures. **Secret.** |

### Cloudflare

| Variable | Required | Default | Description |
|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` | For Cloudflare features | — | Scoped token: Pages Edit/Read, Zone Read. **Secret.** |
| `CLOUDFLARE_ACCOUNT_ID` | For Cloudflare features | — | Account ID |
| `CLOUDFLARE_PROJECT_NAME` | For Cloudflare features | — | Pages project name |

### Firebase (optional)

| Variable | Required | Default | Description |
|---|---|---|---|
| `FIREBASE_PROJECT_ID` | No | — | Firebase project ID |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | No | — | Full service-account JSON as a single-line string. **Secret.** |

### Sentry (optional)

| Variable | Required | Default | Description |
|---|---|---|---|
| `SENTRY_DSN` | No | — | Only needed if the Bot reports its own errors to Sentry |
| `SENTRY_AUTH_TOKEN` | No | — | API token to read Quiz Space's Sentry issues. **Secret.** |
| `SENTRY_ORG_SLUG` | No | — | Organization slug |
| `SENTRY_PROJECT_SLUG` | No | — | Project slug |

### Analytics (optional)

| Variable | Required | Default | Description |
|---|---|---|---|
| `GA_MEASUREMENT_ID` | No | — | GA4 measurement ID |
| `GA_API_SECRET` | No | — | GA4 Measurement Protocol API secret. **Secret.** |
| `UMAMI_API_URL` | No | — | Base URL of the Umami instance |
| `UMAMI_API_KEY` | No | — | Umami API key. **Secret.** |
| `UMAMI_WEBSITE_ID` | No | — | Website ID within Umami |

### Monitored Targets

| Variable | Required | Default | Description |
|---|---|---|---|
| `WEBSITE_URL` | For Website Monitor | — | Public URL checked by `website_monitor` |
| `API_BASE_URL` | For API Monitor | — | Base URL checked by `api_monitor` (expects a `/health` endpoint — see [Health Endpoint](../api/03-health-endpoint.md)) |

### AI Assistant

| Variable | Required | Default | Description |
|---|---|---|---|
| `AI_PROVIDER` | No | `anthropic` | Currently only `anthropic` is implemented |
| `AI_API_KEY` | For AI Assistant | — | Provider API key. **Secret.** |
| `AI_MODEL` | No | `claude-sonnet-5` | Model identifier |

### Automation Schedules

| Variable | Required | Default | Description |
|---|---|---|---|
| `HEALTH_CHECK_INTERVAL_SECONDS` | No | `300` | Interval between automatic health checks |
| `BACKUP_CRON` | No | `0 3 * * *` | 5-field cron expression for automatic backups |
| `DAILY_REPORT_CRON` | No | `0 8 * * *` | Cron expression for the daily report |
| `WEEKLY_REPORT_CRON` | No | `0 8 * * 1` | Cron expression for the weekly report |
| `MONTHLY_REPORT_CRON` | No | `0 8 1 * *` | Cron expression for the monthly report |

---

## 7. Internal Workflow

1. `bot/config.py` reads every variable at import time into a frozen `Settings` dataclass.
2. `settings.validate()` is called once, explicitly, at the top of `bot/main.py:main()` — it fails fast on missing *critical* variables (`TELEGRAM_BOT_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and at least one owner/admin ID).
3. Optional integrations (GitHub, Cloudflare, Firebase, Sentry, Analytics, AI) are validated lazily, per-call, by each `integrations/*` client raising `ConfigurationError` if its specific variables are missing — this lets the Bot run with only a subset of integrations configured.

## 8. Architecture

See [System Architecture §8](./03-system-architecture.md#8-state-ownership) for why RBAC is environment-sourced rather than database-sourced.

## 9. Main Functions

- `Settings.validate() -> None`
- Module-local `_get(name, default, required) -> str | None` helper

## 10. Error Handling

- Missing critical variable → `RuntimeError` at startup, process exits (fail fast, visible in deployment logs — never a silent partial start)
- Missing optional variable → the specific module returns "not configured" rather than raising to the user

## 11. Security Considerations

- Every variable marked **Secret** above must be stored only as a platform secret (GitHub Actions secret, hosting provider's secret manager) — never committed, never logged. See [Security](./07-security.md) for the full policy.
- `.env` is git-ignored; `.env.example` contains no real values, only variable names.

## 12. Performance Considerations

Not applicable — configuration is loaded once at process startup.

## 13. Future Improvements

- Support secret rotation without a full restart (currently requires a redeploy since `Settings` is a frozen singleton)
- Add a `/settings` diagnostic that reports which optional integrations are configured, without revealing values (see [Telegram Commands](../modules/17-telegram-commands.md))

## 14. Example Usage

```bash
# .env (local development)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...
OWNER_USER_IDS=111111111
WEBSITE_URL=https://quizspace.example.com
```

## 15. Related Modules

- [Configuration](./05-configuration.md)
- [Security](./07-security.md)
- [Deployment](./06-deployment.md)

---

**Previous:** [System Architecture](./03-system-architecture.md) · **Next:** [Configuration](./05-configuration.md)
