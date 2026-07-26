# Deployment Module

**Document:** `modules/08-deployment-module.md`
**Code:** `bot/modules/deployment/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Orchestrates build, deploy, and rollback of the **Quiz Space application** (not the Bot itself — see [Deployment](../docs/06-deployment.md) for that) by dispatching GitHub Actions workflows and reporting their status. Backs `/deploy`, `/build`, `/rollback`.

## 2. Responsibilities

- Trigger the Build Pipeline, Deployment Pipeline, and Rollback Pipeline via `workflow_dispatch`
- Enforce confirmation before any trigger (see [Security §8](../docs/07-security.md#8-destructive-action-confirmation))
- Report current deployment status
- Notify on deployment start (success/failure notifications are triggered by the pipeline's own callback — see [Webhooks](../api/02-webhooks.md))

## 3. Inputs

- `/deploy [confirm]`, `/build [confirm]`, `/rollback [target_sha] [confirm]`
- `GITHUB_TOKEN`, `GITHUB_REPO`

## 4. Outputs

- GitHub Actions `workflow_dispatch` event
- `Deployment Started` / `Rollback Started` notifications
- Deployment status dict for `/system` and `/dashboard`

## 5. Dependencies

- `bot/integrations/github_client.py`
- `bot/modules/notifications/service.py`
- [Deployment Pipeline](../workflows/02-deployment-pipeline.md), [Rollback Pipeline](../workflows/03-rollback-pipeline.md)

## 6. Internal Workflow

```
trigger_deploy(confirmed, environment)
   → if not confirmed: raise ConfirmationRequiredError
   → github_client.dispatch_workflow("deploy.yml", inputs={environment})
   → notifications.notify_deployment_started(environment)
   ← confirmation text

get_deployment_status()
   → github_client.get_latest_workflow_run("deploy.yml")
   ← {status, conclusion, run_id, html_url, created_at}
```

## 7. Architecture

This module never talks to Cloudflare or the hosting target directly for a *deploy* — GitHub Actions owns the actual deploy mechanics (per [Deployment Pipeline](../workflows/02-deployment-pipeline.md)); this module is purely a dispatcher + status reader. This keeps deploy logic in one place (the workflow YAML) rather than duplicated between the Bot and CI.

## 8. Main Functions

- `trigger_build(confirmed) -> str`
- `trigger_deploy(confirmed, environment) -> str`
- `trigger_rollback(confirmed, target_sha) -> str`
- `get_deployment_status() -> dict`

## 9. Error Handling

- Missing confirmation → `ConfirmationRequiredError`, router re-prompts (never executes on first call)
- GitHub API failure → `ExternalServiceError("GitHub", ...)`
- No prior deployment found → `{"status": "no_deployments"}`, not an error

## 10. Security Considerations

- `/deploy` and `/build` require Admin; `/rollback` requires Owner (see [Security §7](../docs/07-security.md#7-authorization-model)) since a rollback can itself be disruptive
- `GITHUB_TOKEN` is scoped to the minimum needed (`actions:write`, `contents:read`) — never a full-access PAT

## 11. Performance Considerations

Dispatching a workflow is a fire-and-forget API call; status must be polled separately via `/system` rather than the Bot blocking on pipeline completion (pipelines can run minutes).

## 12. Future Improvements

- Push-based status updates (via the Deployment Pipeline calling back to a Bot webhook on completion) instead of poll-only — see [Webhooks](../api/02-webhooks.md)
- Environment selector beyond `production` (e.g. staging) once Quiz Space has more than one environment

## 13. Example Usage

```
Admin: /deploy
Bot: ⚠️ This action requires confirmation.
     Reply with /deploy confirm to deploy to production.
Admin: /deploy confirm
Bot: 🚀 Deployment to production triggered.
```

## 14. Related Modules

- [GitHub Module](./09-github-module.md)
- [Deployment Pipeline](../workflows/02-deployment-pipeline.md)
- [Rollback Guide](../deployment/04-rollback-guide.md)
