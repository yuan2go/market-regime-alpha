# Architecture Re-foundation Implementation Roadmap

> **Status:** ROADMAP
> **Authority:** Planning and dependency order only; never business, evidence, or qualification Authority
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-29
> **Approved Design:** `d0d1f3152a20f1a3f4f9b8a1d9c4383a49162fb7`
> **Implementation Line Start:** `c3ac21ef1e13f2e8408d30b0481fa9b74c4f9539`
> **Foundation Source Checkpoint:** `eeff49c7a3995ba6d65045be88d4244617301234`
> **Market/PIT Source Checkpoint:** `e7a276a30f71a98b6b32580fa0a4840c2e269b9f`
> **Selection Core Source Checkpoint:** `44caf94aac86c51bb0e69968aadc4dc47ff84907`
> **Research Definition Work Start:** `7932fda7f41c44bc29f04672caaef75d6b9b2c69`
> **Research Definition Source Checkpoint:** `22a5ec692fcc261182197c2953a0a860d7cd6f94`
> **Code Evidence:** `docs/architecture/Canonical-Overall-Design.md`, `docs/status/Current-State.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-01-Domain-Invariant-Catalog.md`

Architecture Re-foundation is the only active engineering program. Historical
Alpha Proof protocols/results remain evidence provenance, not executable
Roadmap items. This document includes the unresolved gap register; there is no
second planning source.

## Sequence

```text
Foundation
→ Market/PIT
→ Selection Core: Universe/Eligibility
→ minimal Research Definition substrate required by Candidate
→ Candidate closure
→ Research Evaluation/Evidence/Qualification
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

| Stage | State | Required scope | Exit gate before next stage |
|---|---|---|---|
| **1. Foundation** | `MERGED_MAIN / EXIT_GATE_PASS` at `eeff49c` | target package boundaries and dependency tests; shared value types; sole `bootstrap.py` composition contract; schema epoch/catalog preflight; unreleased `001_baseline.sql` build contract; stable seeds; cross-cutting schema/migration, command receipt, audit and Artifact metadata foundations | empty PostgreSQL → foundational baseline → seed → verify; retry idempotent; wrong/legacy/unknown epoch fails before DDL; foundational PK/FK/unique/check/index obligations verified; no old migration import |
| **2. Market/PIT** | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` at `e7a276a` | Provider/Product, Capture, Instrument, Session, Classification, Market/Instrument/Corporate Action revisions, Source Gap; exact temporal and price-basis semantics; artifact binding | capture → normalize → exact/as-of query passes clean-database, revision, missing/placeholder/suspension, concurrency, artifact-integrity and PIT tests |
| **3. Selection Core: Universe/Eligibility** | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` at `44caf94` | permanent `market_regime_alpha.selection`; exactly seven Universe revision/member and typed Eligibility policy/rule/assessment/reason tables; independent narrow Selection UoW; behavior-preserving Market physical modularization; generic Market exact/as-of facts and Market-local 24-hour consumer policy | explicit immutable scope config; Market-only query dependency; every scoped instrument and every rule accounted; three-state/count reconciliation; Decision-time lineage, empty-scope, concurrent idempotency, stale-fence and representative-plan tests; no Market Target resolver or global Artifact cadence |
| **4. Research Definition Core for Candidate** | `IMPLEMENTED_DRAFT / EXIT_GATE_PASS / NOT_CUT_OVER` at `22a5ec6` | permanent `market_regime_alpha.research_qualification`; exactly `dataset`, `dataset_source`, and `feature_definition`; shared deterministic command-failure contract; strict label-free Decision-input Dataset whose rows exactly equal same-time `INCLUDED` + `ELIGIBLE` population | real immutable relational Authority, Artifact/lineage integrity, success/failure/fence atomicity, leakage rejection, concurrency/replay/recovery, and representative-plan tests pass; no Model/ModelVersion, placeholder, nullable future FK, Registry, compatibility adapter, Evidence/Qualification surrogate, or dependency cycle |
| **5. Candidate closure** | `READY_FOR_IMPLEMENTATION / NOT_STARTED` | Candidate policy/components/set/candidate/score components; consume only real Selection and Research Definition identities proven by the approved policy | Candidate Set exists independently of Decision Run and Qualification; deterministic ties and complete funnel; future Decision Run must reference an existing Candidate Set |
| **6. Research Evaluation/Evidence/Qualification** | `DEFERRED` | Target/Partition/Experiment/Evaluation/Evidence/Assessment/Qualification aggregates and Artifact lineage plus any remaining research owners | Evidence Class, Assessment Status and purpose-scoped proof floors stay independent; negative results immutable; qualification cannot exceed floors; replay/lineage tests pass |
| **7. Decision/Outcome** | `NOT_STARTED` | Decision Run, Context, Signal, Forecast, Opportunity, Thesis, Strategy, Portfolio, sole post-Portfolio Risk; Outcome/Metric/Attribution | required existing Candidate Set FK; Candidate → Context direction has no cycle; Opportunity has no Risk authorization; exact Target/Outcome/MFE/MAE availability semantics and post-Portfolio Risk constraints pass |
| **8. Execution/Account** | `NOT_STARTED` | Account epoch, Intent, observed Fill/corrections/allocations, broker observations, reconciliation, typed non-trade basis events, derived Position/sleeves | trade delta only from effective Fill; opening/corporate-action/reconciliation invariants; reservation, concurrency, correction, restart and reconciliation tests pass |
| **9. Runtime/CLI Cutover** | `NOT_STARTED` | complete and freeze the target baseline; one Run/Step/Attempt/Lease/Fence Runtime; one `mra` CLI tree; target repositories/adapters, inspection/read models, recovery and Artifact integrity operations | baseline checksum/seed/catalog verify all target tables; clean DB canonical capture → decision → mutation → query → outcome/evidence; restart/recovery/concurrency/idempotency/replay pass; old Runtime receives no canonical entry or write |
| **10. Legacy deletion/qualification** | `NOT_STARTED` | remove old packages, 001–106 migrations, repositories, CLIs, compatibility readers, parallel journals/compositions, legacy tests after invariant replacement; rewrite runbook/status generators | all 98 invariant IDs covered; zero old imports/writers/tables/entry points; full gate clean; destructive cutover rehearsed on an explicitly provisioned database; qualification remains at actual evidence floor |

The target `001_baseline.sql` is an unreleased, reviewable build artifact during
Stages 1–8. Foundation establishes its epoch/bootstrap and cross-cutting
relations; each context checkpoint adds only its own frozen semantics and DDL.
Stage 9 verifies the complete semantically required catalog and makes the
baseline checksum immutable when the new epoch is released. The design-time
91-table estimate is not a quota. Later changes use forward-only `002+`
migrations; no compatibility schema is introduced.

## Foundation checkpoint result

Foundation passed its exit gate and is merged to `main` without changing old
source, migrations, or business-test semantics. It provides 13 Foundation
relations, two read-only views, target-only package boundaries, explicit
bootstrap/verify/recreate operations, Runtime lease/fence/recovery and command
idempotency, application-owned unit-of-work scope, and verified local
content-addressed Artifacts with two-phase garbage collection. The detailed
exact-SHA ledger is
[WP-03 Foundation Verification](../references/WP-ARCHITECTURE-REFOUNDATION-03-Foundation-Verification.md).

## Market/PIT checkpoint result

Market/PIT passes its implementation exit gate on the test-only line. Twelve
owner relations, a narrow Market UoW, exact/as-of queries, unqualified Tencent
and BaoStock adapters, append-only revisions/gaps, DB-clock PIT knowledge,
Artifact reference protection, and a fenced `CAPTURE -> NORMALIZE_PIT` slice
are implemented. The mutable epoch remains `DRAFT / NOT_CUT_OVER`; no legacy
writer was adapted or dual-written. The exact ledger is
[WP-04 Market/PIT Verification](../references/WP-ARCHITECTURE-REFOUNDATION-04-Market-PIT-Verification.md).

## Selection Core checkpoint result

Selection Core passes its engineering exit gate on the test-only line. The
permanent `market_regime_alpha.selection` package owns exactly seven
Universe/Eligibility tables, consumes Market/PIT through a narrow query port,
and commits Selection writes, receipt, audit, live fence, and Step finalization
through an independent short Selection UoW. Explicit immutable scope Artifacts,
complete member and rule accounting, exact/as-of lineage, three-state
aggregation, concurrency/idempotency, stale-fence, empty-scope, Decision-time,
and representative-plan tests pass. Market was physically split without an
Authority or PIT redesign; the named Target resolver was removed and 24-hour
freshness is now a Market consumer policy over unchanged Foundation integrity.
The exact ledger is
[WP-05 Selection Core Verification](../references/WP-ARCHITECTURE-REFOUNDATION-05-Selection-Core-Verification.md).

Candidate is not part of this checkpoint. No Candidate table, future FK,
Registry, Research placeholder, compatibility adapter, or empty future owner
was added.

## Research Definition Core checkpoint result

Research Definition Core passes its engineering exit gate on the test-only
line. Permanent `market_regime_alpha.research_qualification` owns exactly
`feature_definition`, `dataset`, and `dataset_source` through an independent
narrow Research UoW. Dataset population exactly reconciles same-DecisionTime
`INCLUDED` plus `ELIGIBLE` rows, missing Features remain explicit typed cells,
and the closed Domain parser physically rejects posterior/label fields. Source
roles use concrete FKs and reconcile bidirectionally with the manifest.

Market, Selection, and Research share one narrow deterministic command-failure
contract without sharing business repositories or UoWs. All 3,245 collected
tests, clean PostgreSQL bootstrap/verify/recreate, constraints/plans, Ruff,
mypy, build, docs, and diff gates pass locally. The exact ledger is
[WP-06 Research Definition Core Verification](../references/WP-ARCHITECTURE-REFOUNDATION-06-Research-Definition-Core-Verification.md).

Candidate remains absent from this checkpoint. Its real V1 Selection and
Research Definition dependencies now exist in an acyclic physical Authority
order, so Candidate Closure is ready to begin only as the next separately
bounded work package. Model/ModelVersion and Qualification are not Candidate
existence prerequisites.

## Dependency-owned unresolved gaps

| Gap | Owning stage | Required resolution |
|---|---|---|
| Current live database business-row inventory was unavailable to the design audit role | Runtime/CLI Cutover | use a newly provisioned empty target database; before any canonical database destruction, inspect it and use the implemented exact-OID authorization |
| Formal Provider availability/finality evidence is absent | Research/Qualification | Market stores `UNKNOWN`/Exploratory and blocks historical visibility inflation; later qualification is purpose-scoped and cannot mutate old captures |
| Corporate-action and broker account semantics vary | Market/PIT / Execution | adapter-specific fixtures and qualification; no inference from adjusted prices or unexplained broker deltas |
| Later-context physical indexes are not plan-validated | each later persistence stage | repeat the Market representative-plan method before each stage exit; do not hard-code planner shapes |
| Artifact volume/retention is unmeasured | Runtime/CLI Cutover | no partitioning by aesthetics; measure write volume, vacuum/retention and dominant plans |
| Unknown external broker effects lack an operator workflow | Execution / Runtime | remain reconciliation-required; no broker adapter or blind retry before workflow proof |
| Formal PIT/OOS, sustained Prospective value, Production, and broker evidence are absent | Qualification | remain blocked/unsupported; engineering cutover cannot promote them |

## Entry decision for implementation

Foundation is merged; Market/PIT, Selection Core, and Research Definition Core
pass their test-only engineering exit gates. Candidate Closure is the next
dependency-ready stage, but no Candidate code or schema exists yet. Its V1
policy may bind only same-DecisionTime INCLUDED/ELIGIBLE Selection facts plus
the immutable Decision-input Dataset and FeatureDefinition identities it
actually consumes. Candidate Set must exist independently; a future Decision
Run must reference an already-existing Candidate Set. Model/ModelVersion and
full Evidence/Assessment/Qualification are not existence prerequisites unless
a later concrete policy proves otherwise. This is not a Runtime/CLI cutover or
target baseline release.

No Alpha hypothesis, model optimization, OOS outcome access, Provider
qualification, broker integration, or destructive database operation belongs to
Foundation, Market/PIT, or the next stage unless separately approved.
