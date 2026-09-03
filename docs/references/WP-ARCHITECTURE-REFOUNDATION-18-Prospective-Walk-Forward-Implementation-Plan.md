# WP-18 Prospective Operations and Walk-Forward Implementation Plan

> **Status:** CURRENT_STATUS
> **Authority:** Execution plan for the frozen WP-18 design; not empirical evidence Authority
> **Baseline:** `origin/main@097f19ecf846aef7cf55a3013adf5eb91faefce6`
> **Owner:** Market Regime Alpha maintainers
> **Frozen:** 2026-09-03

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` task-by-task and retain red/green evidence.

## Constraints

- Work only in `agent/wp-18-prospective-walk-forward` and its isolated worktree.
- Extend the unreleased `001_baseline.sql`; do not create `002+`.
- Preserve ordinary PIT checks and immutable WP-15/16/17P rows.
- Use disposable PostgreSQL for qualification; operational database upgrades
  are backup-first, additive-only, identity-guarded and never recreated.
- Use existing Runtime, Market Archive, Dataset, Decision Support, Outcome,
  Model and Evaluation owners.
- Evidence ceilings remain as frozen by the Design.

## Task 1: freeze public domain contracts

**Tests first:** archive generation/schedule/domain and exploratory backtest
domain suites.

- [ ] Add typed schedule slots, terminal states, due states, generation/member/
  schedule plans and revision-chain validation.
- [ ] Add four WP-18 arm kinds, arm Strategy binding, paired fold-generation
  lineage and typed observational Context behavior.
- [ ] Prove Friday-to-Monday/holiday resolution consumes TradingSession IDs;
  missing/wrong exchange fails closed.
- [ ] Prove old WP-17P two-arm generation remains valid and immutable.

## Task 2: persist prospective generation closure

**Tests first:** Market PostgreSQL and schema specification suites.

- [ ] Add generation/member/schedule/terminal/revision relations and FK-leading
  indexes to `001_baseline.sql`.
- [ ] Add deferred complete-roster, Target/session, predecessor, one-terminal,
  timeliness and revision-chain guards.
- [ ] Implement narrow Archive UoW persistence and exact replay.
- [ ] Implement typed TradingSession + Target schedule readers with no calendar
  arithmetic.
- [ ] Implement `plan-next-session` and generation reconciliation.

## Task 3: close due operations

**Tests first:** archive operation tests for early, on-time, late, missed,
Provider gap, resource stop, crash and unknown commit.

- [ ] Finalize elapsed open slices before executing currently due slices.
- [ ] Make terminal recording atomic with capture/gap/resource/failure evidence.
- [ ] Preserve raw bytes and execute Provider I/O outside transactions.
- [ ] Add resume, daily-health, missed-window and revision read models.
- [ ] Prove duplicate/changed payload and stale-fence behavior.

## Task 4: extend walk-forward predeclaration

**Tests first:** backtest domain/PostgreSQL suites.

- [ ] Support legacy two-arm and new exact four-arm vocabularies without
  rewriting old rows/hashes.
- [ ] Persist complete per-arm StrategyVersion/context-mode binding.
- [ ] Persist training/validation generation lineage and reject same/earlier
  Model inference.
- [ ] Freeze >=40 unique chronological sessions with explicit purge/embargo.
- [ ] Reconcile complete root/arm/fold/session/policy rosters.

## Task 5: implement observational Context and canonical campaign

**Tests first:** Strategy inference and campaign orchestration suites.

- [ ] Add `OBSERVE_ONLY` as a typed Strategy behavior; keep the numeric Context
  threshold unchanged and retain all exact Context bindings.
- [ ] Materialize one stable deterministic 32-symbol Dataset per effective
  session and shared-input arm group.
- [ ] Execute completed FIT -> ModelTrainingRun -> immutable ModelVersion ->
  later validation inference for every pair.
- [ ] Run the rule/ridge x current/observational arm matrix through canonical
  Decision Support and Outcome.

## Task 6: layer-complete Evaluation

**Tests first:** Evaluation domain/repository and metric-source tests.

- [ ] Add exact Candidate-score/Context/Opportunity/Dataset-feature source
  bindings and closed measures.
- [ ] Preserve complete denominators and terminal missing states.
- [ ] Make zero-exposure economics explicitly NOT_ESTIMABLE.
- [ ] Add Candidate RankIC/spread/hit and full funnel metrics.
- [ ] Derive and test `AlphaFunnelDiagnosis` upstream-first; no caller result.

## Task 7: replay, concurrency and recovery qualification

- [ ] Recompute Track A and Track B complete rosters/hashes/source lineages.
- [ ] Exercise identical/changed planning, due-finalization races, capture
  replay, stale fence, connection failure, unknown commit and crash resume.
- [ ] Exercise fold/arm registration and Evaluation completion races.
- [ ] Require `matched = true`, `mismatch_count = 0`.

## Task 8: exact-SHA engineering gate

- [ ] Freeze implementation SHA after focused regression.
- [ ] On a fresh PostgreSQL 16 database run bootstrap/verify, exact-OID guarded
  recreate/verify and schema/catalog checksum comparison.
- [ ] Run WP-18 focused, refoundation, platform, PostgreSQL and full pytest;
  Ruff, mypy, build, docs/navigation, architecture/import and diff checks.
- [ ] Run representative `EXPLAIN (ANALYZE, BUFFERS)` paths.
- [ ] If code changes, commit a new SHA and repeat every affected gate.

## Task 9: safe operational execution

- [ ] Resource-preflight the operational DB and Artifact root.
- [ ] Verify exact operational DB identity; create and hash a readable backup.
- [ ] Apply and reconcile the additive WP-18 forward upgrade.
- [ ] Resume existing archive facts; close due slices and create the next actual
  XSHG generation; prove future slices are NOT_DUE.
- [ ] Produce daily-health, missed-window and revision reports.
- [ ] Seal the eligible retrospective archive without deleting raw evidence.
- [ ] Execute >=40 sessions/multiple folds, four diagnostic arms, rule/ridge,
  Evaluation and exact replay; report resource/provider limits honestly.

## Task 10: immutable verification and merge gate

- [ ] Create immutable WP-18 Verification only from exact-SHA evidence.
- [ ] Update Current State, Roadmap, Capability Matrix and architecture only
  where executable facts changed.
- [ ] Record every required command PASS/FAIL/NOT_RUN/BLOCKED and keep Remote CI
  `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN` if unchanged.
- [ ] Confirm clean branch, fetch/reconcile latest main, push, open/update PR,
  merge only if all P0/P1 gates pass, then fetch and record merged main.
