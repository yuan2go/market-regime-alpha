# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative implementation status; exact-SHA qualification belongs to Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-07 research operations activation
> **Repository Implementation Checkpoint:** `26d4d98e045d323fd4947ed7df298e0b57867581`
> **Implementation Tree:** `a91d2228f7f3be8fa2e8c1de5c56f945ec5dac9f`
> **Execution-Time Main Baseline:** `2d6fbb2981a4e16fd7701884cc8d040c349bae1c`
> **Containing Documentation Commit:** reported by handoff; no self-referential SHA
> **Schema Epochs:** legacy business `LEGACY_MIGRATIONS_001_106`; target `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Code Evidence:** `src/market_regime_alpha/bootstrap.py`, target PostgreSQL schema/migrations, `tests/refoundation`, `tests/platform`, and immutable Verification records linked below

This replaces the WP-17P-only current read model. Historical checkpoint details
remain in their immutable Verifications; historical PASS is not inherited by
changed implementation.

```text
code exists ≠ canonical wired ≠ tests passed ≠ runtime proven ≠ research valid
WP18Q_EXIT_GATE = BLOCKED
BACKTEST_PLATFORM = ENGINEERING_QUALIFIED_IN_COMPLETED_RECOVERY_SCOPE
Runtime/CLI full cutover = NO-GO
Production = NO-GO
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
production_ready = false
```

## Research operations activation checkpoint

Current frozen implementation `26d4d98e` includes P1 atomic Runtime admission:
supervisor acquisition and all current target Runtime Attempt creation share a
short PostgreSQL admission boundary. Database-wide reservation, exact owned
Attempt identities and a post-claim/pre-Provider check exclude racing workers.
No Provider I/O holds that transaction. Old binaries/arbitrary SQL are not
claimed to participate; activation excludes unknown writers.

The explicitly authorized original OID 287543, cluster
`7681924516459622681`, now passes registered
`wp18q_prospective_revision_gap_v6` upgrade and Schema verification.
Receipt `d785e40c-5608-55e7-a935-285ecc06898b` is recorded at
2026-09-07 13:19:18.304411 UTC. Comparison of 192 ordered table projections
shows only the three Schema metadata tables changing; all 189 business tables
and 2,770 Artifact identities/bytes are unchanged by the upgrade. Original
large-campaign FAILED action `59f66bd4-0e2e-57e5-b9fd-384cb4827202` stays failed.
The operational database was not recreated, replaced or adopted from a copy.

Fresh v5 backup `1b2de45a…` and post-upgrade v6 backup `a528178a…`
have verified dump, inventory, exact Artifact roster and pg_restore readability.
The v6 bundle is mirrored onto a second local physical disk; this is not offsite
protection. Subsequent authorized collection/Artifact-verification appends have
their own time and receipt identities, separate from upgrade preservation.

Actual product access at 2026-09-07 12:47 UTC returns one daily and 48 five-minute
BaoStock rows for that trading day. This is post-close access, not an intraday
timeliness guarantee or a canonical Capture. The first installed service passes
preflight and records 128 MISSED windows, then fails on implicit Schedule
revision replacement. The next field startup exposes unattempted READY members
under an already deadline-failed capture Run. Both failures and their original
code/configuration/log identities are retained.

The fixes inherit the registered Schedule revision and reconcile only exact
missed-window failures without restarting the failed Run. Unknown effects and
other failures still stop work. Independent PostgreSQL counterexamples cover
both Schedule revisions, multiple members, immutable repeated facts and
unknown-effect refusal. The latest activation/runtime/backup observations are
recorded in the incremental addendum of the existing
[R2 Verification](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-R2-Verification.md);
the installed current-user supervisor and backup-refresh procedure are in the
[Runtime Runbook](../operations/Runtime-Runbook.md).

The final installed service records 22 ticks through 14:43:26 UTC, including
canonical generation 2 registration, an exact owned graceful stop and a restart
after a fresh backup/profile update. Current health retains 128 MISSED of 576
expected windows, 448 future and zero due/Capture observations; terminal coverage
is not collection success. Next window is 2026-09-08 00:55–01:05 UTC.
The service stays running under the current-user project supervisor. Backup
maintenance is loaded for 03:00/19:00 local time, but its timer has not fired in
this observation. The manually executed same procedure passes; neither this
bounded observation nor next-generation planning proves cross-day collection.

The P1 checkpoint passes 114 targeted cases. The Schedule/Runtime refinement
passes 45, the final multi-member/continuity refinement passes 30, and shared
Runtime/Backtest/report/architecture consumers pass 31, with
overlap stated in the evidence ledger. Changed-file lint/type checks, locked
wheel build and separate installed environments pass. These are scoped
risk-directed gates; `FULL_REGRESSION=NOT_RUN` for this activation, per the
current explicit request. The previous 4,163-case full result belongs to
`4c764b3d` and is not relabelled as a new full regression.

The completed recovery campaign and prior hard-cut/report/replay evidence are
reused within their recorded scope; no 936-action campaign is rerun. Frozen
V1 economics remains V1. The
[read-only research diagnosis](../operations/Research-Diagnostics.md) still
accounts for 9,472 declared cells: 9,436 eligible Candidates and 36 exclusions.
Its 97 non-estimable metrics retain their original causes and denominator.
Daily Shadow still needs prospective Feature/Target/Model cutoff/Decision
bindings and an explicitly new denominator protocol.

Historical original-database QueryCanceled root cause remains UNPROVEN.
Current raw SQL, plans, waits and backup I/O observations are retained. A new
whole-database Receipt/Audit count probe times out at 10 seconds, then passes
within the unchanged budget with observed data-file read waits. Its failure is
retained; this does not establish the historical timeout's cause. Repeated live
ticks preserve all 14 scoped table hashes, original failed action and both
Receipt/Audit counts (matched=true, mismatch_count=0);
no speculative timeout/index change occurred. A known missed-window terminal,
a real due Attempt, a successful Capture and continuous service duration remain
separate facts. WP18Q total exit is BLOCKED while actual due proof is absent;
Alpha, Model, formal Provider/PIT/OOS and Production are not promoted.

## Research economics correctness checkpoint

[WP-RESEARCH-ECONOMICS-CORRECTNESS-01](../references/WP-RESEARCH-ECONOMICS-CORRECTNESS-01-Verification.md)
passes its bounded local engineering gate at its own exact implementation
`a107d98ee1f4e47db1dca5512211a02ad23029c9`: **4,045 full-repository JUnit cases, zero failures/errors/skips**,
PostgreSQL, static, architecture/docs, build and installed-wheel smoke all pass.
The V2 model remains independent funded, fully liquidated hypothetical
checkpoint-mark episodes. It does not qualify continuous account NAV, A-share
executability, Alpha or the WP-18Q platform.

Result reconciliation checks all eleven explicitly written root fields and
parent bindings against the typed writer contract, even with an unchanged saved
hash. Source/cost/classification children bind the verified result identity.
Missing actual Decision roots and incomplete unselected episodes fail closed.
Four Validation episodes span two folds and January/February: independent hand
expectations, all six full-path projections, report bytes and repeat-operation
snapshots of all 192 schema tables pass. Concurrency, stale fence, rollback,
unknown commit and input-change tests preserve canonical atomicity.

That economics implementation executes a finite 32-instrument Generic control
in a separate restored database: 100,000 capital, 80,000 purchase notional,
80,915.55 sale proceeds and 88.74 assumed fees reconcile to 100,826.81 final cash.
Evaluation/report/replay match; historical WP17P/Generic/V2 identities and old
published report bytes remain preserved in the recorded exact scope. Measured
559 SQL calls, 0.581s completion and 0.208s final write UoW meet frozen budgets.
Outcome remains the exact price owner, Evaluation the economic result owner,
and Report a read-only projection. No actual Fill, Position or Account is written.

Legacy/V1 results keep their original meaning and hashes; affected proposal-based
economics is excluded from V2 correctness evidence. The [model contract](../references/WP-RESEARCH-ECONOMICS-CORRECTNESS-01-Design.md)
lists supported assumptions and explicit refusals. R2 recovery and its frozen
campaign remain separate; future windows and the large campaign were not
prerequisites for that completed package. The R2 continuation below preserves
its frozen V1 meaning and records each database scope independently. Remote Actions remains disabled and
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

## Current implementation truth

| Area | Executable fact and evidence boundary |
|---|---|
| Runtime | `CONTINUOUS_RESEARCH` remains the sole all-day Runtime. The target Schedule/Run/Step/Attempt/lease/fence model coordinates owner commands. No legacy business Runtime/CLI cutover has occurred. |
| Generic Backtest | `BacktestSpecification`, current relational reload, generic planner/executor, Runtime action binding, reconciliation and report wiring exist. The sole root is `exploratory_backtest_run`; `backtest_specification` is a companion, not a second root. |
| Canonical owner chain | Generic action handling delegates Dataset/Selection/Candidate/Decision/Context/Signal/Forecast/Opportunity/Portfolio/Risk/Outcome/Evaluation to existing owners. References and bindings do not replace owner reload/hash/time/lineage verification. |
| Model | Model, completed-FIT TrainingRun/sample roster, reproducibility/dependency/hyperparameter rosters, fitted Artifact, ModelVersion and later-validation binding exist. Deterministic ridge is exploratory and uncalibrated; Model qualification remains absent. |
| Evaluation / Report | Canonical Evaluation formulas, typed observations and metric states exist. JSON/Markdown report rendering consumes reconciled Authority/Evaluation, not raw bars or a second metric calculation. The three-session/two-arm report matches. The 44-session report, repeated publication and zero-write replay are proven in an isolated completed recovery scope; the original operational Run is terminally failed. |
| Prospective | Target-aligned continuation and ordinary Runtime composition are wired. Foreground `serve` serially wakes the same owner and drains shutdown; lifecycle proof and actual due capture remain separate. |
| Historical compatibility | Exact private WP-17P decoding supports completed, reconciliation-only frozen runs. WP-18 compatibility is definition/specification equivalence only. Unknown historical identities and missing/mismatching current specifications fail closed. |
| WP-specific surfaces | After the recorded pre-deletion gates, WP-specific execution and planning facades are removed. Generic composition and private exact historical decoding remain; post-retirement full regression, installed module absence and exact historical/real replay pass. |
| Execution / Account | Human-in-the-loop support only. Targets, recommendations and Portfolio proposals do not create actual Positions. No broker, Production admission or Risk bypass was added. |

## Target draft catalog

PostgreSQL 16 bootstrap and exact-OID guarded recreate independently reproduce
the following current draft catalog. Counts are observed facts, not quotas.
The legacy 001–106 / 283-table business schema remains distinct and uncut.

| Catalog property | Observed value |
|---|---|
| Tables / views | 192 / 4 |
| Indexes / constraints | 1,365 / 1,834 |
| Functions / non-internal triggers | 147 / 386 |
| Catalog objects | 3,929 |
| Baseline SHA256 | `f417b63cf3dc534b1a5d329c5a30462945bfeb6b8c4389bf8ab3a9e1f4efbd27` |
| Current v6 catalog SHA256 | `233c60c2b8b6efca4682f92fff8acbe85895a967cef0e11f7838f572e6ed69db` |
| Original operational v5 catalog SHA256 | `d14348490acefb1becea504ad4cf5bcb65bd482efa02e59343fd9408c851f1f1` |
| Seed SHA256 | `9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11` |
| Reference-vocabulary SHA256 | `d08800892f5e843a756f53e46205dfbb2787386ebf8281564c31049c45659a1b` |

The draft baseline and exact registered additive operational bundles serve
different operations. Operational evidence databases must not be recreated.
A new disposable test database does not attest to an operational upgrade.
The original operational scope now matches v6 after its explicitly authorized,
registered upgrade. Disposable bootstrap and independently restored upgrades
also match v6; the already released numbered migration is
`002_prospective_revision_gap.sql` (SHA256
`bd5978ae2ccfd56a9d117c41e13e0a8f7c76fbdd4d83d4aa1b32757dbe753063`).
Catalog counts are unchanged. All 189 business tables retain their complete
ordered hashes; only three schema metadata tables change during the upgrade.
Released baseline and all prior registered upgrade bytes are unchanged.

## WP-18Q qualification disposition

The [single R2 Verification](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-R2-Verification.md)
and [content index](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-R2-Evidence.json)
preserve the preceding continuation from main `6dc98933`, the `85d0080a`
activation, and the current authorized original activation from `2d6fbb29`.
Earlier R2 began at `780cd964`;
its frozen campaign writer remains `f247ca5d`. Its source, protocols, code bundle
and negative results are preserved independently of current implementation.

Pre-retirement `b69a1e28` passes 4,066 full-repository JUnit cases without
failures/errors/skips, 51 focused cases, static/type/architecture/docs/build,
wheel/sdist source/resource matching and independent installed canonical smoke.
Those are deletion prerequisites, not a substitute for the new post-retirement
implementation's full qualification. The exact 09561b25 retirement source/tests
remain in that Verification; the header above identifies current activation. The final 09561b25 full run passes 4,058 cases with zero failures/errors/skips, including 993 refoundation, 33 platform and 288 PostgreSQL-persistence cases; 78 focused and 41 architecture/docs cases, static/type/docs/build and independent installed-wheel smoke also pass.

The pre-R2 old operational Authority remains unavailable at inspected locations.
The distinct current R2 original database OID 287543 is accessible; its large Run
retains the failed terminal state described below.
Recovered immutable history and the newly captured retrospective archive belong
to an explicitly distinct operational scope. Neither reconstruction nor successful
restore establishes continuous old prospective history.

| Gate | Actual evidence / remaining boundary |
|---|---|
| Operational identity | New operational database OID `287543`; `OPERATIONAL_EVIDENCE_DISCONTINUITY` remains explicit. Upgrade of the unavailable original operational database is unproven. Original historical copy remains untouched. |
| Backup and independent restore | Seven prior backup bundles were physically reverified. New pre-resume backup SHA256 `2575fdb4…` restores all 192 ordered table hashes and 2,770 Artifacts before continuation. After isolated completion, backup `588f09b6…` (309,994,856 bytes) independently restores to OID `118013570`: 2,780 physical Artifacts, five Archives and 16 Backtests reconcile, including completed large-Run and WP-17P replay. A further original pre-service backup `013f366f…` preserves the failed resume and all 2,770 Artifact references; 176 whole-table hashes are unchanged, while 16 explicitly listed tables reflect authorized append/recovery facts. Original source and recovery-copy statuses are never conflated. Final original verification initially times out, then the unchanged canonical diagnostic rerun matches all 2,770 Artifacts, five Archives and 16 Backtests in 577.75 seconds; original failed completion replay remains false. |
| Artifact integrity maintenance | A prior faithful restore failed the Market owner's 24-hour Artifact-verification freshness gate. That negative result is preserved. Existing ArtifactApplication verification then checked 886 capture Artifacts at actual time before the new backup baseline; Artifact IDs/hashes/sizes/locators and complete Capture rows remained unchanged. No freshness policy or known-time was weakened. |
| Prior R2 controlled additive upgrade proof | Independent restored and new operational databases match the disposable v5 catalog. Full-column primary-key ordered hashes preserve all 189 business tables; only schema epoch, migration and upgrade receipt tables change. Physical Artifacts, five Archives, WP-17P/Generic completed replay and published report bytes match. Inventory remains a regenerable operator index. |
| Historical equivalence | Exact completed WP-17P Run `8f7b6def-9c63-533e-9777-a5a6c57866e0` and its 398 Artifacts reconcile through the private decoder and Generic path without business writes. WP-18 proves definition/specification equivalence only. Unknown historical identities and missing/mismatching current specifications fail closed. |
| Canonical qualification archive | New sealed Archive `fc699eea-1283-5192-b3ac-c9cbddc0da5e` reconciles 534 captures, 116 actual sessions and 32 frozen instruments. Daily, intraday, calendar and exact daily membership evidence are materialized. Legitimate missing observations remain typed; original IDs or historical known-times were not reconstructed. |
| Completed small campaign and report | Run `99227101-fabe-5244-a9ab-e2ebe492b22d` completes 25 Generic actions: six Datasets, six Decisions, 192 Outcomes, six Evaluations and one 64-sample TrainingRun. ModelVersion `23155d48-a3c7-5e97-b182-6af99fe1687d` precedes its 32 Validation Forecast bindings. Its report has 154 estimable and 24 typed NOT_ESTIMABLE metrics; published JSON/Markdown and full 192-table/Artifact inspect/resume/replay preserve identities and bytes, with zero mismatches. |
| Independent real comparison | Fresh Run `b8c2fadc-5ac1-5585-bc7c-e131eede53a3` independently completes the same frozen three-session/two-arm research with ModelVersion `7922653d-39eb-5d35-8731-3804c3286a5a`. Canonical comparison returns LIKE_FOR_LIKE: all 178 metrics align, estimable values match, and ModelVersion identities are disjoint. This closes the independent comparison check beyond self-comparison. |
| Large Generic campaign | Original OID `287543`, Run `6318cbb0-e1d5-54b4-96bf-a2f458d0ef71`, is `FAILED`: one Fold Evaluation `EVALUATE` step terminated after PostgreSQL QueryCanceled; five preceding steps remain committed. Its faithful pre-failure recovery copy OID `117559774` completes all 936 actions at unchanged frozen `f247ca5d`: 44 actual FIT/VALIDATION sessions, 32 instruments, four arms, two FIT→VALIDATION dependencies, 296 Datasets/Decisions, 9,436 Outcomes, four ModelVersions and 44 Evaluations. Copy completion does not repair the original terminal identity. |
| Proven repairs and performance boundary | Real failures led to exact Calendar horizon resolution, stable Runtime-derived Evaluation cutoff, completed-FIT Model cutoff, ordered Feature-parent reconciliation, report binding encoding, bounded owner reads and successful-receipt indexing. The real receipt lookup now uses an Index Only Scan, reads one row and returns its original receipt/result hash. Cold/warm timings are observations, not equal-cache speedup claims. Completed-copy EXPLAIN ANALYZE/BUFFERS plans cover all eight required surfaces. A 1,085-sample Model preparation loads each of 34 Dataset definitions once; registered reload loads none. Original cold reads/timeouts and fast later plans are separately retained; the physical slowdown cause is not determined. Frozen recovery completes in 398.70 seconds but one Evaluation write takes 13.68 seconds, exceeding the predeclared 10-second budget. The already implemented current Evaluation owner, under a new isolated component identity, reproduces all 15 reference metrics for 1,085 members with a 7.54-second write; this does not repair the original failed Run. |
| Preserved failures | Failed Runs, Runtime Attempts and original OPEN Evaluations remain immutable. In particular, `a4b98930` stopped after 8,168 Outcomes when its Archive-derived Evaluation cutoff preceded actual settlement; `e948d119` failed on the unindexed receipt lookup. Later executions use new identities and unchanged research parameters. Neither failed execution is relabeled as completed. |
| Prospective continuity | The old CONTINUOUS_RESEARCH CLI prospective switches now refuse before execution; the sole public prospective write entry is guarded `mra archive prospective serve`, which delegates to the same canonical continuation and existing Runtime. PostgreSQL clock, exact TradingSessions, overdue terminalization, planning gaps, due claim, lease/fence and unknown Provider effect recovery are wired and tested. The foreground `mra archive prospective serve` entry uses that same continuation, closes composition between wakeups and drains SIGINT/SIGTERM without signal-handler lock reentry. The explicitly authorized current-user project supervisor invokes this same foreground entry; a bounded lifecycle drill cannot prove sustained collection. |
| Real prospective result | Original scope has 128 honest MISSED terminals from activation after the September 7 windows. Exact current due/future roster, subsequent generation and service observations are in the latest R2 addendum. MISSED/deadline maintenance does not prove a real due capture Attempt. |
| Hard-cut and final qualification | Pre-deletion historical, real recovery campaign/report/replay, backup and b69 full-engineering gates pass. Ten WP-specific public modules are retired; exact historical catalog fixtures and canonical Generic/Economics tests remain. Implementation `09561b25` is frozen in a new clean worktree with fresh disposable DB OID 134217859. Post-retirement full 4,058-case regression, 78 focused cases, static/type/architecture/docs/build, 1,166 packaged source/resource matches, independent installed module-absence/report/replay/compare/schema smoke, and exact completed-backup restore-check all pass. Original terminal failure remains negative evidence; the frozen actual-due requirement still blocks total exit. |
| Remote Actions | Repository API returned disabled: `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`. |

The completed recovery report contains 511 estimable and 97 typed
NOT_ESTIMABLE metrics. Eighty-eight retain `EXPECTED_ROSTER_MISMATCH`
(for example, declared 320 versus canonical 319); nine Context slices retain
`INSUFFICIENT_OBSERVATIONS`. No member, denominator or result is rewritten.
The canonical Alpha funnel diagnosis remains `NOT_DETERMINED`. These are
frozen V1 results, excluded from V2 economic correctness evidence; Target
horizon is not an assumed trade holding period and no continuous-account
validity is inferred from the displayed historical metrics. Positive metrics alone cannot qualify Alpha,
Model, Provider, Formal PIT/OOS, prospective value or Production.

## Historical exact-SHA verification

- [WP-17P Verification](../references/WP-ARCHITECTURE-REFOUNDATION-17P-Prospective-Archive-Exploratory-Backtest-Verification.md) owns its bounded historical real campaign and on-time smoke observation.
- [WP-18 Design](../references/WP-ARCHITECTURE-REFOUNDATION-18-Prospective-Walk-Forward-Design.md) is not proof of historical multi-fold execution.
- [WP-18Q Design](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-Reusable-Backtest-Platform-Design.md) and [Implementation Plan](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-Reusable-Backtest-Platform-Implementation-Plan.md) define the frozen closure gate.
- [WP-15 Verification](../references/WP-ARCHITECTURE-REFOUNDATION-15-Formal-Research-Proof-Campaign-Verification.md) preserves the rejected Provider Decision.
- [WP-16 Verification](../references/WP-ARCHITECTURE-REFOUNDATION-16-Real-Provider-Evidence-Gate-A-Verification.md) preserves the external Provider evidence blocker.

## Research and production ceiling

```text
RETROSPECTIVE = EXPLORATORY_RETROSPECTIVE
FORMAL_PROVIDER = BLOCKED
FORMAL_PIT = BLOCKED
FORMAL_OOS = NOT_RUN
PROSPECTIVE_PROVEN = NO
ALPHA_PROVEN = NO
MODEL_QUALIFIED = NO
Runtime/CLI full cutover = NO-GO
Production = NO-GO
```

## Refresh contract

Regenerate this non-authoritative read model after source/schema/test/composition
changes, using exact-SHA command results. Never reinterpret immutable historical
Verification, negative/inconclusive research or historical identities. Roadmap
owns pending work; status prose cannot promote a capability.
