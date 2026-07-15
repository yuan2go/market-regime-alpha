# Original Intent to R3/R4 Consistency Audit

> **Status:** Current implementation-alignment audit
> **Scope:** Preserved original ChatGPT project conversation, Constitution `00–09`, R0 consistency audit, R1 Legacy characterization, R2 V2 kernel, R3/R4 minimal research spine, and the current transition toward R5 Candidate Discovery
> **Authority:** Architecture and implementation interpretation. This document does not override the Constitution.

---

## 1. Audit Question

This audit asks:

> Has the refoundation remained faithful to the user's original intended trading-research system, or has the project drifted into infrastructure work, a generic quant platform, a fixed overnight strategy, a Legacy rewrite, or a different research objective?

The audit was performed by re-reading the preserved original conversation chronology and then reviewing the current GitHub documents against the Constitution.

The original intent evolved through several explicit corrections. The latest user correction in the original conversation takes precedence over earlier assistant suggestions.

---

## 2. Original Intent Chronology

### 2.1 Initial practical objective

The original practical request had two near-term objectives:

1. use ETF rotation, next-session continuation ideas, Tuishen-inspired theory, Chan Theory, multi-factor research, hot-topic tracking and capital tracking to identify stocks likely to rise;
2. implement ETF Rotation as a separate strategy later.

The user also stated that QMT was not an immediate requirement and that professional data such as Xuntou or other suitable providers could be added where research quality required it.

This establishes an important starting point:

```text
The project was always intended to combine
market / ETF / theme / capital context
with stock-level opportunity discovery.
```

It was not intended to remain a single-stock Dividend-T system.

---

### 2.2 First architecture correction

The repository audit then identified structural risks:

- excessive rule accumulation and overfitting risk;
- repeated use of the same OHLCV information under different names;
- semantic drift between simplified and detailed decision paths;
- fundamental/technical contamination;
- in-sample historical priors;
- lack of broad formal PIT data authority;
- heterogeneous sell intents collapsed into one hit-rate diagnostic.

The resulting migration direction was:

```text
Preserve useful Legacy research assets
        ↓
Freeze uncontrolled Legacy expansion
        ↓
Create a V2 contract and research foundation
        ↓
Migrate incrementally through adapters and characterization
```

The original conversation explicitly rejected a big-bang rewrite.

---

### 2.3 User correction: fixed next-morning exit was rejected

An earlier assistant formulation described:

```text
late-session entry
    ↓
next-morning exit
```

The user explicitly corrected this:

```text
Exit is not necessarily in the morning.
Exit when the sell / invalidation logic requires it.
```

This changed the project architecture materially.

The corrected model became:

```text
Candidate Discovery
        ↓
Entry
        ↓
Repeated Position Lifecycle Evaluation
HOLD / ADD / REDUCE / ROTATE / EXIT
```

Therefore:

- fixed-time exit may remain a scoped strategy baseline;
- it is not the project-wide Exit definition;
- Entry and Exit are separate research systems;
- Position Lifecycle is a repeated re-evaluation problem.

---

### 2.4 Canonical strategic goals that emerged from the conversation

The original conversation then explicitly converged on:

#### Goal A — Candidate Discovery

Find and rank A-share opportunities with attractive forward opportunity profiles.

#### Goal B — Position Lifecycle Management

Manage:

```text
ENTRY
HOLD
ADD
REDUCE
ROTATE
EXIT
```

through repeated evidence updates.

#### Goal C — ETF / Theme Rotation

Use ETF, industry and theme information initially as:

- market context;
- relative-strength context;
- capital-attention context;
- universe narrowing;
- later, a separate direct ETF strategy program.

ETF Rotation was not meant to disappear merely because Candidate Discovery became the first implementation priority.

---

### 2.5 Research Operating System framing

The later Research Operating System framing did not replace the practical trading-research objective.

Its intended role was:

```text
Make the original research loop
verifiable
reproducible
traceable
reviewable
iterable
and capable of promotion / degradation / retirement.
```

The original conversation explicitly warned against allowing local implementation to redefine project direction.

Therefore:

> **The Alpha Research Operating System is the enabling architecture for the practical market-context → Candidate → Entry → Lifecycle → Exit research loop. It is not an infrastructure project with Candidate Discovery deferred indefinitely.**

---

## 3. Original Intent Invariants

The following invariants are treated as the preserved user intent.

### OI-001 — A-share focus

The project is designed around the China A-share market and its specific data, market structure and execution constraints.

### OI-002 — Candidate Discovery is the current first strategic new research priority

The project must build an independent cross-sectional Candidate Discovery capability.

### OI-003 — Candidate Discovery is not a market-wide loop over a single-symbol timing engine

Cross-sectional comparability must be explicit.

### OI-004 — Fixed next-morning exit is not a project law

It may be a strategy-specific baseline only.

### OI-005 — Position Lifecycle is first-class

The intended lifecycle includes:

```text
HOLD / ADD / REDUCE / ROTATE / EXIT
```

after Entry.

### OI-006 — Entry and Exit are independent research problems

Exit is not merely the inverse of Entry.

### OI-007 — ETF / Theme / Market context remains upstream and important

The first simple Candidate baseline may exclude these inputs for attribution, but ETF/Theme/Market research must remain available in parallel and later be measured for incremental value.

### OI-008 — Chan, Tuishen-inspired constructs, MACD and similar theories must be quantified and ablated

They do not receive authority from theory names.

### OI-009 — Professional data improves research authority, not merely model accuracy

Exploratory/rehearsal work may begin before perfect vendor procurement, but formal validation requires the data authority appropriate to the claim.

### OI-010 — Legacy knowledge is preserved through incremental migration

No big-bang rewrite.

### OI-011 — Research value must arrive before refoundation completion

The project must not spend an indefinite period building framework abstractions before Candidate research begins.

### OI-012 — Candidate Prediction is evidence, not an order

Portfolio and Execution remain separate owners.

---

## 4. Constitution Alignment Result

### 4.1 `00-Project-Vision.md`

**Result: ALIGNED**

The Project Vision preserves:

- Candidate Discovery as the current first priority;
- cross-sectional ranking;
- multiple explicit forward opportunity targets;
- independent Entry;
- repeated Position Lifecycle;
- rejection of universal fixed-time exit;
- ETF/Theme as context and universe-selection capability;
- the canonical Market Regime → ETF → Theme → Universe → Feature → Candidate → Entry → Lifecycle → Exit pipeline.

No direction-level correction is required.

---

### 4.2 `05-Factor-Constitution.md`

**Result: ALIGNED**

It correctly converts MACD, Chan, Tuishen-inspired constructs, volume-price ideas and other named theories into:

- explicit information objects;
- source-information families;
- lineage;
- target-specific research claims;
- incremental validation requirements.

This directly supports the original requirement to combine theories without treating correlated OHLCV transformations as independent evidence.

---

### 4.3 `08-Roadmap.md`

**Result: ALIGNED**

The critical path remains:

```text
Minimal V2 Kernel
    ↓
Reproducible Universe + Dataset Slice
    ↓
Minimal Feature Registry
    ↓
Candidate Target
    ↓
Candidate Dataset Builder
    ↓
Simple Candidate Baselines
    ↓
Cross-Sectional Evaluation
```

The Roadmap explicitly rejects both:

- waiting for a complete future platform before Candidate research;
- extending `CoscoTimingEngine` or `backtest.py` into the new platform.

R5 remains the first major new research-value milestone.

---

### 4.4 `09-Glossary.md`

**Result: ALIGNED**

The Glossary correctly separates:

```text
Prediction ≠ Action
Score ≠ Probability
Strategy Proposal ≠ Portfolio Decision
Portfolio Decision ≠ Execution Result
Data Eligibility ≠ Sample Role ≠ Evidence Level ≠ Authority State
```

This is consistent with the original concern that multiple old signals, scores and probability-like outputs were semantically drifting.

---

## 5. New Architecture Document Audit

### 5.1 `Constitution-Consistency-Audit.md`

**Result: ALIGNED**

The document accurately reconstructs the practical loop:

```text
Market / ETF / Theme / Capital Direction
        ↓
Opportunity Set
        ↓
Stock Candidate Discovery
        ↓
Independent Entry
        ↓
Repeated Lifecycle
        ↓
Re-enter Discovery
```

It also correctly states that the Research OS must not become an excuse for infrastructure-only work.

No direction-level correction is required.

---

### 5.2 `R1-Legacy-Characterization.md`

**Result: DIRECTIONALLY ALIGNED; STATUS RESIDUE FOUND**

The R1 program correctly preserves the Strangler migration model and keeps `backtest.py`, `DividendTStrategy`, `CoscoTimingEngine`, `signal_intent.py`, MACD/OOS assets and application surfaces under characterization rather than rewrite.

However, one status sentence became stale after later implementation:

```text
trend_snapshot.py dual-authority characterization
```

was still listed as future work even after:

```text
tests/legacy/test_trend_snapshot_characterization.py
```

was added.

**Resolution:** The current audit records that the first `trend_snapshot` dual-output characterization now exists. R1 remains `ACTIVE` because this does not fully characterize the application or timing engine.

---

### 5.3 `R2-Minimal-V2-Kernel.md`

**Result: ALIGNED; HISTORICAL PRIORITY LIST NOW PARTLY SATISFIED**

R2 correctly remained minimal and did not create:

- a new global Signal;
- generic confidence;
- strategy policy inside Core;
- direct V2 dependence on Legacy policy.

Its earlier priority to begin Data/Dataset and PIT Universe contracts has now been partially satisfied by R3/R4.

This is progression, not contradiction.

R2 should be read as an implementation-stage record, not as a statement that R3 work is still pending.

---

### 5.4 `R3-R4-Minimal-Research-Spine.md`

**Result: ALIGNED AFTER ONE IMPLEMENTATION GAP WAS CORRECTED**

The Data → PIT Universe → Feature → Candidate contract direction is consistent with the original intent and Roadmap.

It correctly preserves:

- Provider ≠ Dataset;
- Data Eligibility boundaries;
- current-snapshot universe ≠ historical PIT universe;
- Universe Membership ≠ Trading Eligibility ≠ Execution Feasibility;
- Missing ≠ Neutral;
- Feature Definition ≠ Feature Materialization;
- Candidate Prediction ≠ Strategy Action;
- Score ≠ Probability;
- no ETF/Theme hard gate in the first baseline;
- no bulk Legacy factor migration.

#### Gap found during this audit

The Roadmap requires the R4 Feature Registry MVP to support at least:

- source lineage;
- decision-time availability;
- frequency;
- lookback;
- missingness policy;
- research status.

The first implementation initially recorded only:

- Semantic Family;
- Source-Information Family;
- Representation Method;
- Value Type;
- Parameters.

This meant the document's `Feature Registry MVP IMPLEMENTED` status was temporarily stronger than the implementation.

#### Correction applied

`FeatureDefinition` now explicitly records:

```text
source_fields
input_feature_ids
frequency
lookback
availability_rule
missingness_policy
research_status
```

in addition to the previously implemented semantic and source-information family metadata.

The correction remains intentionally minimal:

- no Feature Store was introduced;
- no persistence platform was introduced;
- no Predictive Factor authority was granted;
- `research_status` is a qualified registry-navigation field, not Evidence Level or Authority State.

After this correction, the R4 MVP claim is consistent with the Roadmap's minimum metadata requirement.

---

## 6. Current Direction-Level Assessment

### Direction-Level Contradiction

```text
NONE FOUND
```

### Implementation-Status Residues

```text
1. R1 text contains a stale pre-characterization trend_snapshot task.
2. R2 priority text predates the now-implemented R3/R4 contracts.
```

These are status-history issues, not project-direction contradictions.

### Material Implementation Gap Found and Corrected

```text
R4 Feature Definition lacked the minimum Roadmap lineage / availability metadata.
```

This has been corrected before entering R5.

---

## 7. Important Non-Drift Interpretations

### 7.1 Candidate Discovery is broader than one Overnight model

The original overnight/next-session idea remains an important research program.

However:

```text
Candidate Discovery
≠
Only one overnight target
```

The first R5 Research Charter may deliberately choose a next-session target for the MVP, but the platform must not become permanently identified with that horizon.

---

### 7.2 Fixed-horizon Candidate research does not reintroduce fixed-time Exit

A Candidate target such as:

```text
next-session return
next-session MFE
next-3-session opportunity
```

is a prediction horizon.

It does not imply:

```text
The position must be exited at the target horizon.
```

Candidate evaluation and Position Lifecycle/Exit remain different owners.

---

### 7.3 ETF / Theme may be absent from the first baseline without being removed from the architecture

The first baseline should be attributable.

A valid sequence is:

```text
Simple Candidate Baseline
        ↓
Baseline + Market Context
        ↓
Baseline + ETF / Theme Context
        ↓
Controlled Incremental Comparison
```

ETF/Theme research may proceed in parallel.

The project must not reinterpret this sequencing as:

```text
ETF / Theme is unimportant until a late stage.
```

---

### 7.4 Expected Holding Horizon is preserved as a future model output, not required for the first fixed-target baseline

The original conversation and Project Vision include expected holding horizon as a useful Candidate output.

The initial `CandidatePrediction` contract does not yet require a per-symbol expected holding-horizon estimate.

This is acceptable for the first R5 fixed-horizon baseline because:

- the Target Contract defines the evaluation horizon;
- Position Lifecycle remains a separate later research system;
- no claim is made that holding-horizon modeling is complete.

A future model may add a versioned expected holding-horizon output when a Research Charter and validation protocol require it.

---

## 8. R5 Entry Decision

The project may proceed to R5 because:

```text
Original direction remains intact.
R0 direction is frozen.
R1 continues in parallel.
R2 kernel exists.
R3 Data / PIT contracts exist.
R4 minimum Feature metadata gap has been corrected.
Candidate-facing contracts exist.
```

R5 must begin as a deliberately narrow rehearsal research program.

The next implementation sequence is:

```text
R5 Research Charter
        ↓
Candidate Target Materialization Contract
        ↓
Candidate Dataset Builder
        ↓
Small Transparent Feature Set
        ↓
Naive / Simple Ranking Baseline
        ↓
Cross-Sectional Rehearsal Evaluation
```

The first R5 implementation must not wait for:

- complete ETF Rotation;
- complete Market Regime model;
- Level 2;
- every Legacy factor;
- full Position Lifecycle extraction;
- broker automation.

It also must not claim formal Alpha evidence while operating on EXPLORATORY or REHEARSAL data.

---

## 9. Binding R5 Guardrails

1. Preserve the full Candidate Population, not only winners.
2. Do not drop missing-feature symbols silently.
3. Do not impute missing values without an identified transformation.
4. Do not call model scores probabilities without calibration authority.
5. Do not emit trade actions from CandidatePrediction.
6. Do not use `CoscoTimingEngine` as the universal market-wide ranker.
7. Do not bulk-import all Legacy scores into the first baseline.
8. Use only a small, transparent initial feature set.
9. Keep Market/ETF/Theme research available as parallel incremental-context experiments.
10. Keep fixed-time Exit outside the Candidate model.
11. Preserve Dataset, Universe, Feature, Target, Model and Experiment identities.
12. Keep R1 Legacy characterization active in parallel.

---

## 10. Audit Conclusion

> **The project remains consistent with the user's latest preserved intent. The refoundation has not changed the destination from an A-share market-context → Candidate Discovery → Entry → Position Lifecycle → Exit research system into a generic infrastructure project. One real R4 completion gap was found and corrected before R5. The project may now enter R5 Candidate Discovery Rehearsal MVP under the guardrails above.**
