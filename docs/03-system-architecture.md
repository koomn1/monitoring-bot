# System Architecture

**Document:** `docs/03-system-architecture.md`
**Section:** Project Documentation
**Status:** Draft v1.0

---

## 1. Purpose

This document specifies the runtime architecture of the Quiz Space Telegram DevOps Bot: how a request enters the system, which layers it passes through, how state is stored, and how the system behaves under failure. It is the behavioral counterpart to [Project Structure](./02-project-structure.md), which only defines the static file layout.

---

## 2. Responsibilities

- Define the layered architecture and the contract between layers
- Define the request lifecycle for the three trigger types: Telegram command, scheduled job, inbound webhook
- Define state ownership (what lives where)
- Define the failure-handling model shared by every module

---

## 3. Inputs

- Telegram `Update` objects (commands, callback queries)
- Scheduler ticks (interval and cron jobs)
- Inbound webhooks (GitHub, Sentry — see [Webhooks](../api/02-webhooks.md))

## 4. Outputs

- Telegram messages (responses, notifications, reports)
- Rows written to the Bot's Supabase datastore (audit trail, monitoring history, incidents, reports)
- GitHub Actions `workflow_dispatch` events

## 5. Dependencies

All dependencies listed in [Project Overview §5](./01-project-overview.md#5-dependencies) apply at the system level. This document assumes that dependency set as given.

---

## 6. Layered Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. INTERFACE LAYER                                               │
│    bot/main.py — Telegram update loop, webhook receivers          │
└───────────────────────────────┬───────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. CORE LAYER                                                    │
│    bot/core/router.py       — command → handler resolution        │
│    bot/core/permissions.py  — RBAC (Viewer / Admin / Owner)        │
│    bot/core/middleware.py   — audit logging wrapper                 │
│    bot/core/scheduler.py    — recurring job orchestration           │
│    bot/core/exceptions.py   — shared error taxonomy                 │
└───────────────────────────────┬───────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. DOMAIN MODULES LAYER                                           │
│    bot/modules/<name>/service.py — one module per responsibility  │
│    (auth, users, *_monitor, deployment, github, cloudflare,       │
│     firebase, backup, security, logging, analytics, reports,      │
│     telegram_commands, ai_assistant, notifications, automation)   │
└───────────┬─────────────────────────────────┬─────────────────────┘
            ▼                                 ▼
┌───────────────────────────┐   ┌───────────────────────────────────┐
│ 4. DATA LAYER              │   │ 5. INTEGRATION LAYER                │
│  bot/db/repositories/*     │   │  bot/integrations/*                 │
│  (Supabase Postgres —      │   │  (Telegram, Supabase, GitHub,       │
│   the Bot's own state)     │   │   Cloudflare, Firebase, Sentry,     │
│                             │   │   Analytics, AI provider)           │
└───────────────────────────┘   └───────────────────────────────────┘
```

**Layer contract rules** (enforced by convention and code review, see [Project Structure §8](./02-project-structure.md#8-internal-workflow)):

1. Layer 1 only calls into Layer 2 (never directly into Layer 3, 4, or 5).
2. Layer 3 modules call Layer 4 and Layer 5, and may call each other's `service.py` (e.g. `deployment` calls `notifications`), but never call Layer 1 or Layer 2's router.
3. Layer 4 and 5 are leaf layers — they call nothing above them.

---

## 7. Request Lifecycles

### 7.1 Telegram Command

```
Telegram Update
   → bot/main.py (_telegram_command_entrypoint)
   → bot/core/middleware.py (with_audit_log — starts timer)
   → bot/core/router.py (dispatch)
       → bot/core/permissions.py (require_command_permission)
       → bot/modules/telegram_commands/handlers.py (matched handler)
           → relevant module service(s)
               → integrations / db repositories
   ← formatted text response
   → bot/core/middleware.py (writes audit_logs row, regardless of outcome)
   → Telegram reply sent
```

### 7.2 Scheduled Job (Automation)

```
bot/core/scheduler.py tick
   → bot/modules/automation/service.py (run_health_checks / run_scheduled_backup / ...)
       → relevant monitor/backup/report module service
           → integrations / db repositories
           → (on state transition) bot/modules/notifications/service.py
   ← no direct return value; side effects only (DB writes, Telegram notifications)
```

Scheduled jobs never go through `bot/core/router.py` — they call module services directly, since there is no Telegram command/permission concept for an internally-triggered job. Every scheduled job function must catch its own exceptions (see [Error Handling](#9-error-handling)).

### 7.3 Inbound Webhook (GitHub / Sentry)

```
POST /webhooks/github or /webhooks/sentry
   → api layer webhook receiver (see api/02-webhooks.md)
       → signature verification (HMAC, see docs/07-security.md)
       → relevant module service (e.g. deployment, security)
           → bot/modules/notifications/service.py (if state changed)
   ← 200 OK (webhook senders expect fast acknowledgment; heavy work is
      deferred to a background task, not done inline in the handler)
```

---

## 8. State Ownership

| State | Owner | Storage |
|---|---|---|
| Bot admin roster (audit copy) | `auth` module | `bot_users` table |
| Command audit trail | `middleware` / `logs_repo` | `audit_logs` table |
| Monitoring check history | `*_monitor` modules | `monitoring_logs` table |
| Open/resolved incidents | monitor modules | `incidents` table |
| Generated reports | `reports` module | `reports` table |
| Runtime-editable settings | `settings` command / config_repo | `bot_config` table |
| Access control (source of truth) | environment variables | `OWNER_USER_IDS` / `ADMIN_USER_IDS` / `VIEWER_USER_IDS` — **not** the database |
| Quiz Space's own application data | Quiz Space itself | Quiz Space's Supabase project (Bot only reads it) |

Note: role assignment is intentionally sourced from environment variables, not the database, so that access control can never be locked out by a database outage and can only be changed by whoever controls the deployment's secrets (see [Security](./07-security.md)).

---

## 9. Error Handling

The Bot follows one uniform error-handling model across all layers, defined by the exception taxonomy in `bot/core/exceptions.py`:

| Exception | Raised by | Router behavior |
|---|---|---|
| `UnauthorizedError` | `permissions.py` | Generic "not authorized" reply; logged as a security-relevant event |
| `ForbiddenError` | `permissions.py` | "Insufficient permission" reply |
| `ConfirmationRequiredError` | destructive-action modules (deploy, rollback, backup, restore) | Re-prompt with confirmation instructions |
| `ExternalServiceError` | any `integrations/*` client | "Service unreachable" reply; does not crash the Bot |
| `ConfigurationError` | any module needing unset optional config | Graceful "not configured" reply, never a stack trace to the user |
| Any other `Exception` | anywhere | Caught at the top of `router.dispatch`, logged with full traceback, generic error reply sent |

Scheduled jobs (§7.2) apply the same taxonomy but log instead of replying, since there is no chat to reply to.

---

## 10. Architecture Decisions & Rationale

- **Why Supabase for the Bot's own data, not a separate database?** One fewer free-tier service to operate; Supabase's free tier easily covers the Bot's low write volume (audit logs, monitoring history).
- **Why environment variables for RBAC instead of a database table?** Availability — the Bot must be able to authenticate its Owner even if the database is the thing that's down.
- **Why GitHub Actions as the automation/CI engine instead of the Bot's own scheduler for deploy/backup?** Deploy and backup must survive the Bot process being restarted or temporarily down; GitHub Actions cron is independent of the Bot's own uptime. The Bot's internal `scheduler.py` is used for lightweight, frequent checks (health checks) where a few minutes of drift during a Bot restart is acceptable.

---

## 11. Main Functions (System-Level)

Already covered in [Project Overview §8](./01-project-overview.md#8-main-functions-system-level); this document adds the internal contract:

- `router.dispatch(ctx: CommandContext) -> str`
- `middleware.with_audit_log(ctx, next_fn) -> str`
- `scheduler.register_all_jobs() -> None`
- `permissions.require_command_permission(user_id, command) -> Role`

## 12. Security Considerations

Covered in full in [Security](./07-security.md). Architecturally relevant point: Layer 5 (Integration Layer) is the only layer that ever holds third-party credentials in memory — no credential is passed up into Layer 3 or above.

## 13. Performance Considerations

- The Interface Layer (§6.1) is intentionally thin — all latency lives in Layers 3-5, which are async throughout, allowing concurrent monitor checks (see `automation.run_health_checks` using `asyncio.gather`).
- Layer 4 (Data Layer) writes are fire-and-forget where safe (e.g. monitoring log inserts) so they never add latency to a user-facing command response.

## 14. Future Improvements

- Introduce a message queue (still free-tier — e.g. Supabase's own `pgmq` extension) between the Integration Layer and Domain Modules Layer if webhook volume grows enough to need backpressure.
- Add a circuit-breaker state store (currently in-memory only) shared across Bot restarts.

## 15. Example Usage

Not applicable directly (architectural document) — see [Project Overview §13](./01-project-overview.md#13-example-usage) for an end-to-end example trace of `/status`.

## 16. Related Modules

- [Project Structure](./02-project-structure.md)
- [Security](./07-security.md)
- [Automation](../modules/20-automation.md)
- [Webhooks](../api/02-webhooks.md)

---

**Previous:** [Project Structure](./02-project-structure.md) · **Next:** [Environment Variables](./04-environment-variables.md)
