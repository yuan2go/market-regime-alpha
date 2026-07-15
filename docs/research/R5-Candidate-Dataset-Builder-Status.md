# R5 Candidate Discovery Rehearsal MVP — Implementation Status

> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Status:** ACTIVE — first controlled multi-date vertical slice implemented; normal-environment verification and provider-backed rehearsal remain pending
> **Research Charter:** `docs/research/R5-Candidate-Discovery-Rehearsal-Charter.md`
> **Consistency audit:** `docs/architecture/Original-Intent-to-R3-R4-Consistency-Audit.md`

---

## 1. Purpose

This document records the actual implementation authority of the current R5 increment.

The project has now implemented a controlled end-to-end research path:

```text
Controlled Rehearsal Market Observations
        ↓
Candidate Population
        ↓
Transparent Baseline Feature Materialization
        ↓
Explicit Next-Session Target Materialization
        ↓
Candidate Research Dataset Slice
        ↓
Multi-Decision-Time Candidate Panel
        ↓
Deterministic Candidate Ranking Baseline
        ↓
Cross-Sectional Rehearsal Evaluation
```

This is the first complete **controlled rehearsal vertical slice** of the independent Candidate Discovery system.

It is not yet:

- a provider-backed historical Candidate panel;
- a formal PIT validation dataset;
- an OOS-validated model;
- a promoted Alpha component;
- an Entry policy;
- a Position Lifecycle policy;
- an Exit model;
- a trading system.

---

## 2. Original-Intent Guardrails Remain Binding

The current R5 implementation preserves the original project direction:

```text
Market / ETF / Theme / Capital Context
        ↓
Candidate Discovery
        ↓
Entry
        ↓
HOLD / ADD / REDUCE / ROTATE / EXIT
```

The first R5 target is a fixed research horizon.

Therefore:

```text
Candidate Target Horizon
≠
Mandatory Holding Period
≠
Mandatory Exit Time
```

The current next-session target does not restore the earlier rejected project-wide rule of mandatory next-morning or next-session exit.

Market, ETF and Theme research remains available as a parallel program and later incremental context comparison. Their omission from the first transparent baseline is an attribution decision, not a statement that they are unimportant.

---

## 3. Controlled Rehearsal Market Inputs

Implemented:

```text
market_regime_alpha.data.rehearsal
```

The initial explicitly scoped inputs are:

```text
RehearsalDailyBar
RehearsalDecisionSnapshot
RehearsalNextSessionClose
```

These objects are deliberately labeled `Rehearsal`.

They do not:

- define a universal provider schema;
- promote Tencent, EastMoney, BaoStock, Tushare, QMT or another source;
- establish historical PIT authority;
- replace the canonical Data Constitution.

Their role is to provide a controlled consumer for the R5 research contracts.

---

## 4. Transparent Baseline Feature Set

Implemented:

```text
market_regime_alpha.features.rehearsal_baselines
```

The first four Feature Definitions are:

```text
R5 5-Session Momentum
R5 20-Session Realized Volatility
R5 20-Session Log Median Amount
R5 Decision Price versus Prior MA20
```

Their source-information families remain explicit:

```text
Momentum                    → PRICE_ONLY
Realized Volatility         → PRICE_ONLY
Log Median Amount           → TRADE_AMOUNT
Decision Price vs MA20      → PRICE_ONLY
```

This is intentionally a small baseline set.

It does not claim that the four features are independent Alpha sources.

In particular:

```text
Momentum
Volatility
Price vs MA20
```

share substantial price lineage and must not later be treated as three independent confirmations merely because they have different names.

The first feature materializer:

- reads only finalized historical observations available by Decision Time;
- uses the declared Decision Time price snapshot where required;
- ignores future history rather than leaking it;
- emits explicit `MISSING` observations when required history or the Decision Time price is unavailable;
- does not silently impute neutral numeric values.

All four Feature Definitions remain:

```text
research_status = REHEARSAL_BASELINE
```

Registration/materialization does not promote them into Predictive Factors.

---

## 5. Concrete Rehearsal Target

Implemented:

```text
market_regime_alpha.candidates.rehearsal_targets
```

The first target is:

```text
Decision Reference Price
        →
Resolved Next-Session Close
        →
Forward Return
```

Conceptually:

```text
next_session_close / decision_reference_price - 1
```

The materializer requires an explicit:

```text
next_session_date
```

and rejects future-close observations that do not match that resolved date.

This prevents:

```text
Any Later Date
```

from silently satisfying:

```text
Next Session
```

The resolved next-session date is included in the Target Materialization artifact identity.

The current materializer still relies on the caller or future calendar adapter to resolve the correct next trading session. A formal implementation must use an identified historical trading calendar.

---

## 6. Target Observation Semantics

The current statuses are:

```text
AVAILABLE
NOT_YET_OBSERVED
MISSING
INVALID
```

### `AVAILABLE`

Requires:

- finite target value;
- explicit `observed_at` after Decision Time.

### `NOT_YET_OBSERVED`

Means the future target outcome has not yet reached an observation state.

Requires:

- no value;
- no `observed_at`.

### `MISSING`

Means the target observation window has been reached or inspected but the required target value cannot be produced.

Requires:

- no usable value;
- explicit `observed_at` recording when the missing state became known.

### `INVALID`

Means the target cannot be constructed under the Target Contract, for example because the required Decision Time reference price is absent.

Requires:

- no usable value;
- explicit `observed_at` recording when invalidity became known in the materialization process.

This preserves:

```text
Future not reached yet
≠
Future reached but data missing
≠
Target invalid under the contract
```

---

## 7. Candidate Research Dataset Slice

Implemented:

```text
build_candidate_research_dataset(...)
```

One slice represents:

```text
One Decision Time
×
Complete Candidate Population
```

The output records:

- derived Dataset Identity;
- required source Dataset identities;
- effective Data Eligibility;
- Universe Identity;
- Decision Time;
- complete `population_symbols`;
- Target Identity;
- Target Materialization Artifact Identity;
- ordered Feature Definition identities;
- ordered Feature Materialization identities;
- one row for every Candidate Population symbol;
- limitations.

The central invariant is:

```text
Output Row Symbols
=
Candidate Population Symbols
```

exactly.

The builder does not drop:

- missing-feature symbols;
- unresolved-target symbols;
- losing outcomes;
- non-Top-K symbols.

---

## 8. Data Eligibility Propagation

A Candidate research slice may depend on multiple source Datasets.

The output Data Eligibility is the weakest qualification among all required source Dataset Contracts.

For example:

```text
REHEARSAL Universe Data
        +
EXPLORATORY Market Data
        ↓
EXPLORATORY Candidate Research Dataset
```

The derived Dataset cannot acquire stronger authority merely because data was joined, transformed or ranked.

---

## 9. Multi-Decision-Time Candidate Panel

Implemented:

```text
market_regime_alpha.candidates.panel
```

The panel assembles multiple identified Candidate research slices in chronological order.

It requires:

- unique Decision Times;
- unique slice Dataset identities;
- one consistent Target Identity;
- one consistent ordered Feature Definition schema.

It deliberately allows:

```text
Universe Identity at T1
≠
Universe Identity at T2
```

because a valid PIT research panel must allow historical universe membership to change over time.

The panel does not flatten all dates into one timeless Universe.

Its Data Eligibility is the weakest qualification among all included slices.

---

## 10. First Deterministic Candidate Baseline

Implemented:

```text
rank_candidates_by_feature(...)
```

The first baseline is intentionally simple:

```text
Select one registered numeric Feature
        ↓
Rank AVAILABLE finite values descending
        ↓
Emit CandidatePrediction for ranked symbols
        +
Explicit CandidateRankingRejection for unrankable symbols
```

The first controlled end-to-end fixture uses:

```text
R5 5-Session Momentum
```

as the selected baseline Feature.

The baseline:

- does not read future Target values when computing scores;
- does not emit trade actions;
- does not call the score a probability;
- does not silently drop symbols with unavailable Feature values;
- uses deterministic symbol tie-breaking;
- records Experiment Identity.

A dedicated guard test changes future target outcomes while preserving the Feature side and verifies that scores and ranks remain unchanged.

The Experiment Identity changes when the identified Candidate Dataset changes, while the scoring logic remains target-value blind.

---

## 11. Full-Population Ranking Accounting

The ranking output preserves the Candidate Population through:

```text
Predictions
+
Explicit Rejections
=
Complete Candidate Population Accounting
```

The evaluation layer independently verifies that prediction and rejection symbols exactly match the source Dataset `population_symbols`.

This prevents an externally constructed ranking object from substituting:

- unrelated symbols;
- a selected winner-only subset;
- an incomplete population;

while preserving only the same population count.

---

## 12. Cross-Sectional Rehearsal Evaluation

Implemented:

```text
market_regime_alpha.candidates.evaluation
```

The first descriptive metrics include:

```text
Ranking Coverage
Target Coverage
Evaluated Prediction Coverage
Spearman RankIC
Top-K Observed Target Mean
Ranked Observed Target Mean
```

The evaluator uses only Target observations explicitly marked:

```text
AVAILABLE
```

It does not reinterpret:

```text
MISSING
INVALID
NOT_YET_OBSERVED
```

as numeric zero.

The panel evaluator aggregates identified per-slice evaluations chronologically.

Current aggregate metrics such as:

```text
mean_slice_rank_ic
mean_slice_top_k_target
```

are descriptive rehearsal summaries only.

They are not:

- statistical significance claims;
- OOS evidence;
- formal promotion evidence;
- strategy P&L.

---

## 13. Controlled End-to-End Fixture

Added:

```text
tests/candidates/test_r5_rehearsal_pipeline.py
```

The fixture constructs two Candidate Decision Times and exercises:

```text
Historical Rehearsal Bars
        ↓
Decision Time Snapshots
        ↓
Baseline Feature Materialization
        ↓
Explicit Next-Session Target Materialization
        ↓
Candidate Dataset Slices
        ↓
Multi-Date Panel
        ↓
Single-Feature Candidate Rankings
        ↓
Panel Evaluation
```

The fixture also preserves one Candidate with missing selected Feature information through an explicit:

```text
FEATURE_MISSING
```

ranking rejection.

The fixture is controlled pipeline evidence only.

It must not be reported as positive market Alpha.

---

## 14. Test Assets Added

Current R5 test assets include:

```text
tests/candidates/test_dataset_builder.py
tests/candidates/test_target_state_contracts.py
tests/candidates/test_panel.py
tests/candidates/test_rehearsal_materializers.py
tests/candidates/test_r5_rehearsal_pipeline.py
tests/candidates/test_baseline_ranking_evaluation_guards.py
```

They are designed to cover:

- complete Candidate Population preservation;
- explicit Feature missingness;
- Target state separation;
- weakest-input Data Eligibility propagation;
- stable Dataset identity behavior;
- future Feature leakage prevention;
- explicit resolved next-session date;
- changing PIT Universe identities across Decision Times;
- stable panel ordering;
- deterministic one-Feature ranking;
- explicit ranking rejections;
- target-value isolation from ranking scores;
- exact Candidate Population accounting at evaluation time;
- descriptive multi-date rehearsal evaluation.

---

## 15. Execution Status

The current tool environment again attempted to clone the latest GitHub repository and failed because DNS resolution for:

```text
github.com
```

was unavailable.

Therefore this document does **not** claim:

```text
latest HEAD pytest passed
latest HEAD ruff passed
latest HEAD mypy passed
```

The implementation and tests are committed.

The new R5 modules are included in the repository mypy scope.

The normal development environment or CI must execute the complete suite before the current implementation receives higher engineering authority.

---

## 16. Current R5 Status

```text
Original-intent consistency audit                 COMPLETE
R4 minimum Feature metadata correction            COMPLETE
R5 Research Charter                               IMPLEMENTED
Target Observation contract                       IMPLEMENTED
Single-Decision-Time Candidate dataset slice      IMPLEMENTED
Full-population dataset preservation              IMPLEMENTED
Data Eligibility non-inflation                    IMPLEMENTED

Controlled rehearsal market observations          IMPLEMENTED
Four transparent baseline Feature definitions     IMPLEMENTED
Baseline Feature materializer                     IMPLEMENTED
Concrete next-session Target materializer         IMPLEMENTED
Explicit resolved next-session date               IMPLEMENTED
Multi-Decision-Time panel assembly                 IMPLEMENTED
Deterministic one-Feature Candidate ranker         IMPLEMENTED
Explicit ranking rejection accounting             IMPLEMENTED
Cross-sectional rehearsal evaluation              IMPLEMENTED
Two-date controlled end-to-end fixture             ADDED / PENDING NORMAL-ENV EXECUTION

Provider-backed historical Candidate panel        NOT YET IMPLEMENTED
Historical PIT Universe artifact loader            NOT YET IMPLEMENTED
Historical trading-calendar adapter                NOT YET IMPLEMENTED
Real provider Decision Time snapshot materializer  NOT YET IMPLEMENTED
Real provider next-session Target materializer     NOT YET IMPLEMENTED
Naive baseline comparison ladder beyond B0         NOT YET IMPLEMENTED
Immutable R5 run artifact                          NOT YET IMPLEMENTED
Formal chronological/OOS Candidate validation      NOT YET IMPLEMENTED
Formal Candidate evidence                          NOT AVAILABLE
```

R5 is therefore:

```text
NOT COMPLETE
```

but the first controlled Candidate Discovery vertical slice is now implemented.

---

## 17. Next Implementation Sequence

The next sequence should move from controlled fixture capability to a real reproducible rehearsal artifact:

```text
1. Execute current R3/R4/R5 suite in a complete repository environment
        ↓
2. Implement a versioned historical PIT Universe artifact loader
        ↓
3. Implement a historical trading-calendar / next-session resolver
        ↓
4. Adapt one real rehearsal market dataset into the controlled R5 observation boundary
        ↓
5. Build a multi-date provider-backed Candidate rehearsal panel
        ↓
6. Run B0 baseline over actual rehearsal dates
        ↓
7. Write an immutable R5 rehearsal run artifact
        ↓
8. Compare B0 with the next simple baseline rather than jumping directly to complex models
```

Parallel work remains allowed for:

- professional data capability assessment;
- ETF / Theme / Market context research;
- high-risk Legacy characterization.

These parallel programs must not silently become hard gates for the first Candidate baseline.

---

## 18. Non-Goals of the Current Increment

The current implementation does not:

- emit `ENTER / HOLD / ADD / REDUCE / ROTATE / EXIT`;
- define a mandatory Exit time;
- implement direct ETF Rotation trading;
- claim ETF/Theme context is unimportant;
- use `CoscoTimingEngine` as the universal cross-sectional ranker;
- bulk-migrate Legacy F/R/T/C, MACD, Chan or Tuishen scores;
- train a complex model;
- report calibrated probability;
- claim positive Alpha;
- claim formal OOS evidence;
- open sealed-test data;
- grant live trading authority.

---

## 19. Implementation Principle

> **The first R5 vertical slice is successful only if the whole historical opportunity population remains visible from Dataset construction through ranking and evaluation. Missing information must remain explicit, future outcomes must remain on the Target side, changing PIT universes must remain date-specific, and simple baselines must be established before complexity is allowed to claim incremental value.**
