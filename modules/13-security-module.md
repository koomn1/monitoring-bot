# Security Module

**Document:** `modules/13-security-module.md`
**Code:** `bot/modules/security/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Aggregates the Bot-observable security posture of Quiz Space into a single view: open dependency vulnerabilities and recent unauthorized Bot access attempts. Backs `/security`.

## 2. Responsibilities

- Summarize open GitHub Dependabot alerts by severity
- Count recent unauthorized/forbidden Bot access attempts from `audit_logs`
- Feed the [Reports Module](./16-reports-module.md)'s security report

## 3. Inputs

- GitHub Dependabot data (via [GitHub Module](./09-github-module.md))
- `audit_logs` table

## 4. Outputs

- `{dependabot: {...}, recent_unauthorized_attempts: int}`

## 5. Dependencies

- `bot/modules/github/service.py`
- `bot/db/repositories/logs_repo.py`

## 6. Internal Workflow

```
get_security_overview()
   → github_service.get_security_alerts_summary()
   → logs_repo.get_recent_logs(limit=100)
   → filter for rows where error mentions "Unauthorized"
   ← {dependabot, recent_unauthorized_attempts}
```

## 7. Architecture

This module deliberately does not duplicate the authorization *enforcement* logic (that lives solely in `bot/core/permissions.py` — see [System Architecture §6](../docs/03-system-architecture.md#6-layered-architecture)); it only *reads* the audit trail that enforcement already produced.

## 8. Main Functions

- `get_security_overview() -> dict`

## 9. Error Handling

If GitHub is unreachable, `get_security_alerts_summary()` raises `ExternalServiceError`, propagated to `/security`'s caller — a security overview that silently omits the GitHub half without saying so would be misleading, so this module intentionally does not catch that error itself.

## 10. Security Considerations

`/security` itself requires Admin role — the security overview is, unsurprisingly, sensitive operational data.

## 11. Performance Considerations

`get_recent_logs(limit=100)` is a bounded read; filtering happens in Python rather than a dedicated SQL query for simplicity at current audit-log volumes — revisit if `audit_logs` grows large (see [Automation §6](./20-automation.md) cleanup job).

## 12. Future Improvements

- Move the unauthorized-attempt filter into a proper repository query (`logs_repo.get_unauthorized_attempts`) instead of Python-side filtering, once volume warrants it
- Incorporate Sentry error-spike detection into the same overview
- Automatic Security Scan integration (see [Automation §12](./20-automation.md#12-future-improvements))

## 13. Example Usage

```
/security
🛡️ Security Overview
Open Dependabot alerts: 2
Recent unauthorized attempts: 0
```

## 14. Related Modules

- [GitHub Module](./09-github-module.md)
- [Logging Module](./14-logging-module.md)
- [Security](../docs/07-security.md)
