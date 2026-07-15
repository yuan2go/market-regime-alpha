# R1 — Legacy Characterization Program

> **Stage:** R1 — Repository Truth and Legacy Characterization
> **Status:** ACTIVE
> **Machine-readable inventory:** `docs/architecture/legacy-asset-inventory.json`
> **Constitutional basis:** `02-Architecture-Blueprint.md`, `08-Roadmap.md`, `09-Glossary.md`

---

## 1. Objective

R1 creates an evidence-backed map of what the current repository actually does before behavior is destructively extracted or replaced.

The purpose is not to document every line before any V2 work begins.

The purpose is to make high-risk migration decisions answerable:

```text
What behavior exists now?
Who currently owns it implicitly?
Who should own it in the target architecture?
What must be preserved before extraction?
What is Legacy-only?
What can be adapted?
What must remain frozen?
```

R1 may run in controlled parallel with R2, R3, R4 and R5.

---

## 2. Status Semantics

The machine-readable inventory uses:

```text
NOT_STARTED
PARTIAL
CHARACTERIZED
```

### `NOT_STARTED`

No meaningful source or behavior audit exists yet.

### `PARTIAL`

One or more of the following exists:

- source-code audit;
- architecture classification;
- known invariants;
- existing tests;
- documented operating behavior.

`PARTIAL` does **not** mean extraction is safe.

### `CHARACTERIZED`

Important result-affecting behavior for the intended migration scope is protected by reproducible characterization evidence such as:

- golden traces;
- deterministic fixtures;
- state-transition tests;
- contract tests;
- manifest/hash invariants;
- application output snapshots.

No current major Legacy asset is promoted to `CHARACTERIZED` merely because its code has been read. Existing tests may provide substantial characterization coverage, but promotion from `PARTIAL` should be made against an explicit migration scope rather than by test-count alone.

---

## 3. Current Classification Result

The initial inventory classifies 20 major Legacy assets across:

- data access;
- universe construction;
- dataset rehearsal;
- OOS/sealed-test infrastructure;
- experiment identity;
- signal/setup/intent semantics;
- integrated strategy logic;
- integrated timing logic;
- market environment;
- factor/proxy research;
- learned priors;
- hit-rate diagnostics;
- integrated backtesting;
- application snapshots;
- ETF baseline research;
- operational interfaces.

The current default posture is:

```text
Preserve useful behavior.
Freeze new platform-wide expansion in coupling hotspots.
Extract by target owner, not by old file boundary.
Do not retire until replacement evidence and consumer migration exist.
```

---

## 4. Highest-Risk Characterization Targets

### 4.1 Integrated `backtest.py`

Current status: `PARTIAL`

Known embedded responsibilities include:

- strategy simulation;
- attack states;
- beta-hold states;
- risk-on adds;
- trailing-profit and distribution logic;
- position targets;
- accounting;
- execution assumptions;
- research configuration;
- reporting.

Required next characterization work:

1. Identify the smallest high-value lifecycle state-transition set.
2. Capture deterministic input fixtures.
3. Record state before, decision branch, execution assumption and state after.
4. Add golden characterization tests before extracting the corresponding owner.

Do not attempt to characterize every branch before the first Candidate research milestone.

---

### 4.2 `DividendTStrategy`

Current status: `PARTIAL`, with first integrated Golden Behavior tests added.

Characterization asset:

```text
tests/legacy/test_dividend_t_strategy_characterization.py
```

The first Golden Behavior set covers three integrated output paths through:

```text
Fundamental / Retreat / Technical / Position Inputs
        ↓
Score Construction
        ↓
Legacy Candidate Selection
        ↓
MACD Policy Boundary
        ↓
Sizing
        ↓
StrategyDecision
        ↓
OrderIntent + DecisionTrace
```

Covered cases:

#### Hard `CLEAR`

Locks:

- `F < 50` hard-risk path;
- final `Signal.CLEAR`;
- base-position sell intent;
- maximum 20% clear slice under the current Legacy rule;
- `PrimarySetupCode.CLEAR`;
- `RISK_REDUCTION` intent;
- `RiskEnforcement.HARD`.

#### `BUY_T`

Locks:

- current F/R/T score behavior for a representative strong pullback fixture;
- current Python rounding result for `total_score`;
- current target-position delta sizing;
- `PULLBACK_LOW_BUY` setup;
- `MEAN_REVERSION_T` intent;
- BUY/T `OrderIntent` construction;
- original and adjusted suggested trade percentage in `DecisionTrace`.

#### `SELL_T`

Locks:

- high sell-pressure / weak risk-reward branch;
- current 15% active-position sell sizing rule;
- `PRESSURE_SELL_T` setup;
- SELL/T `OrderIntent` construction;
- final Legacy decision trace.

These tests characterize the current integrated output boundary. They do **not** promote the bundled `StrategyDecision` object into the V2 Strategy API.

Remaining characterization work includes:

- representative `STOP_T` and `REDUCE` paths where extraction requires them;
- MACD-enabled policy-change paths at the full `DividendTStrategy.evaluate()` boundary;
- explicit decomposition mapping from current bundled output into future Strategy Proposal / Portfolio / Execution owners.

The purpose is to preserve the Legacy baseline, not to keep its coupling permanently.

---

### 4.3 `CoscoTimingEngine`

Current status: `PARTIAL`, with the first integrated data-freshness gate characterization added.

New characterization asset:

```text
tests/legacy/test_cosco_timing_characterization.py
```

The first integrated fixture uses:

```text
build_sample_cosco_bars()
```

and locks the current stale-data behavior after the engine has already executed its integrated analysis path.

With:

```text
require_fresh = true
and
Data Age > Freshness Limit
```

current behavior is characterized as:

```text
data_fresh = false
freshness_status = stale
signal_blocked = true
final action = WAIT_STALE_DATA
confidence = 0
DecisionTrace.freshness_filtered_action = WAIT_STALE_DATA
DecisionTrace.final_signal = HOLD
```

The same stale fixture with:

```text
require_fresh = false
```

is characterized as:

```text
data_fresh = false
signal_blocked = false
action != WAIT_STALE_DATA
```

This characterization is important because the current integrated engine contains a real Data Quality Gate inside a Legacy timing owner.

Future migration must preserve the observed behavior before deciding which target owner should hold:

```text
Data Freshness / Quality State
        ↓
Strategy Blocking Policy
        ↓
Final Strategy Proposal Semantics
```

The test does **not** promote `CoscoTimingEngine` into the V2 Candidate, Feature, Data or Strategy kernel.

Remaining priority characterization includes:

- component availability and missing-data behavior;
- integrated output snapshots for representative market-state fixtures;
- trace of major component outputs before selective extraction;
- explicit confirmation that per-symbol scores are not being treated as cross-sectional Candidate ranks.

No new platform-wide Candidate, Feature Registry or Portfolio responsibility may be added here.

---

### 4.4 `signal_intent.py`

Current inventory status: conservatively `PARTIAL`

Substantial existing characterization coverage is already present in:

```text
tests/test_signal_intent.py
```

Existing tests cover, among other behavior:

- setup-to-intent mapping;
- complete PrimarySetupCode mapping coverage;
- unknown setup behavior in strict and compatibility modes;
- live Candidate rejection for missing intent;
- no-candidate semantics;
- confirmation timing rules;
- invalid `NONE + real confirmation` combinations;
- candidate construction and current-bar confirmation recomputation;
- risk setup priority;
- setup-code consistency;
- MACD policy downgrade and sizing interactions.

This test suite is a high-value characterization asset and should be preserved during migration.

Remaining migration work is not to rewrite these tests from scratch. It is to:

1. define the exact compatibility scope being extracted;
2. verify which existing tests form the required characterization gate for that scope;
3. add only missing DecisionTrace or adapter-specific cases;
4. preserve Legacy behavior while separating Candidate Prediction from Strategy Action in new contracts.

---

### 4.5 MACD OOS and Experiment Infrastructure

Current inventory status: conservatively `PARTIAL`

Substantial existing characterization coverage is already present in:

```text
tests/test_macd_experiments.py
```

Existing tests cover, among other behavior:

- required experiment identity fields;
- hash changes when result-affecting fields change;
- stable set/enum/float/None canonical serialization;
- distinct four-arm experiment identities;
- baseline MACD role remaining disabled;
- cache paths anchored to full experiment identity rather than display profile;
- cache metadata/config-hash integrity;
- rejection of old or tampered cache identity;
- counterfactual score/policy/interaction classification.

The new R2 `ExperimentIdentity` and Legacy MACD adapter must treat this existing implementation as the behavioral reference, not silently replace it.

Additional compatibility tests include:

```text
tests/legacy/test_macd_experiment_adapter.py
tests/legacy/test_dataset_contract_adapter.py
```

The dataset adapter explicitly prevents:

```text
Legacy FORMAL_FINAL_CANDIDATE
    → silent canonical FORMAL_RESEARCH promotion
```

Remaining priority characterization includes:

- dataset/split manifest invariants not already covered elsewhere;
- immutable run artifact non-overwrite behavior;
- sealed-test access/readiness behavior;
- normal-environment execution of the new compatibility tests against the complete repository.

---

### 4.6 `trend_snapshot.py`

Current status: `PARTIAL`, with the first dual-authority application characterization added.

Characterization asset:

```text
tests/legacy/test_trend_snapshot_characterization.py
```

The first fixture locks the current application-layer fact that:

```text
Legacy Strategy signal
and
Cosco timing_action
```

may coexist and differ for the same output row.

Representative characterized behavior includes:

```text
signal = HOLD
timing_action = BUY_T_TIMING
```

and an error-path case where:

```text
signal remains HOLD
timing_action = ERROR
```

The test does not endorse dual authority.

Its purpose is to preserve the pre-migration payload behavior before R7/R11 moves the migrated Decision Scope toward:

```text
One Authoritative Strategy Proposal
+
explicit shadow / diagnostic / baseline alternatives
```

Remaining characterization includes:

- probability-like application fields and their current non-calibrated semantics;
- additional representative payload snapshots where required by application migration;
- consumer compatibility before removing parallel action-like fields.

---

## 5. Freeze Rules During R1

The following remain active:

1. No new platform-wide responsibility in `CoscoTimingEngine`.
2. No new platform-wide lifecycle, Portfolio or Execution owner inside the integrated Legacy `backtest.py`.
3. No new global semantics added to `dividend_t.models.Signal`.
4. No market-wide Candidate system implemented by looping a symbol-specific timing engine.
5. No destructive refactor of a high-risk Legacy path before required characterization evidence exists.
6. Correctness, tests, reproducibility, trace, security and compatibility work remain allowed.

---

## 6. R1 and V2 Overlap Contract

R1 may continue while R2/R3/R4/R5 build new shared contracts and Candidate research, provided:

```text
V2 Core / Data / Universe / Features / Candidates
    do not import Legacy policy as platform truth.

Legacy
    may be adapted through explicit compatibility boundaries.

R1 characterization
    remains the prerequisite for destructive extraction,
    not for every new independent V2 contract.
```

This prevents both:

```text
Characterize the entire repository before producing new research value
```

and:

```text
Ignore Legacy behavior and rewrite everything
```

---

## 7. R1 Exit Criteria

R1 is not complete yet.

Exit requires, at minimum:

```text
Major Legacy assets classified.
Critical high-risk behavior has characterization coverage.
Future extraction targets are named by owner.
No new platform-wide feature is being added to CoscoTimingEngine or backtest.py.
```

Current progress includes:

- major asset classification;
- strong existing `signal_intent` characterization;
- strong existing MACD experiment identity characterization;
- real Legacy MACD compatibility adapter tests;
- Dataset eligibility compatibility adapter tests;
- integrated `DividendTStrategy` Golden Behavior tests;
- first `trend_snapshot.py` dual-output characterization;
- first integrated `CoscoTimingEngine` stale-data gate characterization.

This still does not imply that the integrated lifecycle, `CoscoTimingEngine`, `trend_snapshot.py` or the backtest God Object are fully characterized.

---

## 8. Next Characterization Batch

The next practical batch should prioritize:

1. execute the new Golden/adapter/Legacy characterization tests in the normal complete repository environment;
2. characterize selected `backtest.py` lifecycle transitions before R8 extraction;
3. add a small set of `CoscoTimingEngine` component-availability and missing-data snapshots;
4. add only missing sealed-test/readiness invariants not already protected by existing OOS tests;
5. preserve application compatibility when the `trend_snapshot.py` dual-authority fields are eventually migrated.

This batch reduces migration risk while allowing the R5 Candidate research path to continue in parallel.
