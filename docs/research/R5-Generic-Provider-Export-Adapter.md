# R5 Generic Provider Export Adapter

> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Status:** IMPLEMENTED — strict normalized-export adapter contract and tests committed; concrete vendor mapping and real data run remain pending
> **Input authority:** `R5-Provider-Rehearsal-Market-Artifact.md`
> **Eligibility authority:** `R5-Provider-Rehearsal-Trading-Eligibility-Policy-v2.md`

---

## 1. Purpose

The Generic Provider Export Adapter provides one strict, provider-neutral bridge:

```text
Explicit normalized provider export bundle
        ↓
Generic Provider Export Adapter
        ↓
ProviderRehearsalMarketArtifact
```

It does **not** provide:

```text
arbitrary CSV auto-detection
vendor field guessing
availability-time invention
bar-finality invention
adjustment-basis invention
buyability inference from insufficient fields
```

Concrete Xuntou, QMT/XtQuant, broker archive or other vendor adapters may later translate their native schemas into the normalized bundle.

---

## 2. Schema Identity

Current normalized bundle schema:

```text
generic-provider-export-bundle-v1
```

The adapter rejects unsupported schema versions.

---

## 3. Required Top-Level Sections

The bundle requires:

```text
schema_version
provider_references
source_artifacts
conventions
pit_correct_for_scope
calendar
universe
daily_bars
decision_snapshots
next_session_bars
raw_eligibility_observations
```

`limitations` may be supplied as an explicit list.

Missing required sections fail closed.

---

## 4. Required Semantic Conventions

The bundle must explicitly declare:

```text
retrieval_convention
market_availability_convention
raw_eligibility_evidence_convention
bar_finality_convention
price_adjustment_basis
```

The adapter does not provide defaults for these semantics.

A concrete provider adapter must map actual vendor behavior into these fields explicitly.

---

## 5. Provider and Source Provenance

Provider references require:

```text
provider_id
product
contract_version
```

Source artifact references require:

```text
artifact_id
provider_id
retrieved_at
content_hash
locator
```

Timestamps must be timezone-aware.

A source artifact whose provider is not declared by the Dataset provider references is rejected by the downstream Provider Rehearsal Market Artifact.

---

## 6. Calendar and Universe

The normalized export must provide explicit historical Calendar and Universe sections.

### Calendar

Requires:

```text
source_dataset_id
market
calendar_version
timezone_name
sessions
```

Every session requires:

```text
trade_date
session_close
```

The adapter never infers Monday-Friday trading days.

### Universe

Requires:

```text
source_dataset_id
method_version
timezone_name
effective_time_convention
records
```

Every record requires:

```text
as_of_date
symbol
is_member
```

The adapter never carries a missing Universe date forward implicitly.

---

## 7. Market Observation Families

### Historical daily bars

Required fields:

```text
symbol
session_date
close
amount
available_at
finalized
```

### Decision-Time snapshots

Required fields:

```text
symbol
decision_time
reference_price
available_at
```

### Next-session OHLC

Required fields:

```text
symbol
session_date
open
high
low
close
available_at
```

The adapter requires explicit timezone-aware timestamps where time is represented.

It does not assume a timezone for naive datetime strings.

---

## 8. Raw Eligibility Evidence

The normalized export can provide:

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
listing_age_calendar_days
liquidity_value
liquidity_measure_id
decision_buyability
```

`decision_buyability` must be one of:

```text
BUYABLE
NOT_BUYABLE
UNKNOWN
```

Unknown strings such as:

```text
PROBABLY_BUYABLE
```

are rejected rather than coerced.

Missing optional v2 evidence remains missing and later becomes `UNKNOWN` when the v2 Policy requires it.

---

## 9. No Semantic Guessing

The Generic Adapter intentionally does not derive:

```text
listing_age_calendar_days from current security master without as-of proof
liquidity measure identity from a numeric column name guess
DecisionBuyabilityStatus from limit_up_price alone
available_at from file retrieval time
bar finality from timestamp age
price adjustment basis from price continuity
```

Those transformations belong to an identified concrete provider adapter or provider-export preparation process.

---

## 10. Validation Behavior

The adapter rejects, among other cases:

```text
missing required sections
unsupported schema version
missing explicit conventions
naive datetimes
invalid booleans
invalid dates
invalid DecisionBuyabilityStatus values
malformed provider/source references
invalid canonical observation values
```

Canonical downstream contracts provide an additional validation boundary for finite/positive prices, OHLC consistency and other observation invariants.

---

## 11. Identity Behavior

The normalized export is converted into:

```text
ProviderRehearsalMarketArtifact
```

The downstream Artifact normalizes result-irrelevant input ordering, such as Source Artifact reference ordering.

Therefore:

```text
same identified sources in different list order
→ same Artifact Identity
```

while changing result-affecting semantic conventions changes Artifact Identity.

---

## 12. Tests

Current tests cover:

```text
valid normalized bundle → REHEARSAL Provider Artifact
v2 Eligibility materialization from normalized export
Source Artifact ordering does not change identity
missing explicit availability time is rejected
naive datetime is rejected
unknown buyability enum is rejected
non-finite numeric input is rejected by the adapter/canonical validation chain
```

---

## 13. Completion Boundary

Current state:

```text
Generic normalized-export schema          IMPLEMENTED
Strict Generic Provider Export Adapter    IMPLEMENTED
Provider Rehearsal Market Artifact        IMPLEMENTED
Provider-rehearsal Eligibility v2         IMPLEMENTED

Xuntou native-field adapter               NOT YET IMPLEMENTED
QMT/XtQuant native-field adapter           NOT YET IMPLEMENTED
Broker archive native-field adapter       NOT YET IMPLEMENTED
Real provider/export data run             NOT AVAILABLE
Provider PIT authority verification       NOT AVAILABLE
```

Therefore:

```text
Generic Export Adapter Implemented
≠
Concrete Provider Integrated
≠
Real Provider Data Validated
```

---

## 14. Next Implementation Step

The next step requires one actual data source or export contract.

Then the project should implement:

```text
Concrete Provider Adapter
        ↓
Generic Provider Export Bundle
        ↓
Provider Rehearsal Market Artifact
        ↓
Provider-Rehearsal Eligibility v2
        ↓
Historical Candidate Populations
        ↓
Features
        ↓
Close Return / MFE / MAE
        ↓
Target-Specific Candidate Panels
```

The first concrete run remains `REHEARSAL`.

---

## 15. Principle

> **The Generic Provider Export Adapter standardizes explicit semantics; it does not manufacture them. A concrete provider integration is complete only when native fields are mapped through an identified adapter without guessing availability, finality, adjustment, liquidity, buyability or PIT meaning.**
