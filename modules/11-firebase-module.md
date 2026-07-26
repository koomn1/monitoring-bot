# Firebase Module

**Document:** `modules/11-firebase-module.md`
**Code:** `bot/modules/firebase/service.py`
**Status:** Draft v1.0 (optional module)

---

## 1. Purpose

Provides optional visibility into Firebase Free-tier services (push notifications, secondary auth) if Quiz Space uses them. Degrades gracefully to "not configured" when it doesn't.

## 2. Responsibilities

- Report whether Firebase is configured at all
- Report basic reachability of the Firebase Admin SDK
- Send push notifications on behalf of other modules, if ever needed (not currently wired to a command)

## 3. Inputs

- `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON`

## 4. Outputs

- `{configured: bool, status: "up" | "down" | "not_configured"}`

## 5. Dependencies

- `bot/integrations/firebase_client.py` (firebase-admin SDK)

## 6. Internal Workflow

```
get_status()
   → firebase_client.health_check()
   → if ConfigurationError: {"configured": False, "status": "not_configured"}
   → else: {"configured": True, "status": "up"|"down"}
```

## 7. Architecture

This is the reference implementation for how *every* optional module in this system should behave: it never raises to the caller for missing configuration, it reports it as data. See [Environment Variables §7](../docs/04-environment-variables.md#7-internal-workflow) for the general pattern.

## 8. Main Functions

- `get_status() -> dict`

## 9. Error Handling

`ConfigurationError` is caught and converted to `not_configured` status, not surfaced as a Bot error — this is intentional and distinct from every other module's error handling because Firebase is genuinely optional infrastructure.

## 10. Security Considerations

`FIREBASE_SERVICE_ACCOUNT_JSON` is the full service-account credential — treat with the same sensitivity as `SUPABASE_SERVICE_ROLE_KEY` (see [Security](../docs/07-security.md)).

## 11. Performance Considerations

`firebase_admin.initialize_app` is cached via `@lru_cache` so it only initializes once per process, not per call.

## 12. Future Improvements

- Wire `send_push_notification` to a `/notify` admin broadcast command
- Report FCM delivery success/failure rates if Quiz Space sends notable notification volume

## 13. Example Usage

```
/system
Firebase: up
```
or, if unconfigured:
```
Firebase: not_configured
```

## 14. Related Modules

- [Environment Variables](../docs/04-environment-variables.md)
- [Free Infrastructure](../docs/08-free-infrastructure.md)
