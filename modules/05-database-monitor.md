# Database Monitor

**Document:** `modules/05-database-monitor.md`
**Code:** `bot/modules/database_monitor/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Verifies that Quiz Space's Supabase Postgres database is reachable and responsive, using a minimal, low-cost query rather than a full health/status API (Supabase does not expose one directly to this Bot's credential scope).

## 2. Responsibilities

- Perform a lightweight query against a known small table/view to prove connectivity
- Record latency and status history
- Manage the `database` incident lifecycle and `Database Failure` notification

## 3. Inputs

- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- Scheduler ticks or `/database` command

## 4. Outputs

- `{status, latency_ms}` dict, `monitoring_logs` row, incident lifecycle, notification on transition

## 5. Dependencies

- `bot/integrations/supabase_client.py:health_check()`
- `bot/db/repositories/incidents_repo.py`, `logs_repo.py`

## 6. Internal Workflow

```
check_database()
   → supabase_client.health_check()
        → SELECT id FROM monitoring_heartbeat LIMIT 1
   → status = "up" if no exception else "down"
   → record_monitoring_result(...)
   → _handle_state_transition(...)
   ← {status, latency_ms}
```

## 7. Architecture

Uses a dedicated `monitoring_heartbeat` table (see [Tables](../database/02-tables.md)) rather than querying a real application table, so the health check has predictable, minimal cost and does not depend on Quiz Space's schema staying stable.

## 8. Main Functions

- `check_database() -> dict`

## 9. Error Handling

Any exception from the Supabase client (network, auth, or query error) is treated uniformly as `status="down"` — the specific exception is logged for `/errors` and `/logs` diagnosis, but the up/down signal stays binary for notification purposes.

## 10. Security Considerations

Uses the service-role key (bypasses RLS) since this is an internal health probe, not a user-facing query — see [Security](../docs/07-security.md) for service-role key handling requirements. This is the highest-sensitivity credential in the system; it must never be logged.

## 11. Performance Considerations

`LIMIT 1` keeps the check's cost negligible regardless of table size; this is the cheapest possible proof of connectivity short of a raw TCP check.

## 12. Future Improvements

- Track connection pool saturation if/when Supabase exposes that metric to project owners
- Query latency percentiles over time (currently only the single last-check latency is surfaced in `/status`)

## 13. Example Usage

```
/database
🟢 Database: Up
```

## 14. Related Modules

- [Tables](../database/02-tables.md)
- [Storage Monitor](./06-storage-monitor.md)
- [Notifications](./19-notifications.md)
