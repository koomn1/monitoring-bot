# Security

**Document:** `docs/07-security.md`
**Section:** Project Documentation
**Status:** Draft v1.0

---

## 1. Purpose

Defines the Bot's complete security model: authentication, authorization, secret handling, audit logging, and the specific safeguards around destructive operations. Every module's own "Security Considerations" section defers to this document as the source of truth.

## 2. Responsibilities

- Define authentication (who can talk to the Bot at all)
- Define authorization (what each role may do)
- Define secret handling policy
- Define the audit trail requirement
- Define confirmation requirements for destructive actions
- Define webhook signature verification

## 3. Inputs

- Telegram `user_id` on every update
- Environment-sourced role lists
- Inbound webhook payloads + signatures

## 4. Outputs

- Allow/deny decisions
- `audit_logs` rows

## 5. Dependencies

- `bot/core/permissions.py`, `bot/core/middleware.py`
- [Environment Variables](./04-environment-variables.md)

---

## 6. Authentication Model

The Bot recognizes exactly three roles, defined entirely by Telegram numeric user ID membership in an environment variable list (see [Environment Variables §6](./04-environment-variables.md)):

- **Owner** — full control, including destructive/irreversible actions
- **Admin** — operational control (deploy, backup, monitoring), not irreversible actions
- **Viewer** — read-only (status, dashboard, reports, analytics)

Any Telegram user not present in one of these three lists receives a flat "not authorized" response to every command and is logged as an unauthorized access attempt (see [Authentication Module](../modules/01-authentication-module.md)).

## 7. Authorization Model

Every command has a minimum required role, enforced centrally in `bot/core/permissions.py:COMMAND_MIN_ROLE` — never re-implemented per-handler. Unknown commands default to requiring Owner (fail closed). The full command-to-role mapping is in [Authentication Module §6](../modules/01-authentication-module.md).

## 8. Destructive Action Confirmation

Any action that is irreversible or hard to reverse (`/deploy`, `/build`, `/rollback`, `/backup`, `/restore`) requires an explicit `confirm` argument on the command. The first invocation without `confirm` returns the consequence of the action in plain language and asks the user to resend with `confirm` — it never executes on the first call. This is implemented uniformly via `ConfirmationRequiredError` (see [System Architecture §9](./03-system-architecture.md#9-error-handling)).

## 9. Secret Handling

- All secrets (see [Environment Variables](./04-environment-variables.md) for the full **Secret**-flagged list) are stored only as environment variables / platform secret stores
- Secrets are never logged — `bot/core/middleware.py` logs command name and arguments, but command handlers must not pass raw secrets as arguments in the first place (none currently do)
- Secrets are never echoed back in a Telegram message, including in error messages (`ExternalServiceError` messages are sanitized to exclude credentials)

## 10. Audit Trail

Every command execution — successful or not — is recorded in `audit_logs` with: `user_id`, `command`, `args`, `duration_ms`, `error` (if any), `created_at`. This is non-optional and implemented once, centrally, in `bot/core/middleware.py`, so no module can accidentally skip logging.

## 11. Webhook Signature Verification

Inbound webhooks (GitHub, and any future source) must verify their signature before processing:

- **GitHub:** HMAC-SHA256 over the raw request body using `GITHUB_WEBHOOK_SECRET`, compared against the `X-Hub-Signature-256` header
- Requests failing signature verification are rejected with `401` and logged as a potential security event, never processed

See [Webhooks](../api/02-webhooks.md) for the endpoint-level contract.

## 12. Internal Workflow

```
Update / Webhook received
   → identify caller (Telegram user_id, or webhook signature)
   → resolve role / verify signature
   → if disallowed: log + generic denial response, STOP
   → if destructive action without `confirm`: explain + STOP
   → execute
   → audit log (always, regardless of outcome)
```

## 13. Architecture

See [System Architecture §8](./03-system-architecture.md#8-state-ownership) for why RBAC is environment-sourced, not database-sourced — this is a deliberate availability/security tradeoff: the Owner's access can never be revoked by a database compromise or outage, only by whoever controls the deployment's secrets.

## 14. Main Functions

- `permissions.require_command_permission(user_id, command) -> Role`
- `middleware.with_audit_log(ctx, next_fn) -> str`
- Webhook signature verifiers (see [Webhooks](../api/02-webhooks.md))

## 15. Error Handling

Covered by [System Architecture §9](./03-system-architecture.md#9-error-handling); security-specific: unauthorized/forbidden attempts always produce a generic message (never revealing which specific check failed) to avoid giving an attacker diagnostic information.

## 16. Security Considerations (Meta)

- Principle of least privilege by default: new commands must be explicitly added to `COMMAND_MIN_ROLE`; the default for anything unlisted is Owner-only
- Regular rotation of `GITHUB_TOKEN`, `CLOUDFLARE_API_TOKEN`, and `SUPABASE_SERVICE_ROLE_KEY` is a recommended operational practice (see [Production Checklist](../deployment/03-production-checklist.md))

## 17. Performance Considerations

Authorization checks are in-memory list lookups (`user_id in [...]`) — negligible cost, no database round-trip required for every command.

## 18. Future Improvements

- Rate limiting per user_id to prevent command spam (currently only implicit via `RateLimitedError`, not yet wired to a concrete limiter)
- Optional two-person confirmation for the most destructive actions (`/restore`)
- Automatic secret-age warnings surfaced via `/security`

## 19. Example Usage

```
Admin (Admin role): /rollback
Bot: ⚠️ This action requires confirmation.
     Reply with /rollback confirm to roll back the last deployment.

Admin: /rollback confirm
Bot: ⏪ Rollback triggered.
```

## 20. Related Modules

- [Authentication Module](../modules/01-authentication-module.md)
- [Security Module](../modules/13-security-module.md)
- [Logging Module](../modules/14-logging-module.md)
- [Webhooks](../api/02-webhooks.md)

---

**Previous:** [Deployment](./06-deployment.md) · **Next:** [Free Infrastructure](./08-free-infrastructure.md)
