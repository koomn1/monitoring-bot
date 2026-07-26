# Storage Monitor

**Document:** `modules/06-storage-monitor.md`
**Code:** `bot/modules/storage_monitor/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Verifies Supabase Storage availability and reports bucket-level visibility, backing `/storage`.

## 2. Responsibilities

- List storage buckets as a connectivity/health proof
- Record status history
- (Future) report approximate usage against the free-tier 1GB cap

## 3. Inputs

- Supabase credentials
- `/storage` command or scheduler tick

## 4. Outputs

- `{status, bucket_count}` dict, `monitoring_logs` row

## 5. Dependencies

- `bot/integrations/supabase_client.py:target_db()`
- `bot/db/repositories/logs_repo.py`

## 6. Internal Workflow

```
check_storage()
   → target_db().storage.list_buckets()
   → status = "up" if no exception else raise ExternalServiceError
   → record_monitoring_result(...)
   ← {status, bucket_count}
```

## 7. Architecture

Unlike Website/API/Database monitors, a storage failure currently raises rather than being silently caught into a "down" status — this is a deliberate v1.0 choice reflecting that storage issues are rarer and worth surfacing loudly; see Future Improvements for aligning this with the other monitors' softer failure handling.

## 8. Main Functions

- `check_storage() -> dict`

## 9. Error Handling

`list_buckets()` failure raises `ExternalServiceError("Supabase Storage", ...)`, caught centrally by the router ([System Architecture §9](../docs/03-system-architecture.md#9-error-handling)) when invoked via `/storage`; when invoked from the scheduler, `automation.run_health_checks` catches it via `asyncio.gather(..., return_exceptions=True)`.

## 10. Security Considerations

Uses the service-role key; bucket listing itself reveals bucket names but not object contents — still treated as Admin-role minimum (see [Security §7](../docs/07-security.md#7-authorization-model)).

## 11. Performance Considerations

Bucket listing is a lightweight metadata call, not an object enumeration — safe to run on the same interval as other monitors.

## 12. Future Improvements

- Align failure handling with the soft up/down pattern used by other monitors, plus incident lifecycle + `Storage Failure` notification (not yet wired — see TODO in code)
- Report approximate usage (bytes) against the 1GB free-tier cap once Supabase's usage API is available to project-scoped credentials

## 13. Example Usage

```
/storage
🟢 Storage: Up (3 buckets)
```

## 14. Related Modules

- [Database Monitor](./05-database-monitor.md)
- [Free Infrastructure](../docs/08-free-infrastructure.md)
