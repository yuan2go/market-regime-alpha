# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative implementation status; exact-SHA qualification belongs to Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-05 WP-18Q qualification closure
> **Repository Implementation Checkpoint:** `b1ecd03a3b549f823628b30dbd432b1afb3af83e`
> **Execution-Time Main Baseline:** `66c30e0159b8ce4bb3e17a7fdf1c3cc48dae6167`
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
| Functions / non-internal triggers | 145 / 386 |
| Catalog objects | 3,926 |
| Baseline SHA256 | `aae59a527154fd19da4bf07a0402d353d2b02a8da56cef6c4a505509683c412b` |
| Catalog SHA256 | `a61a4ed2a4ae93521942053c37ab6560386bc49c43e64ef3a03f21ab4ab14a71` |
| Seed SHA256 | `9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11` |
| Reference-vocabulary SHA256 | `d08800892f5e843a756f53e46205dfbb2787386ebf8281564c31049c45659a1b` |

The draft baseline and exact registered additive operational bundles serve
different operations. Operational evidence databases must not be recreated.
A new disposable test database does not attest to an operational upgrade.

## WP-18Q qualification disposition

The closure began from execution-time fetched main, not an old PR description.
Regression found historical Model/Partition name drift, obsolete fixture and
catalog expectations, shared-owner wiring/export-size contract drift, and an
Evaluation source × metric join amplification. Corrections retain exact
assertions and historical identity semantics. The SQL correction deduplicates
fold/Evaluation identities before joining metrics; it creates no metric truth.

The final exact-SHA suite is independently rerun; intermediate PASS results are
not the final exit gate. One intermediate whole-suite run also rejected
ExperimentRun creation because registration did not precede opening. Isolated,
adjacent and 30-repeat checks did not reproduce it; the unexplained failure
remains recorded rather than weakening the temporal invariant.

| Gate | Proven / remaining boundary |
|---|---|
| PostgreSQL mechanics | Clean bootstrap, verify, exact-OID recreate and matching catalog/reference checksums have been exercised on disposable PostgreSQL 16 with durability enabled. Full per-command results belong to Verification. |
| WP-17P zero-write compatibility | Restored exact completed run `8f7b6def-9c63-533e-9777-a5a6c57866e0` reconciles through the private decoder and generic inspect/resume/replay. Resume dispatches zero business actions. Full-table ordered hashes and all 398 Artifact bytes remain unchanged across read-only proof. |
| Archive health | The restored snapshot initially failed the 24-hour Market readability policy. Fresh physical observations were recorded through the Artifact owner, with new audit/verification receipts; original Artifact IDs/content hashes/bytes were unchanged. Both archive reconciliations then matched. This is current verification, not backdated evidence. |
| Operational upgrade | A verified backup was restored to a new exact-OID copy and the approved additive route preserved its historical projection. The original operational database is not present at the inspected connection: its current identity, upgrade and runtime state remain unproven. |
| Real generic campaign | The accessible canonical retrospective archive ends on 2026-01-19 and cannot supply the requested 40 distinct sessions. The separate qualification manifest/raw objects exist, but archive `94a00500-c867-5ede-bf7d-886fbbd5fcaf` and its source-capture Authority are absent from the accessible restored DB. No old known-time or missing lineage was invented. |
| Standard report / campaign replay | No qualifying real WP-18Q campaign was executed, so its ModelVersion/Evaluation/report Artifact identities, metric outputs and byte-stable resume/replay remain unproven. Alpha funnel diagnosis is `NOT_DETERMINED`, not a return-based attribution. |
| Prospective | PostgreSQL inspection of the restored snapshot at 2026-09-05 06:26 UTC found due=0, overdue=128, not-due=64; one capture is historical. Current generation/planning-gap tables are empty in that old snapshot. `NOT_DUE` is not a new Runtime attempt. The mandatory true-window gate is temporally blocked; original operational state is additionally unavailable. |
| Hard-cut | Blocked by real campaign/report/replay and full exit prerequisites. No WP-specific executor or historical decoder/fixture was deleted. |
| Remote Actions | Repository API reports Actions disabled: `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`. |

Outcome path/checkpoint, overdue terminalization, planning gaps, lease recovery,
unknown-effect reconciliation, concurrency and failures require their explicit
PostgreSQL test evidence. They must not be inferred from the old smoke capture.

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
