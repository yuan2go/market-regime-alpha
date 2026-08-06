# WP-STATE-01 State System Implementation Plan

> **Status:** ROADMAP
> **Authority:** Executable implementation plan for WP-STATE-01
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06
> **Related Documents:** ../specs/2026-08-06-wp-state-01-state-system-design.md, ../../audit/WP-CRR-01-Final-Review.md
>
> **For agentic workers:** REQUIRED SUB-SKILL: use executing-plans and TDD. Steps use checkbox syntax for tracking.

**Goal:** Build deterministic state transitions, Dynamic Stock Pool authority and state-bound Candidate/Signal/Forecast research under the sole Continuous Runtime.

**Architecture:** Add domain-specific immutable contracts/evaluators, PostgreSQL-default plus explicit SQLite repositories, and one Continuous child service. Preserve V0 and historical Readers; add versioned research projections instead of mutating existing Artifacts.

**Tech Stack:** Python 3.12, dataclasses, Decimal, psycopg 3, sqlite3, pytest, Ruff, mypy, uv.

## Global constraints

- Parent Continuous Operation and Runtime Tick fencing are mandatory for writes.
- `AvailableAt <= AsOfTime`; no complete closing bar during 14:30–14:55.
- Model/Configuration selection is explicit and versioned.
- Entry, Opportunity, Order, Fill, Position and Broker authority remain false.
- Historical fixed-14:55 Target, TargetId, Reader and Replay are unchanged.
- PostgreSQL is default; SQLite is explicit compatibility/replay only.

---

### Task 1: CRR merge-preparation hardening

**Files:** `continuous_research/{contracts,evidence,ports,policy,runner,scheduler,postgres_journal}.py`, migration 021, focused tests and final review.

**Interfaces:** produce `ContinuousResearchScheduleRunner.run_due_once`, `PostgresContinuousResearchJournal.reserve_due_tick`, and fenced `ChildExecutionRequest`.

- [x] Record exact baseline and two-axis findings.
- [x] Add failing temporal/provider/scheduler/fencing tests.
- [x] Derive phase from policy and fail closed on future Evidence.
- [x] Persist failed/invalid Attempts and durable schedule reservation/recovery.
- [ ] Run CRR PostgreSQL, SQLite compatibility and exact migration gates.
- [ ] Commit `audit(crr): harden continuous runtime authority`.

### Task 2: Versioned state contracts and configuration

**Files:** create `research/state_system/{common,configuration}.py`; test `tests/research/state_system/test_contracts.py`.

**Interfaces:** `StateLineage`, four domain configurations and canonical identity round trips.

- [ ] Write failing round-trip, tamper, future-time and unversioned-threshold tests.
- [ ] Implement immutable lineage, threshold and policy contracts.
- [ ] Run focused tests, Ruff and mypy.
- [ ] Commit `feat(state): add state transition contracts`.

### Task 3: Stateful Market Regime

**Files:** create `research/state_system/market.py`; test `test_market.py`.

**Interfaces:** `evaluate_market_state(observation, previous, configuration) -> MarketStateEvaluation`.

- [ ] Test initial, pulse, confirmation, dwell, enter/exit, hysteresis, counter evidence, insufficient data and replay.
- [ ] Implement additive V0-observation adapter and deterministic evaluator.
- [ ] Verify Market State never grants Entry/Broker authority.
- [ ] Commit `feat(state): implement stateful market regime`.

### Task 4: ETF and Theme Rotation

**Files:** create `research/state_system/{etf_rotation,theme_rotation}.py`; focused tests.

**Interfaces:** separate `evaluate_etf_rotation` and `evaluate_theme_rotation` functions and domain types.

- [ ] Test ETF pulse/resonance/persistence/liquidity and lifecycle transitions.
- [ ] Implement ETF observation scoring and transition policy.
- [ ] Test many-to-many mapping, breadth/leader conflicts, incomplete mapping, hysteresis and replay.
- [ ] Implement Theme-specific aggregation and transition policy.
- [ ] Commit `feat(rotation): implement ETF and theme rotation states`.

### Task 5: Capital State

**Files:** create `research/state_system/capital.py`; test `test_capital.py`.

**Interfaces:** `evaluate_capital_state` returning proxy-only state and transition.

- [ ] Test four bias states, counter evidence, coverage and replay.
- [ ] Test forbidden institutional assertions are absent.
- [ ] Implement deterministic proxy inference.
- [ ] Commit `feat(capital): implement stateful capital inference`.

### Task 6: Dynamic Stock Pool and persistence

**Files:** create `research/state_system/pool.py`, `application/state_system/{repository,postgres_repository,sqlite_repository}.py`, migration 022 and persistence tests.

**Interfaces:** `evaluate_dynamic_pool` and repository `append_evaluation/read/latest` seams.

- [ ] Test initial/add/remove/no-change/Eligibility/rotation/materiality/future-state/replay.
- [ ] Implement immutable Pool and full member/change records.
- [ ] Add migration 022, schema verification and empty-database/020-upgrade tests.
- [ ] Implement PostgreSQL fenced CAS and concurrent-create tests.
- [ ] Implement explicit SQLite parity and restart recovery.
- [ ] Commit `feat(universe): add dynamic stock pool authority`.

### Task 7: Candidate, Signal and Forecast binding

**Files:** create `research/state_system/research_integration.py`; focused tests; minimally extend exports only.

**Interfaces:** `bind_candidate_set`, `project_signal_v4`, `project_empirical_forecast_v2`, and lineage-exposure audit.

- [ ] Test correct Pool/full cross section/identity reuse/AvailableAt gate.
- [ ] Test new Signal uses `factor_coverage` and legacy Reader remains compatible.
- [ ] Test Forecast is uncalibrated, probability-free and fail closed without samples.
- [ ] Implement additive versioned projections around existing services.
- [ ] Commit `feat(research): bind candidate signal forecast to state and pool`.

### Task 8: Continuous Runtime integration and authority coverage

**Files:** create `application/state_system/runtime.py`; extend continuous child composition, tests and CLI reporting.

**Interfaces:** one material-change child call producing a `StateRuntimeReceipt`; no-change returns prior identities without service calls.

- [ ] Test Evidence-to-Forecast order, no-change suppression, restart and stale fence.
- [ ] Test no Daily Summary/Opportunity/Order/Fill/Position/Broker symbols are invoked.
- [ ] Run PostgreSQL concurrency, SQLite replay and real free-data smoke attempt.
- [ ] Commit `test(state): add replay concurrency and authority coverage`.

### Task 9: Documentation and final gate

**Files:** roadmap WP, runbook, Current State, Capability Matrix, Gap Register and delivery evidence.

- [ ] Record actual call/state diagrams, migrations, tests and evidence ceiling.
- [ ] Run docs, full pytest with PostgreSQL, Ruff, mypy, build and diff checks.
- [ ] Bind evidence to final local SHA and leave Worktree clean.
- [ ] Commit `docs(state): add WP-STATE-01 design runbook and evidence`.
