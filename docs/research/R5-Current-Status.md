# R5 Candidate Discovery — Current Status

> **Status:** CURRENT
> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Purpose:** Current short-form authority for active implementation sequencing
> **Current audit:** `docs/architecture/Original-Intent-to-Current-Docs-and-Codex-Readiness-Audit.md`
> **Primary provider decision:** `docs/research/R5-Xuntou-Provider-and-Strategy-Priority.md`
> **Data-source roles:** `docs/research/R5-Data-Source-Role-Matrix.md`
> **Candidate research program:** `docs/research/R5-Candidate-Model-Research-Program.md`
> **Entry / Lifecycle / Exit research program:** `docs/research/Entry-Position-Lifecycle-Exit-Research-Program.md`

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

R5-Candidate-Model-Research-Program.md
    still contains an earlier B1 status line stating that B1 is the next model implementation.
    The research design remains active, but the current implementation status is defined here.
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
Position Lifecycle
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

ETF / Theme / Market Context remains upstream and available for controlled incremental comparison.

The practical buy/sell-point objective is now explicitly expressed as two separate path-dependent research problems:

```text
Entry:
    reduce adverse events that occur before favorable movement
    after a new position is initiated

Exit:
    reduce strong favorable continuation after premature exit
    without creating excessive late exits
```

Entry and Exit remain independent.

---

## 3. Current Provider Decision

The active primary provider is:

```text
Xuntou / ThinkTrader / XtQuant
```

The active R5 sequence is no longer a provider-selection exercise.

Public sources such as:

```text
Eastmoney
Tencent public market interfaces
other explicitly identified public sources
```

remain auxiliary under the Data Source Role Matrix.

The current rule is:

```text
Research Question
        ↓
Required Evidence
        ↓
Minimum Xuntou Adapter Increment
```

not:

```text
Complete the entire provider API
        ↓
Eventually begin strategy research
```

---

## 4. Current Implemented Research Chain

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
B0 / B1 Candidate Ranking
        ↓
Cross-Sectional Rehearsal Evaluation
```

The provider-input architecture also includes:

```text
Generic normalized Provider Export Bundle
        ↓
Generic Provider Export Adapter
        ↓
Provider Rehearsal Market Artifact
        ↓
R5 research chain
```

The generic provider path is an architecture boundary.

The active concrete provider for the next real adapter is Xuntou.

---

## 5. Eligibility Status

### v1 — Compatibility role

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

v1 is not the complete original first-rehearsal Candidate-pool policy.

### v2 — Provider-rehearsal policy

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

which implements:

```text
listing_age_calendar_days > 60
```

Missing or incompatible required evidence becomes:

```text
UNKNOWN
```

not `ELIGIBLE`.

Candidate buyability remains distinct from final Execution Feasibility.

---

## 6. Provider Rehearsal Contracts

Implemented:

```text
ProviderRehearsalMarketArtifact
Generic Provider Export Bundle schema
Strict Generic Provider Export Adapter
Provider-rehearsal Eligibility v2
```

These contracts can identify:

```text
provider / product contract
source artifact identity
retrieval time
source content hash
source locator
availability convention
bar-finality convention
price-adjustment basis
Calendar identity
Universe identity
Policy identity
Materializer version
Feature / Target / Experiment identities
```

They do not mean that a real Xuntou native adapter or a real Xuntou research run already exists.

---

## 7. Candidate Model Status

### B0 — Single-feature deterministic rank

```text
IMPLEMENTED
```

B0 remains the permanent minimum comparator.

### B1 — Transparent cross-sectional composite rank

Current status:

```text
CORE IMPLEMENTED
TESTS COMMITTED
LATEST FULL VERIFICATION NOT CONFIRMED
```

B1 currently supports the intended transparent design:

```text
explicit component Features
explicit higher/lower direction
explicit research role
cross-sectional rank-percentile normalization
explicit normalized weights
strict complete-case rejection
full Candidate Population accounting
identified composite specification
```

Known verification work remains:

```text
repair an AVAILABLE Target test fixture so future observed_at evidence is present
introduce a common structural ranking evaluation interface for B0 and B1
remove the B0-specific evaluation type workaround
ensure intended B1 public exports
include B1 in mypy scope where required
run focused and full validation
```

Do not change B1 scoring semantics while closing this verification work unless a separate reviewed research decision requires it.

### B2 / B3 and later

Research ladder remains:

```text
B2 — regularized statistical baseline
B3 — nonlinear / Learning-to-Rank
B4 — target-specific / multi-task
B5 — Market / ETF / Theme context increments
B6 — transaction-flow / order-flow increments
```

These are research directions, not current implemented model authority.

---

## 8. Entry / Position Lifecycle / Exit Status

The lower-level research direction is now documented in:

```text
docs/research/Entry-Position-Lifecycle-Exit-Research-Program.md
```

Current status:

```text
Entry / Lifecycle / Exit research decomposition          DOCUMENTED
Entry competing-event research target family            SPECIFIED IN RESEARCH DOC
Entry path Target code contract                          NOT YET IMPLEMENTED
Canonical Position State code contract                   NOT YET IMPLEMENTED
Exit continuation target family                          SPECIFIED IN RESEARCH DOC
Exit continuation Target code contract                   NOT YET IMPLEMENTED
Entry model validation                                   NOT AVAILABLE
Exit model validation                                    NOT AVAILABLE
```

Initial Entry research labels:

```text
UP_FIRST
DOWN_FIRST
TIMEOUT
```

Initial Exit continuation labels:

```text
CONTINUE_UP_FIRST
DRAWDOWN_FIRST
TIMEOUT
```

Diagnostics include:

```text
Post-Exit Regret
Avoided Drawdown
Late Exit
Profit Giveback
```

These are not current production claims.

---

## 9. Current Implementation Status

```text
Original-intent current-doc readiness audit                   COMPLETE
Controlled multi-date Candidate vertical slice                IMPLEMENTED
Four transparent baseline Features                            IMPLEMENTED
Close Return / MFE / MAE Target bundle                         IMPLEMENTED
Deterministic B0 Candidate ranker                              IMPLEMENTED
B1 transparent composite ranking core                         IMPLEMENTED
B1 latest full verification                                   PENDING
Cross-sectional rehearsal evaluation                          IMPLEMENTED

Historical Trading Calendar Artifact                          IMPLEMENTED
Historical PIT Universe Membership Artifact                   IMPLEMENTED
Historical Trading Eligibility Artifact                       IMPLEMENTED
Eligibility v1                                                IMPLEMENTED
Provider-rehearsal Eligibility v2                              IMPLEMENTED
Strict listing age > 60 boundary                              IMPLEMENTED
Policy / Materializer provenance                               IMPLEMENTED
Historical Membership ∩ Eligibility Candidate assembly        IMPLEMENTED
Provider Rehearsal Market Artifact contract                    IMPLEMENTED
Generic Provider Export Adapter                               IMPLEMENTED

Xuntou selected as primary provider                           DECIDED
Eastmoney / Tencent auxiliary role                            DECIDED
Xuntou native-field adapter                                   NOT YET IMPLEMENTED
Real Xuntou provider / export data run                         NOT AVAILABLE
Provider-backed multi-date Candidate panels                    NOT YET IMPLEMENTED
Immutable R5 run artifact                                      NOT YET IMPLEMENTED
Chronological/OOS Candidate validation                         NOT YET IMPLEMENTED

Entry path Target code contract                                NOT YET IMPLEMENTED
Canonical Position State code contract                         NOT YET IMPLEMENTED
Exit continuation Target code contract                         NOT YET IMPLEMENTED

Formal Candidate / Entry / Exit Alpha evidence                 NOT AVAILABLE
```

---

## 10. Current Verification Status

The code and tests are committed, but the current environment has not established a complete latest-HEAD verification result.

This status does not claim:

```text
latest HEAD pytest passed
latest HEAD ruff passed
latest HEAD mypy passed
```

Normal repository execution or CI remains required before implementation authority is increased.

---

## 11. Immediate Implementation Sequence

The current ordered sequence is:

```text
WP-0
Close B1 verification and common ranking evaluation interface
        ↓
WP-1
Freeze minimum Xuntou P0 native field mapping and PIT caveats
        ↓
WP-2
Implement minimum Xuntou P0 native adapter
        ↓
WP-3
Run provider-backed Xuntou REHEARSAL B0 / B1 experiments
        ↓
WP-4
Implement Entry Path Target contracts
UP_FIRST / DOWN_FIRST / TIMEOUT
        ↓
WP-5
Run first Candidate-only vs Candidate + Entry timing experiment
        ↓
WP-6
Implement canonical Position State contract
        ↓
WP-7
Implement Exit continuation Target contracts and simple control arms
```

Data integration remains experiment-driven.

Do not broaden the Xuntou adapter beyond the evidence required by an approved experiment.

---

## 12. Current Codex Handoff Boundary

Repository-level coding-agent guidance is now defined in:

```text
AGENTS.md
```

Current readiness:

```text
Bounded Codex work packages              READY
Unrestricted "finish the whole project" autonomy   NOT READY
```

Codex may implement approved work packages with explicit scope, tests and stop conditions.

Codex must not independently:

```text
change the Constitution
reinterpret project goals
invent provider PIT semantics
promote Alpha
collapse Candidate / Entry / Lifecycle / Exit into one score
open or retune sealed final-test evidence
expand Legacy God Objects as the new platform kernel
```

---

## 13. Current Non-Goals

The current system does not claim to implement:

- a real Xuntou native integration;
- final Execution Feasibility;
- guaranteed price-limit queue fillability;
- Portfolio approval;
- a validated Entry timing model;
- a validated Position Lifecycle model;
- a validated Exit timing model;
- complete event-risk exclusion;
- positive Alpha;
- formal provider PIT authority for every field;
- production trading authority.

---

## 14. Current Principle

> **The project remains an A-share Candidate Discovery → Entry → Position Lifecycle → Exit research system. Xuntou is the active primary data provider and public sources are explicit auxiliaries, but strategy/model research remains the priority. B1 now exists as a transparent ranking core whose verification must be closed before authority increases. The next research expansion is path-dependent Entry and Exit modeling, but only after provider-backed Candidate evidence is reproducible. Codex may implement bounded work packages under `AGENTS.md`; it must not reinterpret the architecture or invent missing market-data semantics.**
