# Free Infrastructure

**Document:** `docs/08-free-infrastructure.md`
**Section:** Project Documentation
**Status:** Draft v1.0

---

## 1. Purpose

Documents every free-tier service the project relies on, the specific free-tier limits relevant to this Bot's usage pattern, and the strategy for staying within them indefinitely without ever requiring a paid upgrade.

## 2. Responsibilities

- Enumerate every external service and its free-tier constraints as they apply to this project
- Define the polling/request budget per service so automation never exceeds free quotas
- Define fallback behavior if a quota is ever approached

## 3. Inputs

Each service's published free-tier limits (subject to change by the provider — this document should be revisited periodically; see [Roadmap](./09-roadmap.md)).

## 4. Outputs

Configuration values (polling intervals, cron schedules — see [Environment Variables](./04-environment-variables.md)) tuned to stay comfortably under quota.

## 5. Dependencies

All integration clients under `bot/integrations/`.

---

## 6. Services & Free-Tier Budgeting

| Service | Free-tier constraint (typical, verify current terms) | This project's usage pattern | Budgeting strategy |
|---|---|---|---|
| Telegram Bot API | No hard rate limit for reasonable bot traffic; soft limits on messages/second per chat | Command responses + notifications, low volume (single-digit admins) | No special handling needed at this scale |
| GitHub Actions | Free minutes/month for public repos are unlimited; private repos have a monthly minute allotment | Build/deploy/rollback/backup/health-check workflows | Keep workflows short (lint+test, not full E2E suites); schedule health-check workflow only if NOT duplicating the Bot's own `scheduler.py` checks |
| Supabase Free | Row/storage/bandwidth caps, project pauses after a period of inactivity | Bot's own audit/monitoring tables (low write volume) + reading Quiz Space's own project | The Bot's own frequent health-check pings to Supabase double as activity that helps prevent free-tier project pausing |
| Cloudflare Free (Pages/Workers) | Generous free request allotment for Pages; Workers free tier has a daily request cap | Reading deployment status, triggering rollbacks (infrequent, admin-driven) | Well within free tier at admin-tool call volumes |
| Firebase Free (Spark plan) | Caps on reads/writes/notifications per day | Optional push notifications only | Only used if Quiz Space itself uses Firebase; the Bot's own calls are infrequent |
| Sentry Free | Capped events/month | Bot only *reads* issue data (does not consume event quota itself) | Read-only usage does not affect the event quota |
| Google Analytics | Free at standard usage tiers | Read-only reporting queries | Batch queries in scheduled reports rather than per-command where possible |
| Umami | Free if self-hosted (or generous free tier on umami.is) | Read-only stats queries | Negligible load |

## 7. Internal Workflow

```
docs/04-environment-variables.md defines polling intervals/cron schedules
   → bot/core/scheduler.py enforces them
   → each integrations/* client makes the minimum number of calls needed
      per check (e.g. one lightweight query, not a full table scan)
```

## 8. Architecture

No service is called more frequently than its monitor's configured interval (`HEALTH_CHECK_INTERVAL_SECONDS`, default 5 minutes) — this single knob is the primary lever for staying within every free tier simultaneously.

## 9. Main Functions

Not applicable — this document governs configuration values, not code.

## 10. Error Handling

If a provider returns a rate-limit response (HTTP 429 or provider-specific equivalent), the relevant `integrations/*` client should back off (see `bot/utils/retry.py`) and the monitor should report "rate limited" rather than "down" — this distinction matters so admins are not falsely alarmed by the Bot's own quota pressure. *(Note: explicit 429 handling per client is listed as a Future Improvement below — see each integration client's current `except httpx.HTTPError` handling.)*

## 11. Security Considerations

Free-tier accounts are still real production credentials — see [Security](./07-security.md) for handling requirements. Free does not mean low-stakes: a leaked Supabase service-role key or GitHub token on a free-tier project is exactly as dangerous as on a paid one.

## 12. Performance Considerations

Free-tier services often have higher latency/cold-start behavior than paid tiers (e.g. Supabase project pausing after inactivity, Workers cold starts). The Bot's own regular health checks help keep the monitored Supabase project warm as a side effect.

## 13. Future Improvements

- Add explicit HTTP 429 handling with provider-specific backoff in each `integrations/*` client
- Add a `/system quota` view aggregating known usage against known limits, once each provider's usage-reporting API is wired in
- Revisit this document whenever a provider changes its free-tier terms

## 14. Example Usage

Not applicable — reference document.

## 15. Related Modules

- [Environment Variables](./04-environment-variables.md)
- [Automation](../modules/20-automation.md)
- All `modules/*-monitor.md` and `modules/09` through `modules/11` (GitHub, Cloudflare, Firebase)

---

**Previous:** [Security](./07-security.md) · **Next:** [Roadmap](./09-roadmap.md)
