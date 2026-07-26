# Reports Module

**Document:** `modules/16-reports-module.md`
**Code:** `bot/modules/reports/service.py`
**Status:** Draft v1.0 (daily implemented; weekly/monthly pending)

---

## 1. Purpose

Generates and persists periodic and on-demand reports summarizing Quiz Space's operational state, combining data from [Analytics Module](./15-analytics-module.md) and [Security Module](./13-security-module.md) (and, as they mature, other modules).

## 2. Responsibilities

- Generate the daily report (scheduled via [Automation](./20-automation.md))
- Persist every generated report to the `reports` table
- Serve the latest report of a given type for `/reports`

## 3. Inputs

- Scheduled trigger (`DAILY_REPORT_CRON`, etc.) or `/reports [type]` command

## 4. Outputs

- Formatted report text, persisted `reports` row

## 5. Dependencies

- `bot/modules/analytics/service.py`, `bot/modules/security/service.py`
- `bot/db/repositories/reports_repo.py`

## 6. Internal Workflow

```
generate_daily_report()
   → analytics_service.get_analytics_summary("24h")
   → security_service.get_security_overview()
   → format into HTML text
   → reports_repo.save_report(type="daily", content, metadata)
   ← content
```

## 7. Report Types (per original specification)

| Type | Status |
|---|---|
| Daily | Implemented |
| Weekly | Interface defined, aggregation pending (see [Automation §12](./20-automation.md#12-future-improvements)) |
| Monthly | Interface defined, aggregation pending |
| Performance | Planned — depends on latency history in `monitoring_logs` |
| Database | Planned — depends on Database Monitor history |
| Infrastructure | Planned — combines all `*_monitor` history |
| Deployment | Planned — depends on Deployment Module's GitHub Actions run history |
| Analytics | Available on-demand via `/analytics`; scheduled version planned |
| Security | Available on-demand via `/security`; scheduled version planned |

## 8. Architecture

Reports are persisted (not just sent and discarded) so `/reports <type>` can always return the most recent one without regenerating — regeneration is explicit (scheduled job or an eventual `/reports <type> --regenerate` flag).

## 9. Main Functions

- `generate_daily_report() -> str`
- `get_report(report_type: str) -> dict | None`

## 10. Error Handling

If either `analytics_service` or `security_service` raises, `generate_daily_report()` currently propagates the error — the scheduled job wrapper (`automation.run_daily_report`) catches and logs it so a failed report generation does not crash the scheduler, but the report is simply not produced that day rather than produced with partial/misleading data.

## 11. Security Considerations

`/reports` is Viewer-accessible; report content should never include raw secrets or full user PII — only aggregate counts (see [Users Module §10](./02-users-module.md#10-security-considerations) for the related PII-handling stance).

## 12. Performance Considerations

Report generation runs on a schedule during low-traffic windows by default (`DAILY_REPORT_CRON=0 8 * * *`) — see [Project Overview §11](../docs/01-project-overview.md#11-performance-considerations-summary).

## 13. Future Improvements

- Implement weekly/monthly aggregation (currently logs a "not yet implemented" message — see `bot/modules/automation/service.py`)
- Implement the remaining report types listed in §7
- CSV/exportable report format

## 14. Example Usage

```
/reports daily
📊 Daily Report — Quiz Space
Errors (24h): 3
Open security alerts: 2
```

## 15. Related Modules

- [Analytics Module](./15-analytics-module.md)
- [Security Module](./13-security-module.md)
- [Automation](./20-automation.md)
