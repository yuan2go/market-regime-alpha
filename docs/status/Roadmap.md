# Architecture Re-foundation Implementation Roadmap

> **Status:** ROADMAP
> **Authority:** Planning and dependency order only; never business, evidence, or qualification Authority
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-09-03
> **Code Evidence:** `docs/architecture/Canonical-Overall-Design.md`, `docs/status/Current-State.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-01-Domain-Invariant-Catalog.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-08-Post-Candidate-Authority-Design.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-09-Target-Commitment-Decision-Run-Verification.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-10-Market-Target-Outcome-Verification.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-11-Research-Validity-Evaluation-Verification.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-12-Research-Evidence-Assessment-Qualification-Verification.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-13-Remaining-Decision-Support-Verification.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-14-Formal-Research-Engineering-Readiness-Verification.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-15-Formal-Research-Proof-Campaign-Verification.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-16-Real-Provider-Evidence-Gate-A-Verification.md`, `docs/references/WP-ARCHITECTURE-REFOUNDATION-17P-Prospective-Archive-Exploratory-Backtest-Verification.md`

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
→ integrated WP-11 Research Partition/Experiment/Evaluation closure
→ Evidence, Research Assessment and Research Qualification
→ remaining Decision Support with rule-based Forecast
→ WP-14 Formal Research/OOS/Prospective engineering readiness
→ WP-15 real Provider qualification and frozen research proof campaign
→ WP-16 external Provider evidence acquisition Gate A
→ WP-17P retrospective exploratory archive/model/backtest and prospective
  contemporaneous evidence accumulation
→ optional Calibration only when separately justified
→ Execution/Account, TradeOutcome and Attribution
→ Runtime/CLI Cutover → separately authorized Legacy deletion
```

WP-08 approved the dependency order. WP-09 and WP-10 now pass their isolated
engineering exit gates without Runtime/CLI cutover. The latest explicit
maintainer decision supersedes WP-08's package split: WP-11 is one integrated
Research Validity and Evaluation Closure work package covering Target/Outcome
parity, Partition, Experiment, Evaluation Protocol/Run, controlled Outcome
access, observations, and metrics. It is implemented and passes its exact-SHA
engineering exit gate at `07151542f12a66d6e7da3e228e2dbf1d7d7771bb`.
WP-11Q and WP-12 are merged in
`origin/main@6e0ad150057e43a89843eb4fb307e0373d5572ac`. WP-12 passes its
independent exact-SHA engineering exit gate at
`48949c87ad0241a8d60031137bc3aa8eb9887525`. WP-13 Remaining Decision
Support passes its independent exact-SHA engineering exit gate at
`fc5993e5d9e05dbe2845659140108e1051cf3704`, and that checkpoint is contained in
merged `origin/main@eb7970b4833228a2faba6715c65c26dae88f6ee5`. WP-14 is the
implemented and exact-SHA engineering-qualified readiness checkpoint at
`ca6f66b50ec2c55250cd82d2fa1ed6c5f35c29b8`, merged through PR #97 as
`origin/main@8067a4be74f697a01aaa996465c10ed5b45b5a7f`. WP-15 passed that
dependency preflight and executed one real BaoStock recorded-Provider gate at
the exact merged main. Its complete ten-floor Decision is `REJECTED`, so the
formal hypothesis/PIT/OOS/prospective branches did not start. WP-16 then found
no accessible inspected Product with
direct recorded evidence for both P0 historical availability and revision
finality. It stopped before adapter/schema/Protocol implementation. This is not
a finding that access-blocked Providers are incapable. WP-17P has now passed
its exact-SHA engineering gate, archived real bytes in separate retrospective
and prospective lanes, and completed one bounded exploratory Model/backtest
campaign. Model is therefore no longer a skipped branch; only Calibration
remains optional and unstarted. That result does not reopen WP-16 Gate A, admit any Provider, or
permit retrospective facts into Formal PIT/OOS/Prospective admission. Every later row retains
its own approval/exit gate;
ordering never grants Runtime cutover, empirical promotion, broker authority,
or Legacy deletion.

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
| **7. WP-09 Target commitment and Decision Run** | `EXIT_GATE_PASS / NOT_CUT_OVER` | provider-neutral TargetDefinition/Checkpoint/Metric plus normalized dependency; independent Target registration seam; `OpenDecisionRun`; exactly one canonical DecisionRun per Candidate Set, explicit requested Target/version/reference-source roster, full Candidate × Target commitment roster and independent Decision reference; mandatory `OPEN_DECISION_RUN` after Candidate and before Context | exact roster/reference/FK/hash reconciliation including empty Candidate Set, idempotency/concurrency/fence/failure/replay and architecture tests pass; no Outcome/Partition/Evaluation/Model/Evidence placeholder |
| **8. Market Target Outcome** | `EXIT_GATE_PASS / NOT_CUT_OVER` | one commitment-bound root, append-only full revisions, concrete source/observation/metric/reference-dependency/observation-dependency/reason children, correction/supersession, two cutoffs, exact replay and narrow read-only port | partial/complete/correction/finality/idempotency/replay/port isolation proven; every old label consumer disposition remains fail-closed until its own cut |
| **9. WP-11 Research Validity and Evaluation Closure** | `WP11_EXIT_GATE_PASS / NOT_CUT_OVER` | Target/Outcome contract parity; immutable single-exchange-calendar Partition/member roster; Decision/Outcome windows and purpose-specific purge/embargo/overlap policy; global ordinal first-access ledger; Experiment with a complete ordered non-empty Partition binding roster and partition-specific Run; predeclared Evaluation Protocol/metrics; Evaluation Run, exact Outcome access/observations and complete metric-member rosters; canonical composition and read-only reconciliation | exact-SHA clean PostgreSQL/recreate, real concurrency/failure/recovery, replay/reconciliation, representative plans, full regression, static/build/docs/architecture gates pass; remote CI is disabled and not claimed; no Runtime/CLI cutover or research promotion |
| **10. WP-12 Research Evidence, Assessment and Qualification Closure** | `WP12_EXIT_GATE_PASS / NOT_CUT_OVER` | Evaluation-bound EvidenceItem/Dependency, Experiment-bound ResearchAssessment with complete terminal Evaluation/Evidence rosters, ResearchQualification policy/floor/decision/result/evidence | exact-SHA concrete FK/DAG/roster closure, negative/inconclusive/not-estimable preservation, every floor and exact Evidence binding, generation safety, idempotency/concurrency/recovery/replay, clean PostgreSQL, plans, full regression, static/build/docs gates pass; remote CI disabled and not claimed |
| **11. WP-13 Remaining Decision Support Closure** | `WP13_EXIT_GATE_PASS / NOT_CUT_OVER` | concrete complete Decision Run Research Qualification roster/members; Context, Signal, rule-based Forecast, Opportunity, Thesis, Strategy, Portfolio and Risk | exact-SHA complete qualification/Context/Signal/Forecast/Opportunity/Portfolio/Risk rosters; one-way generation DAG; uncalibrated Forecast without Model; sole post-Portfolio Decision-Support Risk; composition, concurrency/failure/recovery/replay, clean PostgreSQL/plans/full regression/static/build/docs gates pass; no Runtime dispatch, Execution, broker, or empirical promotion |
| **12. WP-14 Formal Research/OOS/Prospective Engineering Readiness** | `WP14_EXIT_GATE_PASS / NOT_CUT_OVER / NO_EMPIRICAL_PROMOTION` | exact controlled Runtime profiles; immutable campaign predeclaration; protected zero-access opening; database-clock due mechanics; Market-owned Provider qualification and source-specific Formal PIT/Dataset visibility; inspection/reconciliation | exact-SHA PostgreSQL, concurrency/failure/recovery/replay, plans, full regression/static/build/docs gates pass; `FORMAL_RESEARCH_ENGINEERING_READY=true` while `FORMAL_PIT/OOS/PROSPECTIVE/PROVIDER/ALPHA=NOT_PROVEN`; fixtures cannot promote claims |
| **13. WP-15 Formal Research Proof and Provider Qualification Campaign** | `PROVIDER_GATE_REJECTED / FORMAL_CAMPAIGN_STOPPED` | real BaoStock Product gate completed with exact capture bytes and a complete ten-floor Decision; no hypothesis or downstream Authority was created | new adequate recorded Provider availability/finality/calendar/membership/Decision-reference/Outcome-path evidence plus a new immutable Protocol/revision is required before another gate; no synthetic replacement or weakening of the rejected scope |
| **14. WP-16 Real Provider Evidence Acquisition Gate A** | `WP16_GATE_A_BLOCKED / BLOCKED_BY_EXTERNAL_PROVIDER_EVIDENCE` | corrected `F/X/?/B` feasibility matrix across actually inspected Products, including iFinD; immutable preservation of the WP-15 rejection; explicit P0 stop and re-entry contract | at least one accessible exact Product must have direct recorded `HISTORICAL_AVAILABILITY=F` and `REVISION_FINALITY=F`; only a new credential/runtime/license, versioned vendor contract, new actual Product, or new direct evidence may reopen Gate A; no adapter/schema/Protocol work before re-entry |
| **15. WP-17P Prospective Archive Operations and Exploratory Model/Backtest Activation** | `WP17P_ENGINEERING_EXIT_GATE_PASS / EXPLORATORY_ONLY / PROSPECTIVE_ACCUMULATING / NOT_CUT_OVER` | permanently separate `RETROSPECTIVE_BACKFILL` and `PROSPECTIVE_CONTEMPORANEOUS` lanes; explicit dual-clock retrospective simulation; deterministic 32-symbol engineering pilot; minimal optional Model/ModelVersion from completed FIT samples; canonical Decision Support/Outcome/Evaluation backtests; isolated operational persistence | passed at exact implementation SHA `5cc3831e93fa30a58283471e2185bbad5c72cec3`; retrospective results remain `EXPLORATORY_RETROSPECTIVE`, only actual-time captures accumulate prospective evidence, and WP-16 Formal Provider/PIT/OOS blockers remain closed |
| **16. Optional Calibration** | `OPTIONAL / NOT_STARTED` | calibration Evaluation purpose and subject-specific Model qualification when separately approved; concrete calibrated claim only after real parents and empirical floors | calibrated claims require exact partition/metric/evidence floors; WP-17P does not create or imply calibration |
| **17. Execution, TradeOutcome and Attribution** | `NO_GO / SEPARATE_AUTHORIZATION_REQUIRED` | Account/Intent/observed Fill/allocation/reconciliation/Position projection; separate TradeOutcome; Market and Trade Attribution | Fill-only trade mutation, Market/Trade subject separation, reconciliation and human-approval gates pass |
| **18. Runtime/CLI Cutover and Legacy deletion** | `NO_GO / SEPARATE_AUTHORIZATION_REQUIRED` | complete target composition/CLI/epoch release followed by separately approved removal of old writers/readers/schema | complete catalog and consumer cuts proven; no dual write/fallback; clean bootstrap/replay/recovery; empirical/Provider/Production floors remain independent |

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

## WP-09 engineering result

The exact scope is TargetDefinition/TargetCheckpoint/TargetMetricDefinition/
TargetMetricDependency registration, DecisionRun/DecisionRunTarget/DecisionTargetCommitment/
DecisionReferenceObservation,
`OPEN_DECISION_RUN`, and one test-only Candidate-to-commitment vertical slice.
Outcome and every later owner remain non-scope.

| TDD seam | Exit evidence |
|---|---|
| Target/checkpoint/metric identity | Target-owned root-last closure, append-only supersession, immutable hash/order and normalized relational metric/dependency semantics; no receipt closure and no JSON |
| Requested Target and Candidate × Target rosters | one canonical Run per Candidate Set; non-empty Target/version/reference-source roster survives empty Candidate Set; every Candidate disposition exactly once per requested Target; count/hash reconciliation |
| Decision reference | exact Decision-visible Market revision or explicit Source Gap; no late substitution |
| Commitment time/mode | freeze Runtime clock mode and PostgreSQL recorded time; historical/replay opening cannot become Prospective |
| FK/transaction | composite-set/source mismatches rejected; one short fenced transaction with receipt/audit/finalization |
| Runtime DAG | `BUILD_CANDIDATE_SET → OPEN_DECISION_RUN → ASSESS_CONTEXT`; no bypass or Outcome placeholder |
| Idempotency/concurrency/recovery | exact retry reuses identities; changed request/stale fence fails; one writer; deterministic failure atomic |
| Replay/architecture | exact roster/hash with zero mismatches; no Model, Legacy, generic registry, nullable future FK, or reverse package edge |
| Repository gate | clean PostgreSQL full gate plus source/DDL scope proof at exact checkpoint SHA |

The complete WP-09 gate passes at implementation checkpoint
`9a21d5d5384ace9ace987055a131d010e54daf0f`. Exact commands, database identity,
catalog/checksums, concurrency/failure/replay evidence, non-final failures, and
proof ceiling are retained in
[WP-09 Target Commitment and Decision Run Verification](../references/WP-ARCHITECTURE-REFOUNDATION-09-Target-Commitment-Decision-Run-Verification.md).
This closes only stage 7 and identifies Market Target Outcome as the next
independent work package. It does not start stage 8 and never authorizes
Runtime/CLI cutover.

## WP-10 engineering result

The exact scope is one commitment-bound `MarketTargetOutcome` root,
append-only full `MarketTargetOutcomeRevision` snapshots, concrete exact
source/observation/metric/reference-dependency/observation-dependency/reason
children, dual cutoffs, one pure Decimal numerical kernel,
`SettleMarketTargetOutcome`, typed replay/reconciliation, and a permanent narrow
read-only Outcome port. Partition, Experiment, Evaluation, Evidence,
Qualification, Model, Context, execution, and all later owners remain
non-scope.

| TDD seam | Exit evidence |
|---|---|
| Commitment and Decision reference | one root per exact Commitment; direct concrete FK to the immutable WP-09 Decision reference; reference never recomputed or replaced |
| Revision chain | contiguous append-only ordinals, one direct successor/current leaf, exact supersession, root/head serialization and immutable historical revisions |
| Due and temporal semantics | `NOT_DUE` causes zero writes; separate observation/knowledge cutoffs enforce event and known-at bounds |
| Full factual snapshot | exact typed source, observation, metric, dependency and reason rosters plus independent value/completeness, availability and `UNKNOWN` finality |
| Numerical authority | one pure Decimal return/MFE/MAE/barrier/checkpoint/path kernel; Legacy only characterizes intentionally retained semantics |
| FK/transaction | same-revision dependency closure and concrete Market/Target/Decision/Runtime FKs; one short fence-first transaction closes revision, receipt, audit and Runtime finality |
| Idempotency/concurrency/recovery | exact retry, changed-request rejection, one writer, non-forking corrections, bounded whole-transaction retry, unknown-result replay and stale-fence zero-write |
| Replay/port/architecture | exact zero-mismatch replay without Provider/latest access; public package exposes only the typed read-only snapshot port; no later-context or Legacy dependency |
| Repository gate | clean disposable PostgreSQL full gate, representative plans, full regression and source/DDL scope proof at exact checkpoint SHA |

The complete WP-10 gate passes at implementation checkpoint
`56812c58ce7b6e601366ffd0a5cfb52fec573227`. Exact commands, database identity,
catalog/checksums, concurrency/failure/replay evidence, investigated non-final
failures, and proof ceiling are retained in
[WP-10 Market Target Outcome Verification](../references/WP-ARCHITECTURE-REFOUNDATION-10-Market-Target-Outcome-Verification.md).
This closes only stage 8. The later WP-11 ledger below now owns stage 9's
engineering result. Runtime/CLI cutover remains NO-GO.

## WP-11 engineering result

WP-11 closes Gate A Target/Outcome parity, PostgreSQL-derived immutable
single-exchange Partition rosters, trading-session purge/embargo and
purpose-specific overlap, complete ordered Experiment Partition rosters,
pre-access Experiment/Evaluation Protocol/Run, transactional exact-cutoff
Outcome acquisition with globally monotonic per-member access ordinals,
complete Evaluation observations/metric-input rosters, sole target composition,
and permanent read-only reconciliation. Ownership stays inside
`market_regime_alpha.research_qualification` with separate Partition,
Experiment, and Evaluation UoWs.

The exact qualified implementation checkpoint is
`07151542f12a66d6e7da3e228e2dbf1d7d7771bb`. Its status is:

```text
WP11Q = ENGINEERING_QUALIFIED
WP11_EXIT_GATE = PASS
Runtime/CLI Cutover = NO-GO
```

Qualification passes 163 focused, 492 refoundation, 33 platform, 286
PostgreSQL persistence, and all 3,532 repository tests, plus clean bootstrap,
guarded exact-OID recreate, real concurrency/failure/recovery/unknown-commit
replay, read-only reconciliation, representative plans, Ruff, mypy, build,
documentation, architecture/import, and diff gates. GitHub Actions is disabled,
so remote CI is `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, not PASS.
Exact commands, catalog/checksums, investigated failures, and proof ceiling are
retained in the immutable
[WP-11 Verification](../references/WP-ARCHITECTURE-REFOUNDATION-11-Research-Validity-Evaluation-Verification.md).
This result did not itself start stage 10. WP-11Q was subsequently merged at
`883f35835671ebbd7d977b35b36c59528d536990`; only that merged preflight and the
later explicit request authorized WP-12 as the separate checkpoint recorded
below.

## WP-12 engineering result

WP-12 closes immutable Evaluation-bound Evidence and its Evidence-only DAG,
complete Experiment-bound Assessment revisions, purpose-specific relational
Qualification Policies, one explicit result and exact Evidence set per floor,
append-only supersession, and a narrow exact-ID later-generation admission read
port. Evidence, Assessment, and Qualification retain three narrow UoWs inside
the existing Research & Qualification Authority; Model is not a prerequisite.

The exact qualified implementation checkpoint is
`48949c87ad0241a8d60031137bc3aa8eb9887525`. Its status is:

```text
WP12 = IMPLEMENTED_AND_QUALIFIED
WP12_EXIT_GATE = PASS
Runtime/CLI Cutover = NO-GO
Formal OOS/Prospective = NO-GO
Production = NO-GO
```

Qualification passes 216 focused, 545 refoundation, 33 platform, 286
PostgreSQL persistence, and all 3,585 repository tests, plus clean bootstrap,
guarded exact-OID recreate, concurrency/failure/recovery/unknown-commit replay,
read-only reconciliation, representative plans, Ruff, mypy, build,
documentation, architecture/import, and diff gates. GitHub Actions is disabled,
so remote CI is `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, not PASS.
Exact commands, catalog/checksums, investigated failures, and proof ceiling are
retained in the immutable
[WP-12 Verification](../references/WP-ARCHITECTURE-REFOUNDATION-12-Research-Evidence-Assessment-Qualification-Verification.md).
This result does not start Model, Decision Support, Runtime/CLI cutover, or a
formal research campaign.

## WP-13 engineering result

WP-13 closes the exact later-generation Research Qualification input to each
DecisionRun, PIT Context, immutable Strategy, complete Signal and uncalibrated
rule-based Forecast rosters, Opportunity and typed Thesis, complete Decimal
Portfolio proposals, and sole post-Portfolio Decision-Support Risk. All
ownership remains inside permanent `market_regime_alpha.decision_support` with
narrow UoWs and Infrastructure PostgreSQL adapters. Runtime dispatch, business
CLI cutover, Model/Calibration, Execution, broker, and empirical promotion are
not included.

The exact qualified implementation checkpoint is
`fc5993e5d9e05dbe2845659140108e1051cf3704`. Its status is:

```text
WP13 = IMPLEMENTED_AND_QUALIFIED
WP13_EXIT_GATE = PASS
Runtime dispatch / CLI Cutover = NO-GO
Formal PIT / Locked OOS / Prospective = NOT_PROVEN
Provider qualification / Alpha / Production = NOT_PROVEN
```

Qualification passes 51 focused, 585 refoundation, 33 platform, 286
PostgreSQL persistence, and all 3,625 repository tests, plus clean bootstrap,
guarded exact-OID recreate, real concurrency, failure/recovery,
unknown-commit exact probe/replay, read-only reconciliation, representative
plans, Ruff, mypy, build, documentation, architecture/import, and diff gates.
GitHub Actions is disabled, so remote CI is
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, not PASS. Exact commands,
catalog/checksums, investigated failures, and proof ceiling are retained in the
immutable
[WP-13 Verification](../references/WP-ARCHITECTURE-REFOUNDATION-13-Remaining-Decision-Support-Verification.md).
WP-13 was merged as `origin/main@eb7970b4833228a2faba6715c65c26dae88f6ee5`.
WP-14 began only after that latest-main dependency gate was fetched and
rechecked. WP-15 likewise began only after WP-14 passed, merged, and its exact
merged main was freshly fetched and rechecked.

## WP-14 engineering readiness result

WP-14 composes exact Decision Proof and Due Proof Runtime DAGs, immutable
Formal Campaign predeclaration, complete actual Partition/Experiment binding,
protected PostgreSQL-time zero-access opening, database-clock due inspection,
Market-owned purpose-specific Provider qualification, source-specific Formal
PIT/Dataset seams, inspection, and read-only reconciliation. It adds no second
Runtime, Runtime business dispatcher, CLI cutover, Model, Calibration,
Execution, or empirical promotion.

The exact qualified implementation checkpoint is
`ca6f66b50ec2c55250cd82d2fa1ed6c5f35c29b8`. Its status is:

```text
WP14 = IMPLEMENTED_AND_QUALIFIED
WP14_EXIT_GATE = PASS
FORMAL_RESEARCH_ENGINEERING_READY = true
FORMAL_PIT / FORMAL_OOS = NOT_PROVEN
PROSPECTIVE_PROVEN / PROVIDER_QUALIFIED / ALPHA_PROVEN = NO
Runtime dispatch / CLI Cutover = NO-GO
```

Qualification passes 19 focused, 604 refoundation, 33 platform, 286
PostgreSQL persistence, and all 3,644 repository tests, plus clean bootstrap,
guarded exact-OID recreate, concurrency/failure/recovery/replay, read-only
reconciliation, six representative plans, Ruff, mypy, build, documentation,
architecture/import, and diff gates. GitHub Actions is disabled, so remote CI
is `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, not PASS. Exact commands,
catalog/checksums, operator-command corrections, and proof ceiling are retained
in the immutable
[WP-14 Verification](../references/WP-ARCHITECTURE-REFOUNDATION-14-Formal-Research-Engineering-Readiness-Verification.md).
WP-14 was pushed, reviewed, merged through PR #97, fetched again, and proved to
be the exact WP-15 execution baseline.

## WP-15 real Provider gate result

WP-15 registered a `RECORDED_PROVIDER / HISTORICAL_PIT` protocol for BaoStock
`sh.600519` raw five-minute bars, then executed one real capture through the
sole composition root and a fenced `SHADOW` Runtime Run. The exact 17,894-byte
Artifact contains 144 Provider rows and reconciles to one complete ten-floor
Decision.

```text
WP15_CAMPAIGN_EXECUTION = STOPPED_AT_PROVIDER_GATE
PROVIDER_QUALIFICATION = REJECTED
FORMAL_PIT / LOCKED_OOS = BLOCKED_BY_PROVIDER_GATE / NOT_RUN
RESEARCH_QUALIFICATION = BLOCKED_BY_PROVIDER_GATE / NOT_RUN
PROSPECTIVE_CAMPAIGN = NOT_STARTED
PROSPECTIVE_PROVEN / ALPHA_PROVEN = NO
```

Coverage, Runtime/raw lineage, database acquisition known-time, and raw price
basis passed. Historical availability, revision finality, and the declared
five-session Outcome path failed; trading-calendar, membership, and
Decision-reference evidence were insufficient. Qualified visibility and all
Formal Campaign/Dataset/Partition/Experiment/Evaluation counts remain zero.
The exact identities, timestamps, complete floor roster, reconciliation, and
proof ceiling are retained in the immutable
[WP-15 campaign Verification](../references/WP-ARCHITECTURE-REFOUNDATION-15-Formal-Research-Proof-Campaign-Verification.md).

## WP-16 external Provider evidence Gate A result

WP-16 started from fetched merged
`origin/main@16a4ab1d0d42a4144ef1bd1dcd15ac4ba5ab1087` and corrected the
feasibility vocabulary so recorded evidence is `F`, an exact-Product contract
failure is `X`, unestablished capability is `?`, and access-blocked capability
is `B`. The matrix includes BaoStock, Tencent, Tushare, XtQuant, iFinD, Wind,
JQData, RQData, and AKShare/EastMoney without turning missing access into a
vendor incapability claim.

No actually accessible Product has direct recorded evidence for both P0
historical availability and revision finality. Gate A therefore stops before
adapter, schema, multi-Product Authority, Product, Protocol, Capture, Decision,
or Formal PIT implementation.

```text
WP16_GATE_A = BLOCKED
WP16 = BLOCKED_BY_EXTERNAL_PROVIDER_EVIDENCE
WP16_ENGINEERING_IMPLEMENTATION = NOT_STARTED_BY_GATE
NEW_PROVIDER_PROTOCOL = NOT_REGISTERED
NEW_PROVIDER_QUALIFICATION = NOT_RUN
FORMAL_PIT = BLOCKED
WP17 = NO-GO
```

Re-entry is allowed only after a new secure Provider credential/runtime/license,
a versioned vendor publication/revision/finality contract, a new actual Product,
or new direct evidence changes a `B/?` cell. The immutable
[WP-16 Gate A Verification](../references/WP-ARCHITECTURE-REFOUNDATION-16-Real-Provider-Evidence-Gate-A-Verification.md)
records the bounded proof and the
[external evidence checklist](../references/WP-ARCHITECTURE-REFOUNDATION-16-External-Provider-Evidence-Acquisition-Checklist.md)
defines the vendor evidence package required before adapter development.

## WP-17P archive and exploratory execution result

WP-17P passed its exact-SHA engineering gate at
`5cc3831e93fa30a58283471e2185bbad5c72cec3`. Market owns immutable
`RETROSPECTIVE_BACKFILL` and `PROSPECTIVE_CONTEMPORANEOUS` lanes. Research &
Qualification owns explicit dual-clock bindings, the exploratory run, and the
minimal Model family/training/version seam. Decision Support owns the concrete
later-fold Model binding; canonical Outcome and Evaluation owners remain the
only realized-label and metric truth.

```text
WP17P_ENGINEERING_EXIT_GATE = PASS
RETROSPECTIVE_2026_BACKFILL = PARTIAL_WITH_PENDING_NOT_DUE
RETROSPECTIVE_PILOT_CAMPAIGN = COMPLETED
RETROSPECTIVE_EVIDENCE_CEILING = EXPLORATORY_RETROSPECTIVE
PROSPECTIVE_ARCHIVE = STARTED
FIRST_PARTY_KNOWN_TIME = ACCUMULATING
MODEL_RUNTIME = OPERATIONAL
BASELINE_BACKTEST / MODEL_BACKTEST = COMPLETED / COMPLETED
MODEL_CHALLENGER = NOT_ESTIMABLE
FORMAL_PROVIDER_QUALIFICATION / FORMAL_PIT = BLOCKED / BLOCKED
FORMAL_OOS = NOT_RUN
PROSPECTIVE_PROVEN / ALPHA_PROVEN = NO
Runtime dispatch / CLI Cutover / Production = NO-GO
```

The real archive retains 843 captured primary backfill slices with 64 due-time
pending slices. A separate XSHG stable-hash-32 campaign completed 386 captures,
three Datasets, FIT-only deterministic ridge training, later-fold rule/Model
execution, and zero-mismatch replay/reconciliation. A separate prospective
archive rejected a pre-window request and recorded one on-time smoke capture;
192 frozen future windows remain pending. Exact identities, catalog checksums,
test receipts, metrics, retained failures, and the unchanged evidence ceiling
are recorded in the immutable
[WP-17P Verification](../references/WP-ARCHITECTURE-REFOUNDATION-17P-Prospective-Archive-Exploratory-Backtest-Verification.md).

## Dependency-owned unresolved gaps

| Gap | Owning stage | Required resolution |
|---|---|---|
| The live local database is heterogeneous: default-named Legacy schema is at migration 55, a historical proof schema is at 106, target `mra` is absent, and no configured/active Runtime proved current schema selection | Runtime/CLI Cutover | use a newly provisioned empty target database; bind the explicit database/schema, backup and inspect it, and require implemented exact-OID authorization before any canonical database destruction |
| Formal Provider availability/finality evidence is absent | purpose-specific Provider Qualification after Outcome engineering | Market/Outcome store `UNKNOWN`/`PROVISIONAL` honestly and block historical visibility inflation; later qualification cannot mutate old captures or Outcome revisions |
| Corporate-action and broker account semantics vary | Market/PIT / Execution | adapter-specific fixtures and qualification; no inference from adjusted prices or unexplained broker deltas |
| The first real recorded BaoStock scope is rejected: historical availability, finality and Outcome path fail, while calendar/membership/Decision-reference evidence is insufficient | WP-15 external evidence | obtain a Provider/Product with recorded purpose-specific evidence and register a new immutable Protocol/revision; preserve the rejected Decision and do not weaken or relabel it |
| No accessible Product in the WP-16 execution environment has direct recorded evidence for both historical availability and revision finality; Tushare, XtQuant, iFinD, Wind, JQData and RQData remain access-blocked/unverified rather than incapable | WP-16 external Provider evidence | obtain a secure credential/runtime/license, a versioned vendor publication/revision/finality contract, a new actual Product, or new direct evidence; rebuild the four-state matrix before any adapter/schema/Protocol work |
| WP-17P measured a bounded archive pilot, but sustained Artifact volume/retention and operational vacuum behavior remain unmeasured | Runtime/CLI Cutover | continue non-destructive daily measurements; define retention only from observed volume and integrity requirements, never delete immutable evidence to hide a capacity limit |
| The prospective archive has only one on-time smoke observation and 192 frozen future windows remain pending | WP-17P operations follow-through | execute the frozen Decision-near/post-close/next-session/later-verification windows as real time passes; preserve missed windows as explicit gaps and do not infer sustained value |
| Unknown external broker effects lack an operator workflow | Execution / Runtime | remain reconciliation-required; no broker adapter or blind retry before workflow proof |
| Formal PIT/OOS, sustained Prospective value, Production, and broker evidence are absent | Qualification | remain blocked/unsupported; engineering cutover cannot promote them |

## Current handoff boundary

Foundation is merged; Market/PIT, Selection Core, Research Definition Core,
Candidate Closure, WP-09, and WP-10 pass their local engineering exit gates.
The mutable target draft now contains permanent provider-neutral Target,
Decision Run/commitment/reference, and Market Target Outcome bounded-context
modules plus Research-owned Partition, Experiment, Evaluation Protocol/Run,
Outcome access/observations, Evaluation metrics, Evidence DAG, complete
Assessment revisions, purpose-specific Research Qualification, exact later-
generation Decision inputs, PIT Context, Strategy, Signal, uncalibrated rule
Forecast, Opportunity, Thesis, complete Portfolio, and Decision-Support-only
Risk. WP-14 Formal Research orchestration and Provider-qualification mechanics
are present. WP-15 used them for one real recorded BaoStock scope, whose
Provider Decision is `REJECTED`; no qualified visibility or downstream Formal
Campaign claim was admitted. WP-16 found no accessible P0 `F/F` replacement
evidence and stopped before implementation; blocked Products retain `B/?`, not
an incapability label. WP-17P adds engineering-qualified archive mechanics and
an exploratory-only Model owner, completes one bounded rule/Model backtest,
and starts prospective accumulation. Model Qualification, Calibration,
Execution, Account, and broker owners remain absent. This is not a Runtime/CLI
cutover or target baseline release.

WP-08 closes the design dependency review. `OPEN_DECISION_RUN` is mandatory
after Candidate and before Context; it commits the complete Candidate × Target
roster and Decision-visible references before any Outcome. Market Target Outcome
then owns one revisioned realized-market-fact truth. Partition/Evaluation
consumers use its narrow read-only port, and feedback crosses only from generation `n` to
Decision Run `n+1` through a concrete Research Qualification binding.

WP-17P is the latest passed engineering Exit Gate at
`5cc3831e93fa30a58283471e2185bbad5c72cec3`, based on fetched
`origin/main@f67a4f34761516dab65825c38c4e81019f8c2dd1`. WP-15 remains stopped at
its rejected Provider gate, and WP-16 remains blocked at external-evidence
Gate A. The Model seam is operational only inside the WP-17P exploratory
evidence ceiling; Model Qualification and Calibration remain unstarted. An admitted Provider scope and
Formal PIT/OOS/Prospective evidence,
Execution, TradeOutcome, Attribution, compatibility writes, dual writes, and
future placeholders remain absent.

No Alpha optimization, Formal OOS access, follow-on Provider reinterpretation,
Provider-qualification adapter/schema prebuild, broker integration, Runtime
cutover, Legacy deletion, evidence-ceiling increase, or destructive
business-database operation is authorized by the negative WP-15 result, the
WP-16 Gate A blocker, or WP-17P. WP-17P proves only its typed exploratory
simulation, archive operations, narrow Model/backtest execution, and the start
of future evidence accumulation.
