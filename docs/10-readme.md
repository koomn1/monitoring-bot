# README

**Document:** `docs/10-readme.md`
**Section:** Project Documentation
**Status:** Draft v1.0

---

## 1. Purpose

This is the master index and reading guide for the entire Quiz Space DevOps Bot documentation set. It exists so that a new reader — human or AI — can find the right document immediately instead of searching.

## 2. Responsibilities

- Provide a complete table of contents across all five documentation folders
- Provide a recommended reading order for someone implementing the project from scratch
- State the documentation set's scope and non-scope

## 3-5. Inputs / Outputs / Dependencies

Not applicable — index document.

---

## 6. Documentation Map

### `docs/` — Project-level documentation
1. [Project Overview](./01-project-overview.md)
2. [Project Structure](./02-project-structure.md)
3. [System Architecture](./03-system-architecture.md)
4. [Environment Variables](./04-environment-variables.md)
5. [Configuration](./05-configuration.md)
6. [Deployment](./06-deployment.md)
7. [Security](./07-security.md)
8. [Free Infrastructure](./08-free-infrastructure.md)
9. [Roadmap](./09-roadmap.md)
10. README (this document)

### `modules/` — One document per domain module
01. [Authentication Module](../modules/01-authentication-module.md)
02. [Users Module](../modules/02-users-module.md)
03. [Website Monitor](../modules/03-website-monitor.md)
04. [API Monitor](../modules/04-api-monitor.md)
05. [Database Monitor](../modules/05-database-monitor.md)
06. [Storage Monitor](../modules/06-storage-monitor.md)
07. [Realtime Monitor](../modules/07-realtime-monitor.md)
08. [Deployment Module](../modules/08-deployment-module.md)
09. [GitHub Module](../modules/09-github-module.md)
10. [Cloudflare Module](../modules/10-cloudflare-module.md)
11. [Firebase Module](../modules/11-firebase-module.md)
12. [Backup Module](../modules/12-backup-module.md)
13. [Security Module](../modules/13-security-module.md)
14. [Logging Module](../modules/14-logging-module.md)
15. [Analytics Module](../modules/15-analytics-module.md)
16. [Reports Module](../modules/16-reports-module.md)
17. [Telegram Commands](../modules/17-telegram-commands.md)
18. [AI Assistant](../modules/18-ai-assistant.md)
19. [Notifications](../modules/19-notifications.md)
20. [Automation](../modules/20-automation.md)

### `database/`
1. [Database Schema](../database/01-database-schema.md)
2. [Tables](../database/02-tables.md)
3. [RLS Policies](../database/03-rls-policies.md)
4. [Database Functions](../database/04-database-functions.md)
5. [Database Migrations](../database/05-database-migrations.md)

### `api/`
1. [API Reference](../api/01-api-reference.md)
2. [Webhooks](../api/02-webhooks.md)
3. [Health Endpoint](../api/03-health-endpoint.md)

### `deployment/`
1. [Deployment Guide](../deployment/01-deployment-guide.md)
2. [Environment Setup](../deployment/02-environment-setup.md)
3. [Production Checklist](../deployment/03-production-checklist.md)
4. [Rollback Guide](../deployment/04-rollback-guide.md)

### `workflows/`
1. [Build Pipeline](../workflows/01-build-pipeline.md)
2. [Deployment Pipeline](../workflows/02-deployment-pipeline.md)
3. [Rollback Pipeline](../workflows/03-rollback-pipeline.md)
4. [Backup Pipeline](../workflows/04-backup-pipeline.md)
5. [Health Check Pipeline](../workflows/05-health-check-pipeline.md)

## 7. Recommended Reading Order (First-Time Implementation)

1. `docs/01` → `docs/09` in order (project-level context)
2. `database/01` → `database/05` (the schema everything else depends on)
3. `modules/01` → `modules/20` in order (domain logic)
4. `api/01` → `api/03`
5. `workflows/01` → `workflows/05`
6. `deployment/01` → `deployment/04` (last, since it assumes everything above already exists)

## 8. Scope Statement

**In scope:** everything needed to design and implement one Quiz Space DevOps Bot instance, monitoring one Quiz Space deployment, on free-tier infrastructure only.

**Out of scope:** Quiz Space's own application code/architecture; multi-tenant/multi-project support (see [Roadmap](./09-roadmap.md) Phase 3); paid-tier infrastructure of any kind.

## 9-17. (Purpose/Responsibilities-template sections not separately applicable to an index document)

## 18. Related Modules

Every document listed in §6.

---

**Previous:** [Roadmap](./09-roadmap.md) · **This is the last document in `docs/`.** Continue to [modules/01 — Authentication Module](../modules/01-authentication-module.md).
