# R5 Candidate Discovery Rehearsal Charter

> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Status:** ACTIVE — initial rehearsal research program
> **Authority:** Research Charter for the first independent cross-sectional Candidate Discovery vertical slice
> **Constitutional basis:** `00-Project-Vision.md`, `03-Research-Framework.md`, `04-Data-Constitution.md`, `05-Factor-Constitution.md`, `07-Validation-Constitution.md`, `08-Roadmap.md`, `09-Glossary.md`
> **Consistency audit:** `docs/architecture/Original-Intent-to-R5-Consistency-Audit.md`

---

## 1. Research Question

The first R5 research question is deliberately narrow:

> **At a declared late-session decision time, can a small set of transparent and cross-sectionally comparable features rank a reproducible A-share Candidate Population by next-session forward opportunity better than simple naive baselines?**

This is a Candidate Discovery rehearsal question.

It is not:

- a complete trading strategy;
- a universal overnight strategy;
- a fixed next-morning exit rule;
- an Entry policy;
- a Position Lifecycle policy;
- an Exit model;
- an ETF Rotation strategy;
- a production promotion claim.

---

## 2. Why This Is the First R5 Program

The project needs one real research consumer for the new Data → Universe → Feature → Candidate spine.

The first program should be:

- simple enough to attribute;
- broad enough to exercise cross-sectional research contracts;
- narrow enough to reproduce;
- independent from Legacy single-symbol timing authority;
- usable with EXPLORATORY or REHEARSAL data without overstating evidence.

A next-session target family is selected for this rehearsal because it is concrete and measurable.

This does **not** redefine Candidate Discovery as an overnight-only system.

Future Candidate research may use:

- multi-session return targets;
- intraday opportunity-window targets;
- breakout-continuation targets;
- expected holding-horizon targets;
- regime-conditioned opportunity targets.

---

## 3. Decision-Time Contract

The initial rehearsal decision-time convention is:

```text
T day, 14:55 Asia/Shanghai
```

Only information that is eligible and available under its data/feature contract at or before that Decision Time may be used.

The initial implementation may use fixture or controlled rehearsal data.

A later provider-specific implementation must prove:

- bar finalization semantics;
- actual availability time;
- adjustment basis;
- historical universe membership;
- historical trading eligibility;
- required sidecar availability.

The clock time is part of this Research Charter, not a universal project rule.

---

## 4. Candidate Population

The initial population is:

```text
Declared PIT / reproducible Universe Membership
        ∩
Explicit Trading Eligibility
        =
Candidate Population
```

The rehearsal must preserve the complete Candidate Population for every Decision Time.

It must not store only:

- eventual winners;
- Top-K predictions;
- executed trades;
- symbols with complete features;
- symbols that later produced valid targets.

A valid empty Candidate Population remains a valid research outcome.

---

## 5. Target Contracts

### 5.1 B0 primary target

The initial B0 primary evaluation target remains:

```text
Decision-Reference-to-Next-Session-Close Return
```

Conceptually:

```text
next_session_close / decision_reference_price - 1
```

The exact Target Contract must identify:

- Target Identity;
- Decision Time convention;
- Decision reference-price convention;
- next-session calendar rule;
- target observation availability;
- missing/invalid target behavior;
- version.

For the first controlled rehearsal, the Decision Reference Price may be the finalized price of the declared decision snapshot when the dataset contract supports that convention.

This target is a **research outcome**.

It is not an execution return and does not imply that a real position must be exited at the next-session close.

---

### 5.2 Minimum opportunity-profile Target bundle before provider-backed rehearsal

The preserved original project objective includes both forward upside opportunity and adverse excursion.

Therefore, before provider-backed R5 rehearsal becomes the next major data milestone, the minimum Target set is:

```text
1. Next-Session Close Return
2. Next-Session Maximum Favorable Excursion (MFE)
3. Next-Session Maximum Adverse Excursion (MAE)
```

They are separate Target Contracts and separate Target identities.

The initial v1 definitions are:

```text
Close Return
= next_session_close / decision_reference_price - 1

MFE
= max(0, next_session_high / decision_reference_price - 1)

MAE
= min(0, next_session_low / decision_reference_price - 1)
```

Interpretation rules:

- MFE is an observed opportunity outcome and does not assume execution at the session high;
- MAE is an observed adverse-excursion outcome and does not automatically create a stop-loss rule;
- Close Return remains the first B0 ranking-evaluation target;
- MFE and MAE remain separately evaluable opportunity/risk outcomes;
- none of the three creates a mandatory holding period or Exit time.

The three targets may be grouped in one reproducibility bundle, but the bundle must not collapse them into one ambiguous `target` field or one shared Target Identity.

---

### 5.3 Future scoped targets

Later Research Charters may add separate Target Contracts for:

- next-session relative/excess return;
- next-session positive-return events;
- next-30-minute or next-60-minute opportunity windows;
- multi-session return/MFE/MAE;
- expected holding horizon;
- regime-conditioned opportunity.

Earlier morning-window ideas remain valid scoped research questions when suitable intraday PIT data is available.

They must not restore a universal next-morning Exit rule.

---

## 6. Initial Feature Set

The initial baseline should use only a small transparent set.

Candidate families may include:

1. short/medium momentum or relative strength;
2. liquidity;
3. volatility;
4. one simple trend or price-location descriptor.

Every included Feature Definition must declare at least:

- identity;
- semantic family;
- source-information family;
- source fields and/or input feature dependencies;
- frequency;
- lookback;
- availability rule;
- missingness policy;
- transformation/representation;
- qualified research status.

The first baseline must not bulk-import:

- F/R/T/C composites;
- all MACD fields;
- Chan scores;
- Tuishen composites;
- attention proxy;
- certainty score;
- sell-pressure score;
- OHLCV flow proxy;
- dynamic Legacy weights.

Those remain later incremental research candidates.

---

## 7. Market / ETF / Theme Role

Market Regime, ETF and Theme research remains important and may proceed in parallel.

They are intentionally not installed as mandatory hard gates in the first simple baseline.

The intended comparison sequence is:

```text
Simple Candidate Baseline
        ↓
+ Market Context
        ↓
+ ETF / Theme Context
        ↓
Controlled Incremental Comparison
```

A context feature or gate earns authority through incremental evidence.

Its omission from the first baseline is an attribution choice, not a statement that ETF/Theme research is unimportant.

---

## 8. Candidate Dataset Requirements

The first Candidate Dataset Builder must produce a reproducible panel with one row per:

```text
Decision Time × Candidate Symbol
```

Every row must preserve:

- symbol;
- Decision Time;
- Universe Identity;
- source Dataset Identity;
- Target Identity;
- registered Feature Definition identities;
- feature availability status;
- feature values where available;
- target observation status;
- target value where available.

The builder must:

1. preserve all Candidate Population symbols;
2. never silently drop symbols because a feature is missing;
3. never convert missing feature values into numeric neutral values;
4. never impute without an identified transformation;
5. reject future-dated feature materializations relative to Decision Time;
6. reject mismatched Dataset, Universe or Target identities;
7. preserve the difference between a target that is not yet observed and a target that is missing/invalid;
8. produce stable output identity;
9. remain independent from Strategy Action semantics.

A Candidate Dataset remains single-target for explicit evaluation identity. Separate Close Return, MFE and MAE datasets may share one identified Feature side while retaining separate Target identities and Target Materialization artifacts.

---

## 9. Baseline Ladder

The first model sequence is:

### B0 — Naive deterministic baseline

Examples:

- stable symbol ordering control;
- one-feature relative-strength/momentum rank.

Purpose:

- verify the ranking/evaluation pipeline;
- establish a minimum comparator.

The first B0 ranking evaluation uses Next-Session Close Return as the primary Target while MFE and MAE remain separate diagnostics/outcomes.

### B1 — Simple transparent composite rank

A small versioned combination of registered baseline features.

Purpose:

- test whether combining a few transparent information families adds value.

### B2 — Simple linear/statistical baseline

Only after the panel, split and evaluation contracts are stable.

Possible forms:

- linear model;
- logistic model for an explicitly binary target;
- simple ranking model.

Complex tree models, reinforcement learning and LLM-generated trade actions are not first-line requirements.

---

## 10. Evaluation Scope

The first R5 evaluation is rehearsal-level.

It should support, as appropriate to the Target:

- population coverage;
- feature coverage;
- RankIC / Spearman rank relationship;
- top-K target mean;
- quantile spread;
- ranking monotonicity;
- ranking turnover;
- concentration diagnostics;
- missingness diagnostics;
- separate Close Return / MFE / MAE outcome reporting.

No single metric proves Alpha.

A model score is not a probability.

A rehearsal result is not formal OOS evidence.

---

## 11. Data Authority

The first R5 run may use:

```text
EXPLORATORY
or
REHEARSAL
```

Data Eligibility where appropriate.

The resulting evidence authority must remain bounded accordingly.

Formal Candidate validation requires, for the claim being tested:

- FORMAL_RESEARCH eligible data;
- verified PIT Universe and required sidecars;
- decision-time correctness;
- reproducible manifests;
- formal split/OOS protocol.

---

## 12. Relationship to Entry and Exit

Candidate Discovery answers:

> Which securities are comparatively attractive for the defined forward opportunity?

It does not answer:

> Should exposure be established now?

That belongs to Entry.

The Target horizon also does not answer:

> When must an existing position be sold?

That belongs to Position Lifecycle and Exit.

Therefore:

```text
Candidate Target Horizon
≠
Mandatory Holding Period
≠
Mandatory Exit Time
```

MFE does not create a take-profit instruction and MAE does not create a stop-loss instruction.

---

## 13. Relationship to Legacy

Legacy assets may participate only through explicit roles such as:

- baseline comparator;
- hypothesis source;
- later feature candidate;
- compatibility adapter;
- shadow diagnostic.

The first Candidate ranker must not be implemented as:

```text
for every stock:
    run CoscoTimingEngine
sort final score
```

unless cross-sectional comparability is independently established in a future research program.

---

## 14. Current and Next Deliverables

The current R5 implementation has delivered:

1. this Research Charter;
2. Target Observation / Target Materialization contracts;
3. Candidate Dataset Builder;
4. full-population and explicit-missingness tests;
5. a controlled multi-date Candidate panel;
6. stable identities linking Dataset, Universe, Features, Target, Model and Experiment;
7. transparent baseline Feature Materializers;
8. deterministic B0 ranking;
9. descriptive cross-sectional rehearsal evaluation;
10. the minimum Close Return / MFE / MAE Target Materialization bundle capability.

The next major implementation increment should add:

- historical trading-calendar resolution;
- historical PIT Universe artifact loading;
- provider-backed rehearsal market artifacts;
- provider-backed multi-date Candidate panels;
- immutable R5 run artifacts;
- B0/B1 controlled comparison.

---

## 15. Invalidation / Stop Conditions

The first R5 program must stop or be revised if:

- the Candidate Population cannot be reconstructed reproducibly;
- feature availability cannot be represented honestly;
- target construction uses future information relative to the Target Contract;
- rows are silently selected using future target availability;
- the Dataset Builder drops missing-feature symbols;
- one feature identity maps to inconsistent formulas;
- a score is reported as probability without calibration authority;
- the implementation begins emitting trade actions;
- provider-backed rehearsal is built around only one close-return Target while the required opportunity-profile Target bundle is absent;
- infrastructure work expands without enabling a runnable Candidate experiment.

---

## 16. Promotion Boundary

Successful execution of the R5 rehearsal proves only:

```text
The Candidate research pipeline can be constructed and evaluated reproducibly
under the declared rehearsal scope.
```

It does not prove:

```text
Positive Alpha
Formal OOS validity
Production readiness
Live capital authority
```

---

## 17. Charter Commitment

> **R5 exists to produce the first independent, reproducible, cross-sectional Candidate Discovery research system as early as possible. It must remain simple enough to attribute, strict enough to prevent semantic and temporal leakage, broad enough to preserve return opportunity and adverse-excursion outcomes, and narrow enough that later Market, ETF, Theme, Chan, Tuishen, MACD and capital-flow research can be added through controlled incremental evidence rather than hidden complexity.**
