# Project Overview

**Document:** `docs/01-project-overview.md`
**Section:** Project Documentation
**Status:** Draft v1.0
**Applies to:** Quiz Space Telegram DevOps Bot ("the Bot")

---

## 1. Purpose

The Quiz Space Telegram DevOps Bot is a single, centralized command-and-control system that allows the owner/administrators of the **Quiz Space** platform to monitor, manage, secure, and operate the entire Quiz Space infrastructure directly from Telegram, without needing to open a laptop, a cloud dashboard, or an IDE.

Quiz Space (the underlying product being operated) is assumed to be a web application backed by:

- A frontend (hosted on **Cloudflare Pages/Workers**, free tier)
- A backend/database layer (**Supabase Free**, Postgres + Auth + Storage + Realtime)
- Optional secondary services (**Firebase Free** — e.g. push notifications, secondary auth, or analytics)
- Source control and CI/CD (**GitHub** + **GitHub Actions**)
- Error tracking (**Sentry Free**)
- Analytics (**Google Analytics** and/or **Umami**)

The Bot exists to be the **single pane of glass** over all of this — replacing the need to individually check five or six different dashboards. It is the nervous system of Quiz Space's operations: it watches, it reports, it acts (within safe, permissioned limits), and it never requires a paid service to do so.

### Problem Statement

Running a modern web product on a patchwork of free-tier services creates operational fragmentation:

- No unified visibility across services (website, API, database, storage, deployments)
- Manual, reactive incident discovery (a human notices the site is down)
- No centralized audit trail of administrative actions
- Deployment and rollback require direct platform access (GitHub UI, Cloudflare dashboard, etc.)
- No lightweight way to check system health from a phone

### Solution Statement

A modular Telegram bot that:

1. **Monitors** every layer of the stack on a schedule and on-demand
2. **Notifies** administrators immediately when something changes state
3. **Reports** on system health, usage, and security on a recurring cadence
4. **Acts** on infrastructure (trigger deploys, rollbacks, backups, restores) through safe, authenticated, audited commands
5. **Assists** administrators with an AI layer that can answer operational questions, summarize incidents, and suggest actions

---

## 2. Responsibilities

The Bot (as a system) is responsible for:

| Responsibility | In Scope | Out of Scope |
|---|---|---|
| Monitoring uptime/health of Quiz Space services | ✅ | Building the Quiz Space app itself |
| Sending real-time notifications of incidents | ✅ | Being the primary user-facing support channel |
| Triggering and tracking deployments via GitHub Actions | ✅ | Hosting the app itself |
| Managing database backups/restores (metadata + trigger) | ✅ | Being the database itself |
| Enforcing admin authentication & role-based access | ✅ | Managing Quiz Space's own end-user authentication |
| Producing periodic reports (daily/weekly/monthly) | ✅ | Business/financial reporting outside infra & usage |
| Providing an AI assistant for operational Q&A | ✅ | Being a general-purpose chatbot for end users |
| Logging all administrative actions | ✅ | Storing end-user application logs beyond what's needed for ops |

---

## 3. Inputs

The Bot, as a whole system, receives input from:

- **Telegram Updates** — commands and callback queries from authorized administrators (via long polling or webhook)
- **Scheduled Triggers** — GitHub Actions cron jobs / internal scheduler ticks that invoke monitoring and automation routines
- **Webhooks** — inbound events from GitHub (deployment status, push events), Supabase (database events), Sentry (new issues), Cloudflare (deployment events)
- **Configuration** — environment variables and configuration files defining which services to monitor, thresholds, and credentials
- **Direct API polling** — the Bot actively polls third-party free-tier APIs (Supabase, Cloudflare, GitHub, Firebase, Sentry, Umami/GA) where webhooks are unavailable or insufficient

---

## 4. Outputs

- **Telegram messages** — formatted notifications, reports, dashboards, command responses (text, and where useful, simple chart images)
- **Structured logs** — every action and monitoring result persisted to the database (`logs` domain — see [Logging Module](../modules/15-logging-module.md))
- **Database records** — monitoring history, incidents, reports, audit trail (see [Database Schema](../database/01-database-schema.md))
- **GitHub Actions triggers** — dispatches of workflow_dispatch events for deploy/rollback/backup pipelines
- **Exported reports** — periodic report payloads (formatted Telegram messages; optionally exportable as text/CSV summaries)

---

## 5. Dependencies

### External Services (all free-tier)

| Service | Role |
|---|---|
| Telegram Bot API | Command interface, notification delivery |
| GitHub + GitHub Actions | Source control, CI/CD execution engine, automation runner (the Bot's own scheduled jobs also run here) |
| Supabase Free | Primary database (Postgres), Auth, Storage, Realtime — both as *the thing being monitored* and optionally as *the Bot's own data store* |
| Cloudflare Free (Pages/Workers) | Frontend hosting, CDN, monitored deployment target |
| Firebase Free | Secondary services (push notifications / secondary auth), monitored target |
| Sentry Free | Error tracking source, monitored target |
| Google Analytics / Umami | Analytics data source |

### Internal Dependencies

- Python 3.11+ runtime
- `python-telegram-bot` (or equivalent async Telegram library) — see [Telegram Commands Module](../modules/17-telegram-commands.md)
- HTTP client library for polling third-party REST APIs
- Scheduler component (APScheduler or GitHub Actions cron — see [Automation Module](../modules/20-automation.md))
- Structured logging library

Full dependency graph is detailed in [System Architecture](./03-system-architecture.md).

---

## 6. Internal Workflow (High-Level)

```
                 ┌───────────────────────────┐
                 │   Telegram Administrators  │
                 └─────────────┬─────────────┘
                               │ commands / callbacks
                               ▼
                 ┌───────────────────────────┐
                 │      Telegram Bot Core     │
                 │  (Command Router + Auth)   │
                 └─────────────┬─────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                       ▼
┌───────────────┐   ┌───────────────────┐   ┌──────────────────────┐
│ Monitor Modules│   │ Action Modules    │   │  Intelligence Modules │
│ (Website, API, │   │ (Deploy, Backup,  │   │  (AI Assistant,       │
│ DB, Storage,   │   │ Restore, Rollback)│   │  Reports, Analytics)  │
│ Realtime, ...) │   │                    │   │                       │
└───────┬────────┘   └─────────┬──────────┘   └──────────┬────────────┘
        │                      │                          │
        └──────────────┬───────┴─────────────┬────────────┘
                        ▼                     ▼
              ┌──────────────────┐  ┌───────────────────┐
              │  Supabase (Bot's │  │  Notification &    │
              │  own datastore:  │  │  Logging Engine     │
              │  logs, config,   │  │                     │
              │  users, reports) │  └─────────┬───────────┘
              └──────────────────┘            ▼
                                     ┌───────────────────┐
                                     │ Telegram Channel(s) │
                                     │ (alerts, reports)   │
                                     └───────────────────┘
```

Every inbound trigger (a Telegram command, a scheduled tick, or an inbound webhook) is routed through **authentication → authorization → the relevant module → logging → response**. This pipeline is described in detail in [System Architecture](./03-system-architecture.md).

---

## 7. Architecture Summary

The Bot follows a **modular, layered architecture**:

1. **Interface Layer** — Telegram command handlers, webhook receivers
2. **Core Layer** — Auth, routing, permissions, config, scheduler
3. **Domain Modules Layer** — one module per responsibility (monitoring, deployment, backup, security, etc.), each self-contained and independently testable
4. **Data Layer** — Supabase Postgres database (schema in [database/](../database/01-database-schema.md)) storing all bot-owned state
5. **Integration Layer** — thin, isolated clients for each external free-tier service (GitHub, Cloudflare, Firebase, Sentry, Supabase, Analytics)

This layering ensures that:
- Adding a new monitor (e.g. a new service) means adding one new module, not touching existing code
- Every module can be tested, deployed, and reasoned about independently
- The Bot itself has no single point of failure logic buried in one file

Full detail in [System Architecture](./03-system-architecture.md) and [Project Structure](./02-project-structure.md).

---

## 8. Main Functions (System-Level)

At the system level (not module level — see individual module docs for function-level detail), the Bot performs:

- `handle_update()` — entrypoint for all Telegram updates
- `run_scheduled_jobs()` — entrypoint for cron-triggered automation
- `handle_webhook(source)` — entrypoint for inbound third-party webhooks
- `dispatch_notification(event)` — central notification fan-out
- `log_action(actor, action, metadata)` — central audit logger

---

## 9. Error Handling (System-Level Philosophy)

- **Fail loud to admins, fail safe to infrastructure.** Any error in a monitoring or action module must never crash the Bot process; it is caught, logged, and reported as a Bot-level error notification.
- **No silent failures.** Every caught exception is logged with context (module, action, actor, timestamp) and, if severity warrants, sent as a Telegram alert to a designated error channel.
- **Idempotent actions.** Destructive or state-changing commands (deploy, rollback, restore) are designed to be safely retryable and are always confirmed before execution (see [Security](./07-security.md)).
- **Circuit breaking on external APIs.** Repeated failures against a third-party API (e.g. Supabase API down) trigger a backoff and a single "service unreachable" notification rather than a flood of repeated errors.

Full error handling strategy per module is documented in each module's own "Error Handling" section.

---

## 10. Security Considerations (Summary)

- Only pre-authorized Telegram user IDs may interact with the Bot (see [Authentication Module](../modules/01-authentication-module.md))
- Role-based command access (Owner / Admin / Viewer — see [Security Module](../modules/14-security-module.md))
- All secrets stored as environment variables / GitHub Actions secrets, never in code or logs
- All destructive actions require explicit confirmation and are fully audited
- Full detail in [Security](./07-security.md)

---

## 11. Performance Considerations (Summary)

- All monitoring checks are designed to be lightweight (HTTP HEAD/GET with short timeouts) to stay within free-tier rate limits
- Polling intervals are configurable per service to balance freshness vs. quota consumption
- Heavy operations (report generation, analytics aggregation) are scheduled during low-traffic windows where feasible
- Full detail in [System Architecture](./03-system-architecture.md)

---

## 12. Future Improvements

- Multi-project support (operate more than one product from a single bot instance)
- Web-based companion dashboard (optional, still free-tier hosted)
- Voice-note incident summaries via AI Assistant
- Predictive alerting (trend-based, not just threshold-based)
- Multi-channel notification support (Telegram + email fallback)

Full roadmap in [Roadmap](./09-roadmap.md).

---

## 13. Example Usage

```
Admin (Telegram): /status

Bot:
🟢 Quiz Space — System Status
────────────────────────
🌐 Website:      Online (212ms)
🔌 API:          Online (98ms)
🗄️ Database:     Healthy
📦 Storage:      Healthy
🔐 Auth:         Healthy
⚡ Realtime:     Connected
🚀 Last Deploy:  2 hours ago (success)
🛡️ Security:     No active alerts

Updated: 2026-07-23 14:02 UTC
```

---

## 14. Related Modules

- [Project Structure](./02-project-structure.md)
- [System Architecture](./03-system-architecture.md)
- [Authentication Module](../modules/01-authentication-module.md)
- [Telegram Commands](../modules/17-telegram-commands.md)
- [Security](./07-security.md)
- [Free Infrastructure](./08-free-infrastructure.md)

---

**Next document:** [Project Structure](./02-project-structure.md)
