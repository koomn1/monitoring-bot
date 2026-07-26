# Configuration

**Document:** `docs/05-configuration.md`
**Section:** Project Documentation
**Status:** Draft v1.0

---

## 1. Purpose

Defines the difference between **static configuration** (environment variables, fixed at deploy time — see [Environment Variables](./04-environment-variables.md)) and **runtime configuration** (values an Owner can change live via `/settings`, stored in the `bot_config` table), and specifies exactly what belongs in each category.

## 2. Responsibilities

- Draw the line between "requires a redeploy" and "changeable via Telegram"
- Define the `bot_config` key/value contract
- Define default values for every runtime setting

## 3. Inputs

- `/settings` command arguments (Owner only)
- `bot_config` table rows

## 4. Outputs

- Values consumed by module services at call time (e.g. alert thresholds, maintenance-mode flag)

## 5. Dependencies

- [Database Schema](../database/01-database-schema.md) — `bot_config` table
- `bot/db/repositories/config_repo.py`

---

## 6. Static vs. Runtime Configuration

| Category | Examples | Storage | Change requires |
|---|---|---|---|
| Static | Credentials, URLs, cron schedules, role assignments | Environment variables | Redeploy |
| Runtime | Alert thresholds, maintenance mode, feature toggles, notification verbosity | `bot_config` table | `/settings` command (Owner only) |

## 7. Runtime Settings Reference

| Key | Type | Default | Description |
|---|---|---|---|
| `maintenance_mode` | bool | `false` | When `true`, monitor modules suspend down/up notifications (used during planned maintenance) |
| `website_latency_warn_ms` | int | `1000` | Latency above which `/status` marks the website "degraded" rather than "up" |
| `api_latency_warn_ms` | int | `800` | Same, for the API |
| `notify_on_new_user` | bool | `true` | Whether `New User` notifications are sent |
| `report_verbosity` | enum(`brief`,`full`) | `brief` | Controls how much detail scheduled reports include |

## 8. Internal Workflow

1. A module needing a runtime setting calls `config_repo.get_setting(key)`.
2. If unset in the database, the module falls back to the default listed above (defaults live in each module, not centrally, to keep modules self-contained).
3. `/settings <key> <value>` (Owner only) calls `config_repo.set_setting`.

## 9. Architecture

`bot_config` is a simple key-value table (see [Tables](../database/02-tables.md)) rather than a typed table per setting, so new runtime settings can be introduced by a module without a schema migration.

## 10. Main Functions

- `config_repo.get_setting(key) -> Any | None`
- `config_repo.set_setting(key, value) -> None`
- `config_repo.get_all_settings() -> dict`

## 11. Error Handling

- Unknown key passed to `/settings` → Bot replies listing valid keys rather than silently accepting garbage
- Type mismatch (e.g. non-boolean for `maintenance_mode`) → validated in the handler before writing

## 12. Security Considerations

- `/settings` is Owner-only (see [Security](./07-security.md)) since some settings (e.g. `maintenance_mode`) affect what the Bot reports truthfully to all admins
- No secret ever belongs in `bot_config` — it is not encrypted at rest beyond Supabase's standard encryption

## 13. Performance Considerations

- Runtime settings are read on every relevant check; for high-frequency callers (health checks), consider an in-process cache with a short TTL (future improvement below) rather than a DB round-trip per check

## 14. Future Improvements

- In-memory cache for `bot_config` with a 30–60s TTL to reduce read load
- `/settings reset <key>` to restore a default explicitly

## 15. Example Usage

```
Admin (Owner): /settings maintenance_mode true
Bot: ⚙️ maintenance_mode set to true.
```

## 16. Related Modules

- [Environment Variables](./04-environment-variables.md)
- [Database Schema](../database/01-database-schema.md)
- [Telegram Commands](../modules/17-telegram-commands.md)

---

**Previous:** [Environment Variables](./04-environment-variables.md) · **Next:** [Deployment](./06-deployment.md)
