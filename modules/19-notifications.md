# Notifications

**Document:** `modules/19-notifications.md`
**Code:** `bot/modules/notifications/service.py`
**Status:** Draft v1.0 — all 17 notification types implemented

---

## 1. Purpose

Central fan-out for every notification type in this documentation set. No other module sends a Telegram message directly for an alert — everything routes through here so delivery, formatting, and targeting stay consistent.

## 2. Responsibilities

- Format each notification type consistently
- Broadcast to the configured alert channel, or to all Admin+ users individually if no channel is set
- Never fail loudly if one recipient can't be reached (e.g. blocked the Bot)

## 3. Inputs

Calls from monitor modules, deployment/backup modules, and users module — never from Telegram commands directly.

## 4. Outputs

Telegram messages sent via `bot/integrations/telegram_client.py`.

## 5. Dependencies

- `bot/integrations/telegram_client.py`
- `bot/core/permissions.py` (for Admin+ broadcast fallback)

## 6. Complete Notification Type Reference

| Function | Notification |
|---|---|
| `notify_website_down` | Website Down |
| `notify_website_online` | Website Online |
| `notify_api_failure` | API Failure |
| `notify_database_failure` | Database Failure |
| `notify_storage_failure` | Storage Failure |
| `notify_deployment_started` | Deployment Started |
| `notify_deployment_success` | Deployment Success |
| `notify_deployment_failed` | Deployment Failed |
| `notify_rollback_started` | Rollback Started |
| `notify_rollback_completed` | Rollback Completed |
| `notify_backup_started` | Backup Started |
| `notify_backup_completed` | Backup Completed |
| `notify_backup_failed` | Backup Failed |
| `notify_security_alert` | Security Alert |
| `notify_new_user` | New User |
| `notify_new_premium_user` | New Premium User |
| `notify_payment_received` | Payment Received |

## 7. Internal Workflow

```
notify_X(...)
   → format message text
   → _broadcast(text)
        → if TELEGRAM_ALERT_CHANNEL_ID set: send once to that channel
        → else: send individually to every Admin+ user, best-effort
```

## 8. Architecture

`_broadcast` is the single choke point for delivery — adding a new channel type (e.g. email fallback, per [Roadmap](../docs/09-roadmap.md) Phase 2) means changing one function, not seventeen.

## 9. Main Functions

Listed in §6 — one function per notification type, each a thin formatter calling `_broadcast`.

## 10. Error Handling

`telegram_client.broadcast_to_role` catches per-recipient delivery failure (e.g. a user blocked the Bot) and continues to the next recipient rather than aborting the whole broadcast.

## 11. Security Considerations

Notification content must never include secrets or full user PII — e.g. `notify_new_user` takes an `identifier` string that should be a display-safe reference (username or masked email), not raw account data.

## 12. Performance Considerations

Channel-based broadcast (one message) is preferred over per-user broadcast (N messages) whenever `TELEGRAM_ALERT_CHANNEL_ID` is configured — set this in production to reduce Telegram API call volume.

## 13. Future Improvements

- Deduplication window (avoid re-notifying if the same incident flaps within seconds — currently relies entirely on the calling module's own state-transition detection, e.g. [Website Monitor §7](./03-website-monitor.md#7-architecture))
- Per-notification-type severity/routing (e.g. Payment Received to a different channel than Website Down)
- Email fallback channel (see [Roadmap](../docs/09-roadmap.md) Phase 2)

## 14. Example Usage

```
🔴 Website Down
No response after 10.00s.
```

## 15. Related Modules

- Every `*_monitor` module
- [Deployment Module](./08-deployment-module.md), [Backup Module](./12-backup-module.md)
- [Users Module](./02-users-module.md)
