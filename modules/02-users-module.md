# Users Module

**Document:** `modules/02-users-module.md`
**Code:** `bot/modules/users/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Provides read-only visibility into Quiz Space's own end users (distinct from Bot administrators — see [Authentication Module](./01-authentication-module.md)). Backs `/users` and `/user`.

## 2. Responsibilities

- Summarize total user count and recent signups
- Look up a single user by identifier (id or email)
- Detect and surface premium/paying users if Quiz Space's schema distinguishes them

## 3. Inputs

- Telegram command arguments (`/user <id_or_email>`)
- Quiz Space's own `profiles` table (read-only)

## 4. Outputs

- Formatted user summary / detail text for Telegram

## 5. Dependencies

- `bot/db/repositories/users_repo.py`
- Quiz Space's Supabase project (via `bot/integrations/supabase_client.py:target_db()`)

## 6. Internal Workflow

```
/users  → get_user_summary() → { total_users, recent_signups } → formatted reply
/user X → get_user_detail(X) → single profile row → formatted reply
```

## 7. Architecture

This module is strictly read-only against Quiz Space's own data — it never writes to `profiles` or any Quiz Space application table. All writes stay within the Bot's own tables (see [System Architecture §8](../docs/03-system-architecture.md#8-state-ownership)).

## 8. Main Functions

- `get_user_summary() -> dict`
- `get_user_detail(identifier: str) -> dict | None`

## 9. Error Handling

- Unknown identifier → clear "user not found" reply, not a stack trace
- `profiles` table unreachable → `ExternalServiceError`, surfaced as "database unreachable"

## 10. Security Considerations

- User lookups are Admin-role minimum (see [Security §7](../docs/07-security.md#7-authorization-model)) since they expose personal data (email, signup info) of Quiz Space's real users
- No user data is ever logged in `audit_logs` beyond the identifier the admin searched for

## 11. Performance Considerations

`get_recent_signups` is limited (default 5–10 rows) to avoid large payloads in a Telegram message.

## 12. Future Improvements

- Filter/search by plan tier once `profiles` schema defines one (see [Tables](../database/02-tables.md))
- Pagination for `/users` beyond the default summary

## 13. Example Usage

```
Admin: /users
Bot: 👥 Total users: 1,204
     Recent signups: 5
```

## 14. Related Modules

- [Authentication Module](./01-authentication-module.md)
- [Notifications](./19-notifications.md) (New User / New Premium User events)
- [Tables](../database/02-tables.md)
