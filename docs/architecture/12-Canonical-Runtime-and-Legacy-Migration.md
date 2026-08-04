# Canonical Runtime and Legacy Model Migration

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Current implementation architecture for canonical lifecycle orchestration and isolated Legacy model migration
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** 06-Legacy-Migration.md, 10-Production-Decision-Lifecycle.md, 11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md
> **Code Evidence:** `src/market_regime_alpha/application/canonical_lifecycle/**`; `src/market_regime_alpha/features/model_contracts.py`; `src/market_regime_alpha/research/model_contracts.py`; `src/market_regime_alpha/signals/model_contracts.py`; `src/market_regime_alpha/decision/model_contracts.py`; `src/market_regime_alpha/migration/**`; `tests/application/canonical_lifecycle/**`; `tests/migration/**`; `tests/architecture/test_legacy_import_boundary.py`
> **Verification Boundary:** The implementation described here is present on the canonical-runtime development branch. Final whole-branch pytest, Ruff, mypy and package-build verification remains pending the delivery checkpoint.

## 1. Purpose and authority ceiling

`CanonicalDecisionLifecycleRunner` is the single backend orchestration spine
for the existing research and human-in-the-loop decision capabilities. It owns
ordered progress, retry/recovery and cross-domain references. It does not own
or duplicate Market, Theme, Capital, Candidate, Signal, Forecast, Decision,
Portfolio, Risk, ManualTrade, Fill, Position, Holding, Exit or Review rules.

The Daily Runtime Journal remains authoritative for acquisition and Daily
package construction. The Lifecycle Runtime Journal begins from verified H6
evidence or an explicitly scoped H4 risk-reduction continuation:

```text
Daily Runtime Journal
  → immutable Daily/Supplemental/SourceManifest references
  → verified H6 Composite Operational Manifest
  → Lifecycle Runtime Journal
  → existing domain Readers, Repositories and Application Services
```

The following facts are invariant:

```text
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
production_ready = false
```

The Runner is a local, recoverable orchestration mechanism. It is not a
distributed scheduler, Broker gateway, production operator console, model
validation result or permission to trade.

## 2. Actual registered lifecycle chain

The Runner requires exactly one handler for each stage and rejects missing,
extra or reordered registrations. Stages progress as one contiguous slice;
only `RISK_REDUCTION_CONTINUATION` may start later, by recording the preceding
stages as `SKIPPED_NOT_APPLICABLE`.

| Stage | Current handler and actual call boundary | Current observable result |
|---|---|---|
| `VERIFY_COMPOSITE_EVIDENCE` | `VerifiedCompositeEvidenceStageHandler` calls `load_verified_composite_operational_manifest()` and checks the exact Daily, Supplemental and two SourceManifest ID/hash bindings | Completes only for a verified H6 manifest |
| `PLATFORM_RESEARCH` | `PlatformResearchStageHandler` restores the three source packages, calls `OperationalResearchRunner.run()`, which delegates existing Platform V2 computation/publication, and verifies the published Artifact | Produces a verified `PLATFORM_RESEARCH_ARTIFACT` reference |
| `SIGNAL` | `SignalStageHandler` calls the existing `run_signal_model()`, `publish_signal_run()` and Signal Reader | H6 does not yet supply the five Signal factors, so selected rows are explicit `DATA_INSUFFICIENT`; an empty CandidateSet remains an explicit empty result |
| `PATH_FORECAST` | `PathForecastStageHandler` calls existing `build_path_forecast()` for each Signal snapshot, publishes and reloads each Artifact | Uses no invented samples; current forecasts are explicit `DATA_INSUFFICIENT` or the output set is empty |
| `ENTRY_ASSESSMENT` | `EntryAssessmentStageHandler` verifies exact Signal/Forecast lineage and the manifest authority ceiling | Records `BLOCKED` / `BLOCKED_BY_MODEL_VALIDATION`; no Opportunity is manufactured |
| `OPPORTUNITY` | `OpportunityStageHandler` reads an exact existing `TradingOpportunity` through `DecisionLifecycleRepository` | Without persisted validity, actor and reason authority, waits instead of creating one |
| `THESIS` | `ThesisStageHandler` reads an exact approved, unexpired `TradingThesis` | Without durable human approval, waits instead of approving one |
| `PORTFOLIO_RISK` | `PortfolioRiskStageHandler` reloads existing complete-account Portfolio and Risk decisions and verifies Thesis/account lineage | Without Fill-derived complete-account inputs, waits; a non-approved Risk decision does not advance |
| `RISK_REDUCTION` | `RiskReductionStageHandler` reloads H4, PositionBook, Directive, H5, H6, calendar, session status, execution observation and confirmation policy authorities | A current permitted H4 decision completes the stage but sets `WAITING_FOR_MANUAL_CONFIRMATION`; it creates nothing |
| `MANUAL_CONFIRMATION` | `ManualConfirmationStageHandler` calls the read-only `get_confirmed_risk_reduction()` query | Observes an externally completed H4.5 confirmation or remains `WAITING_FOR_MANUAL_CONFIRMATION` |
| `MANUAL_TRADE` | `ManualTradeStageHandler` reloads the ManualTrade already created atomically by H4.5 and verifies its reducing route | Records the existing intent and stops at `WAITING_FOR_FILL` |
| `FILL_POSITION` | `FillPositionStageHandler` reads the append-only Fill ledger and rebuilds the Fill-derived Position with calendar/session evidence | No Fill means `WAITING_FOR_FILL`; an unsellable open position means `WAITING_FOR_T1`; otherwise reports `POSITION_OPEN` or `READY_FOR_EXIT_REVIEW` |
| `THESIS_HEALTH` | `ThesisHealthStageHandler` loads and verifies the command-bound H5 observation and its as-of/latest semantics | Can reach `READY_FOR_HOLDING_ASSESSMENT` without synthesizing a new observation |
| `HOLDING_ASSESSMENT` | `HoldingAssessmentStageHandler` is a fail-closed controlled-Reader boundary | Blocks because durable H7 Holding authority is not implemented |
| `EXIT_ASSESSMENT` | `ExitAssessmentStageHandler` is a fail-closed controlled-Reader boundary | Blocks because durable H7 Exit authority is not implemented |
| `OUTCOME_REVIEW` | `OutcomeReviewStageHandler` is a fail-closed controlled-Reader boundary | Blocks because a durable complete-trade Review Reader is not implemented |

Only `OUTCOME_REVIEW` may transition a run to `COMPLETED`, and that handler
must return `COMPLETED` before the Runner will accept such a result. Current
authority gaps therefore cannot be relabelled as success.

## 3. Command, input and configuration identity

`CanonicalLifecycleCommand` binds:

- `run_type`, `decision_date`, whole-second UTC `as_of_time` and
  `idempotency_key`;
- an optional content-addressed lifecycle input manifest and controlled local
  locator;
- sorted typed object references containing object type, ID, content hash,
  Reader kind, optional controlled local locator and availability time;
- typed configuration references containing kind, ID, version, hash and
  controlled local locator;
- model ID/version references;
- presentation controls such as `stop_after_stage` and output directory,
  which do not change persisted business evidence.

The semantic command is canonicalized and hashed. The deterministic `run_id`
binds the idempotency key and command hash. Reusing one idempotency key with a
different command hash is rejected. A resume reconstructs the stored command;
it cannot change the decision date, as-of time, evidence, configuration or
model versions.

`RuntimeConfigurationReader` restores only the expected typed configuration
kind and verifies its exact ID, version and content hash. Configuration files
therefore remain restart inputs rather than ambient process state.

### 3.1 CLI and replay surface

The unified module entry point is:

```text
python -m market_regime_alpha.cli.run_canonical_lifecycle
```

A new research run accepts `--input-manifest`, `--decision-date`, `--as-of`,
`--idempotency-key`, `--stop-after-stage`, `--output-dir`, the journal
`--database` and an optional explicitly bound `--authority-database`. Resume
accepts `--resume-run-id` and reloads the stored command, manifest,
configuration locators, output directory and authority database binding rather
than accepting replacement evidence.

The same CLI supports `--replay-run-id`; the dedicated equivalent is:

```text
python -m market_regime_alpha.cli.replay_canonical_lifecycle \
  --database ... --run-id ...
```

Replay invokes neither the Runner nor execution services. It reads the journal
twice, requires a stable report hash, and reports pure/Reader-verifiable
subjects as `STABLE`, repository-only unavailable subjects as
`NOT_COMPARABLE`, or tamper/failure as `FAILED`.

The unified CLI emits one structured JSON object containing run/status/stage,
receipt, blocker/failure and safety fields. Stable exit codes distinguish
success (`0`), runtime failure (`1`), command validation (`2`), idempotency
conflict (`3`), journal failure (`4`), replay not-comparable (`5`) and replay
failure (`6`). It separates `manual_trade_observed` from
`MANUAL_TRADE_CREATED=false`; observing an existing H4.5 trade is not creation
by the Runner.

The standalone CLI currently starts `CANONICAL_DECISION_LIFECYCLE`. The
programmatic Runner and journal also support `RISK_REDUCTION_CONTINUATION`, but
the CLI does not infer or fabricate that continuation from incomplete inputs.

## 4. Runtime Journal and migration 011

Migration `011_canonical_lifecycle_runtime` adds five tables without modifying
migrations 002–010.

| Table | Responsibility | Key constraints |
|---|---|---|
| `lifecycle_runs` | Aggregate projection plus immutable original command JSON | PK `run_id`; unique `idempotency_key`; checked SHA-256 command/input hashes; optimistic `version`; monotonic `claim_token` |
| `lifecycle_stages` | Exactly one current projection for every one of the 16 stages | PK `(run_id, stage_name)`; non-negative attempt count; terminal projection trigger |
| `lifecycle_attempts` | One invocation record per stage attempt | Unique `(run_id, stage_name, attempt_number)` and `(attempt_id, run_id, stage_name)`; a `RUNNING` row may be settled once; terminal rows are immutable |
| `lifecycle_stage_receipts` | Immutable content-addressed stage settlement evidence | Unique `(run_id, stage_name, receipt_hash)` and `(receipt_id, run_id, stage_name)`; update/delete prohibited |
| `lifecycle_events` | Gap-free ordered state/event history with canonical payload hash | Unique `(run_id, sequence_number)`; foreign keys to run/stage/attempt/receipt; update/delete prohibited |

The canonical JSON projections retain the complete domain record even where a
field is not duplicated as a relational query column:

- `LifecycleRun` carries run/idempotency/command identity, type, decision/as-of
  time, current and completed stages, manifest identity/hash,
  configuration/model references and manifest hashes, retry state,
  failure/blocker reason, timestamps, version and claim token.
- `LifecycleStage` carries status, attempt count, exact input/output references,
  start/completion timestamps, failure/blocker reason and version.
- `LifecycleAttempt` carries attempt identity/number, claim token, timestamps,
  result and typed exception details.
- `StageReceipt` binds sorted input/output hashes, model versions,
  configuration hashes, reason codes, stage result, creation time and its own
  content identity/hash.
- `LifecycleEvent` binds a monotonic sequence, state transition, optional
  stage/attempt/receipt identities, reason codes, claim token and canonical
  payload hash.

The schema also defines query indexes for run status/date, stage status,
attempt history, receipt history and event history. Repository startup checks
the exact tables, columns, indexes, foreign keys, constraints and triggers; a
spoofed migration marker with a weaker schema is rejected.

### 4.1 Transaction boundaries

All journal mutations use SQLite `BEGIN IMMEDIATE`:

- run creation writes the immutable command, the run projection, all 16
  `PENDING` stage projections and creation history atomically;
- stage start writes the attempt, stage/run projections and events atomically;
- stage settlement writes the attempt completion, immutable receipt, stage/run
  projections and events atomically;
- stage failure writes the exception-bearing attempt, failed projections and
  events atomically;
- resume records `FAILED → RETRYING → RUNNING` and increments the claim token
  atomically.

Domain services and Artifact publication are intentionally outside the journal
transaction because SQLite cannot make a file Artifact or another domain
repository transaction atomic. Each stage therefore calls `recover()` before
`execute()`: if the deterministic domain output already exists, the handler
reloads and validates it and only repairs the missing receipt. A crash after a
durable receipt cannot re-execute that completed stage.

### 4.2 Idempotency, concurrency and history

- Ordinary duplicate `run(command)` is an observation of the existing run,
  not an implicit retry.
- A failed or waiting run advances only through an explicit resume/claim.
- Run and stage `version` fields provide compare-and-set checks.
- Each claim increments `claim_token`; attempts and settlements carrying an
  older token are rejected or explicitly settled as superseded.
- This fencing-shaped token prepares for later lease ownership, but no lease,
  distributed scheduler or multi-instance coordination is implemented.
- `COMPLETED`, `BLOCKED` and `SKIPPED_NOT_APPLICABLE` stages cannot be
  overwritten.
- Identical semantic stage receipts are reused/verified, not replaced.
- `history()` returns the run, all 16 stages, ordered attempts, immutable
  receipts, gap-free events and original canonical event payload JSON.

## 5. Lifecycle state machines

### 5.1 Run states and legal transitions

| Current state | Legal next states |
|---|---|
| `CREATED` | `RUNNING`, `FAILED` |
| `RUNNING` | `WAITING_FOR_ENTRY_CONFIRMATION`, `BLOCKED_BY_MODEL_VALIDATION`, `WAITING_FOR_MANUAL_CONFIRMATION`, `WAITING_FOR_FILL`, `POSITION_OPEN`, `WAITING_FOR_T1`, `READY_FOR_HOLDING_ASSESSMENT`, `READY_FOR_EXIT_REVIEW`, `COMPLETED`, `FAILED` |
| `RETRYING` | `RUNNING`, `FAILED` |
| `WAITING_FOR_ENTRY_CONFIRMATION` | `RUNNING`, `FAILED` |
| `BLOCKED_BY_MODEL_VALIDATION` | none; a changed validation authority requires a new run |
| `WAITING_FOR_MANUAL_CONFIRMATION` | `RUNNING`, `FAILED` |
| `WAITING_FOR_FILL` | `RUNNING`, `FAILED` |
| `POSITION_OPEN` | `RUNNING`, `WAITING_FOR_T1`, `READY_FOR_HOLDING_ASSESSMENT`, `READY_FOR_EXIT_REVIEW`, `FAILED` |
| `WAITING_FOR_T1` | `RUNNING`, `FAILED` |
| `READY_FOR_HOLDING_ASSESSMENT` | `RUNNING`, `READY_FOR_EXIT_REVIEW`, `FAILED` |
| `READY_FOR_EXIT_REVIEW` | `RUNNING`, `COMPLETED`, `FAILED` |
| `COMPLETED` | none |
| `FAILED` | `RETRYING` |

### 5.2 Stage states and legal transitions

| Current state | Legal next states |
|---|---|
| `PENDING` | `RUNNING` |
| `RUNNING` | `COMPLETED`, `WAITING`, `BLOCKED`, `FAILED`, `SKIPPED_NOT_APPLICABLE` |
| `WAITING` | `RUNNING` |
| `FAILED` | `RUNNING` |
| `COMPLETED` | none |
| `BLOCKED` | none |
| `SKIPPED_NOT_APPLICABLE` | none |

`WAITING` records an external or operator-controlled prerequisite.
`BLOCKED` records a current validation/authority ceiling. `FAILED` records an
unexpected exception and preserves its type/message for retry diagnostics.

## 6. H4.5 manual-only safety boundary

The execution route remains:

```text
RiskReducingDecision
  → explicit H4.5 human confirmation command
  → ManualTradeRecord V3 SELL intent
  → separately human-recorded Fill, if one later exists
```

The canonical Runner never invokes the H4.5 confirmation command. Its
`RISK_REDUCTION`, `MANUAL_CONFIRMATION`, `MANUAL_TRADE` and `FILL_POSITION`
handlers are read-only. The separate H4.5 Application Service remains the only
authority that may create the reducing ManualTrade and, in one transaction,
rechecks the permitted/current/non-expired/non-superseded H4 decision, current
Position and PositionBook, Thesis/Opportunity/symbol/direction/quantity
lineage, maximum reducible and T+1 sellable quantity, evidence hashes and
idempotency.

The bridge cannot:

- create a `BrokerOrder`;
- call QMT, PTrade or another Broker;
- synthesize or record a Fill;
- mutate a Position merely because an intent exists;
- bypass the separate human confirmation input.

Its CLI/result boundary explicitly reports
`MANUAL_CONFIRMATION_REQUIRED`, `NO_ORDER_CREATED`, `BROKER_NOT_INVOKED` and
`NO_FILL_CREATED` as applicable. The actor remains audit text rather than an
authenticated principal, so operator authentication is still a blocker.

## 7. Legacy dependency and adapter boundary

The allowed dependency direction is:

```text
canonical core ─X→ market_regime_alpha.dividend_t
migration.legacy adapters → market_regime_alpha.dividend_t
migration.comparison → canonical model + isolated Legacy adapter
```

`tests/architecture/test_legacy_import_boundary.py` scans Python imports and
rejects a direct canonical dependency on `market_regime_alpha.dividend_t`.
Only the Legacy package itself, `legacy`, `migration.legacy`, and the explicitly
Legacy FastAPI compatibility module may import it directly.

A Legacy adapter may normalize standard inputs, invoke a narrow Legacy helper,
normalize the result, expose exceptions and limitations, and provide a
comparison baseline. It receives no new Repository, Broker, Signal, Trade,
Fill or Position authority. It cannot convert a static fallback into market
evidence or hide data unavailability.

| Legacy asset | Migration treatment |
|---|---|
| Pure OHLCV transforms such as moving averages, MACD components and force-ratio observables | Extract incrementally behind `FeatureComputer`, with exact normalized data and differential evidence |
| Volume structure, Chan structure/divergence and Tuishen volume-price logic | Refactor into separately named observables; separate feature calculation from interpretation and from any Decision |
| Buy/sell point, position-sizing, risk and COSCO combined strategy code | Characterize, then split across Signal, Decision, Portfolio/Risk and lifecycle contracts; never copy the God Object |
| Static data fallbacks, direct web-to-strategy mutation and Legacy broker/order paths | Do not promote; isolate and retire only after a verified canonical replacement exists |

## 8. Role-specific migration contracts

There is deliberately no universal `Model` base class.

- `FeatureComputer.compute()` accepts a normalized immutable dataset,
  `as_of_time`, availability state and content-addressed configuration. It is
  side-effect-free and produces an immutable `FeatureArtifact` with explicit
  missingness, input/time/configuration lineage and no trading authority.
- `ResearchModel.run()` is scoped to Market Regime, Theme Rotation, Capital
  Evolution or Candidate Discovery inference and returns model/config/input
  identity, state, optional Decimal score, reason codes, limitations and
  validation status.
- `SignalModel.run()` can express only typed meanings such as
  `ENTRY_CONFIRMATION`, `TREND_CONTINUATION`, `REVERSAL_WARNING`,
  `SELL_PRESSURE`, `OVERHEAT` and `VOLUME_CONFIRMATION`; it cannot express an
  order.
- `DecisionModel.decide()` is capped at `REJECT`, `WAIT`,
  `READY_FOR_MANUAL_CONFIRMATION`, `REDUCE` and `EXIT`; it cannot grant
  automatic execution.

All score fields use finite `Decimal` where the new contracts own the type.
Scores remain scores unless a separate calibration contract establishes a
probability.

## 9. Differential verification and moving-average example

`DifferentialTestHarness` runs one `NormalizedFeatureDataset` through an
isolated Legacy adapter and a canonical `FeatureComputer`. The content-addressed
`ModelComparisonReport` stores both normalized outputs, field/numeric/semantic
differences, the comparison policy and one of:

```text
EXACT_MATCH
NUMERIC_TOLERANCE
EXPECTED_SEMANTIC_CHANGE
LEGACY_DEFECT_FIXED
CANONICAL_REGRESSION
INSUFFICIENT_DATA
NOT_COMPARABLE
```

Tolerance is field-specific; wildcard tolerance is rejected. A
`LEGACY_DEFECT_FIXED` result needs an explicit defect ID and an independently
expected canonical value. A `CANONICAL_REGRESSION` needs an independent
canonical invariant. Unknown differences remain `NOT_COMPARABLE`; the harness
does not force the canonical implementation to reproduce a Legacy defect.

The first vertical slice is `technical.simple-moving-average`:

1. `NormalizedCloseBar` carries symbol, market date, positive `Decimal` close
   and explicit availability time.
2. `SimpleMovingAverageComputer` validates one symbol, strict date order,
   uniqueness and as-of availability, computes with a fixed Decimal context,
   and records `WINDOW_NOT_READY` rather than inventing warm-up values.
3. The immutable Feature Artifact is published through an exact-file Reader
   and can be recomputed by `replay_feature_artifact()`; semantic but false
   stored output is rejected.
4. `LegacyMovingAverageAdapter` converts the exact normalized data to the
   existing pandas helper, labels float/lossy behavior and exposes exceptions.
5. The differential report is itself publishable, readable and replayable.

This is one simple moving-average example, not completion of the broader
Moving Average migration family and not a buy/sell model.

## 10. Manual handoffs reduced, not eliminated

Before this runtime, operators passed JSON paths and IDs separately among the
Daily/Operational Research, Signal, Forecast, Decision, Risk, execution,
Position and Review CLIs. The lifecycle input manifest, typed references,
stage outputs and receipts now preserve that chain durably and allow restart
without retyping upstream IDs.

The following explicit handoffs remain by design:

- the verified H6 package and source/reference locators must exist before a
  canonical research run;
- a risk-reduction continuation must bind its exact existing nine H4/H4.5
  authority references;
- actor, reason, requested price and other confirmation inputs enter through
  the separate H4.5 manual CLI, not through the Runner;
- Fill remains separately human-recorded external evidence;
- Opportunity validity/actor/reason, Thesis approval, complete-account
  Portfolio/Risk inputs and durable H7 Holding/Exit/Review authority are not
  inferred from JSON or defaulted.

## 11. Open work and blockers

The next migration program is **WP-MIG-01 Technical Observable Migration**.
Its named work remains:

- MACD;
- Moving Average beyond the delivered simple Decimal example;
- Volume Structure;
- Force Ratio;
- Chan Features;
- Tuishen Volume-Price Features.

Other current blockers include qualified H6 operating packages, real Signal
factor materialization, historical PathForecast samples and calibration, an
empirically validated Entry model, authenticated Opportunity/Thesis/manual
approval, external account and Fill reconciliation, durable H7
Holding/Exit/Review authority, sustained H8 Shadow operations, H9 formal
validation, PostgreSQL parity, production observability and any separately
approved Broker architecture.

None of these gaps may be replaced with static successful data, synthetic Fill,
implicit current time, a fabricated approval or an inflated evidence status.
