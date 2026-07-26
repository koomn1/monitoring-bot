# Realtime Monitor

**Document:** `modules/07-realtime-monitor.md`
**Code:** `bot/modules/realtime_monitor/service.py`
**Status:** Draft v1.0 (interface defined, probe implementation pending)

---

## 1. Purpose

Verifies that Supabase Realtime (the websocket layer used for live features in Quiz Space, if any) is reachable.

## 2. Responsibilities

- Perform a websocket handshake probe against the Realtime endpoint
- Record status history

## 3. Inputs

- `SUPABASE_URL`
- Scheduler tick

## 4. Outputs

- `{status}` dict, `monitoring_logs` row

## 5. Dependencies

- A websocket client (not yet added to `requirements.txt` — see Future Improvements)
- `bot/db/repositories/logs_repo.py`

## 6. Internal Workflow (Target Design)

```
check_realtime()
   → open websocket to ${SUPABASE_URL}/realtime/v1/websocket
   → send a heartbeat/ping frame
   → status = "up" if pong received within timeout else "down"
   → record_monitoring_result(...)
   ← {status}
```

## 7. Architecture

Deferred to a lightweight, infrequent probe (not on the same interval as HTTP monitors) because a full websocket handshake is comparatively expensive; see [Free Infrastructure §6](../docs/08-free-infrastructure.md#6-services--free-tier-budgeting).

## 8. Main Functions

- `check_realtime() -> dict` (currently returns `status="unknown"` — see status in code)

## 9. Error Handling

Handshake failure or timeout → `status="down"`. Not yet distinguishing "Realtime not used by Quiz Space" from "Realtime is down" — this requires knowing whether Quiz Space actually uses Realtime channels, which is a product-level fact not yet captured in this documentation set.

## 10. Security Considerations

No admin-only data is transmitted in the probe; it is a pure connectivity check.

## 11. Performance Considerations

Should run at a longer interval than HTTP checks (e.g. every 15–30 minutes) to limit connection overhead — see Future Improvements.

## 12. Future Improvements

- Implement the actual websocket handshake (currently a stub returning `"unknown"`)
- Determine and document whether Quiz Space uses Realtime channels at all; if not, this module can be marked optional/disabled via [Configuration](../docs/05-configuration.md)
- Add incident lifecycle + notification once the probe is implemented

## 13. Example Usage

```
/status  (once implemented)
⚪ Realtime: Unknown
```

## 14. Related Modules

- [Database Monitor](./05-database-monitor.md)
- [Configuration](../docs/05-configuration.md)
