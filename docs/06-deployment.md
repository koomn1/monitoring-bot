# Deployment

**Document:** `docs/06-deployment.md`
**Section:** Project Documentation
**Status:** Draft v1.0

---

## 1. Purpose

Describes how the Bot **itself** (not Quiz Space) is deployed and kept running, entirely on free-tier infrastructure. This is distinct from the Deployment Module (`modules/08-deployment-module.md`), which is how the Bot deploys *Quiz Space*.

## 2. Responsibilities

- Define the Bot's own hosting target and runtime model
- Define how the Bot process stays alive on a free tier (which typically sleeps idle services)
- Define the release process for Bot code changes

## 3. Inputs

- Bot source code (this repository)
- `.env` / secret store values (see [Environment Variables](./04-environment-variables.md))

## 4. Outputs

- A running Bot process reachable by Telegram (polling or webhook)

## 5. Dependencies

- [Free Infrastructure](./08-free-infrastructure.md)
- `workflows/01-build-pipeline.md`

---

## 6. Hosting Options (Free Tier)

The Bot is a long-lived process (polling mode) or a lightweight HTTP service (webhook mode). Recommended free-tier hosts, in order of fit:

| Option | Mode | Notes |
|---|---|---|
| A free-tier always-on VM/container host with a generous free monthly allotment | Polling or webhook | Best fit for a long-lived polling process; check current free-tier limits before committing |
| Cloudflare Workers (webhook mode only) | Webhook | Requires porting the Telegram handling to a Workers-compatible request/response model; not a drop-in fit for `python-telegram-bot`'s polling loop |
| GitHub Actions on a schedule (webhook-triggered, not polling) | Webhook, invoked per-update | Only practical if update volume is low; each webhook call would need to cold-start |

**Recommended default:** run the Bot as a single always-on polling process on whichever free-tier container/VM host is available, since polling mode requires no public inbound endpoint and is the simplest to keep within free-tier limits. Webhook mode remains supported in the code (`TELEGRAM_USE_WEBHOOK`) for hosts that only offer request-driven (not always-on) free tiers.

## 7. Internal Workflow (Release Process)

```
1. Push to `main` (or open a PR)
2. Build Pipeline runs (workflows/01-build-pipeline.md) — lint, type-check, tests
3. On merge to `main`: Bot redeploy is triggered
     - either automatically (if the host supports git-push deploys)
     - or via a dedicated `bot-run.yml` workflow that restarts the process
4. Bot comes back online; scheduler re-registers all jobs (state resumes
   from the database, no in-memory state is lost that matters)
```

## 8. Architecture

The Bot is stateless at the process level — every piece of state that must survive a restart (audit logs, monitoring history, incidents, reports, runtime settings) lives in Supabase, not in memory. This means the Bot process can be freely restarted by its host (including free-tier hosts that periodically recycle instances) without data loss.

## 9. Main Functions

Not applicable — deployment is an operational process, not a code interface. See [Deployment Guide](../deployment/01-deployment-guide.md) for the step-by-step.

## 10. Error Handling

- If the Bot process crashes, the host's process supervisor (or a `bot-run.yml` cron-based health-check-and-restart workflow) restarts it
- On restart, `settings.validate()` fails fast if secrets are misconfigured, surfacing the problem in the host's logs immediately rather than running degraded

## 11. Security Considerations

- Deployment secrets live only in the hosting platform's secret store and GitHub Actions secrets — never in the repository
- See [Security](./07-security.md) and [Environment Setup](../deployment/02-environment-setup.md)

## 12. Performance Considerations

- Polling mode has a small inherent latency (Telegram long-poll interval, typically sub-second) — acceptable for an admin tool, not a concern for this use case
- Webhook mode reduces latency further but requires a stable public HTTPS endpoint, which is the tradeoff against staying fully free-tier-simple

## 13. Future Improvements

- Blue/green redeploy of the Bot itself (currently a simple restart)
- Health-checked auto-rollback if the Bot fails to start after a deploy

## 14. Example Usage

See [Deployment Guide](../deployment/01-deployment-guide.md) for the concrete step-by-step first deployment.

## 15. Related Modules

- [Free Infrastructure](./08-free-infrastructure.md)
- [Build Pipeline](../workflows/01-build-pipeline.md)
- [Production Checklist](../deployment/03-production-checklist.md)

---

**Previous:** [Configuration](./05-configuration.md) · **Next:** [Security](./07-security.md)
