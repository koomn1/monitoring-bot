# API Monitor

**Document:** `modules/04-api-monitor.md`
**Code:** `bot/modules/api_monitor/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Verifies that the Quiz Space backend API is reachable and healthy, using the same state-transition/incident/notification pattern as [Website Monitor](./03-website-monitor.md).

## 2. Responsibilities

- Call `${API_BASE_URL}/health` on schedule and on-demand
- Classify up/down, record history, manage incident lifecycle
- Trigger `API Failure` notification on transition to down

## 3. Inputs

- `API_BASE_URL` (environment variable)
- The API's own `/health` endpoint contract (see [Health Endpoint](../api/03-health-endpoint.md))

## 4. Outputs

- `{status, latency_ms, status_code}` dict, `monitoring_logs` row, `incidents` row, notification on transition

## 5. Dependencies

- `httpx`
- `bot/db/repositories/incidents_repo.py`, `logs_repo.py`
- `bot/modules/notifications/service.py`

## 6. Internal Workflow

Identical pattern to [Website Monitor §6](./03-website-monitor.md#6-internal-workflow), targeting `${API_BASE_URL}/health` instead of the website root.

## 7. Architecture

Deliberately mirrors `website_monitor`'s structure rather than sharing a generic "HTTP monitor" base class — see [Project Structure §7](../docs/02-project-structure.md#7-naming-conventions) rationale: each monitor is small enough that duplication is cheaper than a shared abstraction that would need monitor-specific overrides anyway (e.g. API expects a JSON health payload, website does not).

## 8. Main Functions

- `check_api() -> dict`

## 9. Error Handling

Same model as Website Monitor — any request failure is `status="down"`; `API_BASE_URL` unset raises `ConfigurationError`.

## 10. Security Considerations

The `/health` endpoint called here must itself be unauthenticated and side-effect-free on the API side — see [Health Endpoint](../api/03-health-endpoint.md) for the expected contract.

## 11. Performance Considerations

Same 10s timeout and concurrent-check pattern as Website Monitor.

## 12. Future Improvements

- Extend beyond a single `/health` check to a small set of critical endpoint spot-checks (e.g. auth, quiz submission) once [API Reference](../api/01-api-reference.md) defines them
- Track API error-rate (not just up/down) by parsing the health payload's own reported metrics, if the API exposes them

## 13. Example Usage

```
/status
🟢 API: Online (98ms)
```

## 14. Related Modules

- [Health Endpoint](../api/03-health-endpoint.md)
- [Notifications](./19-notifications.md)
- [Website Monitor](./03-website-monitor.md)
