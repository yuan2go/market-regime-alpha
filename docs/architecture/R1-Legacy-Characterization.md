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

R1 may run in controlled parallel with R2.

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

No current major Legacy asset is promoted to `CHARACTERIZED` merely because its code has been read.

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

Current status: `PARTIAL`

Required next characterization work:

- representative `StrategyDecision` golden traces;
- `SignalIntent` and setup mapping invariants;
- sizing/output behavior for representative Legacy position states;
- preservation of current MACD policy interaction where used.

The purpose is to preserve the Legacy baseline, not to promote it as the V2 Strategy API.

---

### 4.3 `CoscoTimingEngine`

Current status: `PARTIAL`

Required next characterization work:

- integrated output snapshots for representative fixtures;
- component availability/missing-data behavior;
- trace of major component outputs before selective extraction;
- explicit confirmation that per-symbol scores are not being treated as cross-sectional Candidate ranks.

No new platform-wide Candidate, Feature Registry or Portfolio responsibility may be added here.

---

### 4.4 `signal_intent.py`

Current status: `PARTIAL`

Priority characterization:

- strict setup-to-intent mapping;
- invalid setup rejection;
- confirmation timing rules;
- risk-enforcement invariants;
- DecisionTrace preservation.

This is a high-value semantic migration seed for future compatibility adapters.

---

### 4.5 MACD OOS and Experiment Infrastructure

Current status: `PARTIAL`

Priority characterization:

- experiment identity hashing invariants;
- four-arm controlled-context invariants;
- dataset/split manifest invariants;
- immutable run artifact non-overwrite behavior;
- sealed-test access/readiness behavior.

R2 will generalize only the shared identity principles. The Legacy MACD implementation remains the behavioral reference until a compatibility path is proven.

---

### 4.6 `trend_snapshot.py`

Current status: `PARTIAL`

Priority characterization:

- current `signal` output;
- current `timing_action` output;
- probability-like fields and their current non-calibrated semantics;
- application payload snapshots for representative inputs.

The migration goal is one authoritative Strategy Proposal per migrated Decision Scope, with alternative engines explicitly labeled shadow/diagnostic/baseline.

---

## 5. Freeze Rules During R1

The following are active immediately:

1. No new platform-wide responsibility in `CoscoTimingEngine`.
2. No new platform-wide lifecycle, Portfolio or Execution owner inside the integrated Legacy `backtest.py`.
3. No new global semantics added to `dividend_t.models.Signal`.
4. No market-wide Candidate system implemented by looping a symbol-specific timing engine.
5. No destructive refactor of a high-risk Legacy path before required characterization evidence exists.
6. Correctness, tests, reproducibility, trace, security and compatibility work remain allowed.

---

## 6. R1 and R2 Overlap Contract

R2 may build new shared contracts while R1 continues, provided:

```text
R2 Core
    does not import Legacy policy as platform truth.

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

The current inventory satisfies the first classification step and identifies the highest-risk characterization backlog. It does not claim that all critical behavior is already characterized.

---

## 8. Next Characterization Batch

The next practical batch should prioritize:

1. `signal_intent.py` invariant tests;
2. generic Experiment Identity compatibility with `MACDExperimentIdentity` semantics;
3. a small set of `DividendTStrategy` golden decision traces;
4. selected `backtest.py` lifecycle transition characterization;
5. `trend_snapshot.py` dual-authority payload characterization.

This batch directly reduces migration risk for R2, R7 and R8 without delaying the R3–R5 Candidate path.
