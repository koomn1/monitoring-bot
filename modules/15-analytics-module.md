# Analytics Module

**Document:** `modules/15-analytics-module.md`
**Code:** `bot/modules/analytics/service.py`
**Status:** Draft v1.0

---

## 1. Purpose

Unifies traffic analytics (Umami and/or Google Analytics) with error volume (Sentry) into a single `/analytics` view.

## 2. Responsibilities

- Fetch Umami stats for a given period, if configured
- Fetch Sentry unresolved-issue count, if configured
- Degrade gracefully per-source when a source is not configured

## 3. Inputs

- `/analytics` command
- `period` parameter (default `24h`)

## 4. Outputs

- `{period, umami: dict | None, error_count: int | None}`

## 5. Dependencies

- `bot/integrations/analytics_client.py`
- `bot/integrations/sentry_client.py`

## 6. Internal Workflow

```
get_analytics_summary(period)
   → try: analytics_client.get_umami_stats(period) except ConfigurationError: None
   → try: sentry_client.get_issue_count() except ConfigurationError: None
   ← merged summary dict
```

## 7. Architecture

Each source is fetched independently and failures are isolated per-source (a missing Sentry config does not prevent Umami data from being shown, and vice versa) — this is the same graceful-degradation pattern as [Firebase Module](./11-firebase-module.md).

## 8. Main Functions

- `get_analytics_summary(period: str = "24h") -> dict`

## 9. Error Handling

Only `ConfigurationError` is caught per-source (meaning "not set up"); a genuine `ExternalServiceError` from either source (misconfigured but present credentials failing at request time) is allowed to propagate, since that indicates something is broken rather than simply unconfigured.

## 10. Security Considerations

`/analytics` is Viewer-accessible (see [Security §7](../docs/07-security.md#7-authorization-model)) since traffic/error counts are lower-sensitivity than deployment or security data.

## 11. Performance Considerations

Both source calls could run concurrently (`asyncio.gather`) rather than sequentially — see Future Improvements; current implementation is sequential for simplicity.

## 12. Future Improvements

- Run Umami and Sentry fetches concurrently
- Add GA4 Data API read support (currently only the write-side Measurement Protocol client exists, for sending events — see `bot/integrations/analytics_client.py:send_ga_event`)
- Top-pages / top-referrers breakdown, not just aggregate counts

## 13. Example Usage

```
/analytics
📈 Analytics
Errors (24h): 3
```

## 14. Related Modules

- [Reports Module](./16-reports-module.md)
- [Free Infrastructure](../docs/08-free-infrastructure.md)
