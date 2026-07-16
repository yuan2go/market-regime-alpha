# R5 Candidate Discovery — Current Status

> **Status:** CURRENT
> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Purpose:** Current short-form authority for active implementation sequencing
> **Current audit:** `docs/architecture/Original-Intent-to-Current-Docs-and-Codex-Readiness-Audit.md`
> **Primary provider decision:** `docs/research/R5-Xuntou-Provider-and-Strategy-Priority.md`
> **Data-source roles:** `docs/research/R5-Data-Source-Role-Matrix.md`
> **Candidate research program:** `docs/research/R5-Candidate-Model-Research-Program.md`
> **Entry / Lifecycle / Exit research program:** `docs/research/Entry-Position-Lifecycle-Exit-Research-Program.md`
> **Xuntou P0 official evidence:** `docs/research/R5-Xuntou-P0-Official-Documentation-Evidence.md`
> **Xuntou P0 mapping / adapter status:** `docs/specs/Xuntou-P0-Native-Field-Mapping.md` / `docs/research/R5-Xuntou-P0-Adapter-Status.md`

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

Xuntou normalized native P0 export
        ↓
Xuntou P0 Native Adapter
        ↓
the same Provider Rehearsal Market Artifact
```

The generic provider path is an architecture boundary.

The active concrete provider adapter is Xuntou. It currently consumes an identified normalized
native export; runtime XtQuant extraction and a real provider-backed run remain unavailable.

An auxiliary Tencent-current + local-history + BaoStock-gap-fill path is now implemented and has
completed one identified live `EXPLORATORY` run. This does not replace the Xuntou primary-provider
decision and cannot produce `REHEARSAL` or `FORMAL_RESEARCH` authority.

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
Xuntou P0 Native Field Mapping contract
Xuntou normalized native export schema and adapter
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

The Xuntou mapping and adapter are bounded to `REHEARSAL`. Their existence does not mean that
XtQuant runtime extraction was executed, historical PIT semantics were verified, or a real Xuntou
research run exists. Current mapping and implementation limitations are recorded in:

```text
docs/specs/Xuntou-P0-Native-Field-Mapping.md
docs/research/R5-Xuntou-P0-Adapter-Status.md
```

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
WP-0 FOCUSED VERIFICATION PASSED
LATEST FULL VERIFICATION PENDING
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

WP-0 closed the intended B1 integration items:

```text
AVAILABLE Target test fixture supplies future observed_at evidence
B0 and B1 share a structural Candidate ranking evaluation interface
B1 evaluation no longer requires a B0-specific type workaround
intended B1 public APIs are exported
B1 is included in the scoped mypy configuration
B1 target-blindness is covered by regression testing
```

B1 scoring semantics were not changed while closing this verification work. Latest full-repository verification remains pending for the reasons recorded in Section 10.

### Tencent composite auxiliary experiment

Current status:

```text
Composite auxiliary acquisition / merge / quality gate          IMPLEMENTED
Non-overwriting seven-file run artifact                          IMPLEMENTED
60-date B0 / B1-A through B1-E exploratory evaluation            COMPLETED
Live run ID                                                      tencent-composite-20260716T164159+0800-4a63e9565c
Accepted symbols                                                 20 / 20
Selected common sessions                                         82
Available common complete sessions                               248
Decision Dates                                                   60; 2026-04-17 through 2026-07-15
Target families                                                  Close Return / MFE / MAE
Models per Target                                                4 B0 controls + 5 fixed B1 ablations
Data eligibility                                                 EXPLORATORY
Canonical provider authority                                     Xuntou primary; unchanged
```

The B1 ladder is fixed and untuned. The run records descriptive metrics and performs no winner
selection. It is not formal Alpha evidence. Historical availability, PIT membership, buyability,
bar-finality, and adjustment revision history remain unverified as recorded in the run limitations.

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
B1 WP-0 focused verification                                  PASSED
B1 latest full verification                                   PENDING
Cross-sectional rehearsal evaluation                          IMPLEMENTED
Tencent composite exploratory auxiliary path                  IMPLEMENTED
Tencent composite 20-symbol live acquisition                  COMPLETED — 20 / 20 accepted
Tencent composite 60-date B0 / B1 run                         COMPLETED — identified run recorded above
Tencent composite non-overwriting run artifacts               IMPLEMENTED
Dividend-T refresh from accepted composite frames             COMPLETED — 20 / 20 rows successful

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
Xuntou P0 official-documentation evidence review              COMPLETE
Xuntou P0 native field mapping specification v2               COMPLETE; RUNTIME SEMANTICS PARTIAL
Xuntou normalized native/export adapter v2                    IMPLEMENTED
Xuntou historical Decision-Time buyability                    UNKNOWN EXCEPT CONFIRMED SUSPENSION
XtQuant runtime extraction                                    NOT IMPLEMENTED / NOT EXECUTED
Real Xuntou provider / export data run                         NOT AVAILABLE
Provider-backed multi-date Candidate panels                    NOT YET IMPLEMENTED
Immutable R5 run artifact                                      NOT YET IMPLEMENTED
Chronological/OOS Candidate validation                         NOT YET IMPLEMENTED

Tencent auxiliary multi-date Candidate panels                  IMPLEMENTED — EXPLORATORY ONLY
Tencent auxiliary chronological descriptive evaluation         IMPLEMENTED — NOT FORMAL OOS EVIDENCE

Entry path Target code contract                                NOT YET IMPLEMENTED
Canonical Position State code contract                         NOT YET IMPLEMENTED
Exit continuation Target code contract                         NOT YET IMPLEMENTED

Formal Candidate / Entry / Exit Alpha evidence                 NOT AVAILABLE
```

---

## 10. Current Verification Status

Tencent composite verification was executed on 2026-07-16. The latest successful live run used
code revision:

```text
d99bb899b7397bba0fd3f8095b04449721923f60
```

Live-source evidence:

```text
Tencent one-symbol smoke test
PASS — 601919.SH, 267 raw one-minute rows, source date 2026-07-16

First full run
tencent-composite-20260716T163401+0800-4a63e9565c
PASS — Candidate path 20 / 20 accepted, 82 selected sessions, 60 Decision Dates
Dividend-T — 18 successful / 2 contract-error rows

Deterministic repair
Filtered Tencent after-hours rows after 15:00 from the composite boundary.
Added missing SOFT risk-enforcement metadata to top-divergence SELL_T candidates.

Latest full run
tencent-composite-20260716T164159+0800-4a63e9565c
PASS — 20 / 20 accepted, 82 selected sessions, 60 Decision Dates
PASS — 3 Target families, each with 4 B0 and 5 fixed B1 evaluations
PASS — 61 source partitions / Source Artifacts, 0 failed attempts, 0 retained conflicts
PASS — Dividend-T snapshot 20 successful / 0 failed rows
```

Focused and affected-area results:

```text
python3 -m pytest -o addopts='' <nine Tencent composite test files> -q
PASS — 29 passed

python3 -m pytest -o addopts='' tests/research tests/candidates tests/test_a_share_bars.py tests/test_tencent_minute_cache.py tests/test_dividend_trend_snapshot.py tests/legacy/test_trend_snapshot_characterization.py tests/test_dividend_t_model.py -q
PASS — 125 passed, 4 subtests passed

python3 -m ruff check <all changed Tencent composite, Feature, CLI, and test files>
PASS — All checks passed

python3 -m mypy scripts/run_tencent_composite_exploratory.py <eight Tencent composite source files>
PASS — no issues found in 9 source files
```

Full-repository results:

```text
python3 -m pytest -q
FAIL — 2 pre-existing import-file-mismatch collection errors for duplicate test_contracts.py names
       under tests/data versus tests/features and tests/universe

python3 -m ruff check .
FAIL — 1 pre-existing F401 unused timedelta import in
       tests/research/test_provider_rehearsal_market_artifact.py

python3 -m mypy
FAIL — 6 pre-existing errors in 4 files outside the Tencent composite changes; 51 files checked
```

No full-repository pass is claimed.

WP-0 verification was executed on 2026-07-15 against code revision:

```text
5d4add36bf27a77277f65eac1f6f819bba6838ba
```

Focused and affected-area results:

```text
python3 -m pytest tests/candidates/test_composite_baseline.py
PASS — 6 passed

python3 -m pytest tests/candidates/test_baseline_ranking_evaluation_guards.py
PASS — 2 passed

python3 -m pytest tests/candidates
PASS — 34 passed

python3 -m ruff check src/market_regime_alpha/candidates tests/candidates
PASS — All checks passed

python3 -m mypy src/market_regime_alpha/candidates/baselines.py src/market_regime_alpha/candidates/composite_baseline.py src/market_regime_alpha/candidates/evaluation.py tests/candidates/test_composite_baseline.py
PASS — no issues found in 4 source files
```

The full-repository commands were also executed, but did not all pass:

```text
python3 -m pytest
FAIL — collection stopped with 2 import-file-mismatch errors for duplicate test_contracts module names in tests/features and tests/universe versus tests/data

python3 -m ruff check .
FAIL — 1 pre-existing F401 unused timedelta import in tests/research/test_provider_rehearsal_market_artifact.py

python3 -m mypy
FAIL — 7 pre-existing errors in 5 files outside the WP-0 changes; 43 source files checked
```

The full-check failures are in files not modified by WP-0. They were not repaired because they are outside the bounded B1 verification work package. Therefore the latest full verification remains `PENDING`.

This status does not claim:

```text
latest HEAD pytest passed
latest HEAD ruff passed
latest HEAD mypy passed
```

Normal repository execution or CI remains required before implementation authority is increased.

WP-1/WP-2 intentionally ran no tests or static quality commands under the task instruction. No
`pytest`, `ruff`, or `mypy` result is claimed for the Xuntou P0 specification/adapter changes.

---

## 11. Immediate Implementation Sequence

The current ordered sequence is:

```text
WP-0
Close B1 verification and common ranking evaluation interface — COMPLETE
        ↓
WP-1
Freeze minimum Xuntou P0 native field mapping and PIT caveats — COMPLETE
        ↓
WP-2
Implement minimum Xuntou P0 native adapter — COMPLETE FOR NORMALIZED EXPORT MODE
        ↓
WP-3
Run provider-backed Xuntou REHEARSAL B0 / B1 experiments — NEXT
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

The completed Tencent auxiliary experiment is a parallel `EXPLORATORY` evidence path. It does not
close or bypass WP-3, which still requires real Xuntou provider-backed `REHEARSAL` data.

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

- XtQuant runtime extraction or a real Xuntou provider-backed data run;
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

> **The project remains an A-share Candidate Discovery → Entry → Position Lifecycle → Exit research system. Xuntou is the active primary data provider and public sources are explicit auxiliaries, but strategy/model research remains the priority. B1 integration closure is implemented while latest full-repository verification remains pending. The next evidence step is a real Xuntou provider-backed REHEARSAL Candidate run; path-dependent Entry and Exit research follows only after Candidate evidence is reproducible. Codex may implement bounded work packages under `AGENTS.md`; it must not reinterpret the architecture or invent missing market-data semantics.**
