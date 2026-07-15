# R5 Candidate Discovery — Current Status

> **Status:** CURRENT
> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Purpose:** Short current-status authority for active implementation sequencing
> **Current audit:** `docs/architecture/Original-Intent-to-R5-Eligibility-Readiness-Audit.md`
> **Detailed references:** `R5-Candidate-Discovery-Rehearsal-Charter.md`, `R5-Versioned-Trading-Eligibility-Policy.md`, `R5-Provider-Rehearsal-Trading-Eligibility-Policy-v2.md`, `R5-Provider-Rehearsal-Market-Artifact.md`

---

## 1. Status Precedence

This file is the current short-form R5 implementation status.

Older documents remain useful as historical implementation records, but their stale status lines do not override this file.

Known historical residues include:

```text
R5-Candidate-Dataset-Builder-Status.md
    contains an older line saying Eligibility Policy / Materializer was not implemented.

R5-Candidate-Discovery-Rehearsal-Charter.md
    contains an older deliverable list that names Historical Calendar / PIT Universe as future work.

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

A downstream Provider Rehearsal Market Artifact contract now exists to compose the identified evidence required by this chain.

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

---

## 5. Provider-Rehearsal Eligibility v2 — Implemented Contract

Policy:

```text
r5-provider-rehearsal-trading-eligibility@v2
```

v2 adds explicit support for:

```text
minimum listing age in calendar days
minimum PIT liquidity value
identified liquidity measure
Decision-Time buyability evidence
```

The current default minimum listing age is:

```text
61 calendar days
```

This implements the preserved original requirement strictly as:

```text
listing_age_calendar_days > 60
```

Therefore:

```text
60 calendar days → INELIGIBLE
61 calendar days → passes the listing-age gate
```

The liquidity threshold is not globally hard-coded.

The caller must explicitly provide:

```text
minimum_liquidity_value
liquidity_measure_id
```

Missing or incompatible required v2 evidence becomes:

```text
UNKNOWN
```

not `ELIGIBLE`.

---

## 6. Provider Rehearsal Market Artifact — Implemented Contract

Implemented:

```text
market_regime_alpha.research.ProviderRehearsalMarketArtifact
```

The artifact can identify and compose:

```text
Provider References
Source Artifact References
retrieval convention
market availability convention
raw eligibility evidence convention
bar finality convention
price-adjustment basis
Historical Trading Calendar Artifact
Historical PIT Universe Artifact
historical daily bars
Decision-Time snapshots
next-session OHLC
raw v2 Eligibility evidence
```

The artifact always exposes:

```text
DataEligibility.REHEARSAL
```

The contract does not mean that any concrete provider has already been integrated or validated.

---

## 7. Provider Artifact Completion Boundary

Current state:

```text
Provider Artifact Contract                 IMPLEMENTED
Generic Provider Export Adapter            NOT YET IMPLEMENTED
Xuntou Adapter                             NOT YET IMPLEMENTED
QMT / XtQuant Adapter                      NOT YET IMPLEMENTED
Other concrete Provider Adapter            NOT YET IMPLEMENTED
Real Provider Data Run                     NOT AVAILABLE
Provider PIT Authority Verification        NOT AVAILABLE
```

Therefore:

```text
Artifact Contract Implemented
≠
Provider Integrated
≠
Provider Data Validated
```

---

## 8. Candidate Eligibility and Execution Remain Separate

v2 defines explicit:

```text
DecisionBuyabilityStatus
    BUYABLE
    NOT_BUYABLE
    UNKNOWN
```

`BUYABLE` does not prove:

```text
guaranteed fill
queue priority
order-book depth
fill probability
final Execution Feasibility
```

Price-limit metadata alone does not automatically create `BUYABLE` or `NOT_BUYABLE`.

---

## 9. Current Provenance Boundary

The current research path can identify:

```text
Provider / product contract
Source Artifact identity
retrieval time
source content hash
source locator
Dataset identity
Calendar identity
Universe identity
Policy identity
Materializer version
raw-evidence convention
market availability convention
bar-finality convention
price-adjustment basis
Feature / Target / Experiment identities
```

Changing a result-affecting semantic convention changes the relevant Artifact identity.

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
Strict listing age > 60 calendar days boundary             IMPLEMENTED
Policy / Materializer provenance                            IMPLEMENTED
Historical Membership ∩ Eligibility Candidate assembly     IMPLEMENTED
Provider Rehearsal Market Artifact contract                 IMPLEMENTED

Normal full-repository test execution                       PENDING
Generic Provider Export Adapter                            NOT YET IMPLEMENTED
Concrete Provider Adapter                                  NOT YET IMPLEMENTED
Real Provider / Export Data Run                            NOT AVAILABLE
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

The next practical step is:

```text
Generic Provider Export Adapter
```

or, when a concrete data export/API contract is available:

```text
Concrete Provider Adapter
```

The adapter must map real provider/export fields into the Provider Rehearsal Market Artifact without inventing:

```text
availability time
bar finality
price-adjustment basis
listing age
PIT liquidity measure
Decision-Time buyability
```

The first real run remains:

```text
REHEARSAL
```

and should produce:

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

- a real Xuntou/QMT/provider integration;
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

> **The project remains an A-share Candidate Discovery → Entry → Position Lifecycle → Exit research system, not a next-close-only model or an infrastructure project. The provider-rehearsal artifact contract now defines what a real data source must supply, while the v2 eligibility policy preserves the original strict `listing age > 60 calendar days` boundary as a default minimum of 61 calendar days. No provider is considered integrated or validated until an explicit adapter and identified source artifacts populate these contracts without invented PIT semantics.**
