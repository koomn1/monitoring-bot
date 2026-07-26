# Telegram Commands

**Document:** `modules/17-telegram-commands.md`
**Code:** `bot/modules/telegram_commands/handlers.py`
**Status:** Draft v1.0 — all 19 commands wired

---

## 1. Purpose

The adapter layer between Telegram and every domain module. Contains no business logic itself — each handler calls exactly one (or a small composition of) module service functions and formats the result.

## 2. Responsibilities

- Register every command with `bot/core/router.py` via `@command(name)`
- Parse command arguments into the shapes module services expect
- Format module output into Telegram-appropriate text (HTML parse mode)

## 3. Inputs

Every inbound `CommandContext` (user_id, chat_id, command, args, raw_text).

## 4. Outputs

A text string reply per command, returned to `bot/core/router.py:dispatch`.

## 5. Dependencies

Every module under `bot/modules/*` is a potential dependency of this file; imports are done function-locally (inside each handler) to avoid a large fixed import cost at module load time and to prevent import cycles.

## 6. Complete Command Reference

| Command | Min. Role | Module(s) called | Purpose |
|---|---|---|---|
| `/start` | Viewer | auth | Welcome + registration |
| `/help` | Viewer | router (self) | List available commands |
| `/status` | Viewer | website/api/database/storage monitors | Full system status |
| `/dashboard` | Viewer | analytics, deployment | Condensed operational dashboard |
| `/users` | Admin | users | End-user summary |
| `/user` | Admin | users | Single end-user lookup |
| `/database` | Admin | database_monitor | Database health |
| `/storage` | Admin | storage_monitor | Storage health |
| `/deploy` | Admin | deployment | Trigger production deploy |
| `/build` | Admin | deployment | Trigger build only |
| `/rollback` | Owner | deployment | Roll back last deployment |
| `/logs` | Admin | logging | Recent command activity |
| `/errors` | Admin | sentry (via integrations) | Recent unresolved errors |
| `/security` | Admin | security | Security overview |
| `/backup` | Admin | backup | Trigger manual backup |
| `/restore` | Owner | backup | Restore from a backup (destructive) |
| `/analytics` | Viewer | analytics | Traffic + error summary |
| `/reports` | Viewer | reports | Fetch latest report of a type |
| `/settings` | Owner | config_repo | View/change runtime settings |
| `/system` | Admin | github, cloudflare, firebase | Infrastructure overview |

## 7. Internal Workflow

```
router.dispatch(ctx)
   → permissions check (role from table above)
   → matched @command handler in this file
       → parse ctx.args as needed (e.g. "confirm" flag detection)
       → call module service(s)
       → format result as HTML text
   ← text reply
```

## 8. Architecture

Handlers are deliberately kept under ~15 lines each — anything longer is a sign the logic belongs in the module's `service.py` instead. This file should always be readable top-to-bottom as a table of contents for "what can this Bot do."

## 9. Main Functions

One `handle_<command>(ctx: CommandContext) -> str` function per command, registered via the `@command("<name>")` decorator.

## 10. Error Handling

Handlers do not catch exceptions themselves — all error handling is centralized in `bot/core/router.py:dispatch` (see [System Architecture §9](../docs/03-system-architecture.md#9-error-handling)). A handler should let exceptions propagate naturally.

## 11. Security Considerations

The permission table in §6 is the authoritative reference — the actual enforcement lives in `bot/core/permissions.py:COMMAND_MIN_ROLE` and must be kept in sync with this document whenever a command is added or its role changes.

## 12. Performance Considerations

Function-local imports mean the first call to a given command pays a small one-time import cost; subsequent calls in the same process are cached by Python's module system. This is a deliberate tradeoff for decoupling over micro-optimizing cold-start.

## 13. Future Improvements

- Inline keyboard / callback-query support for multi-step flows (currently all commands are single-message request/response)
- `/help <command>` for per-command detail instead of only a flat list

## 14. Example Usage

See [Project Overview §13](../docs/01-project-overview.md#13-example-usage) for a full `/status` trace.

## 15. Related Modules

Every module listed in §6's "Module(s) called" column.
