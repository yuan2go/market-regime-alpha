# R5 Candidate Discovery — Current Status

> **Status:** CURRENT
> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Purpose:** Short current-status authority for active implementation sequencing
> **Current audit:** `docs/architecture/Original-Intent-to-R5-Eligibility-Readiness-Audit.md`
> **Detailed references:** `R5-Candidate-Discovery-Rehearsal-Charter.md`, `R5-Versioned-Trading-Eligibility-Policy.md`, `R5-Provider-Rehearsal-Trading-Eligibility-Policy-v2.md`

---

## 1. Status Precedence

This file is the current short-form R5 implementation status.

Older documents remain useful as historical implementation records, but their stale status lines do not override this file.

Known historical residues include:

```text
R5-Candidate-Dataset-Builder-Status.md
    still contains an older line saying Eligibility Policy / Materializer was not implemented.

R5-Candidate-Discovery-Rehearsal-Charter.md
    still contains an older deliverable list that names Historical Calendar / PIT Universe as future work.

Original-Intent-to-R5-Consistency-Audit.md
    records the earlier Close Return-only gap that has since been corrected by Close Return / MFE / MAE.
```

The current architecture direction remains unchanged.

---

## 2. Preserved Original Intent

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

ETF / Theme / Market Context remains upstream and available for later controlled incremental comparison.

---

## 3. Current Implemented Research Chain

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

## 4. Eligibility v1 — Current Role

Policy:

```text
r5-rehearsal-trading-eligibility@v1
```

v1 remains valid for:

```text
Legacy compatibility
minimum infrastructure tests
ST / suspension hard exclusions
exact-Decision-Time evidence semantics
explicit UNKNOWN behavior
```

v1 is **not** the complete original first-rehearsal Candidate-pool policy.

It does not represent:

```text
minimum listing age
minimum liquidity threshold
explicit Decision-Time buyability
```

---

## 5. Provider-Rehearsal Eligibility v2 — Implemented Contract

Policy factory:

```text
r5_provider_rehearsal_trading_eligibility_policy_v2(...)
```

Human-readable version:

```text
r5-provider-rehearsal-trading-eligibility@v2
```

v2 adds explicit policy support for:

```text
minimum listing age in calendar days
minimum PIT liquidity value
identified liquidity measure
Decision-Time buyability evidence
```

The current default listing-age threshold is:

```text
60 calendar days
```

The liquidity threshold is not globally hard-coded.

The caller must explicitly provide:

```text
minimum_liquidity_value
liquidity_measure_id
```

This makes the threshold and measure result-affecting Policy configuration.

---

## 6. v2 Eligibility Semantics

Hard exclusions may include:

```text
SUSPENDED
ST_EXCLUDED
LISTING_AGE_BELOW_MINIMUM
LIQUIDITY_BELOW_MINIMUM
DECISION_NOT_BUYABLE
```

Missing or incompatible required evidence becomes:

```text
UNKNOWN
```

Examples:

```text
LISTING_AGE_MISSING
LIQUIDITY_VALUE_MISSING
LIQUIDITY_MEASURE_MISMATCH
DECISION_BUYABILITY_MISSING
DECISION_BUYABILITY_UNKNOWN
```

`UNKNOWN` does not enter the Candidate Population.

---

## 7. Buyability Is Not Final Execution Feasibility

v2 defines:

```text
DecisionBuyabilityStatus
    BUYABLE
    NOT_BUYABLE
    UNKNOWN
```

`BUYABLE` means only that the identified provider/adapter evidence did not classify the instrument as blocked under the scoped Candidate-population buyability rule.

It does not prove:

```text
guaranteed fill
queue priority
order-book depth
fill probability
final Execution Feasibility
```

Price-limit metadata alone does not automatically create `BUYABLE` or `NOT_BUYABLE`.

---

## 8. Provider-Rehearsal Readiness Boundary

The original-intent readiness audit found:

```text
Direction-Level Contradiction: NONE FOUND
```

and:

```text
Eligibility v1 Infrastructure: VALID
Original MVP Candidate Eligibility Coverage under v1: PARTIAL
```

The v2 contract now restores representational coverage for:

```text
non-ST
non-suspended
minimum listing age
minimum PIT liquidity
explicit Decision-Time buyability
complete required PIT evidence
```

Actual provider-backed materialization is still pending.

The code contract being able to represent v2 evidence does not prove that a provider supplies it correctly.

---

## 9. Current Provenance Boundary

A versioned Eligibility Artifact identifies:

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

when Policy, Materializer or raw-evidence semantics differ.

---

## 10. Legacy Compatibility Limitation

The existing Legacy eligibility sidecar lacks:

```text
separate availability timestamp
listing-age evidence
identified PIT liquidity evidence
explicit Decision-Time buyability evidence
```

Therefore:

```text
Legacy sidecar
+
v2 Policy
+
missing v2 evidence
        ↓
UNKNOWN
```

The system must not silently fall back to v1 eligibility.

The Legacy adapter still uses the explicit rehearsal-only convention:

```text
LEGACY_TIMESTAMP_AVAILABLE_AT_OBSERVATION_TIME
```

This must not be inherited by provider-backed data unless the provider contract justifies it.

---

## 11. Current Implemented Status

```text
Original-intent eligibility readiness audit                 COMPLETE
Controlled multi-date Candidate vertical slice             IMPLEMENTED
Four transparent baseline Features                         IMPLEMENTED
Close Return / MFE / MAE Target bundle                      IMPLEMENTED
Deterministic B0 Candidate ranker                           IMPLEMENTED
Cross-sectional rehearsal evaluation                       IMPLEMENTED

Historical Trading Calendar Artifact                       IMPLEMENTED
Historical PIT Universe Membership Artifact                IMPLEMENTED
Historical Trading Eligibility Artifact                    IMPLEMENTED
Eligibility v1                                             IMPLEMENTED
Provider-rehearsal Eligibility v2 contract                  IMPLEMENTED
Policy / Materializer provenance                            IMPLEMENTED
Historical Membership ∩ Eligibility Candidate assembly     IMPLEMENTED

Normal full-repository test execution                       PENDING
Provider-backed rehearsal market artifact                  NOT YET IMPLEMENTED
Provider-backed v2 eligibility evidence adapter             NOT YET IMPLEMENTED
Provider-backed multi-date Candidate panels                 NOT YET IMPLEMENTED
B1 transparent composite baseline                          NOT YET IMPLEMENTED
Immutable R5 run artifact                                   NOT YET IMPLEMENTED
Chronological/OOS Candidate validation                     NOT YET IMPLEMENTED
Formal Candidate evidence                                  NOT AVAILABLE
```

---

## 12. Current Verification Status

The code and tests are committed.

The current tool environment still does not provide a complete latest-HEAD repository execution path, so this status does **not** claim:

```text
latest HEAD pytest passed
latest HEAD ruff passed
latest HEAD mypy passed
```

Normal repository execution or CI remains required before implementation authority is increased.

---

## 13. Next Implementation Step

The next R5 data step is:

```text
Provider-backed or Provider-export-backed REHEARSAL Market Artifact
```

It must provide or explicitly justify:

```text
source identity
schema identity
retrieval / availability semantics
bar finality
price-adjustment basis
historical Calendar evidence
historical PIT Universe evidence
ST / suspension evidence
listing-age evidence
identified PIT liquidity evidence
Decision-Time buyability evidence
Decision-Time price snapshots
next-session OHLC observations
```

Then the project can materialize:

```text
Provider-backed v2 Candidate Population
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

## 14. Current Non-Goals

The current system does not claim to implement:

- final Execution Feasibility;
- guaranteed limit-up queue fillability;
- Portfolio approval;
- Entry timing;
- Position Lifecycle;
- Exit timing;
- complete event-risk exclusion;
- positive Alpha;
- formal provider PIT authority.

---

## 15. Current Principle

> **The project remains an A-share Candidate Discovery → Entry → Position Lifecycle → Exit research system, not a next-close-only model or an infrastructure project. Candidate eligibility must reproduce the declared research population: v1 remains a valid minimal compatibility policy, while provider-backed R5 research must use explicit listing-age, liquidity and Decision-Time buyability evidence under the versioned v2 policy before claiming that the original first-rehearsal stock-pool scope has been implemented.**
