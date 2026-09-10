# Research Validity baseline — 2026-09-11

> **Status:** HISTORICAL
> **Authority:** Source-bound engineering and exploratory observation evidence
> **Work package:** WP-RESEARCH-VALIDITY-BASELINE-01
> **Evidence class:** DESCRIPTIVE / NOT_ALPHA_EVIDENCE

## Source and delivery identity

Baseline and rechecked remote main:
`c61a133995c015530a992a87421e750e64f4d5ef`.
Implementation: `072ff011f3b1d870c32e5228d29cb566d13a177d`.
The final delivery SHA is the commit containing this immutable record; the private
`final-delivery-attestation.json` records that exact commit and these tracked file
hashes after commit, avoiding a circular self-hash. Final delivery changes only
documentation/evidence after the implementation build.

The isolated analysis wheel SHA-256 is
`d311ed6410bb1bf8a67d518e1e616f4c96a840461a91a7fbb06652ebe4252fc6`.
It was installed outside the checkout against locked dependencies. The operational
wheel remains `b0a5eb49d58ed4e7e9c6022a968fd207103274ec6160e197bc5911b035310e7f`,
implementation `f30d45ab2680798c67ead58d5453e00ed2f2d74e`; no operational
package/profile/permission change or deployment occurred. The original workspace,
branch and pre-existing `.idea/modules.xml` modification were preserved.

The [source/observation index](Research-Validity-Baseline-2026-09-11.json)
binds protocol, raw observations, query plans, checks and failure/recovery records.
Raw private files are identified by logical filename, SHA-256 and size. They can
be located through the private deployment record; no credentials or personal
installation paths are published in this record.

## Current operational observation

At **2026-09-11T01:21:55.565532+08:00**, the original LaunchAgent is running (PID
43984) with 3 consecutive completed recovery ticks. Current
active/expired/unknown Attempts are all zero; durable Attempt totals are 27,508
SUCCEEDED, 43 FAILED_TERMINAL and four ABANDONED. The current service observation
is **RECOVERED_WITH_OPEN_PERFORMANCE_BLOCKER**, not sustained stability PASS.

The entry observation at 00:18 showed a running service. It subsequently stopped
at a 123.92-second tick, exceeding the unchanged 120-second budget. The first
recovery completed a 62.34-second tick, then failed at 01:09:01 with QueryCanceled.
PostgreSQL identified the human-research-disposition health query. All failures
and the recovery monitor's expired window are preserved. Fresh owner/preflight
reconciliation preceded the second recovery; its first two ticks took 67.11 and
61.01 seconds. No failed Run was reopened, and no unknown effect was retried.

Across the corrected deployment's observed logs: 52 emitted ticks,
51 within budget, one resource-budget failure, plus one QueryCanceled
failure before tick emission. Min/median/p95/max emitted tick latency:
13.27/61.97/94.69/123.92 seconds. Provider errors observed: zero.
The two in-package restart requests and downtime bounds remain separate from
routine backup drain/restart. Exact windows and per-process values are indexed.

Two guarded stage profiles took 26.02 and 26.61 seconds. In the first, continuation
used 23.95 seconds, daily work 1.49, prospective health 0.25 and daily health 0.32;
87 full installed-source hash checks consumed 17.53 seconds. The canceled query
scans 112,247 command receipts twice; three same-role read-only EXPLAIN ANALYZE
runs took 0.18–0.28 seconds. These locate actual cost and failure stages but do
not prove the full cause of the historical service timeout. The follow-up
performance boundary is long-lived service guard hashing and that health query
under actual LaunchAgent load. No Provider batching, guard bypass or timeout
increase was introduced.

Latest backup snapshot: Sep-10 23:34:28.815667+08:00; verification
23:38:08.820593+08:00, 3,017 Artifacts. At the last observed tick backup age was
6416.7 seconds, within 24 hours. The Sep-10 19:00 job fired
and **FAILED: SERVICE_NOT_RUNNING_MANUAL_RECOVERY_REQUIRED**; the separate 23:34
manual recovery completed at 23:42:50.618542. Sep-10 03:00 scheduled PASS remains
its own fact. No future scheduled fire is claimed. Same-host redundancy !=
offsite disaster recovery.

Original database `mra_wp18q_r2_operational_20260905`, OID 287543, cluster
`7681924516459622681`, epoch MRA_REFOUNDATION_1, schema v8 with 194 tables.
Artifact-root binding:
`a44c60d4bbf9045fd33a119de4da520d965364d37904a79275fdc2236a7678a0`.
Profile SHA-256:
`d4dfb191f5b681469b412a1f071de8b5f6c76bf2e0f5aa7e2bf469a8dcfcc088`;
receipt SHA-256:
`70c83a03a253cfb10d49e9171c20d4b1d859059f7e5dd76822be4cd41aaae159`.
The installed closed privilege-envelope check passes for runtime login
`mra_r2_runtime_20260909`, OID 6775405. No grant was broadened.

There is one completed real session. Sep-11 Prediction
`53e60935-9130-5898-8a3a-f53e71d0743b`, published Sep-10 23:33:34.510317+08:00,
remains PENDING_MATURITY. No substitute Prediction, terminal reopening or label
write was used. All 704 historical MISSED windows, including the original 544,
remain visible; the current prospective cutover has 160 historical MISSED windows
and one planning gap. Daily and prospective denominators retain their own scope.
The JSON index preserves ALL_HISTORY, POST_CURRENT_CUTOVER and last-five-session
rates with numerator, denominator, denominator_kind, state and reason_code.

## Frozen protocol and cohort

Protocol v1 was declared Sep-11 00:23:57.912926+08:00, hash
`1414d39ab1082fffb1e45499c1ba2d93b1e54a442f58fe7a3cc68509d69c6944`.
A pre-Outcome review found incomplete exact population semantics. Its bytes remain
immutable and it cannot establish a validity baseline.

The v2 successor was declared from the original database clock at
**Sep-11 00:37:36.769896+08:00**, hash
`efb4b9683ccf6201b9c1e3cbe0eb32338559fc430756155b06374794ffdb52de`.
First eligible future Target: **Sep-14**. Sep-10 is POST_HOC_DESCRIPTIVE for new
statistics; Sep-11 belongs to the descriptive predecessor. The revision changes
population binding completeness, not formulas, model, target or sample floors.
No known Outcome informed a model or parameter change.

Frozen policy: 20 estimable real sessions, 500 exact common observations,
20-session rolling window, top/bottom K=5, five-quantile tails, ALL_POPULATION only.
The protocol binds Model/use/Feature/Target hashes, baseline role, Candidate,
Eligibility, Context, classification, exploratory Provider and all 32 sampled
instrument identities. Missing/UNKNOWN/excluded members and failed sessions
remain in their declared denominators. Acceptance has no promotion authority.

The protocol is a hashed, packaged immutable source resource with declaration
observation evidence, not a falsely claimed registered database Artifact. No
second research truth table or migration was introduced. Arbitrary protocol files,
parameter overrides and modified same-version bytes fail closed. A revision needs
a predecessor hash, actual declaration time, reason and a later future cohort.

## Canonical observation and reconciliation

The read-only entry is `mra research validity daily`. The existing
`mra research daily observations` supports Target range, ModelVersion,
ExperimentalModelUse, TargetDefinition, Dataset/Decision IDs, completed-only and
include-unavailable reads. Date filters on validity select a descriptive view;
sample adequacy always uses the full bound cohort, including empty calendar days.

The original completed Prediction is `3c3e181e-692d-535b-aea0-f855c9e9e418`,
plan SHA `eae5144cbdca838cc32e2b673f0a620dcb89455a3b8760cbe9fb37410f3e0442`.
ModelVersion `fe47f296-17dc-5654-a9eb-cf149f5b01c9`, ExperimentalModelUse
`60902ae3-5776-5460-91b1-90ed3bc03525`, Feature
`68aab3d4-bffc-56b3-a5d1-bf5b4616ccfc`, Target
`8cdc2e02-bf29-5f96-995c-4b576b9ab130` and baseline strategy
`e40e1deb-dec2-5b08-bc93-06ca6a79ed31` retain their frozen hashes.

Dataset `351469dd-f65b-540f-845b-37bbfcceab1f` → Decision
`7ac791ea-498d-49f3-ad3d-c768b7a4d6f4` → 31 frozen commitments → 31 acquired
OutcomeRevision identities → Partition `06b3206c-e288-5051-a0f0-8f028b2e5a4f`
→ Evaluation `2849c414-da2a-5a8d-bb9f-483aed6df465` → original reports/replay.
Published commitments = Partition roster = Evaluation acquisition roster =
Commitment-owner roster. Exact source Capture, normalization, known-time,
BarRevision/SourceGap, labels and Model/Target hashes are included in raw output.
No latest-price acquisition or report-level label calculation occurs.

Repeated independent installed processes reconcile `matched=true`,
`mismatch_count=0`, `business_writes=0`. Original publication, acquired observations,
labels, sources, Evaluation metrics and report bytes match the entry observation.
The new statistics are Evaluation-owned interpretations and are separately named;
they do not overwrite the original ten Evaluation metrics. Decimal operation
ordering can differ in the last precision digit from an old stored metric; the
stored original metric remains the authority for that historical Evaluation.

## First session: preserved descriptive results

All sampled 32; eligible/feature-ready/model/baseline/common estimable 31 each.
One sampled member is membership UNKNOWN/excluded. Labels: 31 complete/available,
0 missing or availability UNKNOWN, 0 SourceGap, **31 finality UNKNOWN**. Finality
is not silently promoted. Prediction coverage is 31/32; pair coverage is 31/31.
Both roles use exactly the same 31 commitments and one session.

| Frozen canonical metric | Model | Baseline | Model minus baseline, rounded |
|---|---:|---:|---:|
| Bias | 0.00466075 | 0.00377164 | +0.00088910 |
| MAE | 0.00975429 | 0.01064810 | -0.00089380 |
| RMSE | 0.01108898 | 0.01319516 | -0.00210618 |
| Rank IC | 0.19274194 | -0.19274194 | +0.38548387 |

Actual Target distribution: 10 positive, 20 negative, one flat; range
[-0.028871391076115486, 0.018730489073881374]. Model forecasts: 31 positive,
range [0.000231417736, 0.001220025463]. Baseline: 15 positive, 15 negative, one
flat; range [-0.01, 0.01]. Exact unrounded values and distributions remain in
canonical/report evidence. This is SESSION_1_BASELINE_OBSERVATION only.

New direction diagnostics are **POST_HOC_DESCRIPTIVE**: Model 10/31,
baseline 13/31, delta -3/31. They were not added to Sep-10's Evaluation. No score
is treated as a probability. Better single-day error or IC does not establish
information gain, robustness or Alpha; the negative direction comparison is kept.

## Temporal integrity and multi-session statistics

Sep-10's 31 commitments pass local temporal integrity: actual feature known time
precedes input cutoff/Decision, which precede publication at 02:17:35.943618+08:00,
before Target 09:30–15:00. Dataset registration is a freeze event before
publication, not a substituted feature known time. Model registration/training
cutoff precede Decision. Actual Outcome requests at approximately 22:46–22:49
occurred after Target maturity and remain late observations. The read surface
uses Evaluation-acquired revisions, never mutable latest bars. Temporal violations
are excluded with reasons and cannot enter formal validity statistics.

Versioned Decimal formulas support bias/MAE/RMSE, rank IC, direction, OLS
slope/intercept, dispersion, top/bottom and quantile diagnostics. Cross-session
aggregation reports N, mean, median, sample standard deviation, positive/negative
counts, unannualized ICIR, min/max and descriptive standard error. There is no
complex inference framework, independence assumption or confidence-interval claim.
Rolling windows preserve actual calendar gaps. Rank stability cannot bridge an
empty session. Ranking is deterministic, uses frozen forecasts and exact common
population, and has no tradable-return authority.

Current v2 formal cohort: **0 sessions / 0 observations**. Historical cohort:
**1 session / 31 observations**. Session-level dispersion, ICIR and uncertainty
remain INSUFFICIENT_SESSIONS. Thirty-one stocks do not replace independent days.
`RESEARCH_VALIDITY_STATUS=INSUFFICIENT_OBSERVATIONS`.

## Walk-forward, slice, economic and Formal PIT readiness

Walk-forward protocol/data-boundary validator passes dry-run contracts: rolling
252 training + 63 validation + 1 embargo + 21 OOS, step 21, minimum 337 captured
sessions, immutable Model binding before OOS and exact Dataset/PIT cutoffs. Actual
readiness is **WALK_FORWARD_READY=NO**: 168 completed captured calendar sessions,
one usable canonical session; no training or new ModelVersion. Existing daily
DISCOVERY Partitions do not become formal LOCKED_OOS evidence.

Only ALL_POPULATION is frozen. Extra broad-market, volatility, liquidity,
breadth and regime slices are **REGIME_SLICE_NOT_READY** without exact PIT-bound
facts. No temporary Regime Model or outcome-selected slice was created.

The economic matrix records implemented turnover/cost formulas, independent episode
slippage, suspension/liquidity input wiring, limit-up/down vocabulary, Risk capacity
and separate Account T+1 ownership. None is observed as a complete daily trading
path. **ECONOMIC_VALIDITY_READINESS=NOT_READY**. Fully funded independent hypothetical
episodes are not continuous account NAV or actual P&L. No default cost, turnover,
position size or tradability assumption is injected.

**PROVIDER_EVIDENCE_CLASS=EXPLORATORY; FORMAL_PIT_READINESS=NOT_READY.** The report
lists Xuntou/ThinkTrader/XtQuant blockers for historical coverage, realtime
availability, known-time, revision/finality, suspension/adjustment, calendar,
classification, corporate actions, rate limits and recovery. No Provider promotion.

ExperimentalModelUse expires Oct-08 05:51:44.824938+08:00. Captured calendar extends
only through Sep-17, currently four known v2 future sessions before expiry. The
report does not assume extension, calendar coverage or enough future capacity to
meet 20 sessions. A new authorized identity cannot silently join the old cohort.

## Validation and exit decisions

118 affected tests are covered by passing executions after corrections. The first
117-test batch had two test-assertion failures (TradingSessionId wrapper versus
UUID); both PostgreSQL parameters passed on rerun. Final 70 unit tests include the
additional walk-forward guard. An earlier missing-test-DSN setup error was rerun
against the dedicated disposable database. Raw failures are retained.
An unsupported inventory `--check` invocation also failed; the supported
`--write` invocation and repository hygiene validation passed.

Ruff, mypy (639 files), build, inventory, hygiene, documentation links/tests and
`git diff --check` pass. Seven isolated installed CLI checks pass, with database
read-only credentials and unchanged business counts. No full 4k regression was
run: no Pool/UoW/schema/migration/common Evaluation-engine change. Production was
never a destructive fixture. Live deployment is NOT_RUN; only the separate
analysis wheel was installed. Final documentation checks are in the index.

| Gate | Result and scope |
|---|---|
| CANONICAL_RESEARCH_OBSERVATION_PASS | YES; original one-session chain, exact rosters, replay and read-only projection |
| VALIDITY_PROTOCOL_PREDECLARED_PASS | YES for immutable v2 future cohort; v1 explicitly incomplete |
| TEMPORAL_INTEGRITY_PASS | YES for 31 observed exploratory commitments and refusal contracts; future formal N=0, no Formal PIT qualification |
| MODEL_BASELINE_COMPARABILITY_PASS | YES; exact common population and explicit denominators |
| WALK_FORWARD_READINESS_PASS | YES for protocol/data-boundary validator; actual WALK_FORWARD_READY=NO until history exists |
| ECONOMIC_VALIDITY_READINESS | NOT_READY |
| SUSTAINED_MULTI_DAY_PROOF | BLOCKED_BY_ELAPSED_REAL_TIME; 1/3 consecutive real sessions, 5 preferred |
| RESEARCH_VALIDITY_BASELINE_EXIT_GATE_PASS | YES, infrastructure scope only |
| MODEL_VALUE / ALPHA_PROVEN | NOT_ESTIMABLE / NO |
| WP-ALPHA-ITERATION-01 | NOT_ALLOWED; real predeclared sample floor and repeatable information gain absent |

Remaining blockers are actual multi-day data/history, Model-use/calendar capacity,
Formal PIT, economic/tradability and extra slice evidence, plus the separately
recorded operational performance incident. Research infrastructure completion does
not assert a healthy service, effective model, Alpha, Production admission or
permission to optimize parameters.
