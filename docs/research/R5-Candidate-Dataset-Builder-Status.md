# R5 Candidate Discovery Rehearsal MVP — Implementation Status

> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Status:** ACTIVE — controlled multi-date vertical slice and minimum opportunity Target bundle implemented; normal-environment verification and provider-backed rehearsal remain pending
> **Research Charter:** `docs/research/R5-Candidate-Discovery-Rehearsal-Charter.md`
> **Current consistency audit:** `docs/architecture/Original-Intent-to-R5-Consistency-Audit.md`

---

## 1. Purpose

This document records the actual implementation authority of the current R5 increment.

The project now has a controlled end-to-end research path:

```text
Controlled Rehearsal Market Observations
        ↓
Candidate Population
        ↓
Transparent Baseline Feature Materialization
        ↓
Identity-Distinct Opportunity Targets
Close Return / MFE / MAE
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

## 2. Original-Intent Guardrails

The latest preserved project direction remains:

```text
Market / ETF / Theme / Capital Context
        ↓
Candidate Discovery
        ↓
Entry
        ↓
HOLD / ADD / REDUCE / ROTATE / EXIT
```

The current next-session Target family is a research horizon.

Therefore:

```text
Candidate Target Horizon
≠
Mandatory Holding Period
≠
Mandatory Exit Time
```

Market, ETF and Theme research remains available as a parallel program and later incremental-context comparison.

The current B0 omission of those inputs is an attribution choice, not an architectural demotion.

---

## 3. Consistency Audit Correction Before Provider-Backed Data

The latest original-intent audit found no direction-level contradiction.

It did find one material target-coverage gap:

```text
The controlled R5 implementation had one concrete next-session close-return Target,
while the preserved Candidate objective also includes upside opportunity and adverse excursion.
```

The correction is now implemented before provider-backed rehearsal work.

The minimum R5 opportunity Target set is:

```text
Next-Session Close Return
Next-Session Maximum Favorable Excursion (MFE)
Next-Session Maximum Adverse Excursion (MAE)
```

Each remains a separate Target Contract and Target Identity.

They may be grouped in one reproducibility bundle but are never merged into one ambiguous target.

---

## 4. Controlled Rehearsal Market Inputs

Implemented:

```text
market_regime_alpha.data.rehearsal
```

The current scoped inputs are:

```text
RehearsalDailyBar
RehearsalDecisionSnapshot
RehearsalNextSessionClose
RehearsalNextSessionBar
```

These objects are deliberately labeled `Rehearsal`.

They do not:

- define a universal provider schema;
- promote any free or professional provider;
- establish historical PIT authority;
- replace the Data Constitution.

`RehearsalNextSessionBar` adds controlled future OHLC observation for separate Close Return, MFE and MAE Target materialization.

---

## 5. Transparent Baseline Feature Set

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

Source-information families remain explicit:

```text
Momentum                    → PRICE_ONLY
Realized Volatility         → PRICE_ONLY
Log Median Amount           → TRADE_AMOUNT
Decision Price vs MA20      → PRICE_ONLY
```

The project does not treat the three price-derived features as independent confirmation merely because they have different names.

The materializer:

- reads only finalized historical observations available by Decision Time;
- uses the declared Decision Time price snapshot where required;
- ignores future history rather than leaking it;
- emits explicit `MISSING` values;
- does not silently impute neutral numeric values;
- enforces the R5 14:55 Asia/Shanghai Decision Time.

All four remain:

```text
research_status = REHEARSAL_BASELINE
```

---

## 6. Minimum Opportunity Target Bundle

Implemented:

```text
market_regime_alpha.candidates.target_bundle
market_regime_alpha.candidates.rehearsal_opportunity_targets
```

### Separate Target identities

```text
Close Return
= next_session_close / decision_reference_price - 1

MFE
= max(0, next_session_high / decision_reference_price - 1)

MAE
= min(0, next_session_low / decision_reference_price - 1)
```

Interpretation:

- Close Return remains the first B0 primary evaluation Target;
- MFE is an observed upside-opportunity outcome, not an assumption of executable sale at the high;
- MAE is an observed adverse-excursion outcome, not an automatic stop-loss policy.

### `TargetMaterializationBundle`

The bundle:

- requires at least one Target Materialization;
- requires unique Target identities;
- requires unique member Artifact identities;
- requires one shared Universe Identity;
- requires one shared Decision Time;
- orders members deterministically by Target Identity;
- has its own content-derived bundle Artifact Identity.

The bundle is a reproducibility convenience only.

It does not create one merged Target identity.

---

## 7. Next-Session Resolution

The Target materializers require an explicit:

```text
next_session_date
```

and reject observations that do not match that resolved date.

This prevents:

```text
Any Later Date
```

from silently satisfying:

```text
Next Session
```

The resolved next-session date enters the Target Materialization identity.

The current materializer still relies on the caller or a future calendar adapter to resolve the correct historical next trading session.

A formal implementation must use an identified historical trading calendar.

---

## 8. Candidate Research Dataset Slice

Implemented:

```text
build_candidate_research_dataset(...)
```

One slice represents:

```text
One Decision Time
×
Complete Candidate Population
×
One explicit Target Identity
```

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

Separate Close Return, MFE and MAE Candidate datasets may share the same identified Feature side while retaining different Target identities and Target Materialization artifacts.

---

## 9. Data Eligibility Propagation

A Candidate research slice may depend on multiple source Datasets.

The output Data Eligibility is the weakest qualification among all required inputs.

For example:

```text
REHEARSAL Universe Data
        +
EXPLORATORY Market Data
        ↓
EXPLORATORY Candidate Research Dataset
```

Derived research artifacts cannot acquire stronger data authority merely because data was joined, transformed, bundled or ranked.

---

## 10. Multi-Decision-Time Candidate Panel

Implemented:

```text
market_regime_alpha.candidates.panel
```

The panel requires:

- unique Decision Times;
- unique slice Dataset identities;
- one consistent Target Identity per panel;
- one consistent ordered Feature Definition schema.

It deliberately allows:

```text
Universe Identity at T1
≠
Universe Identity at T2
```

because a valid PIT panel must allow historical membership to change.

A Close Return panel, MFE panel and MAE panel remain separate target-specific panels.

---

## 11. First Deterministic Candidate Baseline

Implemented:

```text
rank_candidates_by_feature(...)
```

The first controlled end-to-end fixture uses:

```text
R5 5-Session Momentum
```

The baseline:

- does not read future Target values when computing scores;
- does not emit trade actions;
- does not call the score a probability;
- does not silently drop symbols with unavailable Feature values;
- uses deterministic tie-breaking;
- records Experiment Identity.

Predictions plus explicit rejections must exactly account for the complete Candidate Population.

---

## 12. Cross-Sectional Rehearsal Evaluation

Implemented:

```text
market_regime_alpha.candidates.evaluation
```

Current descriptive metrics include:

```text
Ranking Coverage
Target Coverage
Evaluated Prediction Coverage
Spearman RankIC
Top-K Observed Target Mean
Ranked Observed Target Mean
```

The evaluator uses only Target observations explicitly marked `AVAILABLE`.

It does not reinterpret `MISSING`, `INVALID` or `NOT_YET_OBSERVED` as numeric zero.

Current aggregate metrics are descriptive rehearsal summaries only.

They are not:

- statistical significance claims;
- OOS evidence;
- formal promotion evidence;
- strategy P&L.

---

## 13. Controlled Test Assets

Current R5 tests cover, among other invariants:

- complete Candidate Population preservation;
- explicit Feature missingness;
- explicit Target state semantics;
- weakest-input Data Eligibility propagation;
- future Feature rejection;
- target chronology;
- multi-date panel assembly;
- target-blind ranking;
- exact predictions + rejections population accounting;
- two-date controlled end-to-end rehearsal wiring;
- 14:55 Asia/Shanghai Decision Time enforcement;
- explicit next-session date binding;
- identity-distinct Close Return / MFE / MAE Target bundle;
- controlled next-session OHLC validation.

The controlled fixture may produce deliberately perfect toy metrics to test wiring.

Such fixture metrics are not market evidence.

---

## 14. R1 Legacy Characterization Continues

R1 remains `ACTIVE` in parallel.

Current added characterization includes:

- `DividendTStrategy` integrated Golden Behavior cases;
- `trend_snapshot` dual-output behavior;
- `CoscoTimingEngine` stale-data gate behavior.

This does not promote Legacy strategy or timing objects into the V2 Candidate system.

---

## 15. Execution Status

The current tool environment has not provided a complete latest-HEAD repository execution environment.

Therefore this document does **not** claim:

```text
latest HEAD pytest passed
latest HEAD ruff passed
latest HEAD mypy passed
```

The implementation and tests are committed and must run in the normal repository development environment or CI before implementation authority is increased.

The new modules are included in the repository mypy scope.

---

## 16. Current R5 Status

```text
Original-intent-to-R5 consistency audit             COMPLETE
R4 minimum Feature metadata correction              COMPLETE
R5 Research Charter                                 UPDATED / ACTIVE
Target Observation contract                         IMPLEMENTED
Single-Decision-Time Candidate dataset slice        IMPLEMENTED
Full-population preservation                        IMPLEMENTED
Data Eligibility non-inflation                      IMPLEMENTED
Controlled Rehearsal market observations            IMPLEMENTED
Four transparent baseline Features                  IMPLEMENTED
Baseline Feature materializer                       IMPLEMENTED
Close Return Target materializer                    IMPLEMENTED
Explicit resolved next-session date                 IMPLEMENTED
Close Return / MFE / MAE Target bundle             IMPLEMENTED
Multi-Decision-Time panel assembly                   IMPLEMENTED
Deterministic one-feature Candidate ranker           IMPLEMENTED
Explicit ranking rejection accounting               IMPLEMENTED
Cross-sectional rehearsal evaluation                IMPLEMENTED
Two-date controlled end-to-end fixture               IMPLEMENTED

Normal full-repository test execution                PENDING
Historical Trading Calendar resolver                NOT YET IMPLEMENTED
Historical PIT Universe artifact loader             NOT YET IMPLEMENTED
Provider-backed rehearsal market artifact           NOT YET IMPLEMENTED
Provider-backed multi-date Candidate panels          NOT YET IMPLEMENTED
B1 transparent composite baseline                   NOT YET IMPLEMENTED
Immutable R5 run artifact                           NOT YET IMPLEMENTED
Chronological/OOS Candidate validation              NOT YET IMPLEMENTED
Formal Candidate evidence                           NOT AVAILABLE
```

---

## 17. Next Implementation Sequence

The next sequence is:

```text
1. Execute current R3/R4/R5 tests in a complete repository environment
        ↓
2. Historical Trading Calendar Resolver
        ↓
3. Historical PIT Universe Artifact Loader
        ↓
4. Provider-Backed Rehearsal Market Artifact
        ↓
5. Materialize Close Return / MFE / MAE for real rehearsal dates
        ↓
6. Build provider-backed target-specific Candidate panels
        ↓
7. Run B0 and first B1 controlled comparison
        ↓
8. Write immutable R5 run artifact
```

Market/ETF/Theme exploratory research and R1 Legacy characterization may proceed in parallel.

The project must not wait for every future data source before running a clearly labeled rehearsal pipeline, but it must not claim formal evidence from data that lacks the required PIT authority.

---

## 18. Non-Goals of the Current Increment

This increment does not:

- emit ENTER/HOLD/ADD/REDUCE/ROTATE/EXIT;
- define a mandatory exit time;
- implement ETF Rotation;
- claim ETF/Theme context is unimportant;
- use `CoscoTimingEngine` as the cross-sectional ranker;
- migrate all Legacy factors;
- train a complex model;
- report calibrated probability;
- claim positive Alpha;
- open sealed-test data;
- grant live trading authority.

---

## 19. Implementation Principle

> **The current R5 system is successful only if it preserves the complete historical opportunity set and makes missingness, Target identity, opportunity/risk outcomes, data authority and temporal direction explicit. A smaller honest panel is more valuable than a larger panel produced by silently dropping difficult rows, collapsing distinct outcomes, or mixing future results into the Feature side.**
