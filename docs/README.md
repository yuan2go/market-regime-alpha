# Documentation Authority

> **Status:** CURRENT_STATUS
> **Authority:** Documentation navigation and precedence only
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-29
> **Code Evidence:** `src/market_regime_alpha`, both legacy and target PostgreSQL migration packages, `tests`

Documentation never creates implementation truth, research evidence,
qualification, account state, or trading authority.

## Two truths that must not be collapsed

| Plane | Meaning | Source |
|---|---|---|
| Approved Target | The Hard Cutover architecture to be implemented | Canonical Overall Design, supporting target documents, ADR-015 |
| Current implementation | What the checked-out source, legacy 001–106 migrations, draft target baseline, tests, and reproducible evidence actually do | code → PostgreSQL → tests → artifacts |

The approved Target is normative for new implementation. Foundation is merged
to `main`. The current implementation line extends its mutable
`MRA_REFOUNDATION_1` draft from 13 Foundation tables to 32 tables by adding the
isolated Market/PIT and Selection Core owners. The target Runtime exercises only
a test-scoped `CAPTURE -> NORMALIZE_PIT -> FREEZE_UNIVERSE ->
ASSESS_ELIGIBILITY` slice. Until Runtime/CLI Cutover, the existing 283-table
system remains the only canonical business implementation; there is no dual
write or target fallback.

## Normative authority order

1. latest explicit user decision not superseded;
2. [Canonical Overall Design](architecture/Canonical-Overall-Design.md) and
   [ADR-015](architecture/decisions/ADR-015-Hard-Cutover-and-Schema-Epoch.md);
3. supporting Target documents below;
4. the planning-only [Implementation Roadmap](status/Roadmap.md);
5. historical ADRs, frozen protocols, and evidence reports as provenance;
6. Git history for historical context only.

## Implementation fact authority order

1. executable code and actual call chains;
2. PostgreSQL schema, migrations, canonical writers, and readers;
3. tests and checks actually executed at an exact SHA;
4. reproducible Runtime, replay, and research artifacts;
5. non-authoritative status read models.

No status page, Capability view, Roadmap, Evidence Ledger, report, or CLI output
may write or promote canonical state.

## Approved Target architecture

- [Context Map](../CONTEXT-MAP.md)
- [Canonical Overall Design](architecture/Canonical-Overall-Design.md)
- [System and Runtime Architecture](architecture/System-Architecture.md)
- [Authority Map](architecture/Authority-Map.md)
- [PostgreSQL, Temporal and Evidence Architecture](architecture/Data-and-Evidence-Architecture.md)
- [Research and Decision Lifecycle](architecture/Research-Strategy-Lifecycle.md)
- [Repository Convergence Inventory](architecture/Repository-Convergence-Inventory.md)

Checkpoint traceability:

- [Capability Preservation Matrix](references/WP-ARCHITECTURE-REFOUNDATION-01-Capability-Preservation-Matrix.md)
- [283 to Target Table Disposition](references/WP-ARCHITECTURE-REFOUNDATION-01-Table-Disposition.md)
- [Domain Invariant Catalog](references/WP-ARCHITECTURE-REFOUNDATION-01-Domain-Invariant-Catalog.md)

All documents in this section have Target status. They define the destination,
not current completion.

## Current implementation and forward plan

- [Current State](status/Current-State.md) — exact-SHA, non-authoritative
  implementation snapshot and invalidation rules.
- [Capability Matrix](status/Capability-Matrix.md) — compact current-to-Target
  convergence view; no evidence promotion.
- [Implementation Roadmap](status/Roadmap.md) — the only active engineering
  sequence. It includes unresolved gaps; there is no separate Gap Register.
- [WP-02 Pre-Refoundation Verification Baseline](references/WP-ARCHITECTURE-REFOUNDATION-02-Pre-Refoundation-Verification-Baseline.md)
  — immutable commands/results at the approved design SHA.
- [WP-03 Foundation Verification](references/WP-ARCHITECTURE-REFOUNDATION-03-Foundation-Verification.md)
  — exact-SHA engineering proof for the merged Foundation substrate.
- [WP-04 Market/PIT Verification](references/WP-ARCHITECTURE-REFOUNDATION-04-Market-PIT-Verification.md)
  — exact-SHA engineering proof for the test-only Market/PIT draft slice.
- [WP-05 Selection Core Verification](references/WP-ARCHITECTURE-REFOUNDATION-05-Selection-Core-Verification.md)
  — exact-SHA engineering proof for the test-only Universe/Eligibility draft
  slice; Candidate remains deferred.
- [Runtime Runbook](operations/Runtime-Runbook.md) — current 001–106 operator
  procedures only; it will be rewritten at Runtime/CLI Cutover.

Current State and Capability Matrix are read models. They must display their
generation time, repository SHA, schema epoch, source tree IDs, and proof
ceiling. A later code/schema change invalidates them until regenerated.

## Historical research and decisions

Frozen protocols, negative/inconclusive results, and execution reports under
`docs/research/` and `docs/references/` are retained only as immutable
provenance. They are not the current engineering program and do not constrain
the Hard Cutover to preserve old module/table identities.

ADR-008 through ADR-014 describe superseded implementation eras. The valid
temporal rules originally established by ADR-014 are restated in the Target
architecture; its v1/v2 readers and additive-migration policy are historical and
create no compatibility requirement. ADR-015 owns the new schema epoch and
destructive-recreate decision.

## Status vocabulary

| Status | Meaning |
|---|---|
| `CANONICAL_TARGET_ARCHITECTURE` | approved future architecture; implementation may be absent |
| `CURRENT_ARCHITECTURE` | retained decision that is both implemented and compatible with the Target |
| `CURRENT_STATUS` | navigation or exact-SHA non-authoritative read model |
| `ROADMAP` | planning order only |
| `HISTORICAL` | immutable provenance, not current instruction |
| `SUPERSEDED` | replaced and retained only for traceability |

`CURRENT_ARCHITECTURE` must not label an unimplemented Target document.

## Start here

For architecture or implementation work, read:

1. [Canonical Overall Design](architecture/Canonical-Overall-Design.md)
2. [System Architecture](architecture/System-Architecture.md)
3. [Authority Map](architecture/Authority-Map.md)
4. [Data and Evidence Architecture](architecture/Data-and-Evidence-Architecture.md)
5. [Research and Decision Lifecycle](architecture/Research-Strategy-Lifecycle.md)
6. [Repository Convergence Inventory](architecture/Repository-Convergence-Inventory.md)
7. [Current State](status/Current-State.md)
8. [Capability Matrix](status/Capability-Matrix.md)
9. [Implementation Roadmap](status/Roadmap.md)
10. affected code, schema, tests, and exact evidence

The design says where to converge. Executable evidence says what is true today.
