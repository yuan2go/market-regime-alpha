# Phase C Formal Research Runtime Final Closure

**Status:** APPROVED DESIGN

**Baseline:** `origin/main@80bd8e85daf6115bbf147fcd3bfbe60ce781e02c`

**Authority boundary:** PostgreSQL owns durable commands, identities, evidence,
qualification and replay. Formal research remains unable to authorize Production
or Broker mutation.

## Problem statement

The current Formal Protocol registry resolves typed PostgreSQL owners, but the
Formal Forecast write path still accepts caller-computed estimates. Migration
056 also treats one subject/session/label-end tuple as one Target consumption,
which blocks a pre-registered multi-target family while still failing to model
the raw market path explicitly. Finally, Formal Evaluation corrects p-values
inside one Target invocation rather than across the complete frozen family.

## Design decisions

### Owner-controlled Formal Forecast computation

`FormalForecastComputationRequest` contains only a Formal Protocol id, Formal
PIT Evidence id, symbol/scope and an idempotency key. It has no estimate fields
or caller timestamp. `PostgresFormalForecastComputationAuthority` executes one
serializable transaction that:

1. reloads the Formal Protocol and every frozen owner resolution;
2. reloads and replays the exact Formal PIT request, snapshot, selected Fact
   revisions and artifact resolutions;
3. verifies DecisionTime, symbol, Dataset, Universe, Feature, Model Definition,
   Model Version Lineage, Configuration, Factor, Threshold, Target Protocol,
   implementation reference, code revision and code hash;
4. selects an installed executor by an exact, versioned executor identity;
5. computes estimates from owner-resolved inputs only;
6. assigns `materialized_at` from PostgreSQL `clock_timestamp()`;
7. persists an immutable request/receipt/input binding and the resulting
   OutcomeTarget-bound forecast; and
8. reads the artifact back and deterministically replays it.

The executor boundary is deliberately narrow: an executor declares its stable
identity and supported configuration schema, and receives a fully resolved,
immutable computation context. There is no dynamic import or generic plugin
registry. Unsupported implementations and insufficient evidence produce a
complete `NOT_ESTIMABLE` target set with explicit reason codes. They never
fall back to caller values.

Legacy `record_forecast` remains only as an explicitly exploratory compatibility
writer. Migration 057 labels old/caller-submitted rows
`EXPLORATORY_CALLER_SUBMITTED`. Formal Evaluation requires a matching immutable
computation receipt and therefore cannot consume them.

### Frozen Hypothesis Family

Recording a Formal Protocol materializes one content-addressed
`FrozenHypothesisFamily` from the Formal Protocol, Formal Evaluation Protocol,
the exact sorted Target id/hash set, folds/windows, sensitivities and
multiple-testing method. The family is immutable and is recorded before any
Locked OOS read. A later Target revision or addition necessarily creates a
different family and cannot join an already unlocked raw path.

### Two-level Locked OOS authority

Migration 057 adds two append-only authorities without changing migrations 046
or 056:

- `locked_oos_raw_evidence_unlock` identifies the underlying market path by
  market-qualified subject, decision session, outcome session and
  `LOCKED_OOS`. It intentionally excludes Model, Forecast, Protocol, Dataset,
  Target and Label revision identities. The first family to unlock it is
  permanent.
- `locked_oos_target_observation_consumption` records one target-specific
  observation underneath that raw unlock. Its uniqueness includes the frozen
  family and exact Target, permitting every pre-registered Target once while
  rejecting a new Forecast, Label revision or observation set for the same
  Target.

An advisory scope lock on the raw identity and database unique constraints make
parallel unlock deterministic. Exact command replay is idempotent only when the
stored payload, family, Target, Forecast, Label and observation set are equal.

The migration-056 ledger remains immutable historical evidence and is no longer
the writer for new family-level Formal Evaluation.

### Family-level Formal Evaluation

The formal writer accepts bindings grouped by every Target in the frozen family
in one command. It owner-reloads every Forecast, Label, Panel row and PIT fact,
then computes the current metrics per Target/fold/slice/sensitivity. Raw
p-values from the complete Cartesian hypothesis family are adjusted together
with the frozen Bonferroni or Benjamini-Hochberg method. The stored metric key
includes Target identity, fold, slice, sensitivity and metric name.

Purging, embargo, walk-forward window membership and trading-date moving-block
bootstrap remain enforced. Missing cross-sections or observations remain
`NOT_ESTIMABLE` and are preserved. The legacy single-Target result remains
replayable engineering evidence, but the Formal OOS qualification owner accepts
only a family-level result with complete frozen-family coverage and matching
consumption receipts.

### Operator workflow

No executable is added. Existing CLIs gain typed owner-specific subcommands:

- `research-shadow`: Target Protocol freeze/read-back;
- `pit-authority`: Trading Calendar and Forecast Configuration canonical
  snapshot/replay;
- `model-governance`: existing Model registration and lineage commands remain
  the model owner;
- `continuous-research`: Evaluation, Feature, Factor, Threshold, Formal OOS,
  Calibration, Cost, Strategy, Entry/Holding/Exit and Formal Protocol freeze;
  Formal Forecast compute/replay; family evaluation/replay.

The continuous formal-operator commands use the existing PostgreSQL RBAC and
audit boundary. A Phase-C-specific command ledger binds idempotency key to the
exact command hash and canonical result. Owner-specific writers create lock and
materialization times from the PostgreSQL clock, perform read-back verification
and never expose a generic artifact registrar.

### Evidence and production ceiling

Current BaoStock/Tencent Provider scopes remain `REJECTED`. Consequently no
current real Formal PIT, Historical, Locked OOS, Calibration or Entry/Holding/
Exit qualification is expected. C7 remains `ACCUMULATING`; C8 and C9 remain
`BLOCKED`. Engineering tests may prove behavior in isolated schemas but cannot
create provider, Alpha, prospective, production or broker authority.

## Failure and recovery semantics

Identity conflicts, owner drift, future PIT inputs, late owner recording,
incomplete family membership, raw-path reuse and idempotency conflicts abort the
transaction. Unsupported executors and genuinely insufficient qualified inputs
commit a replayable `NOT_ESTIMABLE` Forecast rather than inventing values.
Corrupt receipts fail replay. All new evidence tables reject update/delete.

## Public verification seams

The test-first public seams are:

1. owner-specific CLI freeze/compute/replay commands;
2. Formal Forecast compute and deterministic replay authority;
3. family-level Formal Evaluation and two-level Locked OOS consumption;
4. PostgreSQL owner read-back, migration and schema verification.
