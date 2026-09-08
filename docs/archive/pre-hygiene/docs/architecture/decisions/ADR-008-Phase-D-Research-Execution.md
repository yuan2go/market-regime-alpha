# ADR-008: Phase D Research Execution

> **Status:** HISTORICAL
> **Authority:** Accepted architecture decision; not implementation or evidence authority
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-12
> **Baseline:** `d27bc35585220eb20d0c3aabca7c93c8592ec294`
> **Implemented Through:** `5b0d2a8`
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `tests`

This record preserves the accepted Shared Decision Session Kernel, PostgreSQL
Historical Journal and Free-Data-First decision. Current code, schema and
reproducible evidence remain authoritative. The temporary implementation plan
was removed after the durable facts were folded into the canonical architecture,
status, capability and runbook documents.

## Implementation status

Migrations 058–064 implement the decision through one PostgreSQL authority:

- immutable Runtime Scope Policy/receipt and captured Operational Universe inputs;
- shared Decision Session contracts/kernel plus lease/fence Historical Journal;
- Portfolio Performance/Attribution and owner-resolved Shadow Observations;
- deterministic exploratory model training, walk-forward diagnostics and inference;
- ordered Formal Execution assessment that persists `BLOCKED` before any absent
  qualified predecessor can be consumed;
- bounded `continuous-research` build/report/replay/resume operator commands.

The PostgreSQL Historical owner reloads the exact Runtime Scope and existing
Continuous/Shadow/Strategy/Portfolio/Outcome/Performance owners. Decision reuse
requires the same trading date, symbol scope, calendar, decision policy and code
revision. Multiple free Operational Universe artifacts may overlap by symbol;
their provenance is retained and their eligibility facts are combined
conservatively. No Provider-specific dependency leaks into downstream Runtime.

## Approved outcome and boundaries

Phase D adds a replayable research loop around the existing business owners:

```text
Historical Data
-> Historical Session Journal
-> shared Decision Session Kernel
-> Candidate / Signal / Forecast
-> Strategy Shadow / Portfolio Shadow
-> Outcome
-> Performance / Attribution
-> research feedback
```

The implementation has six vertical slices:

1. multi-year Historical Runner;
2. Research Universe Policy to immutable Runtime Scope;
3. owner-resolved Strategy and Portfolio observation construction;
4. multi-period performance and attribution;
5. exploratory model training and deterministic research inference;
6. Formal OOS and calibration orchestration that remains fail-closed until its
   independent evidence floor exists.

It does not add Production trading, broker mutation, unattended orders, actual
Position mutation, a second Backtest engine, or a second persistent authority.
Actual Position remains derived only from an observed Fill.

## Shared Decision Session Kernel

One application kernel runs an ordered decision session. It invokes the current
Universe, State, Pool, Candidate, Signal, Forecast, Strategy and Portfolio
owners rather than creating historical variants of those facts. The kernel is
parameterized only by explicit execution context:

| Context input | Live Research / Shadow | Historical Research |
|---|---|---|
| Clock | trusted operation clock | frozen trading-session clock |
| Data authority | recorded current acquisition | immutable retrieved archive or qualified PIT owner |
| Execution mode | `RESEARCH` / `SHADOW` | `HISTORICAL_RESEARCH` |
| Evidence qualification | source-derived | source-derived; never promoted by the runner |

The kernel accepts owner references and typed policies. It does not accept
unproven raw provider payloads or hidden defaults. The existing Continuous
Runtime remains the sole all-day scheduler; the Historical Runner is a bounded
batch operator child using the same kernel.

## Free-data-first evidence tracks

Provider selection remains below Canonical facts. BaoStock, Tencent, AkShare
and other already-supported free public sources may supply complementary Fact
Kinds under the existing `Provider x Contract x Fact Kind` qualification model.
Every acquisition retains provider, contract, fact kind, retrieval time,
checksum and source-manifest provenance.

The tracks are non-interchangeable:

```text
Free Research Data
-> EXPLORATORY / PIT_INCOMPLETE / UNQUALIFIED
-> Historical Simulation / Model Research / Shadow

Qualified Formal Data
-> owner-verified Formal PIT
-> Formal OOS / Calibration
```

Cross-provider agreement improves engineering confidence but cannot create
historical availability, revision, archive or finality evidence that the
providers do not possess. An immutable free-data archive may only claim its
recorded retrieval time as earliest availability. Unsupported Formal Fact
Kinds remain `REJECTED`, `INCOMPLETE` or `BLOCKED`. XtQuant, PTrade, Wind,
iFinD and other paid providers are not Phase D dependencies or integrations.

## PostgreSQL Historical Journal

The Historical Runner writes an append-only PostgreSQL run definition and
CAS-linked per-session journal. A run freezes:

- inclusive date range and trading-calendar identity;
- Research Universe Policy and scope receipt identity;
- decision-time policy and target protocol;
- feature, factor, candidate, model, strategy, cost and portfolio policy
  identities;
- data-authority and evidence-qualification mode;
- code revision and configuration identity;
- deterministic run seed and canonical request hash.

Each session progresses through explicit stages:

```text
PLANNED -> SCOPE_RESOLVED -> DECISION_COMPUTED -> SHADOW_COMPUTED
        -> OUTCOMES_SETTLED -> PERFORMANCE_COMPUTED -> COMPLETE
```

`BLOCKED` and `FAILED` are recorded terminal attempts, not fabricated empty
successes. A lease/fencing token protects active work. Stage writes compare the
expected predecessor and canonical input hash, so resume is idempotent and
concurrent stale writers fail closed. Historical business sessions are applied
in calendar order. Parallel work is limited to immutable acquisition or
materialization shards sorted by canonical key; portfolio transitions remain
serial.

Replay reloads all referenced owner facts, validates hashes and semantic
identity, recomputes through the shared kernel and compares canonical output
hashes. It never overwrites the original journal.

The installed `continuous-research` executable gains bounded operator commands
equivalent to `historical-run`, `historical-resume`, `historical-report` and
`historical-replay`; no new executable or scheduler is introduced.

## Runtime Scope authority

A versioned Research Universe Policy selects one or more explicit sources:

- full A-share security master;
- historically effective index constituents;
- historically effective industry or theme membership;
- an immutable operator watchlist;
- an optional ETF scope.

The Runtime Scope Builder reloads the applicable PostgreSQL owner snapshots at
the session as-of time, then applies versioned listing/delisting, ST,
suspension, minimum-history, liquidity, tradability and optional membership
rules. Every symbol retains `INCLUDED`, `EXCLUDED` or `UNKNOWN`, its reason and
fact provenance. `UNKNOWN` is never runnable. A missing historical snapshot is
`PIT_INCOMPLETE`, not a substitution with today's membership.

The output is an immutable Runtime Scope receipt containing the ordered symbol
set, excluded and unknown decisions, policy/config/code identities, as-of time,
input owner references and content hash. Live and Historical paths consume the
same receipt contract. Operators select a policy; they do not maintain daily
`requested_symbols`.

## Owner-resolved observations

The Strategy Observation Builder reloads Candidate, Signal, Forecast, State,
price, ADV, status, price-limit/session, cost, liquidity/capacity, current
Shadow Position and available Outcome facts. The Portfolio Observation Builder
reloads the resulting Strategy intents plus the same market/risk facts and the
prior CAS-linked portfolio state.

Every value is represented by a typed provenance category:

- `OBSERVED_FACT` references an immutable fact owner;
- `CALIBRATED_PARAMETER` references a qualified or explicitly exploratory
  parameter artifact;
- `ENGINEERING_ASSUMPTION` references a frozen policy;
- `OPERATOR_INPUT` references an immutable override receipt.

The builders do not fill missing observed facts with zero or a default.
Required missing or stale facts yield typed `NOT_ESTIMABLE`/blocked
observations. Human approval remains a separate governed action. Overrides are
explicit, reasoned, separately persisted and included in replay identity.

The normal operator flow becomes:

```text
run-day -> settle-day -> strategy-day --auto
        -> portfolio-shadow-day --auto -> report-day
```

The existing explicit JSON commands remain backward-compatible and are marked
as operator-input paths rather than silently mixed with automatic facts.

## Multi-period performance and attribution

An immutable performance report owner aggregates the same Strategy and
Portfolio Shadow facts for an explicit portfolio/variant/model/universe/period
and benchmark policy. Metric results carry `ESTIMATED` or `NOT_ESTIMABLE`,
sample count, formula version, input lineage and reason.

The first complete metric contract includes equity curve, cumulative and
annualized return, annualized volatility, Sharpe, Sortino, Calmar, maximum
drawdown, hit rate, win/loss ratio, turnover, cost drag, exposure, capacity,
holding period, MFE/MAE, and monthly/yearly returns. Annualization uses the
frozen trading calendar and explicit risk-free/benchmark policy. Undefined
denominators, absent benchmark facts or insufficient samples are
`NOT_ESTIMABLE`.

Attribution must reconcile to portfolio P&L within a frozen tolerance. Symbol,
cost, entry/exit and rank dimensions are emitted only from owned facts. Regime,
theme, factor and signal attribution require exact effective-time references;
missing dimensions remain `NOT_ESTIMABLE` rather than an unattributed zero.
Comparison reports freeze both report identities and never change either
underlying result.

## Exploratory model and executor

The first model is an interpretable multi-head regularized linear family sized
for the current data volume:

- ridge regression heads for continuous return, MFE and MAE targets;
- regularized logistic-score heads for barrier targets;
- frozen robust preprocessing, missingness indicators and feature ordering;
- deterministic fitting and inference without a large ML framework.

Training consumes only owner-resolved Historical Sample, Panel, Factor,
Candidate and State facts whose availability time is no later than the decision
time. Feature extraction rejects future effective or availability times. A
training run freezes target family, train/validation partitions, purge/embargo,
walk-forward folds, feature/factor lineage, hyperparameter grid, model/config/
code identity and input dataset hashes.

Hyperparameters are selected only from train/validation folds. Locked OOS is
never used for tuning. The model artifact stores exact coefficients,
standardization statistics, missingness policy, feature order, target heads,
training diagnostics and immutable lineage. Insufficient samples, degenerate
targets or lineage mismatch yield `NOT_ESTIMABLE`.

Barrier outputs are raw logits/scores until a separately qualified calibration
artifact exists; they are never labeled probability. The installed executor is
static code that supports this exact artifact schema, reloads its Model
Governance lineage and deterministic parameters, and refuses unsupported or
substituted model/config/code identities.

The current admissible state is:

```text
RESEARCH_MODEL_AVAILABLE = true   # only after a real training artifact exists
FORMAL_MODEL_QUALIFIED = false
FORMAL_OOS = false
CALIBRATED = false
```

A research model may power Historical Research and Daily Shadow. It cannot
satisfy the Formal Forecast computation path while its required PIT and Model
Governance evidence is unqualified; that path returns `NOT_ESTIMABLE`.

## Formal OOS and calibration gate

The orchestration contract reloads and verifies, in order:

1. qualified Provider/Contract/Fact Kind receipts for every required fact;
2. a Formal PIT dataset and frozen Hypothesis Family;
3. train/validation/locked-OOS partitions with purge and embargo;
4. one-time raw OOS unlock for the full family;
5. family-level multiple-testing correction, costs, liquidity, capacity,
   regime/market-cap/theme slices, ablation and sensitivity evidence;
6. calibration evidence containing Brier, log loss, ECE, reliability and
   coverage for applicable targets.

The workflow records negative and inconclusive results. It cannot invoke the
raw OOS consumer or calibration fit when a predecessor is absent, unqualified
or semantically inconsistent. With current free-data evidence, execution must
persist a blocked assessment and leave all Formal booleans false.

## Transaction, recovery and security rules

- Every new writer is reached through `RepositoryFactory` and PostgreSQL.
- Schema migrations are forward-only, checksum-verified and backward-compatible
  with current rows and commands.
- Business fact commits and journal advancement occur in one transaction when
  they share an owner; otherwise the journal stores the committed owner receipt
  before the next stage can begin.
- Immutable artifacts are content-addressed. Reusing an id with different
  content is corruption and fails closed.
- Lease acquisition, expiry and fencing are auditable; resume never assumes a
  previous attempt succeeded.
- Operator mutations require the existing RBAC/approval boundary where
  applicable. Historical execution grants no Production role or admission.
- Logs and reports expose stable ids, stages and rejection reasons, never
  credentials or raw secrets.

## Required validation

Implementation is complete only with negative-path and integration evidence
covering:

- multi-session and representative multi-year journal execution;
- interruption/resume, duplicate requests, fencing and deterministic replay;
- historical universe correctness including delisted, ST, suspended and
  unknown facts;
- automatic Strategy/Portfolio observation provenance and missing-fact blocks;
- T+1 settlement, price limits, lot size, costs, slippage, liquidity and
  capacity;
- train/validation/OOS isolation, future-feature rejection and no OOS reuse;
- model lineage substitution, unsupported artifacts and deterministic
  inference;
- family-level OOS and calibration leakage blocks;
- metric edge cases and full attribution reconciliation;
- migration upgrade/schema verification, corruption and compatibility tests.

No test, fixture, replay or local database result may be promoted into Provider,
Formal PIT, OOS Alpha, calibration, trading or Production authority.
