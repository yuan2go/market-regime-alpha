# Canonical Runtime and Legacy Model Migration Infrastructure Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Approved design for the canonical backend lifecycle and Legacy model migration infrastructure
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../../architecture/01-Domain-Boundaries.md, ../../architecture/06-Legacy-Migration.md, ../../architecture/10-Production-Decision-Lifecycle.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../../status/Current-State.md, ../../status/Capability-Matrix.md, ../../status/Gap-Register.md
> **Code Evidence:** Design baseline is `origin/main@734c8b6f677f458e5048846fa28377b681b1fb65`, including merged H4.5 migration 010 and its reducing-risk manual-intent route.

## 1. Goal and bounded context

This work converges the existing backend capabilities into one recoverable,
human-in-the-loop lifecycle without replacing their domain implementations:

```text
Verified Composite Evidence
→ Platform Research
→ Signal
→ Path Forecast
→ Entry Assessment
→ Opportunity
→ Thesis
→ Portfolio / Risk
→ Manual Confirmation
→ Manual Trade
→ externally observed Fill / Fill-derived Position
→ Thesis Health
→ Holding / Exit
→ Outcome / Review
```

The lifecycle is deliberately resumable and may stop at an honest boundary.
It is not required, or permitted, to manufacture inputs so that a single run
can traverse every stage.

The same delivery establishes an isolated migration boundary for Legacy
`dividend_t` models, role-specific model contracts, a reusable differential
comparison harness and one content-addressed moving-average migration example.

This design is an optimal convergence of the current implementation. It is not
a thin demo and it is not a redesign of every domain. It strengthens the
durable seams, recovery behavior and dependency rules that later MACD, moving
average, volume, force-ratio, Chan and Tuishen migrations need.

## 2. Fixed authority ceiling and non-goals

The implementation must preserve these facts:

```text
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
production_ready = false
```

The work does not:

- add a web page, HTTP service or operator workbench;
- connect to QMT, PTrade or another Broker;
- create a `BrokerOrder`, simulated order or simulated Fill;
- infer a Fill from a ManualTrade;
- change existing model parameters, scores or thresholds;
- label an uncalibrated score as a probability;
- promote exploratory data to formal PIT, OOS Alpha or trading authority;
- migrate the complete Legacy strategy, position, risk, backtest, Chan,
  Tuishen or COSCO model family;
- copy Legacy God Objects into a canonical package;
- replace the existing Daily Runtime Journal or reacquire Daily evidence;
- claim durable H7 assessment authority, H8 sustained Shadow evidence or H9
  formal validation where those capabilities remain absent.

Empty results, `WAIT`, `DATA_INSUFFICIENT`, `NO_ACTION`, blocked validation and
manual waiting are valid outcomes.

## 3. Verified baseline and actual current seams

The implementation baseline contains separate, tested capabilities:

- `application.daily_loop` owns recoverable exploratory Daily acquisition and
  its `DailyRun`/stage receipts;
- `OperationalResearchRunner` verifies composite operational evidence and
  builds a Platform V2 research input;
- `PlatformResearchRunner` executes existing Platform V2 research and
  publishes a verified immutable artifact;
- `signals.engine.run_signal_model()` derives the existing signal artifact;
- `forecasting.path.build_path_forecast()` derives the existing uncalibrated
  path forecast;
- `DecisionLifecycleService` creates Opportunities and confirms Theses;
- `PortfolioRiskApplicationService`,
  `PositionAuthoritativePortfolioRiskApplicationService` and
  `RiskRouteApplicationService` own their respective portfolio/risk rules;
- `RiskReductionConfirmationApplicationService` and the migration-010 SQLite
  composition repository own H4.5 confirmation and reducing ManualTrade
  creation;
- Manual Fill recording and Fill-derived position projection are separate
  operator-driven capabilities;
- `ThesisHealthApplicationService`, the holding/exit assessment services and
  `LifecycleReviewApplicationService` remain independent domain services.

The current operational chain is split across CLI processes. JSON identities,
artifact paths and object IDs are manually transferred between research,
signal, forecasting, decision, risk, ManualTrade, Fill, health and review
commands. The new lifecycle replaces that manual orchestration with references
and receipts, not with copied business logic.

The baseline also has a portability defect in a repository-tamper test: its
fixture uses SQLite `UPDATE ... LIMIT`, which is not enabled in every SQLite
build. The implementation will use a deterministic scalar subquery to select
the row, preserving the test's assertion and semantics.

## 4. Architectural decision

### 4.1 Two journals with non-overlapping authority

The existing Daily Runtime Journal remains authoritative for Daily acquisition
and package-building stages. The new Lifecycle Runtime Journal is a distinct
aggregate that references verified Daily/H6 Artifacts and domain objects.

```text
Daily Runtime Journal
  owns: acquisition, source receipts, Daily package recovery
                 │ verified immutable reference
                 ▼
Lifecycle Runtime Journal
  owns: cross-domain stage progression, attempts, receipts, blockers, replay
```

The lifecycle runner cannot reacquire a source or mark a Daily stage complete.
It can only load a verified input through an existing Reader or Repository.

### 4.2 Package structure

The canonical orchestration package is:

```text
src/market_regime_alpha/application/canonical_lifecycle/
  __init__.py
  commands.py
  contracts.py
  input_manifest.py
  states.py
  repositories.py
  sqlite_repository.py
  runner.py
  replay.py
  stages/
    evidence.py
    research.py
    signal_forecast.py
    decision_risk.py
    execution_position.py
    assessment_review.py
  migrations/
    011_canonical_lifecycle_runtime_up.sql
    011_canonical_lifecycle_runtime_down.sql
```

Stage handlers are adapters around existing application services, Readers,
Repositories and Artifact builders. They do not reproduce model rules.

The public command-line entry points are:

```text
python -m market_regime_alpha.cli.run_canonical_lifecycle
python -m market_regime_alpha.cli.create_manual_trade_from_risk_decision
```

Existing script entry points remain compatible. Where compatibility is useful,
they may delegate to the new application boundary without changing historical
JSON schemas.

## 5. Lifecycle input manifest and command identity

`CanonicalLifecycleCommand` contains only explicit, canonicalized inputs:

```text
run_type
decision_date
as_of_time
input_manifest reference or risk-continuation references
idempotency_key
stop_after_stage
output_directory
configuration references
model-version references
resume_run_id, when resuming
```

`run_type` is one of:

```text
CANONICAL_DECISION_LIFECYCLE
RISK_REDUCTION_CONTINUATION
REPLAY
```

The command hash covers the semantic command fields and their canonical values.
It excludes output presentation, process ID, current wall-clock time and retry
metadata. A resume command proves the original command hash and may add only a
permitted resume control such as `stop_after_stage`; it cannot mutate the run's
decision date, evidence, configuration or model versions.

`CanonicalLifecycleInputManifest` is immutable and content-addressed. It binds:

- input artifact/object IDs, hashes and exact Reader kind;
- controlled locators needed by the relevant existing Reader;
- DecisionTime and availability information;
- source and composition manifest IDs/hashes;
- requested model/configuration IDs, versions and hashes;
- the input authority ceiling and limitations.

Artifact payloads are not copied into the journal. A controlled locator is
stored only when the existing Reader needs one and is always paired with the
expected object ID and content hash.

## 6. Runtime Journal model

### 6.1 LifecycleRun

`LifecycleRun` is the lifecycle aggregate root:

```text
run_id
idempotency_key
command_hash
run_type
decision_date
as_of_time
status
current_stage
input_manifest_id
input_content_hash
completed_stages
configuration_manifest_json / hash
model_version_manifest_json / hash
retry_state
failure_reason
blocker_reason
created_at
updated_at
completed_at
version
claim_token
```

`run_id` is stable. `version` is an optimistic concurrency token.
`claim_token` is monotonically increasing when execution is claimed; no
distributed scheduler or lease renewal is implemented in this work, but a
future lease owner cannot write with an older token.

### 6.2 LifecycleStage

There is exactly one current projection per `(run_id, stage_name)`:

```text
run_id
stage_name
stage_status
attempt_count
input_references
output_references
started_at
completed_at
failure_reason
blocker_reason
version
```

References are sorted canonical JSON records with object type, ID, hash and
optional verified locator. A completed stage is immutable. The projection can
only move through the transition matrix in section 8.

### 6.3 LifecycleAttempt

Every stage invocation creates an append-only attempt before domain work:

```text
attempt_id
run_id
stage_name
attempt_number
started_at
completed_at
result
exception_type
exception_message
claim_token
```

Exceptions are recorded explicitly after rollback. The runner does not catch
all exceptions and convert them to success; unexpected failures produce a
failed attempt and a recoverable `FAILED` run.

### 6.4 StageReceipt

Every completed, waiting, blocked or explicitly not-applicable stage receives
one immutable, content-addressed receipt:

```text
receipt_id
run_id
stage_name
attempt_number
input_hashes
output_hashes
model_versions
configuration_hashes
reason_codes
stage_result
created_at
receipt_hash
```

The receipt hash is calculated from semantic fields. A replay may have a new
attempt timestamp but must reproduce the same semantic receipt hash for the
same model/configuration/input/result combination.

### 6.5 LifecycleEvent

`LifecycleEvent` provides complete state history rather than relying only on
mutable projections:

```text
event_id
run_id
sequence_number
event_type
from_status
to_status
stage_name
attempt_id
receipt_id
reason_codes
payload_hash
created_at
claim_token
```

`(run_id, sequence_number)` is unique and events are append-only. Repository
history queries return events, attempts and receipts in deterministic order.

## 7. SQLite migration 011

Migration 011 creates:

```text
lifecycle_runs
lifecycle_stages
lifecycle_attempts
lifecycle_stage_receipts
lifecycle_events
```

Required constraints and indexes are:

- `lifecycle_runs.idempotency_key` is unique;
- creation with the same idempotency key and command hash returns the existing
  run; a different command hash raises a typed idempotency conflict;
- `(run_id, stage_name)` is unique in `lifecycle_stages`;
- `(run_id, stage_name, attempt_number)` is unique in attempts;
- `(run_id, stage_name, receipt_hash)` and `receipt_id` are unique in receipts;
- `(run_id, sequence_number)` is unique in events;
- foreign keys bind every child record to the run;
- indexes cover status/date discovery, stage status, stage attempts and event
  history;
- checks enforce positive versions, attempt numbers and claim tokens;
- append-only triggers reject `UPDATE` and `DELETE` for attempts, receipts and
  events;
- a trigger rejects mutation of a completed stage projection;
- repository compare-and-set updates require expected run/stage version and
  current claim token.

The runtime repository uses the project's SQLite adapter conventions,
canonical JSON and explicit transactions. Migration up/down behavior,
foreign-key enforcement, repeat application and pre-migration compatibility
are tested.

### 7.1 Transaction and recovery boundaries

One lifecycle transition transaction performs:

1. claim/version validation;
2. attempt start or completion projection;
3. stage transition;
4. immutable receipt insertion where applicable;
5. run projection transition;
6. event append.

Cross-domain repositories cannot be declared atomically committed merely
because the lifecycle database committed. They use a recoverable Saga:

1. record the stage attempt;
2. execute the existing domain service with a deterministic stage
   idempotency key;
3. reload and verify the resulting Artifact/domain object by ID/hash;
4. commit the lifecycle receipt and state transition.

If the process stops after step 2, recovery first reloads the deterministic
domain output. It records the missing receipt instead of repeating the domain
side effect. A domain operation without an idempotent/reloadable result cannot
be called as a mutating stage.

## 8. State machines

### 8.1 Run states

```text
CREATED
RUNNING
RETRYING
WAITING_FOR_ENTRY_CONFIRMATION
BLOCKED_BY_MODEL_VALIDATION
WAITING_FOR_MANUAL_CONFIRMATION
WAITING_FOR_FILL
POSITION_OPEN
WAITING_FOR_T1
READY_FOR_HOLDING_ASSESSMENT
READY_FOR_EXIT_REVIEW
COMPLETED
FAILED
```

Legal run transitions are:

| From | To |
|---|---|
| `CREATED` | `RUNNING`, `FAILED` |
| `RUNNING` | any waiting/blocked/ready state, `POSITION_OPEN`, `COMPLETED`, `FAILED` |
| `FAILED` | `RETRYING` |
| `RETRYING` | `RUNNING`, `FAILED` |
| `WAITING_FOR_ENTRY_CONFIRMATION` | `RUNNING`, `FAILED` |
| `WAITING_FOR_MANUAL_CONFIRMATION` | `RUNNING`, `FAILED` |
| `WAITING_FOR_FILL` | `RUNNING`, `FAILED` |
| `POSITION_OPEN` | `RUNNING`, `WAITING_FOR_T1`, `READY_FOR_HOLDING_ASSESSMENT`, `READY_FOR_EXIT_REVIEW`, `FAILED` |
| `WAITING_FOR_T1` | `RUNNING`, `FAILED` |
| `READY_FOR_HOLDING_ASSESSMENT` | `RUNNING`, `READY_FOR_EXIT_REVIEW`, `FAILED` |
| `READY_FOR_EXIT_REVIEW` | `RUNNING`, `COMPLETED`, `FAILED` |

`BLOCKED_BY_MODEL_VALIDATION` and `COMPLETED` are terminal for the original
command. A new validated input/configuration creates a new run rather than
mutating the evidentiary meaning of the old one.

### 8.2 Stage states

```text
PENDING
RUNNING
COMPLETED
WAITING
BLOCKED
FAILED
SKIPPED_NOT_APPLICABLE
```

Legal stage transitions are:

| From | To |
|---|---|
| `PENDING` | `RUNNING` |
| `RUNNING` | `COMPLETED`, `WAITING`, `BLOCKED`, `FAILED`, `SKIPPED_NOT_APPLICABLE` |
| `FAILED` | `RUNNING` on a new attempt |
| `WAITING` | `RUNNING` on resume when the missing authority is now present |

`COMPLETED`, `BLOCKED` and `SKIPPED_NOT_APPLICABLE` are immutable for the run.
`SKIPPED_NOT_APPLICABLE` is a reasoned stage result, never an implicit jump.

## 9. Canonical stages and actual service calls

The ordered stage set is:

```text
VERIFY_COMPOSITE_EVIDENCE
PLATFORM_RESEARCH
SIGNAL
PATH_FORECAST
ENTRY_ASSESSMENT
OPPORTUNITY
THESIS
PORTFOLIO_RISK
RISK_REDUCTION
MANUAL_CONFIRMATION
MANUAL_TRADE
FILL_POSITION
THESIS_HEALTH
HOLDING_ASSESSMENT
EXIT_ASSESSMENT
OUTCOME_REVIEW
```

The real orchestration mapping is:

| Stage | Existing implementation used | Safe result |
|---|---|---|
| Evidence | H6 verified composite package Reader and `OperationalResearchRunner` input validation | verified reference or fail closed |
| Research | `OperationalResearchRunner` → `PlatformResearchRunner` | verified Platform V2 artifact |
| Signal | `signals.engine.run_signal_model()` and existing publisher/Reader | signal or `DATA_INSUFFICIENT` |
| Path forecast | `forecasting.path.build_path_forecast()` and existing publisher/Reader | uncalibrated forecast or insufficient data |
| Entry assessment | existing entry/path evidence contract and validation status | ready, wait or model-validation blocker |
| Opportunity/Thesis | `DecisionLifecycleService` | durable domain IDs/hashes |
| Portfolio/Risk | existing portfolio/risk application services and repositories | approve/reject/wait/reducing route |
| Risk reduction | `RiskRouteApplicationService.assess_reducing()` and durable H4 Reader/Repository | decision ID/hash or not applicable |
| Manual confirmation | confirmation evidence/policy validation | explicit waiting or confirmed reference |
| Manual trade | `RiskReductionConfirmationApplicationService.confirm()` for reducing H4.5; existing traceable service for separately authorized increasing flow | ManualTrade only |
| Fill/Position | existing Fill repository and Fill-derived position projector | wait for external Fill, position or T+1 wait |
| Thesis health | `ThesisHealthApplicationService.assess()` | H5 observation reference |
| Holding/Exit | existing position assessment services | assessment result or honest readiness boundary |
| Review | `LifecycleReviewApplicationService` | diagnostic evaluation/replay output |

The runner stores returned IDs/hashes and never reconstructs a domain decision
from a score.

Current H6 composition does not necessarily supply every signal factor. A
missing factor produces explicit `DATA_INSUFFICIENT`; it is not filled with a
Legacy value or static fallback. An empirically unvalidated Entry model stops
at `BLOCKED_BY_MODEL_VALIDATION` or
`WAITING_FOR_ENTRY_CONFIRMATION`, according to the existing validation/result
contract.

A `RISK_REDUCTION_CONTINUATION` starts from traceable existing Position,
Thesis, H4/H5/H6 and risk-decision authorities. It does not need to replay a
new entry path. This is the truthful path for the required risk-decision to
ManualTrade integration.

## 10. Runner behavior

`CanonicalDecisionLifecycleRunner` has one orchestration responsibility:

1. canonicalize and create/reload the run;
2. claim it using version and claim token;
3. find the first non-terminal safe stage;
4. load all inputs through controlled Readers/Repositories;
5. call exactly one stage handler;
6. verify output identities/hashes;
7. atomically record attempt, receipt, stage and run transition;
8. stop on the requested stage, a waiting/blocked state, completion or failure.

`--stop-after-stage` is a controlled deterministic stop and receives a receipt
reason. `--resume-run-id` rejects any input identity, command hash or
configuration mismatch. Resume never reruns a completed stage.

`--output-dir` contains only the structured CLI result and immutable packages
created by existing publishers. Journal authority remains SQLite.

Replay reloads every referenced input using the recorded Reader kind and
expected hash, reruns pure/model stages at the recorded as-of time and compares
semantic receipt hashes. It does not replay a ManualTrade creation. For a
mutating domain stage it verifies the original durable object and receipt.

## 11. H4.5 risk-decision to ManualTrade bridge

The merged H4.5 service remains the single authority for:

```text
RiskReducingDecision
→ RiskReductionConfirmationCommand
→ RiskReductionConfirmationAttempt
→ ManualTradeRecord V3 REDUCING
```

The new CLI and runner adapt `ManualTradeCommand` terminology to that existing
confirmed command; they do not introduce a second ManualTrade aggregate.

Before creating a ManualTrade, the application boundary reloads and proves:

1. decision state permits manual confirmation;
2. decision and confirmation evidence have not expired;
3. the referenced Fill-derived Position is still current;
4. symbol, `SELL` direction, quantity, Thesis, Opportunity and PositionBook
   lineage are consistent;
5. quantity is positive and no greater than current reducible/sellable
   quantity;
6. A-share T+1 sellability is satisfied from observed fills;
7. the decision/confirmation idempotency authority has no existing different
   ManualTrade;
8. no newer same-scope RiskReducingDecision supersedes the requested decision;
9. all source objects and hashes can be replayed.

Supersession is fail-closed: a later same PositionBook/Thesis/symbol reducing
decision makes the old decision ineligible even if the old object itself is
immutable. The latest decision and lineage are evaluated inside the existing
H4.5 SQLite transaction boundary.

Successful CLI output contains the stable declarations:

```text
MANUAL_CONFIRMATION_REQUIRED
NO_ORDER_CREATED
BROKER_NOT_INVOKED
NO_FILL_CREATED
```

`MANUAL_CONFIRMATION_REQUIRED` describes the authority of the produced record:
the operator must still manually execute outside the system and later record
an observed Fill. The command cannot construct or import any Broker client.

## 12. Model migration contracts

There is no universal `Model` base class. Contracts live with their semantic
domain:

```text
features/model_contracts.py
research/model_contracts.py
signals/model_contracts.py
decision/model_contracts.py
```

### 12.1 FeatureComputer

`FeatureComputer` receives normalized market data, explicit `as_of_time`, data
availability and immutable configuration. It returns `FeatureArtifact`.

The Protocol guarantees:

- no side effects, repository writes, Broker access or trade creation;
- deterministic calculation from explicit input;
- explicit missing values and unavailable observations;
- recorded event time, availability time, as-of time and configuration
  identity/version/hash;
- content-addressed output with input IDs/hashes and limitations.

### 12.2 ResearchModel

`ResearchModel` expresses Market Regime, Theme, Capital or Candidate research.
Its result contains:

```text
model_id / model_version
configuration_id / configuration_hash
input_artifact_ids / input_hashes
state / score
reason_codes / limitations
validation_status
```

### 12.3 SignalModel

`SignalModel` expresses observation-level meaning such as:

```text
ENTRY_CONFIRMATION
TREND_CONTINUATION
REVERSAL_WARNING
SELL_PRESSURE
OVERHEAT
VOLUME_CONFIRMATION
```

It uses the same trace metadata but cannot emit an order or final trading
command.

### 12.4 DecisionModel

`DecisionModel` may emit only:

```text
REJECT
WAIT
READY_FOR_MANUAL_CONFIRMATION
REDUCE
EXIT
```

It cannot emit automatic execution semantics. A decision remains distinct from
a Signal, ManualTrade, Fill and Position.

New canonical price, money and quantity fields use `Decimal` or integer share
quantities. Existing float-based Legacy data is normalized explicitly at the
adapter/comparison boundary and is not silently promoted to canonical
authority.

## 13. Legacy dependency boundary

Migration code is isolated under:

```text
src/market_regime_alpha/migration/
  legacy/
    adapters/
    normalization/
  comparison/
```

The dependency rule is:

```text
canonical core ─X→ dividend_t
legacy adapter ──→ dividend_t
migration comparison ──→ legacy adapter + canonical model
```

An AST architecture test scans canonical source roots and fails on imports of
`market_regime_alpha.dividend_t`. Explicit compatibility entry points are
allow-listed narrowly and may only delegate into `migration.legacy`.

The existing canonical data-source dependency on
`dividend_t.storage.DEFAULT_RESEARCH_DIR` is removed by moving the shared
storage default to a neutral canonical module. The Tencent/Dividend-T research
bridge implementation moves under the Legacy adapter boundary; the historical
module may remain as a compatibility facade with tests.

A Legacy adapter may:

- normalize standard input into the exact Legacy input shape;
- call Legacy calculation code;
- normalize and label its output;
- capture typed Legacy exceptions;
- record data gaps, float semantics, fallback risk and other limitations;
- provide a differential-test baseline.

It may not write a canonical Repository or create a Signal, Trade, Fill,
Position or Broker request. A static Legacy fallback is labeled unavailable or
non-comparable, never accepted as observed market data.

### 13.1 Migration disposition

Initial classification is:

- **extract as pure features:** simple/weighted moving averages, EMA/MACD base
  values, ATR and raw volume/force computations after normalized-time review;
- **refactor before migration:** Chan structures/divergence, Tuishen
  volume-price rules, composite technical inputs, buy/sell-point scoring,
  position sizing, risk logic and `CoscoTimingEngine`;
- **retain only for compatibility or retire:** Legacy `OrderIntent`, Paper
  Broker behavior, static market fallbacks, QMT/PTrade paths, strategy God
  Objects and monolithic Legacy backtests.

No classification implies empirical validation.

## 14. Differential comparison harness

`DifferentialTestHarness` receives:

```text
normalized dataset
Legacy adapter
canonical model
ComparisonPolicy
```

It returns a content-addressed `ModelComparisonReport` with:

```text
comparison_id
legacy_model_id
canonical_model_id
dataset_id
as_of_time
input_hash
legacy_output
canonical_output
field_differences
numeric_differences
semantic_differences
difference_classification
expected_difference
unexpected_difference
created_at
report_hash
```

`ComparisonPolicy` names exact fields, Decimal tolerances, missing-data rules,
semantic mappings and explicitly accepted Legacy-defect corrections. It is
content-addressed and included in the report identity.

Supported classifications are:

```text
EXACT_MATCH
NUMERIC_TOLERANCE
EXPECTED_SEMANTIC_CHANGE
LEGACY_DEFECT_FIXED
CANONICAL_REGRESSION
INSUFFICIENT_DATA
NOT_COMPARABLE
```

Classification is evidence-based:

- `CANONICAL_REGRESSION` requires violation of a stated canonical invariant or
  an independent expected result; mere disagreement with Legacy is not enough;
- `LEGACY_DEFECT_FIXED` requires a policy-bound defect identifier and an
  independently demonstrated corrected result;
- adapter exception, static fallback or required-data absence becomes
  `INSUFFICIENT_DATA` or `NOT_COMPARABLE`, never a match;
- Legacy floats are compared as `Decimal(str(value))`, preserving the observed
  value without claiming exact binary equality;
- an unexpected difference cannot be hidden by changing a global tolerance.

Reports use an immutable publisher, semantic Reader and replay verifier. The
same dataset, model versions and policy reproduce the same semantic report
hash; `created_at` is explicit evidence metadata and is excluded from the
semantic comparison hash.

## 15. Moving-average example migration

The first migration example is a simple moving average because it is low risk,
pure and exposes the required data/time/missing-value semantics without
claiming buy/sell meaning.

Target files are:

```text
src/market_regime_alpha/features/technical/moving_average.py
src/market_regime_alpha/migration/legacy/adapters/moving_average.py
```

Canonical input contains sorted normalized bars with symbol, market date,
availability time and `Decimal` close; explicit as-of time; a positive integer
window; and configuration ID/version/hash. Duplicate dates, observations after
as-of, non-finite values and unsorted input fail closed.

Canonical output is a `FeatureArtifact` containing:

- model/configuration and input identities/hashes;
- event and availability coverage;
- each date's `Decimal` value or explicit missing reason;
- warm-up count, reason codes and limitations;
- semantic content hash and artifact ID.

The Legacy adapter calls the existing pandas rolling calculation rather than
copying it. It normalizes Legacy `NaN`, float and date behavior and records the
limitations. The differential report demonstrates exact agreement where
representable, tolerance handling where Legacy float representation differs,
warm-up/missing behavior and typed failure classification.

Unit and replay tests prove deterministic output, no Repository/Broker access,
stable hashes, explicit as-of behavior and no hidden current-time dependency.

This feature is an observable only. It is not an Entry confirmation, trade
decision, risk decision or execution command.

## 16. CLI contract and exit codes

`run_canonical_lifecycle` supports:

```text
--input-manifest
--decision-date
--as-of
--idempotency-key
--resume-run-id
--stop-after-stage
--output-dir
```

It prints one canonical JSON result containing run ID/type, command hash,
status, current stage, completed stages, output references, blocker/failure,
retry state, ManualTrade reference if any and fixed Broker safety declarations.

Stable exit codes are:

```text
0  valid terminal/waiting/blocked lifecycle result
2  command or input validation error
3  idempotency/command-hash conflict
4  run not found or unsafe resume
5  recoverable stage failure
6  repository/migration/integrity failure
```

Waiting and evidence-insufficient outcomes are not process failures and return
0 with their explicit state. A thrown unexpected exception never produces a
successful JSON state.

`create_manual_trade_from_risk_decision` accepts the durable decision and
idempotency authorities required by H4.5 and returns the same stable safety
declarations. It never accepts Broker configuration.

## 17. Test strategy and acceptance evidence

### 17.1 Unit tests

Tests cover:

- all legal and illegal run/stage transitions;
- attempt ordering, failure metadata and immutable receipts;
- semantic receipt/configuration/model/input hashes;
- idempotent create and command-hash conflict;
- optimistic version and claim-token conflicts;
- H4.5 valid creation, duplicate replay, expiry, quantity excess, T+1,
  superseded decision and lineage mismatch;
- the Legacy import boundary and compatibility facade;
- FeatureComputer purity, Decimal behavior and missing data;
- every differential classification and unexpected-difference handling;
- migration 011 up/down, triggers, indexes and constraints;
- CLI schema and exit codes.

### 17.2 Integration tests

Two linked but semantically honest paths are exercised:

```text
verified H6 evidence
→ research
→ signal/data sufficiency
→ path forecast
→ entry WAIT or model-validation blocker
```

and:

```text
traceable existing Position/Thesis/H5/H6
→ H4 reducing-risk decision
→ manual confirmation
→ H4.5 ManualTrade
→ WAITING_FOR_FILL
```

Both paths prove run/stage/attempt/receipt/event persistence. They are not
artificially joined by bypassing the Entry blocker.

### 17.3 Recovery tests

Fault injection covers failure:

- before a domain call;
- during a domain transaction;
- after a domain commit but before lifecycle receipt commit;
- after receipt commit before CLI response.

The assertions prove rollback where appropriate, no completed-stage rerun,
attempt-number increase, verified domain-output recovery, immutable receipts
and successful resume from the last safe stage.

### 17.4 Replay tests

The same explicit input and as-of time must produce stable semantic hashes.
The same idempotency key returns the same run and ManualTrade. Replay produces
no Broker calls, Broker objects, Fill records or hidden use of current time.

### 17.5 Quality gate

Final validation follows repository CI and the user-required build:

```bash
git diff --check
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
python -m build
```

Every command is reported as `PASS`, `FAIL`, `NOT_RUN` or `BLOCKED`. Tests are
not deleted, weakened or skipped to obtain a green result.

## 18. Delivery sequence and reviewable checkpoints

Implementation uses dependency-coherent checkpoints:

1. dependency boundary, role-specific model contracts, moving-average example
   and differential harness;
2. migration 011, Runtime Journal repository, transactions and state-history
   queries;
3. stage adapters, canonical runner, resume/replay and CLIs, including H4.5
   hardening;
4. integration/recovery/replay coverage, portability repair, documentation,
   full validation and code review corrections.

Each checkpoint includes focused tests, `git diff --check`, compatibility
review and a coherent commit. Existing unrelated workspace changes are not
staged.

## 19. Rollback and forward repair

Migration 011 is additive. Rollback is safe only when no lifecycle data must be
retained and drops its five tables/triggers/indexes in foreign-key-safe order.
It does not alter migrations 002–010 or historical Artifacts.

Published content-addressed feature/comparison artifacts are immutable. A
defect is repaired with a new schema/model/configuration/builder version and a
new artifact/report, never by editing historical content.

A partially failed lifecycle run is retained as audit evidence and resumed or
superseded by a new run; it is not deleted or relabeled completed. A faulty
stage handler can be disabled while Readers and historical journal queries
remain available.

## 20. Documentation and truthful completion claims

Implementation updates the architecture, Current State, Capability Matrix, Gap
Register, Legacy migration documentation and CLI runbook. Delivery evidence
must cite actual files, migration 011, tests and commands.

Completion of this work means the canonical lifecycle and migration
infrastructure are implemented and tested. It does not mean the platform is
production-ready. The next model work remains explicit:

```text
WP-MIG-01 Technical Observable Migration
- MACD
- Moving Average expansion
- Volume Structure
- Force Ratio
- Chan Features
- Tuishen Volume-Price Features
```

Formal data qualification, empirically validated Entry, durable H7 assessment
authority, sustained H8 Shadow operation, H9 validation, authenticated
operators and any Broker authority remain separate blockers or future work.
