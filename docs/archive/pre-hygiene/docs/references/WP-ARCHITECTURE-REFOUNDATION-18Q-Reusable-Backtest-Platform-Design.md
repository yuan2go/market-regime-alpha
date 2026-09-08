# WP-18Q Continuous Prospective Correctness and Reusable Backtest Platform Design

> **Status:** CURRENT_STATUS
> **Authority:** Canonical implementation contract for WP-18Q; never Provider, Formal PIT/OOS, prospective-value, Alpha, Model Qualification, trading, or Production evidence
> **Baseline:** `origin/main@e45d232cb0c4891a75d55a65ed83398640160893`
> **Owner:** Market Regime Alpha maintainers
> **Frozen:** 2026-09-04
> **Decision:** DESIGN_APPROVED / IMPLEMENTATION_AUTHORIZED
> **Supersession:** Extends the approved WP-18 design. When this document is more specific about generic backtest execution, historical compatibility, report projection, or prospective Runtime continuity, this document controls WP-18Q implementation.

## 1. Outcome and evidence ceiling

WP-18Q closes two equally mandatory P0 tracks:

```text
Track A: exact Target + TradingSession
         -> continuous prospective generation roll-forward
         -> existing Runtime Schedule / Run / Step / Attempt / fence
         -> due capture or explicit terminal absence
         -> immutable revision and missed-window evidence

Track C: immutable Backtest predeclaration
         -> arbitrary ordered FoldDependency DAG
         -> canonical Dataset / Candidate / Decision Support / Outcome
         -> optional ModelTrainingRun / ModelVersion
         -> canonical Evaluation
         -> derived standardized Report / Comparison
```

`ExploratoryBacktestRun` remains the sole Backtest identity and predeclaration
root. Dataset, Candidate, Decision Support, Outcome, Portfolio, Risk, Model,
Evaluation, Runtime, Artifact, receipt, and audit ownership do not move.

The evidence ceiling is invariant under every result:

```text
RETROSPECTIVE = EXPLORATORY_RETROSPECTIVE
FORMAL_PROVIDER = BLOCKED
FORMAL_PIT = BLOCKED
FORMAL_OOS = NOT_RUN
PROSPECTIVE_PROVEN = NO
ALPHA_PROVEN = NO
MODEL_QUALIFIED = NO
PRODUCTION = NO-GO
```

Positive economics cannot promote any state above.

## 2. Hard-cut compatibility boundary

All existing WP-17P/WP-18 relational identities, rows, FKs, hashes,
Artifacts, receipts, audit, Verification, and replay evidence are immutable.
WP-18Q does not rewrite, renumber, re-hash, or reinterpret them.

Historical compatibility is a private read-only implementation. It is enabled
only for an exact checked-in compatibility tuple containing the historical Run
ID, root and roster hashes, code/config Artifact hashes, structural-contract
hash, and expected downstream identity/hash roster. The allowlist is a decoder
guard and test oracle, not business or research Authority.

The following is explicitly false:

```text
missing current specification == legacy
```

A Run not present in that exact allowlist must have a complete current
specification closure. Otherwise inspection, execution, resume, replay, and
reporting fail with `UNSUPPORTED_OR_INCOMPLETE_SPECIFICATION`.

`FrozenBacktestRun` is an immutable in-process projection consumed by the
executor. It has no independent identity, persistence, write interface, or FK
surface and cannot become business truth.

The permanent executor never branches on generation, a WP number, or a
historical arm enum. Historical decoding ends before the executor seam.

## 3. Current Backtest specification closure

The current schema retains `mra.exploratory_backtest_run` as the only root and
adds a root-owned one-to-one `mra.backtest_specification`. The companion uses
`exploratory_backtest_run_id` as its primary key; it has no second Backtest ID.

```text
exploratory_backtest_run
└── backtest_specification
    ├── backtest_sample_member
    ├── exploratory_backtest_feature
    ├── exploratory_backtest_arm
    │   └── backtest_arm_specification
    ├── exploratory_backtest_fold
    │   └── exploratory_backtest_fold_session
    ├── backtest_fold_dependency
    ├── backtest_arm_fold
    ├── backtest_model_training_requirement
    ├── exploratory_backtest_cost_assumption
    └── backtest_evaluation_requirement
```

The current specification freezes and hashes:

- schema and definition version;
- exact `UniverseRevision` ID/hash and deterministic ordered sample roster;
- exchange and exact first/last `TradingSession` identities;
- distinct trading-session count and fold-session binding count separately;
- ordered FeatureDefinition roster;
- exact TargetDefinition version/hash;
- exact Candidate, Context, Strategy, Portfolio, and Risk bindings;
- ordered non-empty unique arm roster;
- ordered non-empty Fold roster and explicit FoldDependency DAG;
- rolling, expanding, or fixed walk-forward policy and typed parameters;
- purge and embargo semantics;
- effective shared and arm-override cost assumptions;
- exact Evaluation requirements and formula roster;
- random seed, code/config Artifacts, provenance, and evidence ceiling.

The root definition hash includes the current specification hash. The current
specification hash includes every child roster hash. Every current child has a
concrete composite FK to the owning `(run_id, specification_hash)` closure.
Registration uses deferred closure checks and root-last validation in one short
transaction.

Historical nullable companion columns remain null. Their old values and hash
algorithms remain unchanged. Current registration is available only through
the current Application command; there is no historical writer.

### 3.1 Universe and sample

`backtest_sample_member` concrete-FKs every ordered instrument to the exact
UniverseRevision membership. A mutable Universe name or caller-provided symbol
list is insufficient. Deterministic sampling freezes the algorithm code,
version, seed/input key, member count, roster hash, and exact instruments.

### 3.2 Arms

Permanent arm meaning is orthogonal:

```text
execution_kind  = RULE | MODEL
comparison_role = BASELINE | CHALLENGER | DIAGNOSTIC
context_mode    = typed exact mode
strategy        = exact StrategyVersion
model           = optional exact Model definition
portfolio       = exact effective policy
risk            = exact effective policy
cost            = exact effective roster
```

Arm codes are ordered, non-empty, unique operator labels. They do not control
execution behavior. MODEL requires a concrete Model definition; RULE forbids
one. No predeclaration contains a nullable future ModelVersion FK. The actual
version exists only after successful FIT execution.

Shared root defaults take precedence unless an arm declares an explicit
override. Every effective binding stores both its exact ID/hash and
`SHARED_DEFAULT` or `ARM_OVERRIDE`. Portfolio, Risk, or Cost differences enter
the comparison compatibility fingerprint.

### 3.3 Folds and counts

Fold ordinals are contiguous and their first sessions are chronological. Each
fold has a unique chronological internal session roster. Rolling or expanding
FIT folds may share sessions across folds. The previous global uniqueness
constraint on `(run_id, trading_session_id)` is not a current invariant.

Current definitions record both:

```text
distinct_trading_session_count
fold_session_binding_count
```

The historical `session_count` field and hash remain untouched.

## 4. FoldDependency, execution, and resume

`backtest_fold_dependency` is an explicit acyclic graph. A MODEL validation
dependency binds an exact predecessor FIT fold, exact successor VALIDATION
fold, Model definition, and required completed FIT Evaluation. No ordinal or
"previous fold" inference is permitted.

`backtest_arm_fold` freezes arm participation. A
`backtest_model_training_requirement` identifies the exact FIT-to-VALIDATION
relationship without referring to an absent future ModelVersion.

After successful training, `backtest_model_lineage` concrete-FKs:

```text
training requirement
-> completed FIT Evaluation
-> ModelTrainingRun
-> fitted Artifact
-> ModelVersion
-> strictly later validation ModelForecast binding
```

### 4.1 Planner and Runtime

`BacktestExecutionPlanner` is a pure projection from a reconciled frozen
specification to dependency-ready Runtime work. It persists no cursor. Because
the existing Runtime protects each mandatory Candidate-to-Context chain, the
bounded execution cell is `arm x fold x session`; FIT Evaluation, Model
training, validation, and aggregate Evaluation use separate controlled Runtime
Runs as needed.

The bounded historical work uses existing Runtime `HISTORICAL` Runs, Steps,
Attempts, receipts, audit, claims, leases, and fences. It creates no scheduler.
`backtest_runtime_binding` is concrete lineage from a Backtest cell/action to
an actual RuntimeRun, not a workflow state owner.

Every run, resume, inspect, or replay rebuilds an expected action graph and
reconciles canonical owners:

```text
MATCHED_COMPLETE   -> reuse and skip
ABSENT             -> call the owning Application
MATCHED_INCOMPLETE -> call that owner's recovery/finalization seam
FAILED_RETRYABLE   -> permit a new fenced Runtime Attempt
MISMATCH           -> stop with INTEGRITY_ERROR and perform no later writes
```

Fold projections keep execution and research states orthogonal:

```text
ExecutionState = PLANNED | RUNNING | COMPLETED | FAILED | INTEGRITY_ERROR
ResearchState  = ESTIMABLE | NOT_ESTIMABLE | NOT_APPLICABLE
```

`NOT_ESTIMABLE` is a successful research result. Existing Runtime attempts,
receipts, audit, and canonical owner states provide exact lifecycle history;
there is no mutable `current_fold` or `current_step`.

An ordinary recoverable failure may produce a later Attempt. A hash, FK,
roster, or Authority mismatch is `INTEGRITY_ERROR` and cannot be resumed
automatically.

## 5. Model extension seam and leakage closure

Infrastructure exposes only:

```python
ModelTrainer.fit(FrozenTrainingInput) -> FittedModelPayload
ModelPredictor.predict(FrozenModelVersion, PredictionBatch) -> PredictionBatch
```

These interfaces do not write Authority. `ResearchModelApplication` loads and
validates canonical training inputs, calls the concrete adapter, writes fitted
bytes through the Artifact owner, and registers/reloads/reconciles the
ModelTrainingRun and ModelVersion. Decision Support remains the Forecast
writer.

The first adapter is deterministic ridge. The composition root performs an
explicit typed adapter selection. There is no dynamic import, arbitrary Python,
AutoML, or generic business registry. Adding a family requires a concrete
adapter and explicit composition wiring, not Backtest engine changes.

Each training closure freezes:

- algorithm code/version and implementation SHA;
- Python/runtime identity;
- `uv.lock` SHA and ordered dependency name/version/hash roster;
- ordered Feature roster and exact Target;
- typed scalar hyperparameters and seed;
- exact training sample roster/hash;
- PostgreSQL-clock training knowledge cutoff;
- input and fitted Artifact identities/hashes;
- FIT Evaluation, fold, arm, and Backtest lineage.

Before fitting, the Application proves:

- every training Outcome was available and known no later than the actual
  PostgreSQL `training_knowledge_cutoff`;
- every training Decision generation is strictly earlier than validation;
- exact purge and embargo contracts hold;
- the FIT Evaluation is completed and reconciled;
- feature order/hash, Target, Model definition, and adapter family match.

Rule arms remain valid without ModelVersion.

## 6. Canonical Evaluation closure

Evaluation remains the sole metric Authority. A report, DataFrame, diagnostic,
or comparison cannot calculate or persist a competing metric.

Each current `EvaluationProtocolMetric` freezes:

- `formula_code` and `formula_version`;
- exact typed source kind/measure and slice;
- ordered typed parameter roster/hash;
- minimum observations;
- inclusion and missingness policy;
- direction and optional acceptance rule.

All numerical computation uses a frozen Decimal precision and rounding mode.
No NaN, infinity, implicit float result, or fabricated zero is permitted.

### 6.1 Frozen V1 definitions

- Coverage, missingness, SourceGap, and unavailable rates use the complete
  expected roster denominator.
- Candidate and Forecast Top-K/Bottom-K membership is fixed from ranking known
  at DecisionTime. Future Outcome is read only after membership is frozen.
- Session RankIC is Spearman correlation over exact midranks; fewer than two
  pairs or zero variance is not estimable.
- IC mean is the arithmetic mean of estimable session ICs. IC standard
  deviation is sample standard deviation. ICIR is `mean / sample_std` without
  implicit annualization.
- Top-K return is the within-session mean of the frozen top K, followed by the
  arithmetic mean across estimable sessions. Top-bottom spread subtracts the
  frozen bottom-K mean; overlapping or incomplete sets are not estimable.
- Hit rate is positive realized Outcomes divided by estimable frozen selected
  membership. Selected ratio is selected divided by eligible.
- Forecast predictive metrics use exact Forecast-Outcome pairs and include
  RankIC, bias, MAE, and RMSE without probability or calibration claims.
- Gross exposure is `sum(abs(w_i))`; net exposure is `sum(w_i)`. They are never
  divided by one another.
- Turnover is `0.5 * sum(abs(w_t - w_(t-1)))` under frozen initial cash,
  carry-forward, final liquidation, and corporate-action conventions.
- ASSUMED_COST uses exact buy/sell turnover, commission, slippage, and sell-side
  stamp duty conventions.
- Cumulative return is `product(1 + r_t) - 1`.
- Annualized return is `(1 + cumulative_return) ** (A / n) - 1`; non-positive
  wealth is not estimable.
- Volatility is sample standard deviation times `sqrt(A)`.
- Sharpe is `mean(r-rf) / sample_std(r-rf) * sqrt(A)` under the frozen
  per-session risk-free convention.
- Sortino downside deviation is
  `sqrt(mean(min(0, r-MAR) ** 2))` over the full estimable period roster;
  Sortino is `mean(r-MAR) / downside_deviation * sqrt(A)`.
- Starting wealth is one. Max drawdown is
  `max(1 - wealth_t / running_peak_t)`. Calmar is annualized return divided by
  absolute max drawdown.
- Win rate is positive estimable period returns divided by all estimable
  periods. MFE and maximum adverse excursion are exact Outcome metrics; the
  latter uses a distinct code from forecast MAE.

Every denominator, K, annualization constant, risk-free convention, MAR,
precision, rounding, cost, cash, carry, terminal, and corporate-action rule is
a typed formula parameter.

`NOT_ESTIMABLE` stores a null value and a closed reason such as insufficient
observations, zero variance, no downside, non-positive wealth, incomplete
canonical source, SourceGap, or incompatible scope.

### 6.2 Required surfaces

Where estimable, the standard roster covers Data, Candidate, Context,
Signal/Forecast, Portfolio/Risk, Economics, and Stability. Evaluation Runs are
created for arm/fold, arm/run aggregate, sufficiently supported monthly and
quarterly slices, and canonical Context-state slices. Complete member
denominators preserve unavailable, failed, rejected, unknown, no-action, and
not-estimable observations.

`AlphaFunnelDiagnosis` is a deterministic read model over reconciled Evaluation
metrics. It does not read bars or write metric truth.

## 7. Report and comparison projections

`BacktestReportApplication` requires a zero-mismatch reconciliation, then uses
a read-only repeatable-read snapshot over canonical Authorities. It never reads
raw bars, settles Outcome, evaluates a formula, or substitutes an unavailable
source.

Canonical JSON is the primary format. Markdown is rendered from the same
in-memory projection. Key ordering, Decimal encoding, line endings, section
ordering, and renderer version are frozen. Wall-clock report generation time is
absent from content bytes and hashes; any displayed time is an existing
canonical completion timestamp.

`backtest_report_artifact` is a derived binding containing exact Backtest root,
specification, Evaluation roster, code/config, projection schema/renderer, and
JSON/Markdown Artifact identities, hashes, and sizes. Neither it nor the report
is a research/business FK target.

Like-for-like comparison requires matching fingerprints for Dataset/source
scope, UniverseRevision/sample, Target, Fold/session/dependency roster,
effective Portfolio/Risk/Cost, Evaluation formulas/parameters, and evidence
lane. Only the explicitly predeclared treatment dimension may differ.

`DESCRIPTIVE_NON_LIKE_FOR_LIKE` lists every mismatch and cannot emit a winner,
promotion, or decision recommendation.

## 8. Operator surface

The sole `mra` CLI exposes Application-backed commands:

```text
mra backtest validate       # read-only static/type validation
mra backtest plan           # read-only canonical reference resolution
mra backtest predeclare     # explicit immutable registration
mra backtest run            # begin a run with no execution evidence
mra backtest resume         # reconcile and continue dependency-ready work
mra backtest inspect        # read-only lifecycle/research/reconciliation
mra backtest report         # deterministic projection/publication
mra backtest compare        # exact or descriptive comparison
```

Input JSON is an operator convenience Artifact, never business Authority. No
command writes SQL directly. No second scheduler is introduced.

## 9. Track A continuous prospective Runtime

The WP-specific archive interface is replaced by permanent Market-owned
target-aligned prospective archive Applications. `CONTINUOUS_RESEARCH` remains
the sole all-day Runtime:

```text
Runtime Schedule -> Run -> Step -> Attempt/fence
-> PostgreSQL-clock due query -> Market Application
-> Provider/Artifact effect -> terminal slice fact
```

The schedule continuously:

- rolls forward the next exact Target/TradingSession generation early enough;
- freezes the stable deterministic instrument roster;
- finalizes overdue scheduled slices before claiming due work;
- performs due Provider captures through fenced Runtime Attempts;
- records capture, SourceGap, resource stop, failure, revision, and health;
- recovers expired leases and reconciles unknown external effects.

The `OUTCOME_PATH` window covers authoritative outcome-session open through the
Target checkpoint. `OUTCOME_10_30` remains the point window. They cannot share
the same one-minute implementation.

An existing elapsed scheduled slice terminalizes as immutable `MISSED`. If a
Runtime outage prevented the generation itself from being prospectively
predeclared, Market records an immutable `ProspectiveArchivePlanningGap` bound
to the exact expected Session, Target, predecessor, detection time, and reason,
then plans the next still-future eligible session. It never retroactively
creates prospective evidence.

Operator commands are generic:

```text
mra archive prospective plan-next
mra archive prospective predeclare
mra archive prospective run-due
mra archive prospective resume
mra archive prospective inspect
mra archive prospective health
```

Future real prospective windows take operational priority over repeatable
retrospective work.

## 10. Transactions, locking, idempotency, and recovery

- Backtest predeclaration is one short root-last transaction with deferred FKs,
  exact idempotency receipt, audit, reload, and reconciliation.
- Runtime schedule/run/step/attempt transitions retain their existing short
  transactions, leases, claims, and fences.
- Dataset, Candidate, Decision Support, Outcome, Model, and Evaluation use only
  their owning UoWs.
- Provider I/O and Artifact content puts remain outside business transactions.
  A binding is written only after bytes/hash verification.
- Unknown commit outcomes are probed by exact request identity before retry.
- Report publication is content-addressed and idempotent.
- Any Authority/hash/FK/roster mismatch is an unrecoverable integrity result,
  not an ordinary retryable failure.

## 11. Safe operational database upgrade

Disposable qualification databases bootstrap from the updated unreleased
`001_baseline.sql`. Durable archive/evidence databases are never recreated.

`SchemaManager` gains a read-only operational upgrade plan and an explicit
apply command. The plan binds exact database name/OID/owner, schema epoch,
prior baseline/catalog checksums, approved additive upgrade bundle hash, next
baseline/catalog expectations, verified-readable `pg_dump` Artifact hash/size,
absence of active Runtime attempts, operator/reason, expiry, nonce, and
challenge.

Apply reacquires the bootstrap advisory lock and rechecks every bound fact. One
transaction changes only the required tables, columns, constraints, indexes,
functions, and triggers, advances unreleased schema metadata, and inserts an
append-only upgrade receipt. It updates no historical business row and never
re-hashes historical evidence.

Pre/post proof compares historical row counts and ordered row hashes, Artifact
bytes/hashes, archive reconciliation, and WP-17P generic replay. Any OID,
checksum, backup, disk, ownership, active-run, or reconciliation mismatch
stops the upgrade.

## 12. Historical equivalence and deletion gate

WP-17P completed historical proof runs through the generic reader, executor
reconciliation planner, and verifier as a no-op. It must match every Dataset,
Candidate, Decision, Outcome, Evaluation, TrainingRun, ModelVersion, receipt,
audit, and Artifact identity/hash while producing zero database and Artifact
changes.

WP-18 currently proves definition/specification equivalence only. Its exact
four-arm multi-fold structural and companion hashes are decoded and verified;
it is not described as completed historical execution equivalence.

WP-specific executors remain present until all of the following pass:

- WP-17P completed zero-write historical equivalence;
- WP-18 definition/specification equivalence;
- fresh generic two-arm single FIT/VALIDATION execution;
- fresh generic four-arm multi-fold rule/ridge execution;
- complete standard Evaluation and deterministic Report/Comparison;
- real at-least-40-session, stable deterministic 32-symbol, four-arm,
  multi-fold rule/ridge campaign;
- replay of that exact run with `matched=true` and `mismatch_count=0`;
- complete PostgreSQL, concurrency, recovery, static, build, docs, and full
  repository qualification.

If any gate fails, deletion stops and the exact compatibility blocker is
reported. Historical evidence is never changed and no delegating facade,
dual-execution path, or availability-selected fallback is allowed.

After the gate, executable WP-specific campaign/model/evaluation/decision/
outcome orchestration and public exports are removed. Historical documents,
IDs, Artifacts, Verification, immutable provenance, and the private exact
decoder remain.

## 13. Real execution and WP-18Q exit gate

The prospective proof must include at least one actual due Runtime Attempt
through the existing claim/fence path. Its honest terminal may be captured,
Provider gap, resource stop, or failure. A future window that is not due stays
`NOT_DUE`.

The real generic retrospective campaign freezes before validation access:

```text
at least 40 distinct actual XSHG sessions
32 deterministic instruments
at least two explicit FIT -> VALIDATION dependencies
four ordered rule/ridge arms
comparison-compatible shared Portfolio/Risk/Cost
EXPLORATORY_RETROSPECTIVE evidence only
```

It publishes deterministic JSON and Markdown report Artifacts and then replays
the exact frozen run to zero mismatches.

Only an immutable exact-implementation-SHA WP-18Q Verification may claim the
engineering exit gate. Verification records database identity, baseline and
catalog checksums, exact commands and PASS/FAIL/NOT_RUN/BLOCKED states, safe
operational upgrade evidence, real prospective and backtest identities/hashes,
historical equivalence, replay, retained failures, and the unchanged evidence
ceiling. Current State, Roadmap, and Capability Matrix must reconcile with that
Verification before `WP18Q_EXIT_GATE = PASS` is stated.

## 14. Non-scope

WP-18Q does not perform model optimization, AutoML, arbitrary code execution,
Formal OOS, Provider reinterpretation, Model Qualification, calibration,
broker integration, Runtime cutover, Legacy deletion, unattended trading, or
evidence promotion.
