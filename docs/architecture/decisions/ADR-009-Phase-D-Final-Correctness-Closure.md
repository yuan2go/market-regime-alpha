# ADR-009: Phase D Final Correctness Closure

> **Status:** CURRENT_ARCHITECTURE
> **Decision:** Typed Lineage Spine with forward migration 067
> **Approved By:** Repository owner, 2026-08-12
> **Base:** `origin/main@383f2430d6879257dae640978a599a1e56f45558`
> **Initial Migration Head:** `066`

## Objective

Close the correctness gaps in the merged Phase D Alpha Proof Foundation without
creating a second Authority, Runtime, Receipt, or qualification control plane.
Phase D may be marked `PHASE_D_ENGINEERING_COMPLETE` only when exact owner
identity, canonical time, deterministic replay, experiment isolation, metric
semantics, and truthful runtime boundaries are executable and fully validated.

This remains engineering closure. It does not establish `ALPHA_PROVEN`,
`FORMAL_PIT_ESTABLISHED`, `FORMAL_OOS_ESTABLISHED`, `STRATEGY_PROVEN`, or
`PRODUCTION_READY`.

## Gate 0: Restore a Verifiable Main Baseline

The current main branch does not collect the full test suite because Phase C/D
reconciliation removed `load_formal_protocol_pre_oos_owner` while retaining its
import and call sites. Restore the current fail-before-read contract from the
merged Phase C implementation, prove normal collection, and commit that repair
independently before changing Phase D lineage.

No later Phase D change may be used to conceal or redefine this baseline defect.

## Domain Invariants

### Exact owner identity

Every authoritative reference is a pair of `artifact_id` and `content_hash`.
Repositories reload the owning row and compare both values. Where the consumer
depends on parameter, policy, target, feature, code, or configuration identity,
the repository also compares that semantic identity. Foreign-key existence is
necessary but not sufficient.

Owner resolution remains bounded and owner-specific. There is no generic
reference registry and no caller-supplied reference that can manufacture
Authority.

### Canonical time

For each derived artifact:

```text
derived_time >= max(required_input_available_or_recorded_times)
```

The comparison is implemented at the real writer boundary for Model,
Observation, Strategy, Portfolio, Outcome, and Performance. It does not create
a general time-governance framework.

Decision date, Outcome research date, Outcome next-session date, Target/Horizon
identity, Strategy session date, Portfolio observation date, and Performance
state sequence must form one canonical trading-session chain. A T+1 observation
cannot be materialized as T-day Portfolio state.

### Typed lineage spine

The spine reuses existing PostgreSQL owners:

```text
Experiment Definition
  -> Research Decision / Settled Panel / Candidate Enrichment
  -> Target Protocol / Outcome
  -> Observation Receipt + value/source bindings
  -> Strategy Session
  -> Portfolio + Portfolio State
  -> Performance Report
```

Each arrow is represented by full immutable references and verified by owner
reload. Automatic Strategy and Portfolio operations receive an explicit typed
context; they never select an owner because it is the only object on a trading
date.

The Observation Receipt remains the existing receipt owner introduced by
migration 063. Its receipt, Target/Outcome, availability, and resolved source
references become durable Strategy/Portfolio lineage rather than being returned
only by the CLI.

### Historical isolation

A Historical Research session carries explicit experiment, configuration,
target, Strategy policy, Portfolio policy, and root owner references. Every
stage resolves only the exact predecessor chain. Date is a temporal predicate,
not owner identity. Ambiguous, missing, legacy-unbound, or hash-mismatched
lineage fails closed.

Strategy, Portfolio, Outcome, and Performance records written before migration
067 remain readable by their legacy APIs. They are not backfilled, inferred, or
silently upgraded into the new lineage contract.

## Model Training Owner Resolution

Formal PostgreSQL-backed training accepts frozen owner references, not a
caller-authored matrix. The repository reloads the supported feature/panel,
target/outcome, dataset or sample owners; checks full hashes, feature and target
identity, availability, PIT/OOS status where applicable; and builds the training
matrix from owner values.

Caller-provided samples remain usable only through an explicitly exploratory
kernel. Such results retain caller-payload provenance and cannot be published as
owner-derived PostgreSQL training evidence.

Inference reloads the exact model artifact and rejects a correct ID paired with
an incorrect hash. Training and inference times cannot precede any required
input availability time.

## Migration 067

Migration 067 is a forward-only correction. Migrations 060-066 are immutable.
It will:

- replace policy-only Portfolio uniqueness with lineage-aware identity for new
  records;
- add only the durable lineage relationships consumed by Strategy/Portfolio
  replay and Historical Research;
- store full owner hashes for relationships previously represented by ID only;
- add foreign keys, checks, uniqueness, and composite indexes matching the
  exact-lineage queries;
- preserve legacy rows without assigning invented hashes or qualification.

Constraints are additive and idempotent under the repository migration runner.
No production-history rewrite is performed.

## Runtime Scope Gate

Runtime eligibility uses a conservative gate:

```text
explicit provider exclusion or included=false or non-listed status
  > suspension or ST exclusion
  > insufficient history
  > insufficient liquidity
  > included
```

Unknown required inclusion/listing state is not converted to included. Combining
sources can only preserve or tighten an exclusion; it cannot re-admit a symbol
already excluded by the provider or listing owner.

## Metrics Semantics

Each Ablation observation carries a canonical trading-session identity.
Observations are normalized to canonical chronological order before any
path-dependent calculation.

- IC and RankIC operate on each canonical cross-section.
- TopK, Spread, and Hit Rate use the current variant's actual ranking and
  selection.
- Turnover compares each variant's own selected weights with that same variant's
  previous canonical session holdings.
- Gross Return, Cost, Net Return, NAV, and Drawdown use the same ordered session
  path and are invariant to input insertion order.
- Incremental Lift compares aligned canonical sessions and cannot borrow another
  variant's holdings.

Adversarial tests use opposite rankings, shuffled observations, and divergent
variant histories with independently calculated expected values.

## Strategy Economics

Strategy Economics models three distinct evidence sets:

- Entry observation at T, including side-aware fillability;
- Holding path after Entry, including suspensions, limit states, missing bars,
  barrier observations, and unobservable intrabar order;
- Exit observation at the intended exit session, including side-aware
  fillability and costs.

T+1 conditions cannot retroactively invalidate an already valid T Entry. A buy
is not assumed fillable through a limit-up condition and a sell is not assumed
fillable through a limit-down condition. Suspension or missing execution
evidence fails the affected Entry or Exit closed. If both barriers touch in one
5-minute bar, the outcome remains `AMBIGUOUS_NOT_OBSERVABLE`; no intrabar path is
invented.

## Runtime Boundary

Historical Research, owner-resolved Observation, Performance, and Model
execution keep their bounded operator/CLI composition. Strategy Economics,
Portfolio Risk Research, Attribution/Feedback, and Ablation remain exploratory
kernels unless current code exposes a natural authoritative consumer. Phase D
completion will not force them into `CONTINUOUS_RESEARCH` or claim production
integration.

## Verification and Delivery

Validation is performed on the final branch HEAD with an isolated PostgreSQL 16
database. It includes full pytest, fresh migration, upgrade and idempotency,
concurrency, replay/recovery, CLI integration, Ruff, mypy, build, documentation
links, and `git diff --check`. Every command is reported as `PASS`, `FAIL`,
`NOT_RUN`, or `BLOCKED`. GitHub Actions is reported as `CI_NOT_RUN` unless it
actually runs.

The branch is pushed and a Draft PR is opened. All newly reported P1/P2
correctness blockers are resolved before any recommendation to merge. The agent
does not merge the PR.
