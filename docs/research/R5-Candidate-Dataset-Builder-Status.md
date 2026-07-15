# R5 Candidate Discovery Rehearsal MVP — Implementation Status

> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Status:** ACTIVE — controlled multi-date vertical slice, opportunity Target bundle, and historical Calendar/Universe/Eligibility artifact spine implemented; provider-backed rehearsal remains pending
> **Research Charter:** `docs/research/R5-Candidate-Discovery-Rehearsal-Charter.md`
> **Current consistency audit:** `docs/architecture/Original-Intent-to-R5-Consistency-Audit.md`

---

## 1. Purpose

This document records the actual implementation authority of the current R5 increment.

The project now has two connected research layers.

### Controlled Candidate research vertical slice

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

### Historical research-input artifact spine

```text
Identified Trading Calendar Artifact
        ↓
Resolved Next Trading Session

Exact-Date PIT Universe Membership Artifact
        +
Exact-Decision-Time Trading Eligibility Artifact
        ↓
Candidate Population
```

This remains a research system under development.

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

## 3. Consistency-Audit Correction Before Provider-Backed Data

The current original-intent audit found no direction-level contradiction.

It did find one material target-coverage gap:

```text
The controlled R5 implementation initially had one concrete next-session close-return Target,
while the preserved Candidate objective also includes upside opportunity and adverse excursion.
```

The correction was implemented before provider-backed rehearsal work.

The minimum R5 opportunity Target set is now:

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

`RehearsalNextSessionBar` provides controlled future OHLC observations for separate Close Return, MFE and MAE Target materialization.

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

## 7. Identified Historical Trading Calendar

Implemented:

```text
market_regime_alpha.data.trading_calendar
```

Core objects:

```text
TradingSession
TradingCalendarArtifact
```

The calendar:

- contains explicit identified trading sessions;
- has a content-derived Artifact Identity;
- records source Dataset Identity, market, calendar version and timezone;
- resolves the next session from the explicit session list;
- never infers trading days from Monday-Friday weekdays;
- never manufactures missing sessions;
- fails when no later identified session exists.

The R5 Target pipeline can now use:

```text
materialize_r5_opportunity_targets_from_calendar(...)
```

so `next_session_date` no longer needs to be guessed manually by the Candidate caller.

The resolved next session is still only as trustworthy as the identified calendar artifact supplied to the resolver.

---

## 8. Legacy Trading-Calendar Compatibility Boundary

Implemented:

```text
market_regime_alpha.legacy.trading_calendar_adapter
```

The adapter preserves the existing Legacy rehearsal sidecar invariant used by `formal_dataset_builder.py`:

```text
set(trading_dates)
=
set(session.trade_date for sessions carrying session_close)
```

It:

- rejects missing session-close coverage;
- rejects duplicate dates;
- converts naive Legacy close timestamps only under an explicit configured timezone;
- exposes a canonical `TradingCalendarArtifact` without making V2 Core depend on Legacy modules.

This is a compatibility boundary, not proof that the Legacy sidecar has formal provider authority.

---

## 9. Historical PIT Universe Membership Artifact

Implemented:

```text
market_regime_alpha.universe.artifacts
```

Core objects:

```text
HistoricalUniverseMembershipRecord
HistoricalPITUniverseArtifact
```

The artifact stores exact-date membership under an explicit:

```text
effective_time_convention
```

It requires:

- explicit historical `as_of_date` records;
- unique date-symbol keys;
- deterministic Artifact Identity;
- deterministic per-date Universe Identity;
- exact-date snapshot resolution;
- no silent carry-forward to a missing date.

Historical membership may change across dates.

The artifact answers:

```text
Does this instrument belong to the declared research population on this date?
```

It does **not** answer:

```text
Is it tradable?
Is it buyable?
Is it liquid enough?
Can an order execute?
```

---

## 10. Legacy Universe Sidecar Compatibility Boundary

Implemented:

```text
market_regime_alpha.legacy.universe_sidecar_adapter
```

The existing Legacy field:

```text
eligible
```

is mapped only to:

```text
membership under the Legacy sidecar's own universe method
```

It is not promoted to canonical Trading Eligibility.

The Legacy sidecar provides a date but no independent availability/effective timestamp.

The adapter therefore records the explicit rehearsal compatibility assumption:

```text
LEGACY_AS_OF_DATE_EFFECTIVE_FROM_LOCAL_DAY_START
```

This assumption enters the Historical PIT Universe Artifact identity.

It must not be treated as a universal rule for future providers.

Provider-backed formal data must declare its actual effective-time and availability semantics.

---

## 11. Historical Trading Eligibility Artifact

Implemented:

```text
market_regime_alpha.universe.eligibility_artifacts
```

Core objects:

```text
HistoricalTradingEligibilityRecord
HistoricalTradingEligibilityArtifact
```

The artifact stores explicit, versioned policy results:

```text
ELIGIBLE
INELIGIBLE
UNKNOWN
```

plus explicit reasons.

It does not infer policy from raw fields such as:

- ST state;
- suspension;
- price-limit state;
- listing age;
- liquidity;
- risk events.

Those inputs must later feed an explicitly versioned Eligibility Policy / Materializer.

The current artifact requires an exact snapshot at the Candidate Decision Time.

It does not silently carry:

```text
14:50 eligibility
```

forward to:

```text
14:55 Candidate Decision Time
```

without an identified materialization process.

---

## 12. Historical Candidate Population Assembly

Implemented:

```text
build_candidate_population_from_historical_artifacts(...)
```

The chain is:

```text
Exact-Date PIT Universe Membership
        ∩
Exact-Decision-Time Trading Eligibility
        =
Candidate Population
```

This preserves the constitutional distinction:

```text
Universe Membership
≠
Trading Eligibility
≠
Execution Feasibility
```

A member that is explicitly `INELIGIBLE` is excluded.

An explicitly eligible instrument that is not a Universe member is also excluded.

---

## 13. Candidate Research Dataset and Panel

Implemented:

```text
build_candidate_research_dataset(...)
market_regime_alpha.candidates.panel
```

One Dataset slice represents:

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

Separate Close Return, MFE and MAE Candidate datasets may share the same identified Feature side while retaining different Target identities and Target Materialization artifacts.

A multi-date panel requires one consistent Target Identity and Feature schema while allowing PIT Universe Identity to change by date.

---

## 14. First Deterministic Candidate Baseline and Evaluation

Implemented:

```text
rank_candidates_by_feature(...)
market_regime_alpha.candidates.evaluation
```

The first controlled fixture uses:

```text
R5 5-Session Momentum
```

The baseline:

- does not read future Target values when computing scores;
- does not emit trade actions;
- does not call the score a probability;
- does not silently drop unavailable-feature symbols;
- records explicit rejections;
- requires predictions + rejections to account for the complete Candidate Population;
- records Experiment Identity.

Current descriptive metrics include:

```text
Ranking Coverage
Target Coverage
Evaluated Prediction Coverage
Spearman RankIC
Top-K Observed Target Mean
Ranked Observed Target Mean
```

They are rehearsal diagnostics only.

They are not:

- statistical significance claims;
- OOS evidence;
- formal promotion evidence;
- strategy P&L.

---

## 15. Controlled Test Assets

Current R5/R3 input tests cover, among other invariants:

- complete Candidate Population preservation;
- explicit Feature missingness;
- explicit Target states;
- weakest-input Data Eligibility propagation;
- target-blind ranking;
- exact predictions + rejections population accounting;
- 14:55 Asia/Shanghai Decision Time enforcement;
- identity-distinct Close Return / MFE / MAE Target bundle;
- controlled next-session OHLC validation;
- explicit calendar session resolution without weekday inference;
- calendar sidecar consistency;
- calendar-resolved next-session Target materialization;
- historical Universe membership change across dates;
- no missing-date Universe carry-forward;
- explicit Universe effective-time convention in identity;
- exact-decision-time Trading Eligibility;
- no stale eligibility carry-forward;
- historical Membership ∩ Eligibility Candidate Population assembly.

Controlled fixture metrics are not market evidence.

---

## 16. R1 Legacy Characterization Continues

R1 remains `ACTIVE` in parallel.

Current added characterization includes:

- `DividendTStrategy` integrated Golden Behavior cases;
- `trend_snapshot` dual-output behavior;
- `CoscoTimingEngine` stale-data gate behavior.

This does not promote Legacy strategy or timing objects into the V2 Candidate system.

---

## 17. Execution Status

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

## 18. Current R5 Status

```text
Original-intent-to-R5 consistency audit                 COMPLETE
R5 Research Charter                                     UPDATED / ACTIVE
Controlled multi-date Candidate vertical slice          IMPLEMENTED
Four transparent baseline Features                      IMPLEMENTED
Close Return / MFE / MAE Target bundle                 IMPLEMENTED
Deterministic B0 Candidate ranker                        IMPLEMENTED
Cross-sectional rehearsal evaluation                    IMPLEMENTED

Historical Trading Calendar Artifact                    IMPLEMENTED
Legacy Trading Calendar adapter                         IMPLEMENTED
Calendar-resolved next-session Target path              IMPLEMENTED
Historical PIT Universe Membership Artifact             IMPLEMENTED
Explicit Universe effective-time convention             IMPLEMENTED
Legacy Universe sidecar adapter                         IMPLEMENTED
Historical Trading Eligibility Artifact                 IMPLEMENTED
Historical Membership ∩ Eligibility Candidate assembly  IMPLEMENTED

Normal full-repository test execution                    PENDING
Versioned raw-field Eligibility Policy / Materializer    NOT YET IMPLEMENTED
Provider-backed rehearsal market artifact               NOT YET IMPLEMENTED
Provider-backed multi-date Candidate panels              NOT YET IMPLEMENTED
B1 transparent composite baseline                       NOT YET IMPLEMENTED
Immutable R5 run artifact                               NOT YET IMPLEMENTED
Chronological/OOS Candidate validation                  NOT YET IMPLEMENTED
Formal Candidate evidence                               NOT AVAILABLE
```

---

## 19. Next Implementation Sequence

The next sequence is:

```text
1. Execute current R3/R4/R5 tests in a complete repository environment
        ↓
2. Define one explicit rehearsal Trading Eligibility Policy / Materializer
   over identified historical raw eligibility fields
        ↓
3. Build one provider-backed / provider-export-backed REHEARSAL market artifact
        ↓
4. Materialize exact Candidate Populations and Close Return / MFE / MAE
        ↓
5. Build provider-backed target-specific Candidate panels
        ↓
6. Run B0 and first B1 controlled comparison
        ↓
7. Write immutable R5 run artifact
```

Market/ETF/Theme exploratory research and R1 Legacy characterization may proceed in parallel.

The project must not wait for every future data source before running a clearly labeled rehearsal pipeline, but it must not claim formal evidence from data that lacks the required PIT authority.

---

## 20. Non-Goals of the Current Increment

This increment does not:

- emit ENTER/HOLD/ADD/REDUCE/ROTATE/EXIT;
- define a mandatory exit time;
- implement ETF Rotation;
- claim ETF/Theme context is unimportant;
- use `CoscoTimingEngine` as the cross-sectional ranker;
- treat date-level Legacy membership semantics as universal provider PIT truth;
- infer Trading Eligibility from incomplete raw fields without a versioned policy;
- migrate all Legacy factors;
- train a complex model;
- report calibrated probability;
- claim positive Alpha;
- open sealed-test data;
- grant live trading authority.

---

## 21. Implementation Principle

> **The current R5 system is successful only if it preserves the complete historical opportunity set and makes missingness, Target identity, opportunity/risk outcomes, Calendar identity, Universe effective time, Trading Eligibility policy, data authority and temporal direction explicit. A smaller honest panel is more valuable than a larger panel produced by silently carrying stale states, collapsing distinct outcomes, or mixing future results into the Feature side.**
