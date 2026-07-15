# R5 Versioned Trading Eligibility Policy and Materializer

> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Status:** IMPLEMENTED — code and tests committed; normal-environment execution remains pending
> **Scope:** Versioned raw-field Trading Eligibility Policy, exact-Decision-Time materialization, and Legacy rehearsal-sidecar compatibility
> **Authority:** Research/implementation status. This document does not override the Constitution.
> **Related:** `R5-Candidate-Discovery-Rehearsal-Charter.md`, `R5-Candidate-Dataset-Builder-Status.md`, `Original-Intent-to-R5-Consistency-Audit.md`

---

## 1. Status Synchronization

This document records the current status of the R5 Trading Eligibility Policy / Materializer increment.

It supersedes the older status line in:

```text
docs/research/R5-Candidate-Dataset-Builder-Status.md
```

that still states:

```text
Versioned raw-field Eligibility Policy / Materializer    NOT YET IMPLEMENTED
```

The current implementation status is now:

```text
Versioned raw-field Eligibility Policy / Materializer    IMPLEMENTED
Legacy eligibility sidecar raw-observation adapter       IMPLEMENTED
Policy Artifact Identity binding                          IMPLEMENTED
Exact-Decision-Time materialization                       IMPLEMENTED
Explicit UNKNOWN semantics                                IMPLEMENTED
Valid empty Eligibility Snapshot preservation             IMPLEMENTED
Provider-backed rehearsal market artifact                 NOT YET IMPLEMENTED
```

The larger R5 status document should be consolidated in a later normal repository editing pass without changing the semantics recorded here.

---

## 2. Purpose

The new capability closes the gap between:

```text
Historical raw eligibility evidence
        ↓
??? implicit rules ???
        ↓
ELIGIBLE / INELIGIBLE / UNKNOWN
```

and replaces it with:

```text
Historical raw eligibility evidence
        ↓
Identified Trading Eligibility Policy
        ↓
Exact-Decision-Time Materializer
        ↓
Historical Trading Eligibility Artifact
        ↓
Candidate Population assembly
```

The goal is not to create a universal definition of whether an A-share order can execute.

The goal is to make the Candidate-population eligibility decision:

- explicit;
- versioned;
- reproducible;
- PIT-aware;
- fail-closed;
- separately owned from Universe Membership and Execution Feasibility.

---

## 3. Ownership Boundary

The preserved ownership chain is:

```text
Universe
    owns historical Membership

Universe Eligibility
    owns raw eligibility evidence,
    versioned eligibility policy,
    and eligibility policy results

Candidate Discovery
    owns Membership ∩ Eligibility
    → Candidate Population

Execution
    later owns actual order feasibility / fill semantics
```

Therefore:

```text
Universe Membership
≠
Trading Eligibility
≠
Execution Feasibility
```

The implementation does not move Candidate Population assembly back into the Universe bounded context.

---

## 4. Existing Raw Eligibility Evidence

The existing Legacy rehearsal sidecar contract already requires these fields:

```text
symbol
timestamp
is_suspended
is_st
prev_close
limit_up_price
limit_down_price
limit_regime
```

The versioned v1 policy uses these fields conservatively.

### Direct policy evidence

```text
is_suspended
is_st
```

### Required raw-evidence completeness in v1

```text
prev_close
limit_up_price
limit_down_price
limit_regime
```

The price-limit metadata is required for the v1 rehearsal raw-evidence contract, but its mere presence does not prove that an order can or cannot execute.

---

## 5. Raw Observation Contract

Implemented:

```text
market_regime_alpha.universe.eligibility_policy.RawTradingEligibilityObservation
```

Each raw observation records:

```text
as_of
available_at
symbol
is_suspended
is_st
prev_close
limit_up_price
limit_down_price
limit_regime
```

### Time semantics

`as_of` means:

> the exact information-state time represented by the raw record.

`available_at` means:

> the earliest time the research system may use the record.

The materializer does not assume that because a record exists in storage it was available at the Candidate Decision Time.

---

## 6. Versioned Policy Identity

Implemented:

```text
market_regime_alpha.universe.eligibility_policy.TradingEligibilityPolicy
```

The initial R5 policy is:

```text
policy_name = r5-rehearsal-trading-eligibility
version = v1
exclude_st = true
require_prev_close = true
require_limit_metadata = true
```

The effective human-readable version is:

```text
r5-rehearsal-trading-eligibility@v1
```

The Policy also has a content-derived:

```text
policy_artifact_id
```

Result-affecting configuration enters Policy Identity.

Therefore:

```text
same policy_name
+
same version string
+
different configuration
```

still produces a different Policy Artifact Identity.

This prevents a version string alone from laundering different policy definitions into one research identity.

---

## 7. R5 Policy v1 Decision Rules

The initial policy is intentionally small.

### Hard ineligibility

```text
is_suspended = true
    → INELIGIBLE
    → reason: SUSPENDED

exclude_st = true
and
is_st = true
    → INELIGIBLE
    → reason: ST_EXCLUDED
```

Hard ineligibility evidence is sufficient to exclude the instrument even if other raw fields are missing.

Example:

```text
is_suspended = true
limit_regime = missing
```

still produces:

```text
INELIGIBLE / SUSPENDED
```

rather than `UNKNOWN`.

---

## 8. Explicit UNKNOWN Semantics

When no hard exclusion is known but required evidence is incomplete, the result is:

```text
UNKNOWN
```

not:

```text
ELIGIBLE
```

Current reason codes include:

```text
RAW_OBSERVATION_MISSING
RAW_OBSERVATION_NOT_AVAILABLE_BY_DECISION_TIME
SUSPENSION_STATUS_MISSING
ST_STATUS_MISSING
PREV_CLOSE_MISSING
LIMIT_UP_PRICE_MISSING
LIMIT_DOWN_PRICE_MISSING
LIMIT_REGIME_MISSING
```

The policy is therefore fail-closed for Candidate Population construction:

```text
UNKNOWN
≠
ELIGIBLE
```

An `UNKNOWN` instrument does not enter the Candidate Population under the current intersection rule.

---

## 9. What Price-Limit Metadata Does Not Mean

The v1 policy deliberately does **not** implement rules such as:

```text
current price == limit_up_price
    → automatically ineligible
```

or:

```text
limit_regime == 20%
    → automatically eligible/ineligible
```

The current raw eligibility evidence does not include enough information to make claims about:

- whether the stock is sealed at limit-up;
- queue depth;
- available ask liquidity;
- order-book state;
- expected fill probability;
- whether a buy order can actually execute;
- whether a sell order can actually execute.

Those belong to later, explicitly scoped capabilities such as:

```text
more specific Trading Eligibility Policy
or
Execution Feasibility
```

with additional PIT inputs.

---

## 10. Exact-Decision-Time Materialization

Implemented:

```text
materialize_historical_trading_eligibility(...)
```

The materializer requires explicit:

```text
decision_times
```

For every Decision Time it:

1. resolves the exact-date PIT Universe Membership snapshot;
2. iterates only that snapshot's member symbols;
3. looks for a raw eligibility observation at the exact Decision Time;
4. checks whether the raw observation was available by Decision Time;
5. evaluates the versioned Policy;
6. creates an explicit `ELIGIBLE / INELIGIBLE / UNKNOWN` result;
7. preserves the Decision Time as an identified Eligibility Snapshot.

It does not silently carry:

```text
14:50 raw eligibility state
```

forward to:

```text
14:55 Candidate Decision Time
```

---

## 11. Missing and Late Raw Observations

### No exact raw observation

```text
RAW_OBSERVATION_MISSING
→ UNKNOWN
```

### Raw observation exists but becomes available after Decision Time

```text
RAW_OBSERVATION_NOT_AVAILABLE_BY_DECISION_TIME
→ UNKNOWN
```

Therefore:

```text
exists in historical storage
≠
available to the model at Decision Time
```

---

## 12. Eligibility Artifact Provenance

`HistoricalTradingEligibilityArtifact` now supports:

```text
policy_artifact_id
```

The artifact identity includes:

- source Dataset Identity;
- policy version;
- Policy Artifact Identity when supplied;
- explicit snapshot times;
- symbol-level eligibility results and reasons.

Two policies that happen to produce the same symbol-level results may still produce different Eligibility Artifact identities when their Policy identities differ.

This preserves:

```text
same observed result
≠
same research definition
```

---

## 13. Valid Empty Opportunity Sets

A valid Candidate Population may be empty.

The initial Eligibility Artifact builder previously required at least one symbol-level eligibility record. That could incorrectly reject:

```text
PIT Universe snapshot exists
but
member_symbols = empty
```

The builder now supports explicit:

```text
snapshot_as_of_times
```

Therefore:

```text
0 Universe members
→ 0 Eligibility records
→ identified empty Eligibility Snapshot
→ valid empty Candidate Population
```

The system does not fabricate fallback candidates merely to avoid an empty result.

---

## 14. Legacy Eligibility Sidecar Compatibility Boundary

Implemented:

```text
market_regime_alpha.legacy.eligibility_sidecar_adapter
```

The existing Legacy sidecar is adapted into:

```text
RawTradingEligibilityObservation
```

The adapter requires:

```text
symbol
timestamp
is_suspended
is_st
prev_close
limit_up_price
limit_down_price
limit_regime
```

It rejects:

- missing required fields;
- string booleans pretending to be booleans;
- invalid timestamps;
- duplicate time-symbol keys;
- missing/invalid symbol strings;
- missing/invalid `limit_regime` strings;
- invalid numeric values through the canonical raw-observation contract.

---

## 15. Explicit Legacy Availability Assumption

The Legacy sidecar exposes:

```text
timestamp
```

but not a separate:

```text
available_at
```

The compatibility adapter therefore records the rehearsal-only assumption:

```text
LEGACY_TIMESTAMP_AVAILABLE_AT_OBSERVATION_TIME
```

Operationally:

```text
available_at = timestamp
```

This is not a universal provider rule.

A provider-backed implementation must supply or justify actual availability semantics.

---

## 16. End-to-End Rehearsal Chain

The current code can now execute the following identified chain:

```text
Legacy eligibility sidecar
        ↓
Legacy compatibility adapter
        ↓
RawTradingEligibilityObservation
        ↓
R5 Trading Eligibility Policy v1
        ↓
Historical Trading Eligibility Artifact
        ↓
Historical PIT Universe Membership
        ∩
Historical Trading Eligibility
        ↓
Candidate Population
```

The integration test verifies that:

- a PIT member with complete eligible evidence enters the Candidate Population;
- an ST member is excluded;
- a suspended member is excluded;
- a raw record for a non-member does not create Candidate membership.

---

## 17. Relationship to Legacy Universe Semantics

The Legacy universe sidecar field:

```text
eligible
```

is still adapted only as:

```text
membership under the Legacy sidecar's own universe method
```

It is not reinterpreted as canonical Trading Eligibility.

A Legacy universe method may already embed exclusions such as ST or liquidity filters. Therefore a Legacy compatibility run may contain overlapping historical filtering between:

```text
Legacy membership method
and
new explicit Eligibility Policy
```

This is a known compatibility limitation.

Provider-backed R5 research should use clearly separated definitions for:

```text
Universe Membership
Trading Eligibility
```

so the same exclusion is not hidden in both owners.

---

## 18. Tests Added

Current new tests cover:

```text
tests/universe/test_eligibility_policy.py
tests/universe/test_eligibility_policy_identity.py
tests/legacy/test_eligibility_sidecar_adapter.py
tests/candidates/test_r5_eligibility_policy_pipeline.py
```

Key invariants include:

- Policy Identity changes with result-affecting configuration;
- hard ineligibility evidence takes precedence over unrelated missing fields;
- incomplete required evidence becomes `UNKNOWN`, not `ELIGIBLE`;
- limit metadata alone does not create an execution/fillability decision;
- only PIT Universe members receive policy materialization records;
- absent raw evidence becomes explicit `UNKNOWN`;
- post-Decision-Time availability becomes explicit `UNKNOWN`;
- duplicate raw time-symbol keys are rejected;
- valid empty Eligibility Snapshots are preserved;
- same policy results under different Policy identities produce different Eligibility Artifact identities;
- Legacy sidecar timestamp availability assumption is explicit;
- Legacy malformed strings are not silently normalized into valid evidence;
- end-to-end raw sidecar → Policy → Eligibility Artifact → Candidate Population wiring is covered.

---

## 19. Current Authority

The current implementation proves only that:

```text
A versioned, explicit, exact-time Trading Eligibility policy can be materialized reproducibly
from the declared rehearsal raw-field contract.
```

It does not prove:

```text
The raw data is provider-authoritative.
The Legacy sidecar is formally PIT-correct.
The policy is the optimal A-share tradability definition.
A symbol marked ELIGIBLE can definitely be filled.
A Candidate will generate positive return.
```

---

## 20. Next Implementation Sequence

The next R5 data step is now:

```text
1. Execute the current R3/R4/R5 suite in a complete repository environment
        ↓
2. Build one provider-backed or provider-export-backed REHEARSAL market artifact
        ↓
3. Supply actual provider availability/finality semantics
        ↓
4. Materialize historical Calendar / Universe / Eligibility / Features / Targets
        ↓
5. Build provider-backed target-specific Candidate panels
        ↓
6. Run B0 and first B1 transparent comparison
        ↓
7. Write an immutable R5 run artifact
```

The next provider-backed artifact must not silently inherit:

```text
LEGACY_TIMESTAMP_AVAILABLE_AT_OBSERVATION_TIME
```

unless the provider contract actually justifies that convention.

---

## 21. Implementation Principle

> **Trading Eligibility is an identified policy result over information actually available at the Candidate Decision Time. Missing evidence becomes UNKNOWN, hard exclusion evidence remains explicit, Policy configuration enters artifact identity, and no amount of price-limit metadata is allowed to masquerade as final execution feasibility without the required PIT market evidence.**
