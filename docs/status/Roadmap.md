# Architecture Re-foundation Implementation Roadmap

> **Status:** ROADMAP
> **Authority:** Planning and dependency order only; never business, evidence, or qualification Authority
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-28
> **Approved Design:** `d0d1f3152a20f1a3f4f9b8a1d9c4383a49162fb7`
> **Current Implementation Parent:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Code Evidence:** `docs/architecture/Canonical-Overall-Design.md`, `docs/status/Current-State.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-01-Domain-Invariant-Catalog.md`

Architecture Re-foundation is the only active engineering program. Historical
Alpha Proof protocols/results remain evidence provenance, not executable
Roadmap items. This document includes the unresolved gap register; there is no
second planning source.

## Sequence

```text
Foundation
→ Market/PIT
→ Universe/Eligibility/Candidate
→ Research/Qualification
→ Decision/Outcome
→ Execution/Account
→ Runtime/CLI Cutover
→ Legacy deletion/qualification
```

No stage begins canonical writes until its predecessor exit gate passes. Before
Runtime/CLI Cutover, completed target modules are test-only and the old Runtime
remains the sole current implementation. There is no dual write or
availability-selected fallback.

## Checkpoints and exit gates

| Stage | Required scope | Exit gate before next stage |
|---|---|---|
| **1. Foundation** | target package boundaries and dependency tests; shared value types; sole `bootstrap.py` composition contract; schema epoch/catalog preflight; unreleased `001_baseline.sql` build contract; stable seeds; cross-cutting schema/migration, command receipt, audit and Artifact metadata foundations | empty PostgreSQL → foundational baseline → seed → verify; retry idempotent; wrong/legacy/unknown epoch fails before DDL; foundational PK/FK/unique/check/index obligations verified; no old migration import |
| **2. Market/PIT** | Provider/Product, Capture, Instrument, Session, Classification, Market/Instrument/Corporate Action revisions, Source Gap; exact temporal and price-basis semantics; artifact binding | capture → normalize → exact/as-of query passes clean-database, revision, missing/placeholder/suspension, concurrency, artifact-integrity and PIT tests |
| **3. Universe/Eligibility/Candidate** | Universe revision/member, typed Eligibility policy/rules/assessment/reasons, Candidate policy/components/set/score components | Market-only dependency direction; complete three-state funnel and counts; deterministic ties; Decision-time evidence; empty-set and concurrent idempotency tests |
| **4. Research/Qualification** | Dataset/Feature/Target/Partition/Experiment/Model/Evaluation/Evidence/Assessment/Qualification aggregates and Artifact lineage | Evidence Class, Assessment Status and proof floors stay independent; negative results immutable; qualification cannot exceed floors; replay/lineage tests pass |
| **5. Decision/Outcome** | Decision Run, Context, Signal, Forecast, Opportunity, Thesis, Strategy, Portfolio, sole post-Portfolio Risk; Outcome/Metric/Attribution | Candidate → Context direction has no cycle; Opportunity has no Risk authorization; exact Target/Outcome/MFE/MAE availability semantics and post-Portfolio Risk constraints pass |
| **6. Execution/Account** | Account epoch, Intent, observed Fill/corrections/allocations, broker observations, reconciliation, typed non-trade basis events, derived Position/sleeves | trade delta only from effective Fill; opening/corporate-action/reconciliation invariants; reservation, concurrency, correction, restart and reconciliation tests pass |
| **7. Runtime/CLI Cutover** | complete and freeze the 91-table baseline; one Run/Step/Attempt/Lease/Fence Runtime; one `mra` CLI tree; target repositories/adapters, inspection/read models, recovery and Artifact integrity operations | baseline checksum/seed/catalog verify all 91 tables; clean DB canonical capture → decision → mutation → query → outcome/evidence; restart/recovery/concurrency/idempotency/replay pass; old Runtime receives no canonical entry or write |
| **8. Legacy deletion/qualification** | remove old packages, 001–106 migrations, repositories, CLIs, compatibility readers, parallel journals/compositions, legacy tests after invariant replacement; rewrite runbook/status generators | all 98 invariant IDs covered; zero old imports/writers/tables/entry points; full gate clean; destructive cutover rehearsed on an explicitly provisioned database; qualification remains at actual evidence floor |

The target `001_baseline.sql` is an unreleased, reviewable build artifact during
Stages 1–6. Foundation establishes its epoch/bootstrap and cross-cutting
relations; each context checkpoint adds only its own frozen semantics and DDL.
Stage 7 verifies the complete 91-table catalog and makes the baseline checksum
immutable when the new epoch is released. Later changes use forward-only `002+`
migrations; no compatibility schema is introduced.

## Dependency-owned unresolved gaps

| Gap | Owning stage | Required resolution |
|---|---|---|
| Current migration operator falls through to `pg_catalog` when the configured schema is absent | Foundation | epoch bootstrap must create/verify the exact schema or fail with a typed pre-DDL error; never rely on `search_path` fallback |
| Current live database business-row inventory was unavailable to the design audit role | Foundation / Cutover | use a newly provisioned empty target database; any old-database destruction requires separate exact-OID authorization |
| Provider availability/finality semantics may be absent | Market/PIT | store `UNKNOWN`/Exploratory and block historical visibility inflation; adapter qualification is purpose-scoped |
| Corporate-action and broker account semantics vary | Market/PIT / Execution | adapter-specific fixtures and qualification; no inference from adjusted prices or unexplained broker deltas |
| Target physical indexes are not plan-validated | each persistence stage | representative query plans and measured indexes before stage exit |
| Artifact volume/retention is unmeasured | Foundation / Runtime | no partitioning by aesthetics; measure write volume, vacuum/retention and dominant plans |
| Unknown external broker effects lack an operator workflow | Execution / Runtime | remain reconciliation-required; no broker adapter or blind retry before workflow proof |
| Formal PIT/OOS, sustained Prospective value, Production, and broker evidence are absent | Qualification | remain blocked/unsupported; engineering cutover cannot promote them |

## Entry decision for implementation

Foundation is dependency-ready when the Repository Governance checkpoint is
committed with its full validation green. Market/PIT becomes dependency-ready
only after the Foundation exit gate passes. Technical readiness does not itself
authorize implementation; the next work package must explicitly grant the
corresponding business/schema implementation scope.

No Alpha hypothesis, model optimization, OOS outcome access, Provider
qualification, broker integration, or destructive database operation belongs to
Foundation or Market/PIT unless separately approved.
