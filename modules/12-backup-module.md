# Backup Module

**Document:** `modules/12-backup-module.md`
**Code:** `bot/modules/backup/service.py`
**Status:** Draft v1.0 (storage target pending decision)

---

## 1. Purpose

Triggers, tracks, and restores database backups of the Quiz Space Supabase project via the [Backup Pipeline](../workflows/04-backup-pipeline.md). Backs `/backup` and `/restore`.

## 2. Responsibilities

- Trigger a manual or scheduled backup
- Trigger a restore from a named backup (Owner-only, always confirmed)
- List available backups

## 3. Inputs

- `/backup [confirm]`, `/restore <backup_id> [confirm]`
- Scheduled trigger via `automation.run_scheduled_backup` (`BACKUP_CRON`)

## 4. Outputs

- GitHub Actions `workflow_dispatch` for `backup.yml` / `restore.yml`
- `Backup Started` / `Backup Completed` / `Backup Failed` notifications (completion/failure notified by the pipeline callback — see [Webhooks](../api/02-webhooks.md))

## 5. Dependencies

- `bot/integrations/github_client.py`
- `bot/modules/notifications/service.py`
- [Backup Pipeline](../workflows/04-backup-pipeline.md)

## 6. Internal Workflow

```
trigger_backup(confirmed)
   → if not confirmed: raise ConfirmationRequiredError
   → github_client.dispatch_workflow("backup.yml")
   → notifications.notify_backup_started()

trigger_restore(confirmed, backup_id)
   → if not confirmed: raise ConfirmationRequiredError (always, no exceptions)
   → github_client.dispatch_workflow("restore.yml", inputs={backup_id})
   ← "Restore triggered" text
```

## 7. Architecture

Automatic scheduled backups call `trigger_backup(confirmed=True)` directly (bypassing the confirmation gate, since it's an unattended scheduled action, not an interactive command) — see [Automation §6](./20-automation.md#6-internal-workflow) — while `/backup` from a human always requires explicit confirmation.

## 8. Main Functions

- `trigger_backup(confirmed) -> str`
- `trigger_restore(confirmed, backup_id) -> str`
- `list_backups() -> list[dict]` *(not yet implemented — see §12)*

## 9. Error Handling

Confirmation is checked before any GitHub API call; a restore without `confirm` always explains the consequence and never executes on the first call, matching [Security §8](../docs/07-security.md#8-destructive-action-confirmation).

## 10. Security Considerations

- `/backup` requires Admin; `/restore` requires Owner — restoring overwrites current data and is the single most destructive command in the system
- Backup artifacts (wherever stored — see §12) must be access-controlled at least as strictly as the production database itself, since a backup contains the same data

## 11. Performance Considerations

Backup/restore execution time lives in the GitHub Actions workflow, not the Bot — the Bot only dispatches and reports, keeping the command response instant.

## 12. Future Improvements

- **Decide and implement the backup storage target** (GitHub Releases vs. Cloudflare R2 free tier vs. Supabase Storage) — this decision blocks `list_backups()` — see [Backup Pipeline](../workflows/04-backup-pipeline.md) §6 for the current recommendation
- Retention policy (auto-delete backups older than N days) once the storage target is chosen

## 13. Example Usage

```
Owner: /restore 2026-07-20-nightly confirm
Bot: ♻️ Restore from '2026-07-20-nightly' triggered. This is a destructive, audited action.
```

## 14. Related Modules

- [Backup Pipeline](../workflows/04-backup-pipeline.md)
- [Security](../docs/07-security.md)
- [Database Migrations](../database/05-database-migrations.md)
