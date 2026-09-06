# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative implementation status; exact-SHA qualification belongs to Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-06 research economics correctness
> **Repository Implementation Checkpoint:** `a107d98ee1f4e47db1dca5512211a02ad23029c9`
> **Implementation Tree:** `fe5c2d80fcdfc2364df45cd822cc8a8e9cebbc60`
> **Execution-Time Main Baseline:** `58640732b1c51ccec004dc574d3df790ccc4994d`
> **Containing Documentation Commit:** reported by handoff; no self-referential SHA
> **Schema Epochs:** legacy business `LEGACY_MIGRATIONS_001_106`; target `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Code Evidence:** `src/market_regime_alpha/bootstrap.py`, target PostgreSQL schema/migrations, `tests/refoundation`, `tests/platform`, and immutable Verification records linked below

This replaces the WP-17P-only current read model. Historical checkpoint details
remain in their immutable Verifications; historical PASS is not inherited by
changed implementation.

```text
code exists ≠ canonical wired ≠ tests passed ≠ runtime proven ≠ research valid
WP18Q_EXIT_GATE = BLOCKED
BACKTEST_PLATFORM = NOT_ENGINEERING_QUALIFIED
Runtime/CLI full cutover = NO-GO
Production = NO-GO
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
production_ready = false
```

## Research economics correctness checkpoint

[WP-RESEARCH-ECONOMICS-CORRECTNESS-01](../references/WP-RESEARCH-ECONOMICS-CORRECTNESS-01-Verification.md)
passes its bounded local engineering gate at the exact source/test checkpoint
above: **4,045 full-repository JUnit cases, zero failures/errors/skips**,
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

The exact final implementation executes a finite 32-instrument Generic control
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
campaign remain separate and untouched; future windows and the large campaign
are not prerequisites for this package. Remote Actions remains disabled and
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

## Current implementation truth

| Area | Executable fact and evidence boundary |
|---|---|
| Runtime | `CONTINUOUS_RESEARCH` remains the sole all-day Runtime. The target Schedule/Run/Step/Attempt/lease/fence model coordinates owner commands. No legacy business Runtime/CLI cutover has occurred. |
| Generic Backtest | `BacktestSpecification`, current relational reload, generic planner/executor, Runtime action binding, reconciliation and report wiring exist. The sole root is `exploratory_backtest_run`; `backtest_specification` is a companion, not a second root. |
| Canonical owner chain | Generic action handling delegates Dataset/Selection/Candidate/Decision/Context/Signal/Forecast/Opportunity/Portfolio/Risk/Outcome/Evaluation to existing owners. References and bindings do not replace owner reload/hash/time/lineage verification. |
| Model | Model, completed-FIT TrainingRun/sample roster, reproducibility/dependency/hyperparameter rosters, fitted Artifact, ModelVersion and later-validation binding exist. Deterministic ridge is exploratory and uncalibrated; Model qualification remains absent. |
| Evaluation / Report | Canonical Evaluation formulas, typed observations and metric states exist. JSON/Markdown report rendering consumes reconciled Authority/Evaluation, not raw bars or a second metric calculation. The three-session/two-arm R2 report and full zero-write replay match; the 44-session report remains pending. |
| Prospective | Target-aligned generations, planning gaps, terminal/revision observations and ordinary Runtime composition exist. Fixture mechanics are not a real-time attempt or prospective value proof. |
| Historical compatibility | Exact private WP-17P decoding supports completed, reconciliation-only frozen runs. WP-18 compatibility is definition/specification equivalence only. Unknown historical identities and missing/mismatching current specifications fail closed. |
| WP-specific surfaces | Executable WP-17P/WP-18 orchestration and generation dispatch remain physically present. Hard-cut prerequisites are not complete; deletion is blocked, not silently waived. |
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
| Catalog SHA256 | `d14348490acefb1becea504ad4cf5bcb65bd482efa02e59343fd9408c851f1f1` |
| Seed SHA256 | `9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11` |
| Reference-vocabulary SHA256 | `d08800892f5e843a756f53e46205dfbb2787386ebf8281564c31049c45659a1b` |

The draft baseline and exact registered additive operational bundles serve
different operations. Operational evidence databases must not be recreated.
A new disposable test database does not attest to an operational upgrade.
The new operational scope and independently restored upgrade drill now match this
verified v5 catalog. All 189 business tables retain their complete ordered hashes;
only the three controlled schema metadata tables changed.

## WP-18Q qualification disposition

R2 began from fetched main `780cd964fd47fffac13edd0cf52547d12fff2bfc`, tree
`0663cf127357c2cd24c49a23bbe3484e2f72e234`. At clean implementation
`f247ca5d`, the locked full repository gate passes **3,997 tests and four
subtests**, without skips or xfails. Its 39 focused tests, Ruff, mypy, build,
documentation checks, built-wheel source/resource verification and disposable
PostgreSQL bootstrap/exact-OID recreate also pass. These results qualify that
implementation only; the final source after hard-cut still requires its own
complete qualification.

The retained R2 correction `f1c17ae5` closes an unfenced entry into
`MarketArchiveOperations.execute_slice`: due prospective effects require a
Runtime claim before capture, normalization or resource-stop commands. Terminal
and future NOT_DUE observations remain side-effect free. Its clean locked
worktree passes 25 focused unit/continuity/PostgreSQL tests, Ruff, mypy, build and
documentation checks. The current `a107d98e` implementation, which retains that
guard, now has the complete local regression recorded above. This does not
requalify the frozen large campaign or satisfy hard-cut: that campaign retains
its exact `f247ca5d` source and frozen bundle.

The original operational Authority remains unavailable at inspected locations.
Recovered immutable history and the newly captured retrospective archive belong
to an explicitly distinct operational scope. Neither reconstruction nor successful
restore establishes continuous old prospective history.

| Gate | Actual evidence / remaining boundary |
|---|---|
| Operational identity | New operational database OID `287543`; `OPERATIONAL_EVIDENCE_DISCONTINUITY` remains explicit. Upgrade of the unavailable original operational database is unproven. Original historical copy remains untouched. |
| Backup and independent restore | Verified exported-snapshot baseline: 115,800,171 bytes, SHA256 `685b52518b5587b8667b9334c4226f9e41cbca2066e255cd80b3135f0b031e29`, 2,463 Artifacts. Fresh restore OID `98243926` matches all 192 JSON-C ordered table hashes, physical bytes, five Archives and WP-17P/Generic completed replay. This baseline precedes the new comparison and large campaign; their final backup/restore is still required. |
| Artifact integrity maintenance | A prior faithful restore failed the Market owner's 24-hour Artifact-verification freshness gate. That negative result is preserved. Existing ArtifactApplication verification then checked 886 capture Artifacts at actual time before the new backup baseline; Artifact IDs/hashes/sizes/locators and complete Capture rows remained unchanged. No freshness policy or known-time was weakened. |
| Controlled additive upgrade | Independent restored and new operational databases match the disposable v5 catalog. Full-column primary-key ordered hashes preserve all 189 business tables; only schema epoch, migration and upgrade receipt tables change. Physical Artifacts, five Archives, WP-17P/Generic completed replay and published report bytes match. Inventory remains a regenerable operator index. |
| Historical equivalence | Exact completed WP-17P Run `8f7b6def-9c63-533e-9777-a5a6c57866e0` and its 398 Artifacts reconcile through the private decoder and Generic path without business writes. WP-18 proves definition/specification equivalence only. Unknown historical identities and missing/mismatching current specifications fail closed. |
| Canonical qualification archive | New sealed Archive `fc699eea-1283-5192-b3ac-c9cbddc0da5e` reconciles 534 captures, 116 actual sessions and 32 frozen instruments. Daily, intraday, calendar and exact daily membership evidence are materialized. Legitimate missing observations remain typed; original IDs or historical known-times were not reconstructed. |
| Completed small campaign and report | Run `99227101-fabe-5244-a9ab-e2ebe492b22d` completes 25 Generic actions: six Datasets, six Decisions, 192 Outcomes, six Evaluations and one 64-sample TrainingRun. ModelVersion `23155d48-a3c7-5e97-b182-6af99fe1687d` precedes its 32 Validation Forecast bindings. Its report has 154 estimable and 24 typed NOT_ESTIMABLE metrics; published JSON/Markdown and full 192-table/Artifact inspect/resume/replay preserve identities and bytes, with zero mismatches. |
| Independent real comparison | Fresh Run `b8c2fadc-5ac1-5585-bc7c-e131eede53a3` independently completes the same frozen three-session/two-arm research with ModelVersion `7922653d-39eb-5d35-8731-3804c3286a5a`. Canonical comparison returns LIKE_FOR_LIKE: all 178 metrics align, estimable values match, and ModelVersion identities are disjoint. This closes the independent comparison check beyond self-comparison. |
| Large Generic campaign | Run `6318cbb0-e1d5-54b4-96bf-a2f458d0ef71` is predeclared and executing through Generic CLI at clean `f247ca5d`: 44 distinct actual FIT/VALIDATION sessions, 32 instruments, four arms, two FIT→VALIDATION dependencies and four Model training requirements. Parameters preserve the original frozen research without tuning. Completion, full Model/Evaluation roster, standard report and exact replay remain unproven. |
| Proven repairs and performance boundary | Real failures led to exact Calendar horizon resolution, stable Runtime-derived Evaluation cutoff, completed-FIT Model cutoff, ordered Feature-parent reconciliation, report binding encoding, bounded owner reads and successful-receipt indexing. The real receipt lookup now uses an Index Only Scan, reads one row and returns its original receipt/result hash. Cold/warm timings are observations, not equal-cache speedup claims. Full plans on the completed large campaign remain required. |
| Preserved failures | Failed Runs, Runtime Attempts and original OPEN Evaluations remain immutable. In particular, `a4b98930` stopped after 8,168 Outcomes when its Archive-derived Evaluation cutoff preceded actual settlement; `e948d119` failed on the unindexed receipt lookup. Later executions use new identities and unchanged research parameters. Neither failed execution is relabeled as completed. |
| Prospective continuity | The sole CONTINUOUS_RESEARCH runner invokes canonical continuation before its trading-day early return. PostgreSQL clock, exact TradingSessions, overdue terminalization, planning gaps, due claim, lease/fence and unknown Provider effect recovery are wired and tested. This is not proof of an installed continuously running service. |
| Real prospective result | New series `r2_xshg32`, generation `1303080a-8a96-51dc-9021-31a9250c85d9`, begins at 2026-09-05 15:56:17.897411 UTC. Canonical continuation at 2026-09-06 08:42:56 UTC finds due=0, no new generation and no planning gap. Health shows 288 NOT_DUE slices, zero overdue/missed/captured. `REAL_DUE_ATTEMPT=BLOCKED_BY_TEMPORAL_WINDOW`; frozen WP-18Q total exit still requires actual due proof. |
| Hard-cut and final qualification | WP-specific executable surfaces remain until all historical, real campaign, report, replay, recovery and regression prerequisites pass. No deletion has started. Final implementation freeze, full requalification and immutable R2 Verification remain pending. |
| Remote Actions | Repository API returned disabled: `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`. |

Alpha funnel bottleneck remains `NOT_DETERMINED` pending the completed large
campaign's canonical Evaluation. Positive metrics alone cannot qualify Alpha,
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
