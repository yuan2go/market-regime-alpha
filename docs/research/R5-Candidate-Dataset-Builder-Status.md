# R5 Candidate Dataset Builder — Implementation Status

> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Status:** ACTIVE — first cross-sectional dataset slice implemented
> **Research Charter:** `docs/research/R5-Candidate-Discovery-Rehearsal-Charter.md`
> **Consistency audit:** `docs/architecture/Original-Intent-to-R3-R4-Consistency-Audit.md`

---

## 1. Purpose

This document records the actual implementation authority of the first R5 increment.

The project has now implemented the contract path required to construct one reproducible Candidate research cross-section:

```text
Dataset Contracts
        +
Candidate Population
        +
Registered Feature Definitions / Materializations
        +
Target Contract / Target Materialization
        ↓
Candidate Research Dataset Slice
```

This is not yet a multi-date training panel, a ranking model, or validated Alpha evidence.

---

## 2. Implemented Research Charter

Implemented:

```text
docs/research/R5-Candidate-Discovery-Rehearsal-Charter.md
```

The first R5 program freezes a narrow rehearsal question:

> At a declared late-session Decision Time, can a small set of transparent, cross-sectionally comparable features rank a reproducible A-share Candidate Population by a declared next-session forward opportunity target better than naive baselines?

The first fixed target horizon is a research evaluation horizon.

It is explicitly not:

```text
Mandatory Holding Period
Mandatory Exit Time
Universal Overnight Strategy
```

---

## 3. Target Observation Semantics

Implemented in:

```text
market_regime_alpha.candidates.dataset
```

Canonical initial statuses:

```text
AVAILABLE
NOT_YET_OBSERVED
MISSING
INVALID
```

Their meanings are intentionally different.

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

Means the attempted target observation is invalid under the Target Contract.

Requires:

- no usable value;
- explicit `observed_at` recording when invalidity became known.

This prevents:

```text
Future not reached yet
```

from being collapsed into:

```text
Future reached but data missing / invalid
```

---

## 4. Target Materialization

`TargetMaterialization` records:

- Artifact Identity;
- Target Identity;
- source Dataset Identity;
- Universe Identity;
- Decision Time;
- materialization time;
- code revision;
- config hash;
- symbol-level Target Observations.

Fail-closed invariants include:

- materialization cannot precede Decision Time;
- available/known missing/invalid future observations cannot claim an observation time at or before Decision Time;
- observation time cannot be after materialization time;
- symbol observations must be unique.

The current contract materializes one Target Contract for one Decision Time cross-section.

---

## 5. Candidate Research Dataset Slice

The first builder is:

```text
build_candidate_research_dataset(...)
```

It constructs one reproducible Decision Time cross-section.

The output records:

- derived Dataset Identity;
- all required source Dataset identities;
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

---

## 6. Full-Population Preservation

The central invariant is:

```text
Output Row Symbols
=
Candidate Population Symbols
```

exactly.

The builder does not:

- drop symbols with missing features;
- drop symbols without realized targets;
- keep only Top-K;
- keep only winners;
- keep only eventually tradable outcomes;
- fabricate fallback candidates.

A missing feature cell is explicitly represented as:

```text
status = MISSING
value = None
```

A target absent from the current Target Materialization is explicitly represented as:

```text
status = NOT_YET_OBSERVED
value = None
```

---

## 7. Data Eligibility Propagation

A Candidate research slice may depend on multiple source Datasets.

The output Data Eligibility is the weakest qualification among all required source Dataset Contracts.

Conceptually:

```text
REHEARSAL Universe Data
        +
EXPLORATORY Market Data
        ↓
EXPLORATORY Candidate Research Dataset
```

The derived panel cannot automatically acquire a stronger data qualification than its weakest required input.

This prevents data-authority inflation during feature/target joining.

---

## 8. Temporal Safety

The current builder rejects:

```text
Feature Materialization As-Of Time
>
Candidate Decision Time
```

Target observations are separately required to occur after Decision Time when they represent realized or known future outcomes.

Therefore:

```text
Feature Side
uses information available by Decision Time

Target Side
may become known only after Decision Time
```

The two temporal roles are not collapsed.

---

## 9. Stable Dataset Identity

The derived Candidate Dataset ID is content-addressed from the identified research dependencies:

- source Dataset identities;
- Universe Identity;
- Decision Time;
- Target Identity;
- Target Materialization Artifact Identity;
- ordered Feature Definition identities;
- ordered Feature Materialization identities;
- complete Candidate Population symbols.

Reordering input Dataset Contracts does not change the derived ID.

Changing an identified result-affecting dependency changes the identity.

The builder relies on upstream Feature Materialization and Target Materialization identities being truthful. Their future immutable artifact implementation remains a separate research-infrastructure concern.

---

## 10. Test Assets Added

Added:

```text
tests/candidates/test_dataset_builder.py
tests/candidates/test_target_state_contracts.py
```

The tests are designed to cover:

- complete population preservation;
- explicit feature missingness;
- `AVAILABLE` target preservation;
- explicit `MISSING` target preservation;
- absent target → `NOT_YET_OBSERVED`;
- weakest-input Data Eligibility propagation;
- stable derived Dataset Identity under source-contract ordering changes;
- future Feature Materialization rejection;
- future target observation chronology;
- unidentified source Dataset rejection;
- direct Target-state construction invariants.

---

## 11. Execution Status

The current tool environment was unable to clone the latest GitHub repository because DNS resolution for `github.com` failed.

Therefore this document does **not** claim:

```text
latest HEAD pytest passed
latest HEAD ruff passed
latest HEAD mypy passed
```

The tests and implementation are committed and must be run in the normal repository development environment or CI before increasing implementation authority.

The new Candidate Dataset Builder module has been added to the repository mypy scope.

---

## 12. Current R5 Status

```text
Original-intent consistency audit             COMPLETE
R4 minimum Feature metadata correction        COMPLETE
R5 Research Charter                           IMPLEMENTED
Target Observation contract                   IMPLEMENTED
Target Materialization contract               IMPLEMENTED
Single-Decision-Time Candidate dataset slice  IMPLEMENTED
Full-population preservation                  IMPLEMENTED
Explicit feature/target missingness            IMPLEMENTED
Data Eligibility non-inflation                 IMPLEMENTED

Multi-Decision-Time panel assembly             NOT YET IMPLEMENTED
Concrete PIT Universe artifact loader          NOT YET IMPLEMENTED
Concrete target materializer from market data  NOT YET IMPLEMENTED
Baseline feature materializers                 NOT YET IMPLEMENTED
Naive Candidate ranker                         NOT YET IMPLEMENTED
Cross-sectional rehearsal evaluation           NOT YET IMPLEMENTED
Formal Candidate evidence                      NOT AVAILABLE
```

---

## 13. Next Implementation Sequence

The next sequence is:

```text
1. Execute current R3/R4/R5 tests in a complete repository environment
        ↓
2. Implement multi-Decision-Time Candidate panel assembly
        ↓
3. Implement one concrete rehearsal Target Materializer
        ↓
4. Implement a very small transparent baseline Feature set
        ↓
5. Build a multi-date Candidate panel
        ↓
6. Implement naive / simple ranking baseline
        ↓
7. Produce cross-sectional rehearsal evaluation
```

The PIT Universe artifact loader and professional-data procurement track may proceed in parallel.

The project must not wait for every future data source before running a clearly labeled rehearsal pipeline.

---

## 14. Non-Goals of the Current Increment

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

## 15. Implementation Principle

> **The first R5 Dataset Builder is successful only if it preserves the complete historical opportunity set and makes missingness, target availability, data authority and temporal direction explicit. A smaller honest panel is more valuable than a larger panel produced by silently dropping difficult rows or mixing future outcomes into the feature side.**
