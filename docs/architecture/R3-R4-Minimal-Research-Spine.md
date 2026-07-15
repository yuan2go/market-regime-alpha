# R3 / R4 — Minimal Data → PIT Universe → Feature → Candidate Research Spine

> **Stages:** R3 Data / PIT and R4 Feature System MVP, with the minimum Candidate-facing contracts required to prove the vertical boundary
> **Status:** ACTIVE — first contract spine implemented
> **Constitutional basis:** `04-Data-Constitution.md`, `05-Factor-Constitution.md`, `07-Validation-Constitution.md`, `08-Roadmap.md`, `09-Glossary.md`
> **Predecessor:** `R2-Minimal-V2-Kernel.md`

---

## 1. Objective

The purpose of this increment is not to build a generic data platform or a production Candidate model.

It establishes the smallest trustworthy contract path required for the next falsifiable Candidate research question:

```text
Provider / Source Artifact
        ↓
Dataset Contract + Data Eligibility
        ↓
PIT Universe Membership
        +
Trading Eligibility
        ↓
Candidate Population
        ↓
Feature Definition
        ↓
Feature Materialization
        ↓
Target Contract
        ↓
Candidate Prediction
        ↓
Experiment Identity
```

This is a contract and identity spine.

It does not claim that the project already has:

- FORMAL_RESEARCH eligible market data;
- a complete historical PIT universe;
- a promoted Feature Registry;
- a validated Candidate model;
- ETF/Theme/Market Regime incremental evidence;
- live trading authority.

---

# 2. R3 — Canonical Data Contracts

Implemented:

```text
market_regime_alpha.data.contracts
```

## 2.1 `DataEligibility`

Canonical values:

```text
UNQUALIFIED
EXPLORATORY
REHEARSAL
FORMAL_RESEARCH
```

This remains independent from:

```text
Sample Role
Evidence Level
Authority State
```

No second global data-qualification ontology is introduced.

---

## 2.2 `ProviderReference`

A Provider is identified separately from a Dataset.

The reference records:

- Provider Identity;
- provider product;
- provider contract version.

Multiple products from the same provider may contribute to one Dataset.

---

## 2.3 `SourceArtifactReference`

A source artifact has explicit:

- Artifact Identity;
- Provider Identity;
- retrieval time;
- content hash;
- locator.

This does not imply PIT correctness or formal eligibility.

---

## 2.4 `DatasetContract`

The initial canonical Dataset boundary records:

- Dataset Identity;
- schema version;
- Data Eligibility;
- manifest artifact identity;
- provider references;
- whether PIT correctness is established for the declared scope;
- scope;
- limitations.

Important invariant:

```text
FORMAL_RESEARCH
    requires
pit_correct_for_scope = true
```

This is necessary, but not sufficient, for formal promotion evidence.

The contract intentionally does not replace every rich Legacy manifest.

Existing dataset builders may preserve their own detailed manifests and expose a canonical boundary through an adapter.

---

# 3. Legacy Dataset Compatibility

Implemented:

```text
market_regime_alpha.legacy.dataset_contract_adapter
```

The adapter reuses the existing Legacy MACD dataset content identity:

```text
dataset_version(manifest)
```

and applies a deliberately conservative mapping:

```text
Legacy FIXTURE
    → Canonical UNQUALIFIED

Legacy REHEARSAL
    → Canonical REHEARSAL

Legacy FORMAL_FINAL_CANDIDATE
    → BLOCKED
      CANONICAL_DATA_ELIGIBILITY_REVIEW_REQUIRED
```

This directly enforces the Glossary rule:

```text
FORMAL_FINAL_CANDIDATE
≠
FORMAL_RESEARCH
```

The old local classification therefore cannot silently acquire canonical formal evidence authority.

---

# 4. R3 — PIT Universe Boundary

Implemented:

```text
market_regime_alpha.universe.contracts
```

The central distinction is:

```text
Universe Membership
≠
Trading Eligibility
≠
Execution Feasibility
```

---

## 4.1 `PITUniverseSnapshot`

Represents:

- Universe Identity;
- As-Of Time;
- source Dataset Identity;
- evidence Artifact Identity;
- method version;
- symbol membership records.

It does not infer that a member is tradable.

The existing Legacy `build_largecap_universe()` remains current-snapshot exploratory infrastructure and is not automatically adapted into this PIT authority.

---

## 4.2 `TradingEligibilitySnapshot`

Represents explicit eligibility under a declared upstream policy.

Canonical statuses in the initial contract are:

```text
ELIGIBLE
INELIGIBLE
UNKNOWN
```

Missing eligibility is:

```text
UNKNOWN
```

not:

```text
ELIGIBLE
```

No current ST or suspension field is silently converted into one universal eligibility policy by this contract.

Those rules remain data/policy-version dependent.

---

# 5. Candidate Population Construction

Implemented:

```text
build_candidate_population(...)
```

The initial rule is:

```text
PIT Universe Members
∩
Explicitly ELIGIBLE Instruments
=
Candidate Population
```

Future-dated Universe or Eligibility snapshots are rejected.

An empty Candidate Population is valid.

It means:

```text
No eligible instruments under the declared population and eligibility process
```

not:

```text
System failure
```

The system must not fabricate a fallback population merely because the valid result is empty.

---

# 6. R4 — Feature System MVP

Implemented:

```text
market_regime_alpha.features.contracts
```

The first Feature System intentionally contains only:

```text
FeatureDefinition
FeatureObservation
FeatureMaterialization
FeatureRegistry
```

It does not yet contain a promoted Factor Registry implementation.

---

## 6.1 Feature Definition

A Feature Definition records:

- Feature Definition Identity;
- name;
- Semantic Family;
- Source-Information Family or families;
- Representation Method;
- value type;
- parameters.

This preserves:

```text
Semantic Family
≠
Source-Information Family
≠
Representation Method
```

For example:

```text
Semantic Family:
Relative Strength

Source-Information Family:
PRICE_ONLY

Representation Method:
relative-return
```

Registration alone does not make the object a Predictive Factor.

---

## 6.2 Missingness

The Feature contract enforces:

```text
MISSING
≠
0.0
```

A non-available feature observation cannot carry a usable numeric value.

This prevents silent neutralization such as:

```text
missing flow = 0
missing signal = 50
missing feature = neutral
```

unless a separate, explicit imputation transformation is defined and identified.

---

## 6.3 Feature Materialization

A materialization is identified separately from its Feature Definition.

It records:

- Feature Materialization Identity;
- Feature Definition Identity;
- Dataset Identity;
- Universe Identity;
- As-Of Time;
- code revision;
- config hash;
- symbol-level observations.

This allows one Feature Definition to be materialized under different datasets, universes, dates and configurations without pretending they are the same artifact.

---

## 6.4 Feature Registry MVP

The initial registry is intentionally in-memory.

Its purpose is to freeze two semantics required by Candidate research:

```text
Same Feature ID + Same Definition
    → idempotent registration

Same Feature ID + Different Definition
    → identity conflict
```

Persistence technology is deliberately deferred.

---

# 7. Minimum Candidate-Facing Contracts

Implemented:

```text
market_regime_alpha.candidates.contracts
```

These contracts are included now only because they are the first consumer of the R3/R4 spine.

They do not implement a complex Candidate model.

---

## 7.1 `TargetContract`

The target records:

- Target Identity;
- name;
- horizon;
- outcome;
- price convention;
- decision-time convention;
- population scope;
- version.

This prevents a model from being implemented before the future quantity it is trying to predict is defined.

---

## 7.2 `CandidatePrediction`

The initial schema may contain:

- Model Identity;
- Target Identity;
- Universe Identity;
- Decision Time;
- Experiment Identity;
- population size;
- model score;
- rank;
- percentile;
- calibrated probability, only when valid;
- expected return;
- expected MFE;
- expected MAE;
- uncertainty;
- expiry.

It deliberately contains no:

```text
ENTER
HOLD
ADD
REDUCE
ROTATE
EXIT
```

Candidate Prediction remains prediction/ranking evidence.

---

## 7.3 Score / Probability boundary

The contract validates probability range separately from score semantics.

Therefore:

```text
model_score = 82
```

cannot be silently interpreted as:

```text
calibrated_probability = 82
```

Probability semantics still require target, horizon, population, calibration method, calibration sample and evidence.

---

# 8. Vertical Contract Test

A repository test now constructs the complete minimal path:

```text
REHEARSAL DatasetContract
        ↓
PITUniverseSnapshot
        +
TradingEligibilitySnapshot
        ↓
CandidatePopulation
        ↓
FeatureDefinition
        ↓
FeatureRegistry
        ↓
FeatureMaterialization
        ↓
TargetContract
        ↓
ExperimentIdentity
        ↓
CandidatePrediction
```

The test explicitly verifies that:

- rehearsal data remains rehearsal;
- only eligible PIT members enter the Candidate Population;
- Feature Materialization is linked to Dataset and Universe identities;
- Candidate output remains a score/rank without fabricated probability;
- Experiment Identity links Dataset, Universe, Target, Feature and Model identities.

---

# 9. Test Execution Status

Before repository submission, the initial isolated vertical-slice contract implementation was executed with:

```text
5 passed
```

That isolated run covered the core Data → Universe → Feature → Candidate path.

After that run, several additional guard refinements and repository tests were added:

- valid empty Candidate Population semantics;
- explicit `TradingEligibilityStatus` type validation;
- non-empty Source-Information Family validation;
- Legacy Dataset classification adapter tests;
- Legacy `DividendTStrategy` Golden Behavior characterization tests.

Those later additions were committed after the isolated five-test run.

The current execution environment still does not provide a usable latest-repository checkout and previously could not resolve `github.com` for clone-based full-HEAD execution. Therefore this document does not claim that the complete latest repository test suite, Ruff and mypy have passed in this session.

The normal project environment or CI should run:

```text
pytest
ruff check .
mypy
```

before increasing implementation authority.

---

# 10. What This Increment Does Not Do

This increment does not:

1. promote Tencent, EastMoney, BaoStock, Tushare, QMT or another provider;
2. claim the current large-cap snapshot universe is historical PIT truth;
3. define one universal A-share eligibility policy;
4. migrate every Legacy factor into the Feature Registry;
5. claim MACD, Chan or Tuishen-derived features are predictive;
6. build a complex ensemble;
7. use ETF/Theme/Market Regime as a hard Candidate gate;
8. open sealed-test data;
9. claim positive Alpha;
10. grant automatic trading authority.

---

# 11. Current Stage Status

```text
R3 Canonical Data Contract                    IMPLEMENTED
R3 Legacy Dataset Contract Adapter            IMPLEMENTED
R3 PIT Universe Contract                      IMPLEMENTED
R3 Trading Eligibility Contract               IMPLEMENTED
R3 Real Historical PIT Universe               NOT YET AVAILABLE

R4 Feature Definition Contract                IMPLEMENTED
R4 Feature Materialization Contract           IMPLEMENTED
R4 Feature Registry MVP                       IMPLEMENTED
R4 Legacy Factor Migration                    NOT STARTED AS BULK MIGRATION

Candidate Population Contract                 IMPLEMENTED
Candidate Target Contract                     IMPLEMENTED
Candidate Prediction Schema                   IMPLEMENTED
Candidate Baseline Model                      NOT YET IMPLEMENTED
Candidate Dataset Builder                     NOT YET IMPLEMENTED
Formal Candidate Evidence                     NOT AVAILABLE
```

---

# 12. Next Implementation Sequence

The next sequence should remain consumer-driven:

## Step 1 — Normal-environment verification

Run the complete project test/lint/type-check suite and correct any integration failures.

## Step 2 — Canonical Dataset adapter around the existing rehearsal path

Use the existing `formal_dataset_builder.py` output through the new compatibility boundary.

Do not rewrite the builder merely to move files.

## Step 3 — PIT Universe input implementation

Define an explicit loader/materializer for a historical Universe artifact that satisfies the new `PITUniverseSnapshot` contract.

The current-snapshot `build_largecap_universe()` remains exploratory.

## Step 4 — Candidate baseline feature set

Start small.

The first Candidate baseline should use a limited number of transparent, cross-sectionally comparable features such as, subject to a formal Research Charter:

- relative strength / momentum;
- liquidity;
- volatility;
- possibly one simple trend descriptor.

Do not begin by copying all Legacy F/R/T/C, Chan, Tuishen, attention, certainty and flow-proxy scores into V2.

## Step 5 — Candidate Dataset Builder

Build a reproducible panel from:

```text
Declared Dataset
+
PIT Candidate Population
+
Registered Feature Materializations
+
Target Contract
```

Preserve the full population, not only selected winners.

## Step 6 — First simple Candidate baseline

Only after the above contracts are connected should the project implement the first baseline ranker.

Market Regime, ETF and Theme research may continue in parallel, but their first Candidate role should be measured as incremental context rather than silently installed as mandatory gates.

---

# 13. Implementation Principle

> **The R3/R4 spine is successful only when it enables a reproducible Candidate experiment without inflating data authority, fabricating PIT history, laundering missing values into neutral scores, or turning a ranking output into a trade action.**
