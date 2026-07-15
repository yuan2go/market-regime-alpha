# R5 Provider-Rehearsal Market Artifact

> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Status:** ARTIFACT CONTRACT IMPLEMENTED — provider adapter and real provider run remain pending
> **Purpose:** Identify and compose the provider-backed/provider-export-backed evidence required by the first R5 Candidate research pipeline
> **Eligibility basis:** `R5-Provider-Rehearsal-Trading-Eligibility-Policy-v2.md`

---

## 1. Purpose

The next R5 step requires more than a collection of bars.

The first provider-backed Candidate panel needs an identified research input bundle containing enough evidence for:

```text
Historical Calendar
Historical PIT Universe
Historical Candidate Eligibility
Feature Materialization
Decision-Time reference prices
Close Return / MFE / MAE Targets
```

The new contract is:

```text
ProviderRehearsalMarketArtifact
```

implemented in:

```text
market_regime_alpha.research.provider_rehearsal_market_artifact
```

It lives in the downstream Research context because it composes independently owned Data, Calendar, Universe and Eligibility evidence.

It does not make the Data bounded context depend on Universe.

---

## 2. What the Artifact Contains

The first artifact identifies:

```text
Provider references
Source Artifact references
Retrieval convention
Market availability convention
Raw eligibility evidence convention
Bar finality convention
Price-adjustment basis
Historical Trading Calendar Artifact
Historical PIT Universe Artifact
Finalized daily rehearsal bars
Decision-Time price snapshots
Next-session OHLC observations
Raw Trading Eligibility observations
```

The raw Eligibility observations can carry provider-rehearsal v2 evidence for:

```text
listing age
PIT liquidity
Decision-Time buyability
```

---

## 3. Data Authority

Every artifact built by this contract exposes:

```text
DataEligibility.REHEARSAL
```

The contract does not grant:

```text
FORMAL_RESEARCH
```

merely because:

- a professional provider name is present;
- a source export exists;
- a Dataset Identity exists;
- the artifact can be materialized reproducibly.

Formal data authority remains claim- and scope-specific under the Data Constitution.

---

## 4. Provider and Source Provenance

The artifact requires:

```text
ProviderReference
SourceArtifactReference
```

A Provider Reference identifies:

```text
provider_id
product
contract_version
```

A Source Artifact Reference identifies:

```text
artifact_id
provider_id
retrieved_at
content_hash
locator
```

Every Source Artifact provider must be declared by the Dataset's Provider References.

This prevents an undeclared source file from silently entering the identified research bundle.

---

## 5. Semantic Conventions Enter Artifact Identity

The artifact identity includes explicit conventions for:

```text
retrieval
market-data availability
raw eligibility evidence availability
bar finality
price adjustment
```

Therefore:

```text
same numeric observations
+
different availability convention
```

produce a different Artifact Identity.

This is required because identical stored values can have different PIT meanings.

---

## 6. Upstream Artifact Composition

The R5 Research bundle composes:

```text
TradingCalendarArtifact
HistoricalPITUniverseArtifact
```

by identified artifact references/content.

The ownership remains:

```text
Data / Calendar / Universe
        ↓
Research input bundle
```

not:

```text
Research bundle becomes a new universal owner of Calendar or Universe semantics
```

---

## 7. Observation Families

### Historical daily bars

Current minimum fields:

```text
symbol
session_date
close
amount
available_at
finalized
```

These support the first transparent R5 Feature set.

They are not a universal provider bar schema.

### Decision-Time snapshots

Current minimum fields:

```text
symbol
decision_time
reference_price
available_at
```

These provide the declared 14:55 reference side for Candidate research.

### Next-session OHLC

Current minimum fields:

```text
symbol
session_date
open
high
low
close
available_at
```

These belong to the future Target side.

They must never enter Feature materialization for the earlier Decision Time.

### Raw Eligibility observations

The current canonical raw contract supports:

```text
ST
suspension
previous close
price-limit metadata
listing age
identified liquidity value / measure
Decision-Time buyability
```

with explicit:

```text
as_of
available_at
```

---

## 8. Stable Identity

The Provider Rehearsal Market Artifact derives identity from result-affecting dependencies including:

```text
Provider References
Source Artifact References
semantic conventions
Trading Calendar Artifact identity
PIT Universe Artifact identity
historical bars
Decision-Time snapshots
next-session OHLC
raw Eligibility observations
PIT-correct-for-scope declaration
limitations
```

Input ordering is normalized before hashing.

Therefore reordering Source Artifact references does not change identity.

Changing a result-affecting semantic convention does change identity.

---

## 9. Eligibility Materialization

The artifact can materialize:

```text
HistoricalTradingEligibilityArtifact
```

under an explicitly supplied:

```text
TradingEligibilityPolicy
```

The intended provider-backed path is:

```text
ProviderRehearsalMarketArtifact
        +
Provider-Rehearsal Eligibility Policy v2
        ↓
Historical Trading Eligibility Artifact
        ↓
PIT Universe Membership ∩ Eligibility
        ↓
Candidate Population
```

Missing required v2 evidence remains:

```text
UNKNOWN
```

The presence of a Provider Artifact does not automatically make missing evidence eligible.

---

## 10. Current Validation Boundaries

The current artifact validates, among other invariants:

- REHEARSAL Data Eligibility only;
- manifest Artifact Identity consistency;
- Source Artifact identity uniqueness;
- declared Provider ownership of source artifacts;
- unique historical bar keys;
- unique Decision-Time snapshot keys;
- unique next-session OHLC keys;
- unique raw Eligibility time-symbol keys;
- observation dates must belong to the identified Trading Calendar.

The current contract is intentionally smaller than a future formal provider dataset specification.

---

## 11. What Is Not Implemented Yet

The current increment does not yet provide:

```text
Generic provider-export file loader
Xuntou adapter
QMT/XtQuant adapter
broker archive adapter
actual provider authentication
provider API calls
provider licensing verification
provider field mapping
real provider PIT evidence verification
provider-backed multi-date Candidate panel run
```

Therefore:

```text
Provider Artifact Contract Implemented
≠
Provider Integrated
≠
Provider Data Validated
```

---

## 12. Tests

Current tests cover:

```text
REHEARSAL-only Dataset authority
stable Artifact Identity under source-reference reordering
identity change when availability convention changes
v2 Eligibility materialization from the artifact
missing v2 evidence remains UNKNOWN
undeclared Source Artifact provider is rejected
```

---

## 13. Next Implementation Step

The next concrete step is one of:

```text
A. Generic provider-export bundle adapter
```

or, when a specific data source/export is available:

```text
B. Concrete provider adapter
```

The adapter must map real provider/export fields into the identified Artifact without silently inventing:

```text
availability time
bar finality
adjustment basis
listing age
liquidity measure
Decision-Time buyability
```

The first real run should remain:

```text
REHEARSAL
```

and produce:

```text
provider-backed v2 Candidate Population
        ↓
Feature Materialization
        ↓
Close Return / MFE / MAE
        ↓
Target-specific Candidate panels
```

---

## 14. Principle

> **A provider-backed research run is not defined by a provider name. It is defined by identified source artifacts, explicit availability/finality/adjustment semantics, reproducible Calendar and Universe evidence, and enough point-in-time eligibility evidence to reconstruct the declared Candidate Population.**
