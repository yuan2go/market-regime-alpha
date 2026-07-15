# R2 — Minimal V2 Kernel and Compatibility Boundary

> **Stage:** R2
> **Status:** ACTIVE — initial kernel implemented
> **Constitutional basis:** `02-Architecture-Blueprint.md`, `08-Roadmap.md`, `09-Glossary.md`
> **R0 consistency record:** `docs/architecture/Constitution-Consistency-Audit.md`

---

## 1. Objective

R2 creates the smallest stable shared contract layer required for new research work without rewriting the repository or importing Legacy strategy semantics as platform truth.

The initial implementation deliberately contains:

```text
Stable Identity Primitives
+
Semantic Time Primitives
+
Input Availability / Validity Status
+
Project-Wide Experiment Identity
+
Explicit Legacy Experiment Compatibility Adapter
```

It deliberately does **not** contain:

- Candidate model logic;
- Feature definitions;
- Strategy actions or policy logic;
- Portfolio allocation;
- Execution logic;
- Data-provider implementations;
- PIT Universe implementation;
- a new global `Signal` type;
- a generic `confidence` field;
- a mixed Evidence/Authority/Eligibility status enum.

---

## 2. Implemented Packages

### `market_regime_alpha.core.identity`

Provides immutable identity types:

```text
ArtifactId
DatasetId
UniverseId
FeatureDefinitionId
FeatureMaterializationId
TargetId
ModelId
StrategyId
ExperimentId
```

The initial contract validates identity hygiene only:

- non-empty;
- trimmed;
- no control characters;
- immutable typed identity.

It intentionally does not impose one global prefix convention because existing registries and Legacy artifacts do not yet share one proven naming scheme.

---

### `market_regime_alpha.core.time`

Provides owner-neutral semantic time wrappers:

```text
DecisionTime
AvailabilityTime
FinalizationTime
AsOfTime
ExecutionEligibleTime
```

All values must be timezone-aware.

The purpose is to prevent future contracts from collapsing:

```text
decision_time
available_at
finalized_at
as_of
execution_eligible_time
```

into one ambiguous `timestamp`.

---

### `market_regime_alpha.core.status`

Provides:

```text
InputAvailabilityStatus
```

with:

```text
AVAILABLE
MISSING
UNAVAILABLE
STALE
INVALID
UNSUPPORTED
BLOCKED
```

This implements the R0 consistency resolution:

```text
Input Availability / Validity
≠
Strategy Action
```

Therefore:

```text
NO_ACTION
```

is intentionally **not** part of this enum.

---

### `market_regime_alpha.research.experiment_identity`

Provides the initial canonical:

```text
ExperimentIdentity
```

It can identify, as applicable:

- code revision;
- Dataset Identity;
- config hash;
- Universe Identity;
- Target Identity;
- Feature Definition identities;
- Feature Materialization identities;
- Model Identity;
- Strategy Identity;
- parent Experiment identities;
- execution assumption reference;
- environment reference;
- additional named semantic references.

It provides:

- deterministic canonical JSON;
- SHA-256 identity hash;
- content-derived `ExperimentId`.

The first version is intentionally small. A new dedicated field should be added only when the concept has earned project-wide canonical semantics.

---

## 3. Legacy Compatibility Boundary

### `market_regime_alpha.legacy.macd_experiment_adapter`

The first explicit compatibility adapter maps the minimum identity anchors from the existing Legacy MACD experiment identity into the canonical V2 `ExperimentIdentity`.

The dependency direction is:

```text
Canonical Core / Research Contracts
        ↑
Legacy Compatibility Adapter
        ↓
Legacy MACD Identity
```

not:

```text
V2 Core
    ↓
Legacy Dividend-T Internals
```

The adapter requires the existing Legacy canonical config hash to be supplied by the caller.

It preserves:

- Git/code revision;
- Legacy dataset-version reference;
- Legacy data-split hash;
- Legacy pipeline ID;
- Legacy execution-config hash;
- Legacy sizing owner;
- Legacy full config hash.

It does **not** invent:

- canonical PIT Universe Identity;
- canonical Target Identity;
- canonical Feature Definition identities.

Those remain absent until they can be reconstructed truthfully.

---

## 4. Test and Characterization Coverage

### 4.1 New isolated V2 tests

The new V2 code was first executed in an isolated local package copy.

Coverage included:

#### Identity

- immutable typed IDs;
- invalid empty/whitespace/control-character IDs;
- different identity types remain different.

#### Semantic time

- naive datetimes rejected;
- timezone-aware values preserved;
- semantic time types remain distinct;
- UTC conversion.

#### Availability status

- only `AVAILABLE` is usable by default;
- `NO_ACTION` cannot silently re-enter the input-status enum.

#### Experiment Identity

- deterministic canonical serialization and hashing;
- metadata reference order normalization;
- result-affecting dataset change changes identity;
- duplicate feature identities rejected;
- duplicate semantic-reference keys rejected.

#### Legacy adapter protocol boundary

- preserves Legacy identity anchors;
- does not invent Target or Universe scope;
- rejects objects that do not satisfy the minimum compatibility shape.

The isolated test result before adding the real-Legacy integration case was:

```text
16 passed
```

`ruff` and `mypy` were not installed in that isolated execution environment, so no claim is made that those checks passed there. The new modules are included in the repository mypy file scope and should be checked in the normal project development environment or CI.

### 4.2 Existing Legacy characterization reused

R1 review found substantial existing coverage in:

```text
tests/test_signal_intent.py
tests/test_macd_experiments.py
```

The project will reuse these tests instead of duplicating their intent.

Existing coverage includes:

- setup-to-intent mapping and completeness;
- strict/compatibility handling of unknown setup codes;
- confirmation timing and consistency;
- risk-priority and MACD policy behavior;
- Legacy MACD Experiment Identity required fields;
- identity hash changes for result-affecting mutations;
- stable canonical serialization;
- four-arm experiment identity separation;
- cache identity and tamper detection;
- counterfactual score/policy/interaction classification.

### 4.3 Real Legacy adapter test added

A repository test now constructs a real Legacy `MACDExperimentIdentity`, computes its existing canonical Legacy hash, adapts it to V2, and verifies that:

- code revision is preserved;
- Legacy full config hash is preserved;
- Legacy dataset-version reference is preserved;
- data-split and pipeline references are preserved;
- canonical Target and Universe identities remain absent rather than being invented.

This new real-Legacy integration test was committed after the isolated 16-test run.

The current execution environment could not clone the latest GitHub repository because DNS/network access to `github.com` was unavailable. Therefore, this document does **not** claim that the new real-Legacy integration test was executed in this session against the latest GitHub HEAD. It should run in the normal project environment or CI together with the existing Legacy test suite.

---

## 5. R2 Boundaries That Remain Binding

1. `core` must not import Legacy strategy policy.
2. `research` must not depend directly on `dividend_t` internals.
3. Legacy dependencies belong behind explicit compatibility adapters.
4. No second Experiment Identity system may be created for Candidate research.
5. `NO_ACTION` remains a Strategy Action, not an Input Availability Status.
6. Generic `confidence: float` is not a canonical V2 contract.
7. Data Eligibility, Sample Role, Evidence Level and Authority State remain separate dimensions.
8. Stable IDs identify objects; they do not by themselves prove data, research or promotion authority.

---

## 6. R2 Completion Status

The initial kernel is implemented, but R2 is not fully complete.

Current state:

```text
Core identity primitives                         DONE
Semantic time primitives                         DONE
Input availability semantics                     DONE
Generic Experiment Identity                      DONE
First explicit Legacy compatibility adapter      DONE
Adapter test against real Legacy identity         ADDED / PENDING NORMAL-ENV EXECUTION
Existing signal-intent characterization reused    IDENTIFIED
Existing MACD identity characterization reused    IDENTIFIED
Legacy strategy compatibility boundaries          PENDING
Candidate-facing semantic contracts               DEFERRED TO OWNING STAGES/SPECS
```

The next R2-compatible work should be driven by actual consumers rather than abstract completeness.

Priority:

1. run the complete project tests, ruff and mypy in the normal repository environment;
2. add only missing Legacy strategy compatibility boundaries required by a concrete migration consumer;
3. begin the minimal Data/Dataset contracts required by R3;
4. create PIT Universe and Candidate Target contracts when their owning stages begin;
5. avoid adding speculative framework abstractions that do not unblock Candidate research.

---

## 7. Exit Direction

R2 succeeds when new research can identify its data, target, feature/model dependencies and experiment semantics without treating Legacy action enums or integrated timing engines as platform truth.

The implementation principle remains:

> **Build only the shared contract needed by the next falsifiable research consumer, preserve Legacy behavior behind explicit boundaries, and do not confuse a new package layout with migrated authority.**
