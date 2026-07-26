# Authentication Module

**Document:** `modules/01-authentication-module.md`
**Code:** `bot/modules/auth/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Resolves every inbound Telegram user to a role (Owner / Admin / Viewer / none) and maintains an audit-visible registry of every user who has ever interacted with the Bot, regardless of authorization outcome.

## 2. Responsibilities

- Resolve `user_id` → `Role | None` on every interaction
- Record/update the caller's row in `bot_users` for audit visibility
- Provide `is_known_bot_user()` for other modules that need a lightweight "has this person ever used the bot" check

## 3. Inputs

- Telegram `user_id`, `username` (from the update)
- `OWNER_USER_IDS` / `ADMIN_USER_IDS` / `VIEWER_USER_IDS` environment variables

## 4. Outputs

- A `Role` enum value or `None`
- An upserted row in the `bot_users` table

## 5. Dependencies

- `bot/core/permissions.py` (role source of truth)
- `bot/db/repositories/users_repo.py`

## 6. Internal Workflow

```
authenticate(user_id, username)
   → permissions.get_role(user_id)     # env-list membership check
   → users_repo.upsert_bot_user(...)   # audit record, regardless of role
   ← Role | None
```

## 7. Architecture

This module is intentionally thin — it does not own the role source of truth (that is `bot/core/permissions.py`, reading environment variables per [System Architecture §8](../docs/03-system-architecture.md#8-state-ownership)). Its only job is the audit side-effect and a convenience wrapper.

## 8. Main Functions

- `authenticate(user_id: int, username: str | None) -> Role | None`
- `is_known_bot_user(user_id: int) -> bool`

## 9. Error Handling

A failed `upsert_bot_user` write (e.g. database temporarily unreachable) must not block authentication — the role resolution from environment variables always succeeds independent of the database; the audit write failure is logged but does not raise to the caller.

## 10. Security Considerations

- This module never grants access — it only records and reports what `permissions.py` already decided
- Unauthorized attempts (role = `None`) are still recorded in `bot_users` with role `"UNAUTHORIZED"` for visibility into who has tried to use the Bot

## 11. Performance Considerations

One upsert per interaction; acceptable at expected admin-tool volumes (see [Free Infrastructure](../docs/08-free-infrastructure.md)).

## 12. Future Improvements

- Self-service admin invitation flow (see [Roadmap](../docs/09-roadmap.md) Phase 4)
- Track last-seen timestamp per bot_user for a future `/users --admins` view

## 13. Example Usage

```
Telegram user (not in any role list) sends /status
→ authenticate() returns None
→ router replies "🚫 You are not authorized to use this bot."
→ bot_users row recorded with role="UNAUTHORIZED" for audit visibility
```

## 14. Related Modules

- [Security](../docs/07-security.md)
- [Security Module](./13-security-module.md)
- [Logging Module](./14-logging-module.md)
