# Capability Matrix

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative capability read model; never qualification Authority
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-07 research operations activation
> **Repository Implementation Checkpoint:** `26d4d98e045d323fd4947ed7df298e0b57867581`
> **Implementation Tree:** `a91d2228f7f3be8fa2e8c1de5c56f945ec5dac9f`
> **Execution-Time Main Baseline:** `2d6fbb2981a4e16fd7701884cc8d040c349bae1c`
> **Containing Documentation Commit:** reported by handoff; no self-referential SHA
> **Schema Epochs:** legacy `LEGACY_MIGRATIONS_001_106`; target `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Code Evidence:** `src/market_regime_alpha/bootstrap.py`, `src/market_regime_alpha/infrastructure/postgres/migrations`, `tests/refoundation`, `tests/platform`, [Current State](Current-State.md), and linked immutable Verifications

This matrix supersedes the WP-17P-only active-state snapshot. It distinguishes
implemented target mechanics from actual engineering qualification and research
evidence. Existing legacy business owners remain in service until an explicit
cutover; target-draft writes do not acquire legacy business Authority.

Research economics V2 passes its bounded [exact-revision engineering gate](../references/WP-RESEARCH-ECONOMICS-CORRECTNESS-01-Verification.md):
4,045 full-repository cases without failures/errors/skips, complete root/child
integrity, four Validation episodes across folds/months, independent hand values,
concurrency/recovery, deterministic report/replay, installed-wheel/schema smoke
and a finite restored-input comparison. Full paths close before slicing and
samples count complete independently funded episodes. Continuous accounts,
carry/overlap and actual market executability remain unsupported. Legacy/V1
hashes, meaning and report bytes are preserved in the verified exact scope and
excluded from V2 correctness claims. See the [model contract](../references/WP-RESEARCH-ECONOMICS-CORRECTNESS-01-Design.md).

Current target catalog: **192 tables, 4 views, 3,929 catalog objects**.
Counts remain unchanged by v6; exact checksums and separately scoped original-v5
and restored-v6 evidence are in Current State. Original OID 287543 now passes its authorized registered v6 upgrade.
Old 165-table and 3,776-test WP-17P numbers belong only to its historical
[Verification](../references/WP-ARCHITECTURE-REFOUNDATION-17P-Prospective-Archive-Exploratory-Backtest-Verification.md).

```text
WP18Q_EXIT_GATE = BLOCKED
BACKTEST_PLATFORM = ENGINEERING_QUALIFIED_IN_COMPLETED_RECOVERY_SCOPE
```

| Capability | Current implementation / evidence boundary | Target owner / convergence |
|---|---|---|
| Runtime | Existing Schedule → Run → Step → Attempt → fence, PostgreSQL due/recovery and owner command composition; sole all-day `CONTINUOUS_RESEARCH`; no business CLI cutover | Runtime / `NOT_CUT_OVER` |
| Market / PIT | Capture, append-only facts/revisions, exact as-of reads and typed SourceGap/unavailable states; public providers remain exploratory | Market / `IMPLEMENTED_DRAFT` |
| Market archive | Separate retrospective/prospective lanes, immutable slices/observations/seals and read-only reconciliation; restored archives verify after new owner-recorded physical Artifact checks | Market + Runtime/Artifact / `RECOVERED_NEW_SCOPE / EXPLORATORY_ONLY` |
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
| Evaluation | Canonical protocols/formulas/typed observations and source rosters; insufficient samples require typed NOT_ESTIMABLE | Research / `COMPLETED_RECOVERY_SCOPE / ORIGINAL_RUN_FAILED` |
| Generic Backtest | Existing root + frozen Specification; generic Runtime executor, inspect/resume/replay and canonical owner delegation | Research / `ENGINEERING_QUALIFIED_IN_COMPLETED_RECOVERY_SCOPE` |
| Standard Backtest Report | Deterministic JSON/Markdown projection from reconciled Authority/Evaluation; no raw-bar metric recomputation | Research report projection / `LARGE_REPORT_REPLAYED_IN_RECOVERY_SCOPE` |
| Historical compatibility | WP-17P exact allowlist/private decoder/reconciliation-only proof; WP-18 definition equivalence, not historical multi-fold execution | Private compatibility read / `NO_WRITE_AUTHORITY` |
| WP-specific hard-cut | WP-specific executors are removed after pre-deletion gates; private exact historical decoding and Generic composition remain | Generic surface / `HARD_CUT_PASS_AT_09561b25` |
| Research Qualification | Concrete Evidence/Assessment/policy/floor/decision and later-generation reads; training or positive returns never qualify a model | Research / `NO_EMPIRICAL_PROMOTION` |
| Formal Research Campaign | Freeze/protected-open/Runtime/Provider-gate mechanics exist; rejected Provider evidence prevents real Formal OOS execution | Research + Runtime / `FORMAL_OOS_NOT_RUN` |
| Prospective | Atomic admission shared by current target Runtime claims/supervision; bounded Provider effects; exact Schedule lineage and multi-member missed-window restart reconciliation. Original v6 is upgraded; current-user deployment and backup-refresh procedures are installed within the authorized scope. Actual due/successful capture and sustained duration remain separate evidence gates | Market + existing Runtime / `GUARDED_IMPLEMENTATION / LIVE_PROOF_SCOPED` |
| Operational health / recovery | Canonical full-roster window/Runtime projection, separate capture/on-time/terminal rates, actionable internal alert changes, unknown-effect reconciliation and partial-registration recovery | Read-only operational projection / `NO_BUSINESS_AUTHORITY` |
| Research funnel diagnosis | Complete 9,472-cell denominator: 9,436 eligible and 36 canonical exclusions; 97 typed non-estimable metrics explained without rewriting the frozen report. Rule/ridge ranking increment is not demonstrated | Read-only reconciled Evaluation projection / `DAILY_SHADOW_NOT_READY` |
| Original database diagnosis | Exact SQL/parameters and bounded PK plans retained; original planning/metadata reads remain slower, without historical failure-time causal evidence | Read-only PostgreSQL diagnostics / `ROOT_CAUSE_UNPROVEN` |

The pre-R2 old operational scope remains unavailable at inspected locations.
The distinct current R2 original database OID 287543 is accessible and retains
its failed large Run.
R2 recovered immutable history into a distinct operational scope, built a new
116-session/32-instrument canonical archive, and verified exported-snapshot
backup, independent restore and additive v3/v4/v5 preservation. All 189 business
tables, physical Artifacts and completed historical/Generic replay survive the
latest controlled upgrade. Artifact owner verification uses actual maintenance
time; a prior restore's expired-verification failure remains negative evidence.

The frozen writer `f247ca5d` retains its own 3,997-test/four-subtest evidence.
It now completes the unchanged 44-session/four-arm, 936-action Run
`6318cbb0-e1d5-54b4-96bf-a2f458d0ef71` in an isolated faithful recovery copy:
296 Dataset/Decision identities, 9,436 Outcomes, four ModelVersions and 44
Evaluations. Original OID 287543 retains its terminal Evaluation timeout;
copy completion does not change that original fact. A post-completion backup
and second independent restore match all 192 table hashes, 2,780 Artifacts,
five Archives and 16 Backtest reconciliations. Repeated publication, resume and
replay preserve completed report bytes and business facts.

The large report retains 511 estimable and 97 typed NOT_ESTIMABLE entries,
including all declared roster gaps. Frozen V1 economics is never promoted by
the completed V2 package. Independent small-campaign comparison returns
LIKE_FOR_LIKE for 178 metrics. The current CLI serializes finite Decimal values
as exact strings and refuses non-finite values; it does not recompute metrics.
Alpha funnel bottleneck remains `NOT_DETERMINED`.

New Runtime progress reads every frozen action binding, last Attempt, lease and
error through bounded queries and explicitly reports owner reconciliation as
NOT_PERFORMED. Foreground prospective `serve` wakes the same continuation owner,
closes each composition and drains signals; it has no business clock, scheduler,
effect retry or state Authority. Final implementation qualification is recorded
in the existing R2 Verification, independently of frozen execution provenance.

The `mra evidence` inventory is a regenerable non-authoritative operator index.
It records database/root identities and verified backup/integrity/restore facts;
it cannot promote a failed or incomplete campaign into successful execution.

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

Frozen writer `f247ca5d` completed the 936-action large Run in its explicit
isolated recovery scope, recorded by the prior 09561b25 continuation. The
`4c764b3d` activation only replays and diagnoses that preserved completed evidence; it does
not retrain or repeat campaign execution. The completed scope contains four ModelVersions, 44
Evaluations, 608 declared metrics and deterministic report/replay. Original
operational OID 287543 retains its terminal Evaluation timeout. Generic
`backtest progress` exposes exact Runtime bindings with
`owner_reconciliation=NOT_PERFORMED`; it cannot admit business completion.
Foreground prospective supervision delegates every wakeup to existing
continuation. An explicitly authorized current-user project LaunchAgent invokes
that entry; it owns no business clock. Final gate results and the
remaining temporal/operational boundaries are recorded in Current State.

Previous activation `4c764b3d` passes 4,163 full cases with zero failures/errors/
skips; focused 152, architecture/docs 41, static/type/docs/build and independent
installed-wheel/schema/real replay smoke also pass.
Its preceding f55 full run retains three failures (4,160 passes, zero skips);
exact migration-roster and SQL-layer repairs have focused green evidence.
The exact final result is appended to the existing R2 Verification.
Restored-v6 upgrades preserve all 189 business tables and Artifact identities;
independent v6 restore preserves all 192 table hashes and 2,770 physical Artifacts.
The original database's fresh v6 challenge is applied under explicit authorization;
189 business-table hashes and Artifact bytes remain unchanged by that upgrade.
No recovery-copy adoption occurs. Frozen V1 campaign outputs are reverified in completed restore
OID 144400596 with no business writes. No new Model, protocol or training occurs.

Final completed-v6 backup `72edc6c6…` restores independently to OID 157024168:
192 table hashes, 2,780 physical Artifacts, five Archives, WP17P/large Run replay
and original report bytes match with zero source writes. The prior `4c764b3d` Provider refusals remain preserved. Current post-close
product access succeeds; current activation records 128 MISSED windows and
preserves two corrected startup failures. Latest runtime `26d4d98e` is validated
with targeted concurrency/continuity/recovery and installed-wheel checks;
The actual current-user service records 22 bounded ticks, successor generation
registration, graceful stop, a new 2,774-Artifact backup and verified profile
refresh/restart. The same backup has copies on two local physical disks; a new
independent database restore is NOT_RUN in this activation. Repeated scoped
facts match without additional Receipt/Audit facts. No actual due Attempt or
Capture is inferred from these maintenance results.
FULL_REGRESSION=NOT_RUN for this risk-directed activation. The remaining frozen
WP18Q due-proof gate and sustained collection remain independently unproven.
