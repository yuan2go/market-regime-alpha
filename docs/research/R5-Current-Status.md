# R5 Candidate Discovery — Current Status

> **Status:** CURRENT
> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Purpose:** Short current-status authority for active implementation sequencing
> **Detailed references:** `R5-Candidate-Discovery-Rehearsal-Charter.md`, `R5-Candidate-Dataset-Builder-Status.md`, `R5-Versioned-Trading-Eligibility-Policy.md`

---

## 1. Status Precedence

This file is the current short-form R5 implementation status.

Where the older detailed status document:

```text
R5-Candidate-Dataset-Builder-Status.md
```

still contains:

```text
Versioned raw-field Eligibility Policy / Materializer    NOT YET IMPLEMENTED
```

that single line is superseded by the current implementation recorded here and in:

```text
R5-Versioned-Trading-Eligibility-Policy.md
```

The older document remains useful as a detailed historical implementation record.

---

## 2. Current Implemented Chain

```text
Historical Trading Calendar Artifact
        ↓
Resolved Next Trading Session

Historical PIT Universe Membership Artifact
        +
Raw Historical Eligibility Evidence
        ↓
Versioned Trading Eligibility Policy
        ↓
Exact-Decision-Time Eligibility Materializer
        ↓
Historical Trading Eligibility Artifact
        ↓
Candidate Population
        ↓
Transparent Feature Materialization
        ↓
Close Return / MFE / MAE Target Materialization
        ↓
Target-Specific Candidate Dataset / Panel
        ↓
Deterministic B0 Ranking
        ↓
Cross-Sectional Rehearsal Evaluation
```

---

## 3. Newly Completed in the Current Increment

```text
Versioned Trading Eligibility Policy                       IMPLEMENTED
Policy Artifact Identity                                    IMPLEMENTED
Versioned Eligibility Materializer                          IMPLEMENTED
Raw Evidence Availability Convention in Artifact Identity  IMPLEMENTED
Exact-Decision-Time Eligibility Materialization             IMPLEMENTED
Explicit ELIGIBLE / INELIGIBLE / UNKNOWN semantics         IMPLEMENTED
Valid empty Eligibility Snapshot preservation               IMPLEMENTED
Legacy eligibility sidecar raw-observation adapter          IMPLEMENTED
Legacy raw sidecar → Policy → Candidate integration test    IMPLEMENTED
```

---

## 4. R5 Eligibility Policy v1

Current policy:

```text
r5-rehearsal-trading-eligibility@v1
```

Current hard exclusions:

```text
SUSPENDED
ST_EXCLUDED
```

Current incomplete-evidence behavior:

```text
missing required evidence
or
raw observation unavailable by Decision Time
        ↓
UNKNOWN
```

`UNKNOWN` does not enter the current Candidate Population.

The v1 policy requires raw completeness for:

```text
prev_close
limit_up_price
limit_down_price
limit_regime
```

but does not interpret these fields as proof of execution feasibility.

---

## 5. Current Provenance Boundary

A versioned eligibility artifact now identifies:

```text
Source Dataset Identity
Policy Version
Policy Artifact Identity
Materializer Version
Raw Evidence Convention
Exact Snapshot Times
Eligibility Results and Reasons
```

Therefore:

```text
same symbol-level results
≠
same research artifact
```

when Policy, Materializer, or raw evidence semantics differ.

---

## 6. Legacy Compatibility Limitation

The existing Legacy eligibility sidecar lacks a separate availability timestamp.

The adapter therefore uses the explicit rehearsal-only convention:

```text
LEGACY_TIMESTAMP_AVAILABLE_AT_OBSERVATION_TIME
```

This must not be silently inherited by provider-backed data.

The Legacy universe sidecar may also already embed filters such as ST or liquidity restrictions inside its own membership method. Provider-backed research should separate:

```text
Universe Membership
from
Trading Eligibility
```

more cleanly than the compatibility path can guarantee.

---

## 7. Current Non-Goals

The current eligibility policy does not claim to model:

- limit-up queue fillability;
- order-book depth;
- real buy/sell execution probability;
- final Execution Feasibility;
- Portfolio risk approval;
- Entry timing;
- Position Lifecycle;
- Exit timing;
- positive Alpha.

---

## 8. Current Verification Status

The code and tests are committed.

The current tool environment still does not provide a complete latest-HEAD repository execution path, so this status does **not** claim:

```text
latest HEAD pytest passed
latest HEAD ruff passed
latest HEAD mypy passed
```

Normal repository execution or CI remains required before implementation authority is increased.

---

## 9. Next Implementation Step

The next R5 data step is:

```text
Provider-backed or provider-export-backed REHEARSAL Market Artifact
```

It must provide or explicitly justify:

```text
source identity
schema identity
retrieval / availability semantics
bar finality
price-adjustment basis
historical raw eligibility evidence
Decision Time snapshots
next-session OHLC observations
```

Then the project can build the first provider-backed:

```text
Historical Candidate Population
        ↓
Feature Materialization
        ↓
Close Return / MFE / MAE
        ↓
Target-Specific Candidate Panels
        ↓
B0 vs B1 Comparison
        ↓
Immutable R5 Run Artifact
```

---

## 10. Current Principle

> **Trading Eligibility is now an identified, versioned policy result over evidence actually available at the Candidate Decision Time. Missing evidence becomes UNKNOWN, policy and materializer semantics enter artifact identity, and execution feasibility remains a separate future owner.**
