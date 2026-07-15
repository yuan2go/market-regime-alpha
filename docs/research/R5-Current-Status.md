# R5 Candidate Discovery — Current Status

> **Status:** CURRENT
> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Purpose:** Current short-form authority for active implementation sequencing
> **Current audit:** `docs/architecture/Original-Intent-to-R5-Eligibility-Readiness-Audit.md`
> **Detailed references:** `R5-Candidate-Discovery-Rehearsal-Charter.md`, `R5-Provider-Rehearsal-Trading-Eligibility-Policy-v2.md`, `R5-Provider-Rehearsal-Market-Artifact.md`, `R5-Generic-Provider-Export-Adapter.md`

---

## 1. Status Precedence

This file is the current R5 implementation-status authority.

Older documents remain historical records. Their stale status lines do not override this file.

Known historical residues include:

```text
R5-Candidate-Dataset-Builder-Status.md
    predates the implemented Eligibility Policy / Materializer.

R5-Candidate-Discovery-Rehearsal-Charter.md
    contains an older deliverable list that predates implemented Calendar / PIT Universe work.

Original-Intent-to-R5-Consistency-Audit.md
    records the earlier Close Return-only gap that was later corrected by Close Return / MFE / MAE.
```

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

The provider-input path now has two implemented provider-neutral contracts:

```text
Generic normalized Provider Export Bundle
        ↓
Generic Provider Export Adapter
        ↓
Provider Rehearsal Market Artifact
        ↓
R5 research chain
```

---

## 4. Eligibility v1 — Compatibility Role

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

## 5. Provider-Rehearsal Eligibility v2 — Implemented

```text
r5-provider-rehearsal-trading-eligibility@v2
```

v2 supports:

```text
non-ST
non-suspended
listing age > 60 calendar days
minimum PIT liquidity under an identified measure
explicit Decision-Time buyability evidence
complete required PIT evidence
```

The default minimum listing age is:

```text
61 calendar days
```

which implements the original strict condition:

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

## 6. Candidate Buyability Is Not Execution Feasibility

v2 defines:

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

## 7. Provider Rehearsal Market Artifact — Implemented Contract

Implemented:

```text
market_regime_alpha.research.ProviderRehearsalMarketArtifact
```

It can identify and compose:

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

It always exposes:

```text
DataEligibility.REHEARSAL
```

The contract does not mean that a concrete provider has been integrated or validated.

---

## 8. Generic Provider Export Adapter — Implemented

Implemented:

```text
market_regime_alpha.research.provider_export_adapter
```

Current normalized schema:

```text
generic-provider-export-bundle-v1
```

The adapter accepts only explicitly normalized semantics and rejects missing or malformed required evidence.

It does not:

```text
auto-detect arbitrary CSV columns
guess vendor field meanings
invent timezone
invent availability time
invent bar finality
invent price-adjustment basis
infer listing age from a present-day snapshot
infer liquidity measure identity from a numeric column
infer buyability from limit_up_price alone
```

Concrete Xuntou/QMT/broker adapters may later map native provider fields into the generic normalized bundle.

---

## 9. Provider Integration Completion Boundary

Current state:

```text
Provider Rehearsal Market Artifact contract       IMPLEMENTED
Generic Provider Export Bundle schema             IMPLEMENTED
Strict Generic Provider Export Adapter            IMPLEMENTED
Provider-rehearsal Eligibility v2                  IMPLEMENTED

Xuntou native-field adapter                        NOT YET IMPLEMENTED
QMT / XtQuant native-field adapter                 NOT YET IMPLEMENTED
Broker archive native-field adapter                NOT YET IMPLEMENTED
Other concrete provider adapter                    NOT YET IMPLEMENTED
Real Provider / Export Data Run                    NOT AVAILABLE
Provider PIT Authority Verification                NOT AVAILABLE
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

## 10. Current Provenance Boundary

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

Changing result-affecting semantic conventions changes the relevant Artifact identity.

---

## 11. Legacy Compatibility Limitation

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

## 12. Current Implemented Status

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
Provider-rehearsal Eligibility v2                          IMPLEMENTED
Strict listing age > 60 calendar days boundary             IMPLEMENTED
Policy / Materializer provenance                            IMPLEMENTED
Historical Membership ∩ Eligibility Candidate assembly     IMPLEMENTED
Provider Rehearsal Market Artifact contract                 IMPLEMENTED
Generic Provider Export Adapter                            IMPLEMENTED

Normal full-repository test execution                       PENDING
Concrete Provider Adapter                                  NOT YET IMPLEMENTED
Real Provider / Export Data Run                            NOT AVAILABLE
Provider-backed multi-date Candidate panels                 NOT YET IMPLEMENTED
B1 transparent composite baseline                          NOT YET IMPLEMENTED
Immutable R5 run artifact                                   NOT YET IMPLEMENTED
Chronological/OOS Candidate validation                     NOT YET IMPLEMENTED
Formal Candidate evidence                                  NOT AVAILABLE
```

---

## 13. Current Verification Status

The code and tests are committed.

The current tool environment still does not provide a complete latest-HEAD repository execution path, so this status does **not** claim:

```text
latest HEAD pytest passed
latest HEAD ruff passed
latest HEAD mypy passed
```

Normal repository execution or CI remains required before implementation authority is increased.

---

## 14. Next Implementation Step

The next step requires one actual native data contract or export format:

```text
Xuntou export/API
QMT/XtQuant export/API
broker historical archive
or another identified provider
```

Then implement:

```text
Concrete Provider Adapter
        ↓
Generic Provider Export Bundle
        ↓
Provider Rehearsal Market Artifact
        ↓
Provider-Rehearsal Eligibility v2
        ↓
Provider-backed Candidate Population
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

The concrete adapter must map real provider fields without inventing:

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

---

## 15. Current Non-Goals

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

## 16. Current Principle

> **The project remains an A-share Candidate Discovery → Entry → Position Lifecycle → Exit research system, not a next-close-only model or an infrastructure project. The current provider-neutral contracts define what explicit data semantics are required, but the next meaningful step now needs one real native provider/export contract. No concrete provider is considered integrated or validated until its native fields are mapped through an identified adapter without invented PIT semantics.**
