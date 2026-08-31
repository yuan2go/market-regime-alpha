# WP-11 Research Validity and Evaluation Closure Implementation Status

> **Status:** CURRENT_STATUS
> **Authority:** Mutable implementation/status record; not immutable engineering Verification
> **Owner:** Market Regime Alpha maintainers
> **Recorded At:** 2026-09-01
> **Execution-Time Main:** `4aaf4eb1c13f42c01dbc0057078f916fd50cf022`
> **Implementation Checkpoint:** `b0520ae69ff1879a640f4cee98eb07b82ee3fce7`
> **Branch:** `agent/wp-11-research-validity-evaluation-closure`
> **Worktree:** isolated linked worktree for the branch above; primary checkout untouched
> **Schema Epoch:** `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`

```text
IMPLEMENTATION = COMPLETE
FOCUSED_UNIT_VALIDATION = PASS
FULL_ENGINEERING_QUALIFICATION = NOT_RUN

WP11_IMPLEMENTED_DRAFT
FOCUSED_VALIDATION_PASS
ENGINEERING_QUALIFICATION_PENDING
```

This record is deliberately not named Verification and does not establish
`WP11_EXIT_GATE = PASS`. It records a complete implementation draft plus the
focused validation authorized for this work package. Independent full
engineering qualification remains the next work package.

## 1. Execution and document checkpoints

The implementation started from the execution-time `origin/main` SHA above in
an isolated branch/worktree. The original workspace and its pre-existing
`.idea/modules.xml` change were not modified.

| Checkpoint | Commit | Result |
|---|---|---|
| stale/superseded document cleanup | `e31014e` | Roadmap and active authority converge on one integrated WP-11; immutable WP-09/WP-10 Verification files unchanged |
| canonical design freeze | `bb00378` | approved ownership, three UoWs, live-clock Prospective rule, purpose-specific overlap, private acquisition, ordinal and PostgreSQL-time rules frozen |
| detailed implementation plan | `eab0cae` | Gate A → Gate B → Gate C sequence and focused validation scope frozen |
| Gate A | `00f90d0` | Target Domain/PostgreSQL/Outcome contract parity closed |
| Gate B and Gate C implementation | `406f55c` | Partition, Experiment, Evaluation Protocol/Run, Outcome access, observations, and metric closure implemented |
| two-axis review corrections | `b0520ae` | Application/Infrastructure dependency boundary, symmetric serialized overlap, database-derived roster closure, protected Gate B, PIT leaf revalidation, EvaluationRun artifacts/provenance and FAILED replay hardened |

## 2. Gate A — Target/Outcome parity

Target Domain validation and PostgreSQL root-last closure now require at least
one `REQUIRED` metric and enforce exactly the same five dependency shapes that
Outcome reconstructs:

| Metric | Dependency contract |
|---|---|
| `SIMPLE_RETURN` | exactly one `REFERENCE` + one `OBSERVATION` |
| `OBSERVATION_VALUE` | exactly one `OBSERVATION` |
| `MAX_FAVORABLE_EXCURSION` | exactly one `REFERENCE` + at least one `PATH_MEMBER` |
| `MAX_ADVERSE_EXCURSION` | exactly one `REFERENCE` + at least one `PATH_MEMBER` |
| `BARRIER_HIT` | exactly one `REFERENCE` + at least one `PATH_MEMBER` |

WP-10 Outcome arithmetic, status/finality dimensions, and append-only revision
lifecycle are unchanged.

## 3. Gate B — pre-access freeze

All new ownership remains in canonical
`market_regime_alpha.research_qualification`, cohesively split into Partition,
Experiment, and Evaluation modules:

- Partition UoW owns only `ResearchPartition` and
  `ResearchPartitionMember`. PostgreSQL derives the complete member roster from
  exact Target, Decision window, and declared population scope; no caller
  member roster exists.
- Target horizon, purge, and embargo expand by exact ordered trading sessions.
  `ISOLATED_PROTECTED`, `PURGED_WALK_FORWARD`, and `DIAGNOSTIC_REUSE` implement
  purpose-compatible protected ranges without globally forbidding rolling,
  cross-fold, or diagnostic reuse.
- Prospective eligibility consumes canonical Runtime lineage semantics. It
  rejects `HISTORICAL`/`REPLAY`, accepts another mode only when its full lineage
  satisfies the live-clock timestamp contract, and always requires
  `commitment_recorded_at < earliest_outcome_event`.
- Experiment UoW owns only Experiment, Partition binding, and Experiment Run.
  It freezes research question, primary change/hypothesis, exact Target,
  Partition roster/purpose, protocol/code/config, acceptance, and provenance.
- Evaluation UoW alone owns Evaluation Protocol/Metric and Evaluation Run. A
  Protocol freezes exact Target/purpose, reducer/source-type compatibility,
  concrete Candidate-disposition slices, direction, missingness,
  inclusion/exclusion, acceptance, code/config, and provenance.
- Protected purposes prove `Partition frozen < Experiment registered <
  ExperimentRun opened < EvaluationRun OPEN`, with zero access before
  acquisition. Concrete FKs, state guards, PostgreSQL authoritative time, and
  transaction locks enforce the order.

## 4. Gate C — controlled access and Evaluation closure

`AcquireOutcomeInputs` performs one short PostgreSQL transaction:

```text
lock exact eligible Outcome revisions
→ lock Partition and complete member roster
→ lock OPEN EvaluationRun and prove access_count = 0 for Gate B
→ select one unique revision visible at requested knowledge cutoff
→ append global per-member access ordinal
→ write one EvaluationObservation per member
→ reconcile complete access and observation rosters
→ transition to INPUTS_ACQUIRED
→ commit
```

The resolver is private to the Evaluation transaction. It does not expose a
general latest/current API, call a Provider or Market repository, access bars,
or rebuild a label. Outcome values cannot leave before the access rows,
observations, reconciliation, and lifecycle transition commit. Ordinal one is
first-access Authority; non-protected diagnostic/reuse Evaluation Runs append
ordinal two or greater, while protected purposes reject access reuse.

`UNAVAILABLE` and `FAILED` Outcome revisions remain members and observations.
`NOT_DUE`, a missing due revision, ambiguous eligible revision, or incomplete
member roster fails closed without shrinking the sample.

After `INPUTS_ACQUIRED`, pure Evaluation computes V1 reducers
`MEAN_DECIMAL`, `MEDIAN_DECIMAL`, `TRUE_RATE`, and `ESTIMABLE_RATE` only from
the exact committed revision metrics. Every declared protocol metric/slice
writes an `EvaluationMetric` and the complete observation roster in
`EvaluationMetricObservation`, with explicit `INCLUDED`, `EXCLUDED`, or
`NOT_ESTIMABLE` state and reason. Only complete reconciliation permits
`COMPLETED`; reopen, input replacement, posterior protocol change, and
posterior member selection are prohibited.

## 5. Persistence and recovery shape

Only the unreleased `001_baseline.sql` changed. It adds twelve tables and no
`002+` migration:

```text
research_partition
research_partition_member
experiment
experiment_partition
experiment_run
evaluation_protocol
evaluation_protocol_metric
evaluation_run
research_partition_outcome_access
evaluation_observation
evaluation_metric
evaluation_metric_observation
```

The clean focused catalog contains 68 tables, four views, 523 indexes, 810
constraints, 54 functions, 140 non-internal triggers, and 1,600 catalog
objects. Checksums are:

| Artifact | SHA-256 |
|---|---|
| baseline | `99db3d71fee59ba330cb552509d8231f0628a47b0ae16539363ef3e9d2649486` |
| seed | `9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11` |
| reference vocabulary | `06d6c1f1b8a15c9ae83bc2f0124c003b3fe193f5a4ad5bdf09d3e8a1e3db0dcb` |
| focused clean catalog | `31d865d1a99f753b39fe34520082f9f0e3deec6993d2599470db445bfa3d1891` |

Concrete/composite FKs and closure/lifecycle/append-only triggers cover Target
matching, immutable rosters, Experiment binding, access ordinal, exact Outcome
revision, observation/metric-input completeness, and forward-only state. The
commands use exact receipts, short transactions, fence-first behavior when a
Runtime claim participates, bounded transient retries, unknown-commit exact
replay, and fresh-transaction deterministic failure recording.

## 6. Focused validation

The following directly affected suite is `PASS` with 110 tests:

```bash
PYTHONPATH=src \
MARKET_REGIME_ALPHA_TEST_DATABASE_URL='postgresql://%2Ftmp/mra_wp11_test_20260831' \
uv run python -m pytest -q \
  tests/refoundation/research_qualification/test_target_domain.py \
  tests/refoundation/outcome/test_outcome_kernel.py \
  tests/refoundation/research_qualification/test_target_postgres.py \
  tests/refoundation/research_qualification/test_target_schema_specification.py \
  tests/refoundation/research_qualification/test_partition_domain.py \
  tests/refoundation/research_qualification/test_experiment_domain.py \
  tests/refoundation/research_qualification/test_evaluation_domain.py \
  tests/refoundation/research_qualification/test_wp11_schema_specification.py \
  tests/refoundation/research_qualification/test_wp11_architecture.py \
  tests/refoundation/research_qualification/test_evaluation_closure_postgres.py \
  tests/refoundation/research_qualification/test_architecture.py \
  tests/refoundation/research_qualification/test_schema_specification.py \
  tests/refoundation/test_schema_specification.py
```

The focused PostgreSQL cases cover database-derived roster completeness, wrong
Target/member rejection, exact trading-session shifting across a calendar gap,
protected overlap rejection, protected ordering, exact cutoff selection across
Outcome correction, access ordinals one then two, completed observation/metric
rosters, replay, `NOT_DUE` zero access/observation, and unavailable-member
retention as `NOT_ESTIMABLE`. Review regressions additionally cover symmetric
protected overlap, protected second-Run rejection after first access, direct
database rejection of a future Outcome correction at an earlier cutoff,
EvaluationRun FAILED exact replay, and the Application/PostgreSQL-driver
dependency boundary.

Changed-scope Ruff, mypy, documentation link checks, and `git diff --check` are
also `PASS`. Two non-final setup observations are not promoted into evidence:
an initial PostgreSQL invocation without the test database environment was
blocked, and an inherited helper with a next-day 00:05 wall-clock fixture failed
during the few minutes before 00:05 then passed unchanged after its due time.

## 7. NOT_RUN_BY_SCOPE

The following are explicitly `NOT_RUN`, never `PASS`:

- full repository pytest;
- full Legacy regression;
- full refoundation/platform suites outside the affected set;
- large PostgreSQL integration and isolation-level matrix;
- full concurrent identical/changed request campaign;
- full crash, deterministic failure, transient retry, stale-fence, unknown-
  commit, and recovery campaign;
- full replay/reconciliation qualification campaign;
- clean exact-OID guarded recreate qualification campaign;
- representative production-scale query-plan campaign;
- full-repository Ruff and mypy qualification gates;
- package build;
- remote CI;
- production/operations campaign;
- formal PIT, OOS, Locked-OOS, or Prospective campaign/promotion;
- Provider, Alpha, trading, broker, or Production qualification;
- Runtime/CLI cutover and Legacy deletion.

## 8. Remaining NO-GO and next step

EvidenceItem/EvidenceDependency, ResearchAssessment,
ResearchQualification, Model/ModelVersion, Calibration, Context, Signal,
Forecast, Opportunity, Thesis, Portfolio/Risk, Execution, Fill/Position,
TradeOutcome, Attribution, Runtime/CLI cutover, Legacy deletion, formal
PIT/OOS/Prospective promotion, Alpha optimization, and Production Qualification
remain absent and prohibited by this checkpoint. No placeholder, nullable future
FK, compatibility facade, dual write, or empty package/table was added for them.

The next recommended step is a separately authorized WP-11 engineering
qualification work package: run the complete clean PostgreSQL concurrency,
failure/recovery, exact-replay/recreate, representative-plan, full regression,
static, build, and remote-CI-when-available gates. Only that independent result
may create an immutable WP-11 Verification and decide the exit gate.
