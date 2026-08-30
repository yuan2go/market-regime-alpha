# Architecture Re-foundation Implementation Roadmap

> **Status:** ROADMAP
> **Authority:** Planning and dependency order only; never business, evidence, or qualification Authority
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-30
> **Code Evidence:** `docs/architecture/Canonical-Overall-Design.md`, `docs/status/Current-State.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-01-Domain-Invariant-Catalog.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-07-Candidate-Closure-Verification.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-08-Post-Candidate-Authority-Design.md`

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
→ post-Candidate dependency and Outcome Authority design closure
→ Target commitment and Decision Run
→ Market Target Outcome revision/settlement and read-only port
→ Research Partition roster/access and Experiment
→ Evaluation protocol/run/observation/metric
→ Evidence, Research Assessment and Research Qualification
→ optional Model/ModelVersion and Calibration
→ remaining Decision Support, including optional model-backed Forecast binding
→ Execution/Account, TradeOutcome and Attribution
→ Runtime/CLI Cutover → separately authorized Legacy deletion
```

WP-08 approves this implementation order without implementing any listed
post-Candidate owner. WP-09 is the sole next coding work package. Every later
row remains blocked by its predecessor and retains its own approval/exit gate;
ordering never grants Runtime cutover, empirical promotion, broker authority, or
Legacy deletion.

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
| **6. WP-08 post-Candidate design closure** | `DESIGN_APPROVED / IMPLEMENTATION_ORDER_AUTHORIZED / NOT_IMPLEMENTED` | whole-repository writer/reader/FK/Artifact/Runtime/replay audit; freeze Target commitment, Market/Trade Outcome split, Partition access, Evaluation, concrete Evidence/Assessment/Research Qualification and cross-generation DAG | canonical documents and WP-08 record agree; no generic subject/JSON Authority, bars-to-label second truth, Model prerequisite, or same-generation cycle; current implementation/DDL unchanged |
| **7. WP-09 Target commitment and Decision Run** | `READY_FOR_IMPLEMENTATION / NEXT / NOT_CUT_OVER` | TargetDefinition/Checkpoint/Metric; `OpenDecisionRun`; DecisionRun, explicit requested Target roster, full Candidate × Target commitment roster and independent Decision reference; mandatory `OPEN_DECISION_RUN` after Candidate and before Context | exact roster/reference/FK/hash reconciliation including empty Candidate Set, idempotency/concurrency/fence/failure/replay and architecture tests pass; no Outcome/Partition/Evaluation/Model/Evidence placeholder |
| **8. Market Target Outcome** | `ORDER_AUTHORIZED / BLOCKED_BY_STAGE_7` | one commitment-bound root, append-only full revisions, observation/metric/reason children, correction/supersession, two cutoffs, exact replay and narrow read-only port | partial/complete/correction/finality/idempotency/replay/port isolation proven; every old label consumer disposition remains fail-closed until its own cut |
| **9. Research Partition and Experiment** | `ORDER_AUTHORIZED / BLOCKED_BY_STAGE_8` | immutable partition/member roster, Decision/Outcome windows, purge/embargo, ordinal first-Outcome-access ledger, Experiment/partition/run | Locked-OOS/Prospective roster and Experiment binding predate ordinal one; reused access is diagnostic only; range/composite-FK/leakage/concurrency/replay gates pass |
| **10. Evaluation** | `ORDER_AUTHORIZED / BLOCKED_BY_STAGE_9` | predeclared Evaluation Protocol/metrics; Experiment/Partition-bound Run; exact access/Outcome observations and metrics; no Forecast child table yet | no Model requirement, no bar/provider/repository import, no posterior Dataset write, complete input/metric reconciliation or nullable future Forecast FK |
| **11. Research Evidence and Qualification** | `ORDER_AUTHORIZED / BLOCKED_BY_STAGE_10` | Evaluation-bound EvidenceItem/Dependency, Experiment-bound ResearchAssessment with complete terminal Evaluation/Evidence rosters, ResearchQualification policy/floor/decision/result/evidence | concrete FK closure and Evidence DAG; negative/inconclusive preserved; no polymorphic subject, JSON owner, weak reference or nullable future branch |
| **12. Optional Model and Calibration** | `ORDER_AUTHORIZED / BLOCKED_BY_STAGE_11` | Model/ModelVersion from completed training Evaluation, calibration Evaluation purpose and subject-specific Model qualification where approved; no Forecast child table yet | Model remains optional; calibrated claims have exact partition/metric/evidence floors; no Candidate/Target/Outcome prerequisite or nullable future Forecast FK |
| **13. Remaining Decision Support** | `ORDER_AUTHORIZED / BLOCKED_BY_PREDECESSORS` | add concrete Decision Run Research Qualification roster/members only after their real parent; Context, Signal, Forecast, then optional concrete `forecast_model_binding` and `evaluation_forecast_binding`, Opportunity, Thesis, Strategy, Portfolio and Risk | qualification/Forecast binding children follow their real parents; same-generation DAG remains one-way; rule Forecast needs no Model; Risk is sole post-Portfolio authorization; no Outcome feedback into current generation |
| **14. Execution, TradeOutcome and Attribution** | `ORDER_AUTHORIZED / BLOCKED_BY_PREDECESSORS` | Account/Intent/observed Fill/allocation/reconciliation/Position projection; separate TradeOutcome; Market and Trade Attribution | Fill-only trade mutation, Market/Trade subject separation, reconciliation and human-approval gates pass |
| **15. Runtime/CLI Cutover and Legacy deletion** | `NO_GO / SEPARATE_AUTHORIZATION_REQUIRED` | complete target composition/CLI/epoch release followed by separately approved removal of old writers/readers/schema | complete catalog and consumer cuts proven; no dual write/fallback; clean bootstrap/replay/recovery; empirical/Provider/Production floors remain independent |

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

## Post-Candidate design result

WP-08 freezes the post-Candidate DAG, concrete FK/port/lock semantics, Legacy
writer/reader disposition, logical catalog change and small work-package order
without changing implementation. The authoritative detailed decision is the
[WP-08 Post-Candidate Authority Design](../references/WP-ARCHITECTURE-REFOUNDATION-08-Post-Candidate-Authority-Design.md).

## WP-09 coding contract

The minimum scope is TargetDefinition/TargetCheckpoint/TargetMetricDefinition
registration, DecisionRun/DecisionRunTarget/DecisionTargetCommitment/
DecisionReferenceObservation,
`OPEN_DECISION_RUN`, and one test-only Candidate-to-commitment vertical slice.
Outcome and every later owner remain non-scope.

| TDD seam | Exit evidence |
|---|---|
| Target/checkpoint/metric identity | immutable hash/order and relational metric/dependency semantics; no JSON |
| Requested Target and Candidate × Target rosters | non-empty Target roster survives empty Candidate Set; every Candidate disposition exactly once per requested Target; count/hash reconciliation |
| Decision reference | exact Decision-visible Market revision or explicit Source Gap; no late substitution |
| Commitment time/mode | freeze Runtime clock mode and PostgreSQL recorded time; historical/replay opening cannot become Prospective |
| FK/transaction | composite-set/source mismatches rejected; one short fenced transaction with receipt/audit/finalization |
| Runtime DAG | `BUILD_CANDIDATE_SET → OPEN_DECISION_RUN → ASSESS_CONTEXT`; no bypass or Outcome placeholder |
| Idempotency/concurrency/recovery | exact retry reuses identities; changed request/stale fence fails; one writer; deterministic failure atomic |
| Replay/architecture | exact roster/hash with zero mismatches; no Model, Legacy, generic registry, nullable future FK, or reverse package edge |
| Repository gate | clean PostgreSQL full gate plus source/DDL scope proof at exact checkpoint SHA |

Only that complete gate authorizes the separate Market Target Outcome coding
package. It never authorizes Runtime/CLI cutover.

## Dependency-owned unresolved gaps

| Gap | Owning stage | Required resolution |
|---|---|---|
| The live local database is heterogeneous: default-named Legacy schema is at migration 55, a historical proof schema is at 106, target `mra` is absent, and no configured/active Runtime proved current schema selection | Runtime/CLI Cutover | use a newly provisioned empty target database; bind the explicit database/schema, backup and inspect it, and require implemented exact-OID authorization before any canonical database destruction |
| Formal Provider availability/finality evidence is absent | purpose-specific Provider Qualification after Outcome engineering | Market/Outcome store `UNKNOWN`/`PROVISIONAL` honestly and block historical visibility inflation; later qualification cannot mutate old captures or Outcome revisions |
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

WP-08 closes the design dependency review. `OPEN_DECISION_RUN` is mandatory
after Candidate and before Context; it commits the complete Candidate × Target
roster and Decision-visible references before any Outcome. Market Target Outcome
then owns one revisioned label truth. Partition/Evaluation consumers use its
narrow read-only port, and feedback crosses only from generation `n` to
Decision Run `n+1` through a concrete Research Qualification binding.

WP-09 is ready for implementation with only Target Definition/Checkpoint/Metric,
Decision Run/requested Target/Target Commitment/Reference, and the test-only
Runtime Step seam.
It must not create Outcome, Partition, Experiment, Evaluation, Model, Evidence,
Assessment, Qualification, Context, Signal, Forecast, Portfolio, Risk,
Execution, Attribution, compatibility reads, dual writes, or placeholders.

No Alpha hypothesis/optimization, Formal OOS access, Provider campaign, broker
integration, Runtime cutover, Legacy deletion, evidence-ceiling increase, or
destructive database operation is authorized by WP-08.
