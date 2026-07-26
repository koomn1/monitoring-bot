# Website Monitor

**Document:** `modules/03-website-monitor.md`
**Code:** `bot/modules/website_monitor/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Continuously verifies that the Quiz Space public website is reachable and responsive, and manages the open/resolved lifecycle of website-down incidents.

## 2. Responsibilities

- Perform an HTTP check against `WEBSITE_URL` on schedule and on-demand
- Classify the result as up/down (and, via [Configuration](../docs/05-configuration.md), degraded on high latency)
- Record every check in `monitoring_logs`
- Open an incident on the first down result, resolve it on the first subsequent up result
- Trigger `Website Down` / `Website Online` notifications on state transitions only (not on every check)

## 3. Inputs

- `WEBSITE_URL` (environment variable)
- Scheduler ticks (`HEALTH_CHECK_INTERVAL_SECONDS`) or `/status` command

## 4. Outputs

- `{status, latency_ms, status_code}` dict
- `monitoring_logs` row per check
- `incidents` row on open/resolve
- Telegram notification on transition

## 5. Dependencies

- `httpx` (HTTP client)
- `bot/db/repositories/incidents_repo.py`, `logs_repo.py`
- `bot/modules/notifications/service.py`

## 6. Internal Workflow

```
check_website()
   → GET WEBSITE_URL (10s timeout, follow redirects)
   → status = "up" if status_code < 400 else "down"
   → record_monitoring_result(...)
   → _handle_state_transition(status, latency_ms)
        → get_open_incident("website")
        → if down & no open incident: open_incident + notify_website_down
        → if up & open incident exists: resolve_incident + notify_website_online
   ← {status, latency_ms, status_code}
```

## 7. Architecture

State-transition detection (rather than notifying on every failed check) is centralized in `_handle_state_transition` so a website that is down for an hour produces exactly one "down" notification and one "online" notification, not one every 5 minutes.

## 8. Main Functions

- `check_website() -> dict`

## 9. Error Handling

- Any `httpx.HTTPError` (timeout, connection refused, DNS failure) is treated as `status="down"` — the monitor does not distinguish failure causes at the notification level, though the underlying exception is available in logs for `/logs` and `/errors` diagnosis
- Missing `WEBSITE_URL` → `ConfigurationError`, surfaced clearly rather than silently skipping the check

## 10. Security Considerations

The check is a simple unauthenticated GET — it must not include any credential or admin-only path, since it runs unattended on a schedule.

## 11. Performance Considerations

10-second timeout keeps a hung website from blocking the health-check job indefinitely; `automation.run_health_checks` runs this concurrently with other monitors via `asyncio.gather`.

## 12. Future Improvements

- Multi-region checks (currently single-origin, from wherever the Bot runs)
- Content assertion (verify a specific string/element is present, not just a 2xx status)
- Latency trend charting via `chart_display`-style visualization in a future dashboard

## 13. Example Usage

```
/status
🟢 Website: Online (212ms)
```

## 14. Related Modules

- [Notifications](./19-notifications.md)
- [Automation](./20-automation.md)
- [Free Infrastructure](../docs/08-free-infrastructure.md)
