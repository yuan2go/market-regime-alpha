# Architecture Re-foundation Implementation Roadmap

> **Status:** ROADMAP
> **Authority:** Planning and dependency order only; never business, evidence, or qualification Authority
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-30
> **Code Evidence:** `docs/architecture/Canonical-Overall-Design.md`, `docs/status/Current-State.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-01-Domain-Invariant-Catalog.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-07-Candidate-Closure-Verification.md`

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
→ post-Candidate dependency review across Target/Research/Model/Decision/Outcome/Evaluation/Evidence/Qualification
```

WP-07 stops at Candidate Closure. With its local engineering exit gate passed,
the only next activity is the separate dependency review. Later Research/
Decision/Outcome, Execution/Account, Runtime/CLI Cutover, and Legacy deletion/
qualification work remains an unordered, unauthorized backlog until that review
publishes an approved dependency map.

No stage begins canonical writes until its predecessor exit gate passes. Before
Runtime/CLI Cutover, completed target modules are test-only and the old Runtime
remains the sole current implementation. There is no dual write or
availability-selected fallback.

## Checkpoints and exit gates

| Stage | State | Required scope | Exit gate before next stage |
|---|---|---|---|
| **1. Foundation** | `EXIT_GATE_PASS` | target package boundaries and dependency tests; shared value types; sole `bootstrap.py` composition contract; schema epoch/catalog preflight; unreleased baseline build contract; stable seeds; cross-cutting schema/migration, command receipt, audit and Artifact metadata foundations | empty PostgreSQL → foundational baseline → seed → verify; retry idempotent; wrong/legacy/unknown epoch fails before DDL; foundational PK/FK/unique/check/index obligations verified; no old migration import |
| **2. Market/PIT** | `EXIT_GATE_PASS / NOT_CUT_OVER` | Provider/Product, Capture, Instrument, Session, Classification, Market/Instrument/Corporate Action revisions, Source Gap; exact temporal and price-basis semantics; artifact binding | capture → normalize → exact/as-of query passes clean-database, revision, missing/placeholder/suspension, concurrency, artifact-integrity and PIT tests |
| **3. Selection Core: Universe/Eligibility** | `EXIT_GATE_PASS / NOT_CUT_OVER` | permanent `market_regime_alpha.selection`; Universe revision/member and typed Eligibility policy/rule/assessment/reason owners; independent narrow Selection UoW; behavior-preserving Market physical modularization; generic Market exact/as-of facts and Market-local consumer policy | explicit immutable scope config; Market-only query dependency; every scoped instrument and every rule accounted; three-state/count reconciliation; Decision-time lineage, empty-scope, concurrent idempotency, stale-fence and representative-plan tests; no Market Target resolver or global Artifact cadence |
| **4. Research Definition Core for Candidate** | `EXIT_GATE_PASS / NOT_CUT_OVER` | permanent `market_regime_alpha.research_qualification`; `dataset`, `dataset_source`, and `feature_definition`; shared deterministic command-failure contract; strict label-free Decision-input Dataset whose rows exactly equal same-time `INCLUDED` + `ELIGIBLE` population | real immutable relational Authority, Artifact/lineage integrity, success/failure/fence atomicity, leakage rejection, concurrency/replay/recovery, and representative-plan tests pass; no Model/ModelVersion, placeholder, nullable future FK, Registry, compatibility adapter, Evidence/Qualification surrogate, or dependency cycle |
| **5. Candidate closure** | `EXIT_GATE_PASS / NOT_CUT_OVER` | Selection-owned Candidate Policy, Policy Component, Candidate Set, Candidate, and Candidate Score Component; consume the immutable Decision-input Dataset and real Feature Definitions through a Selection-owned Research-input port and Infrastructure adapter | exact WP-07 proof that every Dataset row has one terminal disposition and a complete score-component matrix; STRICT complete case, exact-rational arithmetic-midrank/composite/competition rank, explicit constant/not-estimable diagnostics, include-all boundary ties, independent short Candidate UoW, fenced atomic success/failure/replay/concurrency, dossier/funnel and representative plans; no later-context Authority |
| **6. Post-Candidate dependency review** | `NEXT_DEPENDENCY_REVIEW / NOT_STARTED / IMPLEMENTATION_ORDER_NOT_AUTHORIZED` | after Stage 5 exit, audit the real code and Authority dependencies among Target Definition/Checkpoint, Research Partition, Experiment, Model, Decision Run, Outcome, Evaluation, Evidence, and Qualification | publish an approved acyclic implementation order; prove that Research does not construct realized labels independently of future Outcome Authority; the review itself implements and authorizes none of the listed contexts |
| **Unordered later target work** | `ORDER_NOT_AUTHORIZED` | Research/Decision/Outcome, Execution/Account, Runtime/CLI Cutover, and Legacy deletion/qualification retain their target invariants but have no WP-07 stage number or relative implementation order | replace this row with dependency-coherent checkpoints only after Stage 6 review is separately approved; this row grants no implementation authority |

The target `001_baseline.sql` remains an unreleased, reviewable build artifact
during pre-cutover checkpoints. Foundation establishes its epoch/bootstrap and
cross-cutting relations; each separately authorized context checkpoint adds
only its own frozen semantics and DDL. A later explicitly authorized Runtime/
CLI Cutover must verify the complete semantically required catalog and make the
baseline checksum immutable when the new epoch is released. The design-time
relation count is not a quota. Later changes use forward-only `002+`
migrations; no compatibility schema is introduced.

## Foundation checkpoint result

Foundation passed its exit gate. Its scope, exact source SHA, catalog, commands,
results, and proof ceiling are retained only in
[WP-03 Foundation Verification](../references/WP-ARCHITECTURE-REFOUNDATION-03-Foundation-Verification.md).

## Market/PIT checkpoint result

Market/PIT passed its implementation exit gate without cutover or dual write.
Its scope, exact source SHA, catalog, commands, results, and proof ceiling are
retained only in
[WP-04 Market/PIT Verification](../references/WP-ARCHITECTURE-REFOUNDATION-04-Market-PIT-Verification.md).

## Selection Core checkpoint result

Selection Core passed its engineering exit gate without cutover. Its scope,
exact source SHA, catalog, commands, results, and proof ceiling are retained only
in
[WP-05 Selection Core Verification](../references/WP-ARCHITECTURE-REFOUNDATION-05-Selection-Core-Verification.md).

## Research Definition Core checkpoint result

Research Definition Core passed its engineering exit gate without cutover. Its
scope, exact source SHA, catalog, commands, results, and proof ceiling are
retained only in
[WP-06 Research Definition Core Verification](../references/WP-ARCHITECTURE-REFOUNDATION-06-Research-Definition-Core-Verification.md).

## Candidate Closure engineering result

Candidate Closure passed its engineering exit gate without cutover. Its scope,
exact source SHA, catalog, commands, results, investigated failures, and proof
ceiling are retained only in
[WP-07 Candidate Closure Verification](../references/WP-ARCHITECTURE-REFOUNDATION-07-Candidate-Closure-Verification.md).

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

## Current handoff boundary

Foundation is merged; Market/PIT, Selection Core, and Research Definition Core
pass their historical test-only engineering exit gates. Candidate Closure passes
its local WP-07 engineering exit gate in the mutable target draft. Its V1 policy
binds only real Feature Definitions; Candidate Set binds the
immutable same-DecisionTime Decision-input Dataset whose population already
proves INCLUDED plus ELIGIBLE. It introduces no Model/ModelVersion, Target,
Outcome, Evidence, Assessment, Qualification, or future placeholder. This is not
a Runtime/CLI cutover or target baseline release.

Only the Stage 6 dependency review is now next. It does not freeze Research
Evaluation before Decision/Outcome, or the reverse. That review must inspect the
actual Target, partition, Experiment, Model, Decision Run, Outcome, Evaluation,
Evidence, and Qualification call chains and must prevent Research-created
realized labels from becoming a second Authority beside future Outcome facts.

No Target, Research Evaluation, Model, Decision/Outcome, Evidence,
Qualification, Alpha hypothesis, model optimization, OOS outcome access,
Provider qualification, broker integration, Runtime cutover, or destructive
database operation is authorized by Candidate implementation or the dependency
review.
