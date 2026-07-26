# Roadmap

**Document:** `docs/09-roadmap.md`
**Section:** Project Documentation
**Status:** Draft v1.0

---

## 1. Purpose

Tracks planned evolution of the Bot beyond the v1.0 specification captured in this documentation set, so future contributors (human or AI) know what is intentionally deferred versus what is missing by oversight.

## 2. Responsibilities

- Distinguish "v1.0 scope" from "future scope"
- Sequence future work by dependency, not just desirability

## 3-5. Inputs / Outputs / Dependencies

Not applicable — planning document.

---

## 6. v1.0 Scope (this documentation set)

Everything described in `docs/`, `modules/`, `database/`, `api/`, `deployment/`, and `workflows/` as currently written: single-project monitoring, deployment/rollback/backup/restore orchestration, RBAC, notifications, reports, and a read-only AI assistant.

## 7. Phase 2 — Near-Term

| Item | Depends on |
|---|---|
| Web-based companion dashboard (read-only, free-tier hosted) | v1.0 API layer ([API Reference](../api/01-api-reference.md)) |
| Multi-channel notifications (Telegram + email fallback) | Notifications module stabilized |
| In-memory cache for `bot_config` reads | Configuration module |
| Explicit HTTP 429 / backoff handling per integration | Free Infrastructure budgeting proven in production |

## 8. Phase 3 — Mid-Term

| Item | Depends on |
|---|---|
| Multi-project support (one Bot instance, several monitored products) | Database schema generalized beyond a single Quiz Space target |
| Predictive/trend-based alerting (not just threshold-based) | Sufficient monitoring history accumulated in `monitoring_logs` |
| Two-person confirmation for `/restore` | RBAC model extended beyond single-approver |

## 9. Phase 4 — Long-Term / Exploratory

| Item | Notes |
|---|---|
| Voice-note incident summaries via AI Assistant | Requires Telegram voice message support + AI Assistant read access already in place |
| Self-service admin onboarding (currently manual via `OWNER_USER_IDS`) | Requires a secure invitation/approval flow |

## 10. Internal Workflow

Not applicable.

## 11. Architecture

Not applicable — this document does not describe running code.

## 12. Main Functions

Not applicable.

## 13. Error Handling

Not applicable.

## 14. Security Considerations

Any Phase 2+ item that touches authentication or destructive actions must be reviewed against [Security](./07-security.md) before implementation, not after.

## 15. Performance Considerations

Multi-project support (Phase 3) is the item most likely to require an architecture revisit of [System Architecture §8](./03-system-architecture.md#8-state-ownership) (state ownership), since it changes "the Bot's own data" from singular to per-project.

## 16. Future Improvements

This document *is* the future-improvements ledger; see phases above.

## 17. Example Usage

Not applicable.

## 18. Related Modules

- [Project Overview §12](./01-project-overview.md#12-future-improvements)
- Every module's own "Future Improvements" section feeds into this roadmap

---

**Previous:** [Free Infrastructure](./08-free-infrastructure.md) · **Next:** [README](./10-readme.md)
