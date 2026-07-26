# Automation

**Document:** `modules/20-automation.md`
**Code:** `bot/modules/automation/service.py`
**Status:** Draft v1.0 — health checks, backup, daily report implemented; weekly/monthly/cleanup/security-scan pending

---

## 1. Purpose

Composes every other module into scheduled, unattended jobs. This is the only module invoked directly by `bot/core/scheduler.py` rather than by a Telegram command.

## 2. Responsibilities

- Run all monitor checks concurrently on the configured interval
- Trigger the scheduled backup
- Generate scheduled reports (daily implemented; weekly/monthly planned)
- (Planned) automatic cleanup, security scans, dependency-update checks

## 3. Inputs

Scheduler ticks only — no user input, ever.

## 4. Outputs

Side effects only: database writes (via the modules it calls) and Telegram notifications — no return value is consumed by anything.

## 5. Dependencies

Every monitor module, `backup`, `reports`, and (for the security scan) `github` and `notifications`.

## 6. Complete Job Reference

| Function | Schedule (env var) | Status |
|---|---|---|
| `run_health_checks` | `HEALTH_CHECK_INTERVAL_SECONDS` (default 300s) | Implemented |
| `run_scheduled_backup` | `BACKUP_CRON` (default `0 3 * * *`) | Implemented |
| `run_daily_report` | `DAILY_REPORT_CRON` (default `0 8 * * *`) | Implemented |
| `run_weekly_report` | `WEEKLY_REPORT_CRON` (default `0 8 * * 1`) | Stub — logs only |
| `run_monthly_report` | `MONTHLY_REPORT_CRON` (default `0 8 1 * *`) | Stub — logs only |
| `run_cleanup` | Not yet scheduled | Stub — logs only |
| `run_security_scan` | Not yet scheduled | Implemented, not yet wired to a schedule |

## 7. Internal Workflow

```
run_health_checks()
   → asyncio.gather(
        website_monitor.check_website(),
        api_monitor.check_api(),
        database_monitor.check_database(),
        storage_monitor.check_storage(),
        return_exceptions=True,
     )
   → log any per-check exception, do not raise
```

Every job function in this module follows the same shape: **catch everything, log, never raise** — because an unhandled exception here would otherwise propagate into APScheduler and could silently deregister the job.

## 8. Architecture

This module is the only place in the codebase where monitor modules are invoked outside of a direct Telegram command — see [System Architecture §7.2](../docs/03-system-architecture.md#72-scheduled-job-automation) for the full lifecycle diagram.

## 9. Main Functions

Listed in §6.

## 10. Error Handling

Every function wraps its body in `try/except Exception: logger.exception(...)` (or, for `run_health_checks`, relies on `asyncio.gather(..., return_exceptions=True)`) — this is the one module in the codebase where a bare `except Exception` is the *correct* pattern, since there is no caller to propagate a meaningful error to.

## 11. Security Considerations

`run_scheduled_backup` calls `backup_service.trigger_backup(confirmed=True)` — bypassing the interactive confirmation gate is safe here specifically because it is not user-initiated and is fully audited via the same `Backup Started` notification path as a manual backup.

## 12. Future Improvements

- Implement `run_weekly_report` / `run_monthly_report` aggregation logic
- Implement and schedule `run_cleanup` (retention policy for `audit_logs` / `monitoring_logs`)
- Schedule `run_security_scan` (currently implemented but not registered in `scheduler.register_all_jobs`)
- Automatic Dependency Updates — not yet represented by any function; likely implemented as a GitHub Actions workflow (Dependabot auto-merge policy) rather than Bot-triggered, given GitHub already owns dependency scanning

## 13. Example Usage

Not user-invoked — see [System Architecture §7.2](../docs/03-system-architecture.md#72-scheduled-job-automation) for the trace.

## 14. Related Modules

- [System Architecture](../docs/03-system-architecture.md)
- Every `*_monitor` module
- [Backup Module](./12-backup-module.md), [Reports Module](./16-reports-module.md)
