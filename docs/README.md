# Documentation Authority

> **Status:** CURRENT_STATUS
> **Authority:** Canonical documentation index
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-13
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `tests`

Documentation describes the code; it does not create implementation or evidence authority.

## Normative authority order

1. latest explicit user decision not superseded;
2. `docs/constitution/00` through `09`;
3. the current architecture documents below;
4. current status and roadmap;
5. historical Git revisions as context only.

## Implementation fact authority order

1. current executable code and actual call chains;
2. PostgreSQL schema and current migration head;
3. tests and static checks;
4. reproducible runtime/evidence artifacts;
5. current status documents.

## Current canonical documents

- [System Architecture](architecture/System-Architecture.md)
- [Authority Map](architecture/Authority-Map.md)
- [Data and Evidence Architecture](architecture/Data-and-Evidence-Architecture.md)
- [Research and Strategy Lifecycle](architecture/Research-Strategy-Lifecycle.md)
- [Current State](status/Current-State.md)
- [Capability Matrix](status/Capability-Matrix.md)
- [Gap Register](status/Gap-Register.md)
- [Roadmap](status/Roadmap.md)
- [Runtime Runbook](operations/Runtime-Runbook.md)
- [ADR-010: Phase E Historical Alpha Evidence Production](architecture/decisions/ADR-010-Phase-E-Historical-Alpha-Evidence-Production.md)
- [ADR-011: Phase E2 Selective Historical Evidence Runtime](architecture/decisions/ADR-011-Phase-E2-Selective-Historical-Evidence-Runtime.md)

The Constitution remains the normative source. [Negative and Inconclusive Results](research/Negative-and-Inconclusive-Results.md) is the sole current research-claim registry.

Historical audits, plans, deliveries, superseded architectures, work packages and designed-only specifications were removed from the default tree during the 2026-08-10 convergence. Git history preserves them; [Archive](archive/README.md) explains the boundary.
