# Project Structure

**Document:** `docs/02-project-structure.md`
**Section:** Project Documentation
**Status:** Draft v1.0

---

## 1. Purpose

This document defines the canonical folder and file layout of the Quiz Space Telegram DevOps Bot codebase. It exists so that any developer — human or AI — implementing this project produces a structure that matches the architecture described across the rest of this documentation set, with no ambiguity about where a given piece of logic belongs.

---

## 2. Responsibilities

- Define the top-level repository layout
- Define the internal layout of the `bot/` application package
- Map every module described in [modules/](../modules/) to a physical file location
- Define where configuration, tests, scripts, and CI/CD live
- Establish naming conventions used throughout the project

---

## 3. Inputs

- The full set of module specifications in [modules/](../modules/)
- The database schema in [database/](../database/01-database-schema.md)
- The deployment/workflow requirements in [workflows/](../workflows/)

## 4. Outputs

- A concrete directory tree (below) that is the single source of truth for "where does X go"
- Naming conventions applied consistently across the codebase

## 5. Dependencies

- Python packaging conventions (standard `src`-style layout)
- GitHub Actions workflow file conventions (`.github/workflows/`)

---

## 6. Full Repository Structure

```
quiz-space-bot/
├── .github/
│   └── workflows/
│       ├── build.yml                  # Build Pipeline (see workflows/01-build-pipeline.md)
│       ├── deploy.yml                 # Deployment Pipeline
│       ├── rollback.yml               # Rollback Pipeline
│       ├── backup.yml                 # Backup Pipeline (scheduled)
│       ├── health-check.yml           # Health Check Pipeline (scheduled)
│       └── bot-run.yml                # Keeps the bot process alive / redeploys bot itself
│
├── bot/                                # Main application package
│   ├── __init__.py
│   ├── main.py                         # Entry point: initializes and runs the bot
│   ├── config.py                       # Loads & validates environment variables (see docs/04-environment-variables.md)
│   │
│   ├── core/                           # Cross-cutting core system
│   │   ├── __init__.py
│   │   ├── router.py                   # Command routing / dispatch
│   │   ├── scheduler.py                # Internal job scheduler (APScheduler wrapper)
│   │   ├── permissions.py              # Role-based access control
│   │   ├── middleware.py               # Auth + logging middleware chain
│   │   └── exceptions.py               # Shared exception types
│   │
│   ├── modules/                        # One subpackage per domain module
│   │   ├── auth/                       # Authentication Module
│   │   │   ├── __init__.py
│   │   │   ├── service.py
│   │   │   └── models.py
│   │   ├── users/                      # Users Module
│   │   ├── website_monitor/            # Website Monitor
│   │   ├── api_monitor/                # API Monitor
│   │   ├── database_monitor/           # Database Monitor
│   │   ├── storage_monitor/            # Storage Monitor
│   │   ├── realtime_monitor/           # Realtime Monitor
│   │   ├── deployment/                 # Deployment Module
│   │   ├── github/                     # GitHub Module
│   │   ├── cloudflare/                 # Cloudflare Module
│   │   ├── firebase/                   # Firebase Module
│   │   ├── backup/                     # Backup Module
│   │   ├── security/                   # Security Module
│   │   ├── logging/                    # Logging Module
│   │   ├── analytics/                  # Analytics Module
│   │   ├── reports/                    # Reports Module
│   │   ├── telegram_commands/          # Telegram Commands (handlers only)
│   │   ├── ai_assistant/               # AI Assistant
│   │   ├── notifications/              # Notifications
│   │   └── automation/                 # Automation
│   │
│   ├── integrations/                   # Thin API clients for third-party free services
│   │   ├── __init__.py
│   │   ├── telegram_client.py
│   │   ├── supabase_client.py
│   │   ├── github_client.py
│   │   ├── cloudflare_client.py
│   │   ├── firebase_client.py
│   │   ├── sentry_client.py
│   │   ├── analytics_client.py         # Google Analytics + Umami
│   │   └── ai_client.py                # AI provider client (see modules/18-ai-assistant.md)
│   │
│   ├── db/                             # Data access layer
│   │   ├── __init__.py
│   │   ├── client.py                   # Supabase Postgres connection/session management
│   │   ├── migrations/                 # SQL migration files (see database/05-database-migrations.md)
│   │   └── repositories/               # Query layer, one file per table group
│   │       ├── users_repo.py
│   │       ├── logs_repo.py
│   │       ├── incidents_repo.py
│   │       ├── reports_repo.py
│   │       └── config_repo.py
│   │
│   └── utils/                          # Generic helpers (formatting, time, retries, etc.)
│       ├── __init__.py
│       ├── formatting.py
│       ├── time_utils.py
│       └── retry.py
│
├── scripts/                            # One-off / operational scripts
│   ├── seed_admin.py                   # Register first Owner admin
│   ├── run_migrations.py
│   └── local_dev_runner.py
│
├── tests/                              # Test suite, mirrors bot/ structure
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── docs/                               # This documentation set
├── modules/
├── database/
├── api/
├── deployment/
├── workflows/
│
├── .env.example                        # Template for environment variables
├── requirements.txt                    # Python dependencies
├── pyproject.toml                      # Project metadata & tooling config
├── Dockerfile                          # Optional container build (for free-tier container hosts)
├── .gitignore
└── README.md                           # Root README (see docs/10-readme.md)
```

---

## 7. Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Python modules/files | `snake_case.py` | `website_monitor.py` |
| Python classes | `PascalCase` | `WebsiteMonitorService` |
| Python functions/vars | `snake_case` | `check_website_uptime()` |
| Environment variables | `SCREAMING_SNAKE_CASE` | `TELEGRAM_BOT_TOKEN` |
| Database tables | `snake_case`, plural | `monitoring_logs` |
| Telegram command handlers | mirror the command name | `/status` → `handle_status()` |
| GitHub Actions workflow files | `kebab-case.yml` | `health-check.yml` |
| Documentation files | `NN-kebab-case.md` (numeric prefix for reading order) | `03-system-architecture.md` |

---

## 8. Internal Workflow

This document has no runtime workflow of its own — it is a static reference. However, it dictates the **import boundaries** enforced across the codebase:

```
telegram_commands  →  modules/*  →  integrations/* & db/repositories/*
                                          ↑
                                   never imported back into
                                   telegram_commands directly
```

- `modules/*` never import from `bot/core/router.py` (no circular dependency on the router)
- `integrations/*` never import from `modules/*` (integrations are pure clients, domain-agnostic)
- `db/repositories/*` are the **only** place raw SQL/Supabase queries are written

---

## 9. Architecture

See [System Architecture](./03-system-architecture.md) for the runtime/behavioral architecture. This document only describes the static file layout that implements it.

---

## 10. Main "Functions" (Structural Rules)

Not applicable in the traditional sense — this document defines structure, not behavior. The structural rules that substitute for "main functions" here are:

1. Every domain module directory under `bot/modules/` MUST contain a `service.py` exposing its public interface
2. Every domain module SHOULD contain its own `models.py` if it defines data shapes
3. Every third-party integration MUST live only under `bot/integrations/`
4. Every SQL query MUST live only under `bot/db/repositories/`

---

## 11. Error Handling

Not applicable directly — structural document. However, misplacement of code (e.g. direct API calls inside `telegram_commands/`) is considered an architecture violation and should be caught in code review / CI linting (see [Build Pipeline](../workflows/01-build-pipeline.md)).

## 12. Security Considerations

- Secrets never live in this tree as files — `.env` is git-ignored, only `.env.example` (no real values) is committed
- `scripts/seed_admin.py` must only be runnable manually/locally or via a protected one-time GitHub Actions workflow, never exposed as a bot command

## 13. Performance Considerations

- Keeping integrations isolated from modules allows independent caching strategies per external service without leaking complexity into domain logic

## 14. Future Improvements

- Split `bot/` into a proper installable package if the Bot ever needs to be reused across multiple Telegram bot instances
- Add a `bot/modules/*/tests/` colocation option if the mirrored `tests/` tree becomes hard to navigate

## 15. Example Usage

Adding a new monitor (e.g. a future "Payments Monitor") means:

1. Create `bot/modules/payments_monitor/` with `service.py`
2. Add a client method to `bot/integrations/` if a new external API is needed
3. Add a repository file under `bot/db/repositories/` if new tables are needed
4. Register the new scheduled job in `bot/core/scheduler.py`
5. Add a new module doc under `modules/`

No existing module needs to change.

## 16. Related Modules

- [System Architecture](./03-system-architecture.md)
- [Environment Variables](./04-environment-variables.md)
- [Configuration](./05-configuration.md)
- All files under [modules/](../modules/)

---

**Previous:** [Project Overview](./01-project-overview.md) · **Next:** [System Architecture](./03-system-architecture.md)
