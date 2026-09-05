# Capability Matrix

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative exact-SHA implementation read model
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-05 qualification closure
> **Repository Implementation Checkpoint:** `7818253cda85755175d87ff3acec1b1d8d7af762`
> **Execution-Time Main Baseline:** `66c30e0159b8ce4bb3e17a7fdf1c3cc48dae6167`
> **Schema Epochs:** legacy `LEGACY_MIGRATIONS_001_106`; target `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Source Tree IDs:** source `a411f63a5534dd91ed4562c9fe87133490d4db51`; tests `8b0c63e5349651f14e583d96a936725498b3d886`; baseline blob `0f40f6d667fc4ecf561162cad4f6434efba9d033`
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`, `tests/refoundation`

This view separates implementation from real qualification. The exact ledger is
[WP-18Q Final Closure Verification](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-Final-Closure-Verification.md); [Roadmap](Roadmap.md) owns planning order.

| Capability | Owner and executable surface | Qualification boundary |
|---|---|---|
| Universe / Eligibility / Candidate | Selection; immutable scope and Candidate-first ordering | Prior engineering checkpoints preserved; no full Runtime cutover |
| Target / Decision / Outcome | Research / Decision Support / sole Market Target Outcome | Historical identities preserved; no second label truth |
| Context / Signal / Forecast / Opportunity | Decision Support; rule and optional ridge inference | Exploratory, uncalibrated; no Model qualification |
| Portfolio / Risk | Complete Portfolio followed by sole Risk decision | No execution, Position or broker authority |
| Generic specification | Sole Backtest root with explicit arms/folds/dependencies | Implemented/wired; real 40-session/32-symbol campaign blocked by unavailable canonical archive |
| Generic executor / resume / replay | Existing Runtime and canonical owner Applications | WP-17P zero-write historical proof; real current campaign unproven |
| Model training | Completed FIT, TrainingRun, fitted Artifact, ModelVersion, later validation | Mechanics only; `MODEL_QUALIFIED = NO` |
| Standard Evaluation | Canonical formulas/sources and typed not-estimability | No newly measured campaign economics |
| Report / comparison | Reconciled Evaluation, content-addressed JSON/Markdown | Implemented; real campaign Artifact identities/stability unproven |
| Prospective archive | Market generation/window/gap/terminal/revision owners | Restored history inspected; original operational DB unavailable |
| Prospective Runtime | Existing Schedule/Run/Step/Attempt/fence, PostgreSQL time | No new real due Attempt; continuous planning-gap/roll-forward/overdue wiring remains unproven |
| PostgreSQL | Target draft 192 tables and 4 views; guarded recreate/additive API | Disposable qualification and restored-copy rehearsal do not attest to original operational upgrade |
| WP-17P compatibility | Private exact decoder and Generic reconciliation | Completed historical zero-write evidence |
| WP-18 compatibility | Exact four-arm multi-fold definition decoder | Definition-only, no completed historical execution claim |
| WP-specific hard cut | Existing executors retained pending prerequisites | `BLOCKED`; no new permanent facade |
| Formal Provider / PIT / OOS | Purpose-specific qualification owners | `BLOCKED / BLOCKED / NOT_RUN` |
| Alpha / Prospective value / Model qualification | Separate empirical gates | `NO / NO / NO` |
| Execution / Position / TradeOutcome | Human/manual boundary; observed fills | No new implementation or broker integration |
| Runtime/CLI full cutover / Production | Separate admission gates | `NO-GO / NO-GO` |

```text
WP18Q_EXIT_GATE = BLOCKED
BACKTEST_PLATFORM = NOT_ENGINEERING_QUALIFIED
```

Historical WP-17P success remains bound to its
[immutable Verification](../references/WP-ARCHITECTURE-REFOUNDATION-17P-Prospective-Archive-Exploratory-Backtest-Verification.md).
