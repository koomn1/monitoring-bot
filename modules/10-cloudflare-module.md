# Cloudflare Module

**Document:** `modules/10-cloudflare-module.md`
**Code:** `bot/modules/cloudflare/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Provides visibility into the Quiz Space frontend's Cloudflare Pages deployment status and enables a fast, Cloudflare-native rollback path independent of the GitHub Actions [Rollback Pipeline](../workflows/03-rollback-pipeline.md).

## 2. Responsibilities

- Report the latest Pages deployment's status and URL
- Roll back to a previous Pages deployment directly via Cloudflare's own rollback mechanism

## 3. Inputs

- `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_PROJECT_NAME`

## 4. Outputs

- `{id, status, url, created_on}` deployment status dict

## 5. Dependencies

- `bot/integrations/cloudflare_client.py`

## 6. Internal Workflow

```
get_deployment_status()
   → cloudflare_client.get_latest_pages_deployment()
   ← formatted status dict

rollback(deployment_id)
   → cloudflare_client.rollback_to_deployment(deployment_id)
   ← Cloudflare's rollback result
```

## 7. Architecture

Two independent rollback paths exist by design: the GitHub Actions [Rollback Pipeline](../workflows/03-rollback-pipeline.md) (redeploys a prior commit, full CI path) and this module's direct Cloudflare rollback (re-activates a prior *build artifact* instantly, no rebuild). `/rollback` uses the GitHub path by default; the Cloudflare-direct path is available for a faster emergency reversion. See [Rollback Guide](../deployment/04-rollback-guide.md) for when to use which.

## 8. Main Functions

- `get_deployment_status() -> dict`
- `rollback(deployment_id: str) -> dict`

## 9. Error Handling

Cloudflare API failures (including a non-`success` response body) raise `ExternalServiceError("Cloudflare", ...)`.

## 10. Security Considerations

`CLOUDFLARE_API_TOKEN` should be scoped narrowly (Pages Edit/Read + Zone Read for the Quiz Space zone only), never a Global API Key.

## 11. Performance Considerations

Cloudflare-direct rollback is near-instant (no rebuild) — this is its main advantage over the GitHub Actions path during an active incident.

## 12. Future Improvements

- Zone analytics (`get_zone_analytics` in the integration client) surfaced via `/analytics`, not yet wired into a command
- List multiple recent deployments (not just latest) for `/rollback --list`

## 13. Example Usage

```
/system
Cloudflare Pages: success (deployed 12m ago)
```

## 14. Related Modules

- [Deployment Module](./08-deployment-module.md)
- [Rollback Guide](../deployment/04-rollback-guide.md)
- [Free Infrastructure](../docs/08-free-infrastructure.md)
