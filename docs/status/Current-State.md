# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative implementation status; exact-SHA qualification belongs to Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-06 WP-18Q-R2 operational recovery
> **Repository Implementation Checkpoint:** `02751b199788f44cab89c5ecbccec6b3afcc6fab`
> **Implementation Tree:** `9f3167c567815ea7780b2fe6d7d048b89ed44682`
> **Execution-Time Main Baseline:** `780cd964fd47fffac13edd0cf52547d12fff2bfc`
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

## Current implementation truth

| Area | Executable fact and evidence boundary |
|---|---|
| Runtime | `CONTINUOUS_RESEARCH` remains the sole all-day Runtime. The target Schedule/Run/Step/Attempt/lease/fence model coordinates owner commands. No legacy business Runtime/CLI cutover has occurred. |
| Generic Backtest | `BacktestSpecification`, current relational reload, generic planner/executor, Runtime action binding, reconciliation and report wiring exist. The sole root is `exploratory_backtest_run`; `backtest_specification` is a companion, not a second root. |
| Canonical owner chain | Generic action handling delegates Dataset/Selection/Candidate/Decision/Context/Signal/Forecast/Opportunity/Portfolio/Risk/Outcome/Evaluation to existing owners. References and bindings do not replace owner reload/hash/time/lineage verification. |
| Model | Model, completed-FIT TrainingRun/sample roster, reproducibility/dependency/hyperparameter rosters, fitted Artifact, ModelVersion and later-validation binding exist. Deterministic ridge is exploratory and uncalibrated; Model qualification remains absent. |
| Evaluation / Report | Canonical Evaluation formulas, typed observations and metric states exist. JSON/Markdown report rendering consumes reconciled Authority/Evaluation, not raw bars or a second metric calculation. A real WP-18Q report has not been proven. |
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
| Indexes / constraints | 1,364 / 1,834 |
| Functions / non-internal triggers | 146 / 386 |
| Catalog objects | 3,927 |
| Baseline SHA256 | `fa322ee492e40b44a740e8c48d055aa0d56e857dd89a5e13792f55777628cea8` |
| Catalog SHA256 | `0a4caa3dd51462f80a6b1cd94dde606d1e4336d8df9a1d02478a0f6687efbe6c` |
| Seed SHA256 | `9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11` |
| Reference-vocabulary SHA256 | `d08800892f5e843a756f53e46205dfbb2787386ebf8281564c31049c45659a1b` |

The draft baseline and exact registered additive operational bundles serve
different operations. Operational evidence databases must not be recreated.
A new disposable test database does not attest to an operational upgrade.

## WP-18Q qualification disposition

R2 fetched exact main `780cd964fd47fffac13edd0cf52547d12fff2bfc`, tree
`0663cf127357c2cd24c49a23bbe3484e2f72e234`. Historical verification is not
inherited. The clean `f4296252bfa174c36c77d1db70e9526ec6e0c46c` worktree passed
3,967 repository tests and 4 subtests without skips/xfails. The current
`02751b19` checkpoint passed 191 affected Backtest/Outcome/pool tests;
a final exact-SHA full qualification remains required.

| Gate | Proven / remaining boundary |
|---|---|
| PostgreSQL mechanics | Durable disposable PostgreSQL 16 bootstrap/recreate and catalog verification have been exercised. The current v3 catalog includes the exact Context TRUE_RATE precision repair; final qualification is still pending. |
| Historical compatibility | Exact completed WP-17P run `8f7b6def-9c63-533e-9777-a5a6c57866e0` and its 398 Artifacts were recovered and replayed without business writes. WP-18 remains definition equivalence only. |
| Operational recovery | Original operational DB Authority was not found at inspected locations. `OPERATIONAL_EVIDENCE_DISCONTINUITY` separates recovered old evidence from the new operational scope, database OID `287543`. Original operational upgrade remains unproven. |
| Backup / restore / inventory | Exported snapshot backups, physical Artifact roster verification and independent fresh-DB/root restore drills were executed. Non-authoritative inventory includes backup, integrity and restore receipts. Incomplete/failed execution remains incomplete/failed after restoration. |
| Additive upgrade | Exact v3 upgrade was exercised on an independently restored database and the new operational scope after identity/disk/backup/idle checks. All 192 tables were compared: 189 unchanged; only schema epoch, migration and upgrade receipt tables changed. Original historical copy remains untouched. |
| Canonical archive | New sealed archive `fc699eea-1283-5192-b3ac-c9cbddc0da5e` reconciles 534 canonical captures, 116 actual sessions and the frozen 32-instrument roster. Daily/intraday/calendar and exact daily membership evidence exist. Legitimate missing observations remain typed; reconstructed old identities or known-times were not used. |
| Real generic campaign | Run `a4b98930-a609-57c4-9e9a-4072d52397d8` freezes 44 executed sessions, four arms and two FIT→VALIDATION dependencies on the new archive. Explicit observational arms bind OBSERVE_ONLY Strategies; Forecast binds the Decision reference checkpoint. It is in progress, not completed evidence. Earlier failed/interrupted declarations are preserved. |
| Observed performance | On the same stopped campaign with 296 Datasets, 256 Decisions and 4,116 Outcomes, full inspect took 306.27 seconds before Outcome batching and 117.93 seconds afterward; complete plan hashes and all existing scoped rows matched. The fixed 64-Outcome sample now uses two bounded owner SELECTs and one connection lease instead of 448 SELECTs and 64 leases. A 64-row cold query previously timed out; the final per-query limit is 32 and the 30-second timeout is unchanged. Every owner is reloaded; no verification result is cached. Cache/IO conditions affect timings, and completed-campaign plans remain required. |
| Fresh two-arm engineering gate | The first small Run failed on a Calendar horizon limited to the Decision roster; canonical Calendar resolution is repaired and all 44 real horizons were verified. A subsequent concurrent Run exhausted the three SERIALIZABLE transaction attempts and retained its terminal failure/receipt. A fresh sequential two-arm execution remains required; parallel campaign success is not claimed. |
| Standard report / exact replay | A completed R2 campaign, trained ModelVersions, canonical standard metrics, report Artifacts and byte-stable inspect/resume/replay remain unproven. Alpha bottleneck is `NOT_DETERMINED`. |
| Prospective continuity | The sole CONTINUOUS_RESEARCH runner can invoke the canonical series continuation before its trading-day early return. PostgreSQL clock, exact TradingSessions, overdue terminalization, planning gaps, due claim, lease/fence recovery and unknown Provider effect handling are wired and have focused tests. This is not proof of an installed continuously running service. |
| Real prospective attempt | New series `r2_xshg32`, generation `1303080a-8a96-51dc-9021-31a9250c85d9`, began at 2026-09-05 15:56:17.897411 UTC with 288 future slices. At 2026-09-05 23:39:54 UTC, canonical continuation found due=0, no new generation and no planning gap. `REAL_DUE_ATTEMPT=BLOCKED_BY_TEMPORAL_WINDOW`; the frozen WP-18Q total exit still requires real due proof. |
| Hard-cut | Prerequisites remain incomplete; WP-specific executors are retained. |
| Remote Actions | Repository API returned disabled: `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`. |

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
