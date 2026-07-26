# GitHub Module

**Document:** `modules/09-github-module.md`
**Code:** `bot/modules/github/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Provides domain-level GitHub visibility: latest commit, repository metadata, and Dependabot security alerts. Used by [Deployment Module](./08-deployment-module.md), [Security Module](./13-security-module.md), [Reports Module](./16-reports-module.md), and directly by `/system`.

## 2. Responsibilities

- Summarize the latest commit on the default branch
- Summarize open Dependabot alerts by severity

## 3. Inputs

- `GITHUB_TOKEN`, `GITHUB_REPO`

## 4. Outputs

- `{default_branch, latest_commit_sha, latest_commit_message, latest_commit_author}`
- `{total_open, by_severity}`

## 5. Dependencies

- `bot/integrations/github_client.py`

## 6. Internal Workflow

```
get_repo_status()
   → github_client.get_latest_commit() + get_repo_info()
   ← formatted summary dict

get_security_alerts_summary()
   → github_client.get_dependabot_alerts(state="open")
   → group by severity
   ← {total_open, by_severity}
```

## 7. Architecture

This module owns *interpretation* of raw GitHub API responses (e.g. grouping alerts by severity); `bot/integrations/github_client.py` owns only the *transport* (auth headers, error translation). This split keeps the integration client reusable if a second module needs raw GitHub data in a different shape.

## 8. Main Functions

- `get_repo_status() -> dict`
- `get_security_alerts_summary() -> dict`

## 9. Error Handling

Any GitHub API failure propagates as `ExternalServiceError("GitHub", ...)` from the integration client — this module does not add its own error handling beyond that.

## 10. Security Considerations

`GITHUB_TOKEN` needs only `contents:read`, `security_events:read`, and `actions:write` (the latter for [Deployment Module](./08-deployment-module.md)) — never repo admin or org-level scopes.

## 11. Performance Considerations

Both functions are single-call reads with no pagination beyond GitHub's default page size (alerts capped at 50 per [github_client.py](../modules/09-github-module.md)); acceptable for a single-repo project.

## 12. Future Improvements

- Surface CI status (not just Dependabot) from the Build Pipeline's own run history
- Branch protection / required-review status surfaced via `/security`

## 13. Example Usage

```
/system
🖥️ System Overview
GitHub: a1b2c3d — Fix quiz timer bug
Cloudflare Pages: success
Firebase: up
```

## 14. Related Modules

- [Deployment Module](./08-deployment-module.md)
- [Security Module](./13-security-module.md)
- [Build Pipeline](../workflows/01-build-pipeline.md)
