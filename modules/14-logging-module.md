# Logging Module

**Document:** `modules/14-logging-module.md`
**Code:** `bot/modules/logging/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Provides the read-side formatting layer over the audit and monitoring log tables. The write-side is centralized and covered in [System Architecture §9](../docs/03-system-architecture.md#9-error-handling) and [Security §10](../docs/07-security.md#10-audit-trail) — every command execution and every monitoring check writes automatically, with no per-module opt-in required.

## 2. Responsibilities

- Retrieve recent command execution logs for `/logs`
- Retrieve monitoring history for a given service (used by future trend features)

## 3. Inputs

- `/logs` command
- `service` + `hours` parameters (internal callers)

## 4. Outputs

- List of formatted log entries

## 5. Dependencies

- `bot/db/repositories/logs_repo.py`

## 6. Internal Workflow

```
get_recent_command_logs(limit)
   → logs_repo.get_recent_logs(limit)
   ← list of audit_log rows

get_service_history(service, hours)
   → logs_repo.get_monitoring_history(service, hours)
   ← list of monitoring_log rows
```

## 7. Architecture

Write path (middleware + monitor modules → `logs_repo`) and read path (this module) are intentionally separated so that no domain module needs to know about logging mechanics to be correctly audited — see [System Architecture §6](../docs/03-system-architecture.md#6-layered-architecture), layer contract rule 2.

## 8. Main Functions

- `get_recent_command_logs(limit: int = 20) -> list[dict]`
- `get_service_history(service: str, hours: int = 24) -> list[dict]`

## 9. Error Handling

Read failures propagate as `ExternalServiceError` like any other database read — logging itself never silently fails on the read side (only the *write* side is defensive, per [Authentication Module §9](./01-authentication-module.md#9-error-handling)'s pattern, to avoid breaking user-facing responses).

## 10. Security Considerations

`/logs` is Admin-role minimum; log contents can reveal operational details (which commands are run, error messages) not meant for Viewer-level users.

## 11. Performance Considerations

Both functions are bounded reads (`limit`, `hours`); no unbounded table scans are exposed to a Telegram command.

## 12. Future Improvements

- Structured log export (CSV) for `/logs --export`
- Retention/cleanup job (see [Automation §12](./20-automation.md#12-future-improvements))

## 13. Example Usage

```
/logs
📜 Recent Activity
/status — 340ms
/deploy — 12ms
```

## 14. Related Modules

- [Security](../docs/07-security.md)
- [Automation](./20-automation.md)
- [Reports Module](./16-reports-module.md)
