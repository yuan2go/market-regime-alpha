# Deployment and Operations Boundary

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Operational requirements for reproducible daily research  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** 05-Phase-D-Daily-Decision-Engine-V1.md, ../status/External-Blockers.md  
> **Code Evidence:** Current scheduler/notifications are Legacy; canonical workflow not implemented

## Components

- local/controlled scheduler;
- append-only artifact store;
- DuckDB/Parquet for analytical materialization;
- PostgreSQL optional registry/transaction authority when persistence requires it;
- source adapters with timeouts and quality metrics;
- observability, retries, locks and audit logs;
- Feishu/UI delivery adapters reading canonical outputs.

## Operational invariants

1. A Decision Time run has one immutable Run ID.
2. Re-run with identical inputs is idempotent.
3. Partial failure cannot publish a complete recommendation.
4. Data freshness/coverage is monitored and stored.
5. Provider downgrade follows a predeclared policy and lowers evidence authority.
6. Secrets and broker credentials never enter research artifacts.
7. Codex runs in a read-evidence/write-proposal sandbox.

## Recovery

A failed run resumes from the last verified artifact only when upstream identities match. Any input correction creates a new run linked to the failed run; it does not overwrite historical evidence.
