# Capability Matrix

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative capability read model; never qualification Authority
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-05 WP-18Q qualification closure
> **Repository Implementation Checkpoint:** `b1ecd03a3b549f823628b30dbd432b1afb3af83e`
> **Execution-Time Main Baseline:** `66c30e0159b8ce4bb3e17a7fdf1c3cc48dae6167`
> **Containing Documentation Commit:** reported by handoff; no self-referential SHA
> **Schema Epochs:** legacy `LEGACY_MIGRATIONS_001_106`; target `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Code Evidence:** `src/market_regime_alpha/bootstrap.py`, `src/market_regime_alpha/infrastructure/postgres/migrations`, `tests/refoundation`, `tests/platform`, [Current State](Current-State.md), and linked immutable Verifications

This matrix supersedes the WP-17P-only active-state snapshot. It distinguishes
implemented target mechanics from actual engineering qualification and research
evidence. Existing legacy business owners remain in service until an explicit
cutover; target-draft writes do not acquire legacy business Authority.

Current target catalog: **192 tables, 4 views, 3,926 catalog objects**.
Exact checksums and observed PostgreSQL counts are in Current State.
Old 165-table and 3,776-test WP-17P numbers belong only to its historical
[Verification](../references/WP-ARCHITECTURE-REFOUNDATION-17P-Prospective-Archive-Exploratory-Backtest-Verification.md).

```text
WP18Q_EXIT_GATE = BLOCKED
BACKTEST_PLATFORM = NOT_ENGINEERING_QUALIFIED
```

| Capability | Current implementation / evidence boundary | Target owner / convergence |
|---|---|---|
| Runtime | Existing Schedule → Run → Step → Attempt → fence, PostgreSQL due/recovery and owner command composition; sole all-day `CONTINUOUS_RESEARCH`; no business CLI cutover | Runtime / `NOT_CUT_OVER` |
| Market / PIT | Capture, append-only facts/revisions, exact as-of reads and typed SourceGap/unavailable states; public providers remain exploratory | Market / `IMPLEMENTED_DRAFT` |
| Market archive | Separate retrospective/prospective lanes, immutable slices/observations/seals and read-only reconciliation; restored archives verify after new owner-recorded physical Artifact checks | Market + Runtime/Artifact / `COPY_PROVEN / LIVE_STATE_UNPROVEN` |
| Provider qualification | Immutable purpose-specific protocols/finality/decisions/rosters; WP-15 rejected, WP-16 external-evidence gate remains blocked | Market / `FORMAL_PROVIDER_BLOCKED` |
| Formal PIT / Dataset | Admitted exact recorded-provider decision and typed visibility remain mandatory; no latest/backfill assertion can substitute | Market + Research / `FORMAL_PIT_BLOCKED` |
| Regime | Legacy State System remains in service; target MARKET_REGIME Context policy/assessment/source lineage exists | Decision Context / `IMPLEMENTED_DRAFT` |
| ETF | Reference/rotation capability retained; target ETF_ROTATION Context exists | Market + Decision Context / `IMPLEMENTED_DRAFT` |
| Theme | Classification/theme capability retained; target THEME_ROTATION Context exists | Market + Decision Context / `IMPLEMENTED_DRAFT` |
| Capital | Public-proxy breadth capability retained, without hidden institutional-intent claims | Decision Context / `IMPLEMENTED_DRAFT` |
| Universe | Explicit frozen scope/member/revision and exact Market lineage; no implicit current-universe discovery | Selection / `IMPLEMENTED_DRAFT` |
| Eligibility | Immutable policy/rules and complete eligible/ineligible/unknown dispositions | Selection / `IMPLEMENTED_DRAFT` |
| Candidate | Policy/components, exact Dataset population, ranking and complete score/disposition roster | Selection / `IMPLEMENTED_DRAFT` |
| Target Definition | Provider-neutral Target/Checkpoint/Metric/Dependency contract, immutable version and Artifact binding | Research / `IMPLEMENTED_DRAFT` |
| Decision / Commitment | Candidate × Target commitments, frozen Decision references and exact qualification-generation roster | Decision Support / `IMPLEMENTED_DRAFT` |
| Context | Explicit policy/assessment/metric/source lineage and missing/pass/fail states | Decision Support / `IMPLEMENTED_DRAFT` |
| Signal | Complete exact Candidate/Context/Strategy lineage, including no-signal/wait/unknown | Decision Support / `IMPLEMENTED_DRAFT` |
| Forecast | Rule and exact ModelVersion binding paths; uncalibrated coverage/estimate states | Decision Support / `EXPLORATORY_ONLY` |
| Opportunity | Complete Candidate/Signal/Forecast/Context/Strategy evidence; no pre-Strategy Risk authority | Decision Support / `IMPLEMENTED_DRAFT` |
| Thesis | Append-only revisions and separately falsifiable conditions | Decision Support / `IMPLEMENTED_DRAFT` |
| Strategy | Immutable versions with concrete Context, Signal and Forecast rules | Decision Support / `IMPLEMENTED_DRAFT` |
| Portfolio | Explicit complete proposed allocation/line roster; never creates actual Positions | Decision Support / `DECISION_SUPPORT_ONLY` |
| Risk | Sole post-Portfolio assessment with preserved rejection/unknown/no-action; no operator or strategy bypass | Decision Support / `NO_EXECUTION_AUTHORITY` |
| Execution / Account | Existing human/manual capability preserved; no new broker or target Execution owner | Execution & Account / `NOT_STARTED` |
| Position / Holding | Actual positions derive from observed effective fills, not recommendations or target exposure | Derived account query / `NOT_CUT_OVER` |
| Market Outcome | One commitment-bound root, append-only revisions, checkpoint/path/MFE/MAE source/observation lineage and exact reconciliation | Outcome / `IMPLEMENTED_DRAFT` |
| TradeOutcome / Attribution | Retained legacy capability; new target owners not implemented | Outcome & Attribution / `NOT_STARTED` |
| Research Definition | Dataset/DatasetSource/FeatureDefinition and explicit retrospective dual-clock lineage, without ordinary PIT weakening | Research / `IMPLEMENTED_DRAFT` |
| Model / Training / Version | Completed FIT samples, deterministic ridge, reproducibility/dependency/hyperparameter rosters, fitted Artifact and later-validation binding | Research / `MODEL_QUALIFIED_NO` |
| Evaluation | Canonical protocols/formulas/typed observations and source rosters; insufficient samples require typed NOT_ESTIMABLE | Research / `IMPLEMENTED / REAL_WP18Q_CAMPAIGN_UNPROVEN` |
| Generic Backtest | Existing root + frozen Specification; generic Runtime executor, inspect/resume/replay and canonical owner delegation | Research / `QUALIFICATION_BLOCKED` |
| Standard Backtest Report | Deterministic JSON/Markdown projection from reconciled Authority/Evaluation; no raw-bar metric recomputation | Research report projection / `REAL_REPORT_UNPROVEN` |
| Historical compatibility | WP-17P exact allowlist/private decoder/reconciliation-only proof; WP-18 definition equivalence, not historical multi-fold execution | Private compatibility read / `NO_WRITE_AUTHORITY` |
| WP-specific hard-cut | Executable WP orchestration remains because real campaign/report/replay prerequisites are not complete | Generic surface target / `HARD_CUT_BLOCKED` |
| Research Qualification | Concrete Evidence/Assessment/policy/floor/decision and later-generation reads; training or positive returns never qualify a model | Research / `NO_EMPIRICAL_PROMOTION` |
| Formal Research Campaign | Freeze/protected-open/Runtime/Provider-gate mechanics exist; rejected Provider evidence prevents real Formal OOS execution | Research + Runtime / `FORMAL_OOS_NOT_RUN` |
| Prospective | Target-aligned generation/planning/terminal/revision and Runtime mechanics exist; restored snapshot has due=0, overdue=128, future=64, and no current-generation rows | Market + existing Runtime / `NOT_DUE / LIVE_PROOF_BLOCKED` |

The accessible old canonical archive cannot supply the required 40 sessions;
the separate qualification archive's canonical DB records are missing.
Original operational upgrade, the real generic four-arm campaign, standard
report and exact campaign replay therefore remain unproven. No hard-cut was
performed. Alpha funnel bottleneck is `NOT_DETERMINED`.

`IMPLEMENTED` never means qualified or cut over. Evidence ceilings remain:

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

[Roadmap](Roadmap.md) alone owns pending work. The
[Capability Preservation Matrix](../references/WP-ARCHITECTURE-REFOUNDATION-01-Capability-Preservation-Matrix.md)
retains the complete preservation contract. Neither this view nor a passing
fixture, local suite or report can grant Provider, PIT, OOS, trading or
Production authority.
