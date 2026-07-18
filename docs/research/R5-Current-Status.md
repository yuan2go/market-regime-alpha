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
> **WP-3 routing / run status:** `docs/research/R5-WP3-Provider-Routing-Status.md`
> **WP-4A Entry Target contract:** `docs/specs/Entry-Path-Target-V1.md`
> **Current PIT replication charter:** `docs/research/PIT-Candidate-Replication-Charter.md`

---

## 1. Status Precedence

This file is the current R5 implementation-status authority.

Older documents remain historical records. Their stale status lines do not override this file.

The current Candidate-validation sequence is now:

```text
MR-2B F2B v3 exact implementation identity              COMPLETE
PIT replication protocol and provider-bound preflight  IMPLEMENTED
PIT blocked/invalid Artifact identity v2                IMPLEMENTED
Real normalized Xuntou validation bundle                BLOCKED EXTERNAL INPUT
Expanded PIT replication result                         NOT PRODUCED
```

The frozen MR-2B Primary remains `PRIMARY_HYPOTHESIS_NOT_SUPPORTED`. The next research question is
the unconditional B1-E lift over the model-population multi-seed matched-K median. The rejected
auxiliary-watchlist UP/DOWN Gate is not being restored. Missing Xuntou input produces a checksummed
blocker Artifact; Tencent/current-watchlist evidence cannot be silently substituted as PIT.

F2B v3 run `mr2b-f2b-v3-bb34b06f7446aa0af9e7` supersedes v2 as the current
identity contract while preserving the exact frozen statistical result. Its implementation hash map
is code-owned and exact; verifier routing is deliberately outside statistical identity. The actual
PIT v2 blocker is `pit-replication-v2-c681ed11199027ea819d`.

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
        +
Target-Aware Candidate Directional Diagnostic
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
        ↓
Authority-aware source routing
        ↓
Provider-backed Candidate panels / fixed B0-B1 evaluation
        ↓
Atomic content-hashed WP-3 run artifact
```

The generic provider path is an architecture boundary.

The active concrete provider adapter is Xuntou. It currently consumes an identified normalized
native export; runtime XtQuant extraction and a real provider-backed run remain unavailable.

WP-3 source-aware execution infrastructure is implemented. A valid normalized Xuntou bundle can
traverse provider-rehearsal Eligibility v2, exact Candidate Population assembly, the three existing
Target families and the fixed B0/B1 ladder. A truthful empty Candidate Population remains an
identified successful diagnostic and does not trigger auxiliary fallback. No real Xuntou bundle was
available in this environment, so WP-3 remains pending as a provider-evidence result.

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
LATEST FULL-REPOSITORY VERIFICATION PASSED — 2026-07-16
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

B1 scoring semantics were not changed while closing this verification work. The repository quality
repairs completed before WP-4A removed the previously recorded collection, Ruff, and mypy blockers;
the latest full-repository verification is recorded in Section 10.

### WP-3 Candidate directional diagnostic

Current status:

```text
Diagnostic core                                             IMPLEMENTED
Fixed protocol identity                                     R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_V1
Applicable Target                                           Next-Session Close Return only
MFE / MAE applicability                                     NOT_APPLICABLE — EXPLICIT
Fixed selection depth                                       TOP 5
Affected verification                                       PASSED
Formal OOS / Alpha authority                                 NOT AVAILABLE
```

The diagnostic classifies an already observed Close Return as positive, negative, or exactly
neutral after the Candidate ranking is fixed. It reports Top-5 positive/negative rates, Candidate
and ranked baselines, micro/macro aggregates, observed denominators, and per-Decision-Time
stability. An unavailable Target reduces the observed denominator and is never replaced by a lower
ranked symbol. The diagnostic does not change B0/B1 scoring and is not an Entry, Exit, probability,
Portfolio, or execution contract.

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
WP-4A Entry path Target code contract                    IMPLEMENTED
WP-4A future daily path evidence contract                IMPLEMENTED IN DATA DOMAIN
WP-4A Calendar multi-session resolver                    IMPLEMENTED
WP-4A pure daily-OHLC materializer                       IMPLEMENTED / VERIFIED
Entry Gate / Entry Proposal / Entry model                NOT IMPLEMENTED
Canonical Position State code contract                   NOT YET IMPLEMENTED
Exit continuation target family                          SPECIFIED IN RESEARCH DOC
Exit continuation Target code contract                   NOT YET IMPLEMENTED
Entry timing accuracy                                    NOT VALIDATED
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

WP-4A uses the versioned start convention:

```text
NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1
```

The reference is the 14:55 Asia/Shanghai Decision Snapshot. Daily V1 explicitly does not claim to
observe the Decision Date's final five-minute path. Future OHLC and suspension observations remain
Data evidence; Entry owns only Target semantics, observations, identity, and pure materialization.
Same-session high/low dual touch is terminal `AMBIGUOUS`, and missing bars are never inferred as
suspension.

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
B1 latest full-repository verification                        PASSED — 2026-07-16
Cross-sectional rehearsal evaluation                          IMPLEMENTED
WP-3 Candidate positive-return directional diagnostic         IMPLEMENTED / VERIFIED
WP-3 directional metric identity                              R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_V1
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
Xuntou P0 native field mapping specification v3               COMPLETE; RUNTIME SEMANTICS PARTIAL
Xuntou normalized native/export adapter v3                    IMPLEMENTED
Xuntou historical Decision-Time buyability                    UNKNOWN EXCEPT CONFIRMED SUSPENSION
XtQuant runtime extraction                                    NOT IMPLEMENTED / NOT EXECUTED
Real Xuntou provider / export data run                         NOT AVAILABLE
Authority-aware Xuntou/Tencent provider router                 IMPLEMENTED
Provider-backed multi-date Candidate panel runner              IMPLEMENTED — REAL XUNTOU RUN PENDING
Shared fixed B0/B1 provider evaluation seam                    IMPLEMENTED
Immutable hashed WP-3 run artifact                             IMPLEMENTED
Source-aware WP-3 CLI                                          IMPLEMENTED — LIVE RUN NOT EXECUTED
Chronological/OOS Candidate validation                         NOT YET IMPLEMENTED

Tencent auxiliary multi-date Candidate panels                  IMPLEMENTED — EXPLORATORY ONLY
Tencent auxiliary chronological descriptive evaluation         IMPLEMENTED — NOT FORMAL OOS EVIDENCE
PRR-MVP-1 reproducible Candidate replay                        IMPLEMENTED / LOCALLY VERIFIED
PRR-MVP-1 live auxiliary end-to-end run                        VERIFIED — MIXED source partitions
PRR-MVP-1 cached end-to-end run                                VERIFIED

WP-4A Entry path Target code contract                           IMPLEMENTED
WP-4A future path evidence / Calendar resolver                  IMPLEMENTED
WP-4A pure materializer / deterministic identity                IMPLEMENTED / VERIFIED
WP-4A.1 Entry price lineage / temporal completeness hardening   IMPLEMENTED / VERIFIED
WP-4A.2 as-of readiness / coverage correction                   IMPLEMENTED / LOCALLY VERIFIED
Entry Gate / Entry Proposal / Entry model                       NOT IMPLEMENTED
Entry timing accuracy                                           NOT VALIDATED
Canonical Position State code contract                         NOT YET IMPLEMENTED
Exit continuation Target code contract                         NOT YET IMPLEMENTED
Exit timing accuracy                                            NOT AVAILABLE
Trading execution                                               OUT OF SCOPE FOR CURRENT VERSION

Formal Candidate / Entry / Exit Alpha evidence                 NOT AVAILABLE
```

### PRR-MVP-1 run record

The bounded Tencent/local/BaoStock Candidate replay is a separate `EXPLORATORY` research-mark
control. It reuses the fixed B0 controls and B1-A through B1-E ladder without model selection and
does not create an Entry signal, Position state, Exit policy, Portfolio approval, or execution
authority.

```text
Live auxiliary run (mixed local/cache plus live auxiliary requests)
run_id:       prr-mvp-1-20260718T163000+0800-b682a4e71a
dataset_id:   prr-dataset-623069776325c7e05ca176a8
acquisition:  prr-raw-87aa3ce58e1fe3289a2fcbaf
accepted:     20 symbols / 60 Decision Dates / 9 fixed models

Cached end-to-end run
run_id:       prr-mvp-1-20260718T163100+0800-7013f43a2f
dataset_id:   prr-dataset-fa40337727427b2f1ff63548
acquisition:  prr-raw-716c0fee1549b0c678d9fe2d
```

Both runs retain immutable raw evidence, normalized Dataset and Run artifacts with SHA-256
manifests. The 14:55 reference is explicitly a research mark, not historical fill proof. Results
are descriptive only: `EXPLORATORY`, current-watchlist backfill-biased, without verified
historical PIT, buyability, finality, adjustment, Level-2, or order-book semantics.

---

## 10. Current Verification Status

WP-4A verification was executed on 2026-07-16. Its independent prerequisite quality repairs are:

```text
a45e51e  pytest collection-package repair + Ruff F401 repair
1326b31  six current mypy error repairs
```

WP-4A implementation commits before the documentation closeout are:

```text
5f7a015  future path evidence + Calendar horizon resolver
901bc8a  Entry path Target contracts + Target identity
d6d72a3  pure materializer + Artifact identity
```

Focused verification:

```text
.venv/bin/python -m pytest -q tests/strategies/entry tests/data/test_path_evidence.py tests/data/test_trading_calendar.py
PASS — 66 tests

python3 -m ruff check <WP-4A source and tests>
PASS — All checks passed

python3 -m mypy
PASS — no issues found in 54 source files
```

Latest full-repository verification:

```text
.venv/bin/python -m pytest -q
PASS — 686 tests collected and passed; 6 existing pandas fragmentation warnings

python3 -m ruff check .
PASS — All checks passed

python3 -m mypy
PASS — no issues found in 54 source files
```

The repository virtual environment was used for pytest because it contains the declared runtime
dependencies (`pyarrow` and `duckdb`) that are absent from the system interpreter. The earlier
system-interpreter attempt therefore does not supersede the successful repository-environment run.

These checks establish implementation consistency only. They do not establish a real Xuntou run,
Entry timing accuracy, formal OOS evidence, or Alpha. The older failure blocks later in this
section are dated historical verification records and do not override this latest result.

WP-4A.2 closure status:

```text
WP-4A.2 implemented and locally verified
Entry model not implemented
Entry accuracy not validated
CI workflow implemented
remote CI result not verified
```

The materialization correction separates readiness policy from as-of coverage assertion, retains
only consumed coverage identity, and leaves `entry-path-target-v1` truth semantics unchanged.

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

No full-repository pass was claimed for that historical Tencent checkpoint.

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

At that historical WP-0 checkpoint, the full-check failures were in files not modified by WP-0 and
were outside its bounded work package. Full verification therefore remained `PENDING` at that
time; the newer WP-4A prerequisite repairs and latest result above supersede that status.

This status does not claim:

```text
latest HEAD pytest passed
latest HEAD ruff passed
latest HEAD mypy passed
```

Normal repository execution or CI remains required before implementation authority is increased.

WP-1/WP-2 intentionally ran no tests or static quality commands under the task instruction. No
`pytest`, `ruff`, or `mypy` result is claimed for the Xuntou P0 specification/adapter changes.

WP-3 source-routing infrastructure verification was executed on 2026-07-16 against code revision:

```text
712ec8568806284a154232ccc71ddf9dedc305c3
```

Focused and affected-area results:

```text
WP-3 focused pytest set
PASS — 36 tests

Combined research/candidates/universe/data/features command
FAIL DURING COLLECTION — 2 existing import-file-mismatch errors for duplicate
                         test_contracts.py module names

Partitioned affected-area commands
PASS — research + candidates: 115 tests
PASS — universe: 38 tests
PASS — data: 8 tests
PASS — features: 7 tests
PASS — 168 tests total across the four non-conflicting commands

Scoped Ruff over all WP-3 source and test files
PASS — All checks passed

Scoped mypy over eight affected source files
PASS — no issues found

WP-3 CLI --help smoke
PASS
```

The full-repository commands were executed after the final WP-3 verification fixes:

```text
python3 -m pytest
FAIL — 2 existing import-file-mismatch collection errors for duplicate test_contracts.py names

python3 -m ruff check .
FAIL — 1 existing F401 unused timedelta import in
       tests/research/test_provider_rehearsal_market_artifact.py

python3 -m mypy
FAIL — 6 existing errors in 4 files; 51 source files checked
```

No full-repository pass was claimed for that historical WP-3 checkpoint. No real Xuntou export or
new source-aware Tencent live run was executed by those tests.

WP-3 Candidate directional diagnostic verification was executed on 2026-07-16 against code
revision:

```text
b368397f01ded670ef2a8de7a03a2b99e3e08580
```

Results:

```text
Focused / affected pytest set
PASS — 34 tests

Scoped Ruff over changed Candidate/WP-3 source and tests
PASS — All checks passed

Scoped mypy over three affected source files
PASS — no issues found

python3 -m pytest -o addopts='' -q
FAIL DURING COLLECTION — the same 2 existing import-file-mismatch errors for duplicate
                         test_contracts.py module names

python3 -m ruff check .
FAIL — the same existing F401 unused timedelta import in
       tests/research/test_provider_rehearsal_market_artifact.py

python3 -m mypy
FAIL — the same 6 existing errors in 4 files; 51 source files checked
```

The diagnostic verification did not execute a real Xuntou run or a new Tencent live acquisition.
The scoped checks establish the implementation contract only; they do not establish formal OOS,
Candidate Alpha, Entry accuracy, or Exit accuracy.

---

## 11. Immediate Implementation Sequence

### MR-1 — Overnight Morning-Pop Signal Validation

`MR-1` is implemented as a bounded auxiliary-data `EXPLORATORY` validation, separate from
WP-3 and not a replacement for its Xuntou provider-backed requirement. It reuses immutable PRR
5-minute data to evaluate the fixed B0/B1 ladder at exact next-session 09:35, 10:00, 10:30, and
the retained close comparator. Exact endpoint bars are required; missing endpoints are not
forward-filled. Morning exits release the daily sleeve before the next 14:55 Decision Time.

The current local v4 run is `mr1-c06821bf7db2dc787244` on Dataset
`prr-dataset-fa40337727427b2f1ff63548`. It persists a four-member daily comparator family:
all-Candidate gross, matched-K rank-blind gross/net, and all-Candidate net diagnostic. Matched-K
uses frozen SHA-256 seed 17, Top-5 capital, the model cost mechanics, fixed missing weight, and
the same CLOSE cash-lock state. Each baseline is scoped to the corresponding model/date eligible
ranking population; 28,350 matched-K slot rows retain the actual selected symbols and identities.
All-Candidate net is not a primary Candidate-Alpha comparator. The prior MR-1 runs are retained
but **SUPERSEDED** for baseline-comparability interpretation.

The current run still classifies every BASE model/endpoint combination as
`FAILED_EXPLORATORY` under its predeclared cost-sensitive rule.
This is not formal OOS evidence, does not select a model, and does not justify Entry, Position,
Exit, Portfolio, or execution implementation. See
`docs/research/MR-1-Overnight-Morning-Pop-Signal-Validation.md`.

### MR-2 — Morning-Pop Failure Decomposition

`MR-2` is retained as a historical `EXPLORATORY` diagnosis. Its old **C — signal appears only in
specific regimes** result is **SUPERSEDED**: it used Decision-Date full-session fields and did not
establish Candidate excess relative to a population-matched comparator. It is not current research
authority. See `docs/research/MR-2-Morning-Pop-Failure-Decomposition.md`.

### MR-2A — Leak-Free Regime Diagnostic

MR-2A supersedes the old MR-2 `C` conclusion because the old Context used Decision Date
full-session fields and mixed gross/net baseline semantics. Its historical leak-free,
cutoff-14:50 result was `C1. REGIME_HETEROGENEITY_HYPOTHESIS`, but MR-2A is now
`SUPERSEDED_FOR_CURRENT_RESEARCH_AUTHORITY`: absolute-return conditionality and the earlier
non-population-aware comparator cannot establish Candidate excess Alpha. It is not C2 replication
or a production Regime Gate. ETF/sector Context remains unavailable. See
`docs/research/MR-2A-Leak-Free-Regime-Diagnostic.md`.

### MR-2B-F1.2 — Model-Population Comparator Parity

MR-2B-F1.1 and F1.2 are complete. Artifact schemas have one source of truth; verified readers retain
the original quality evidence and fail closed on checksum, exact-file-set, primary-key,
cross-table date/symbol, weight, comparator-parity, and CLOSE sleeve-state violations. MR-1
baseline calculations live in the research domain rather than the CLI. MR-2B observations are
typed and descriptive; duplicate dates, unknown Context labels, and non-finite values fail
closed. Premature primary-hypothesis promotion has been removed. F1.2 additionally binds every
baseline to its model/date eligible population, persists the actual matched-K slots, reconstructs
those selections in the reader, and excludes local Dataset paths from semantic run identity.

### MR-2B-F2A — Exact Context and Multi-Seed Conditionality Inputs

F2A semantic closure is implemented as descriptive input construction only. Run
`mr2b-f2a-99cd5a71a92fa5eb0366` uses Dataset
`prr-dataset-fa40337727427b2f1ff63548` and MR-1 v4
`mr1-c06821bf7db2dc787244`. It requires the exact 46-bar accepted-watchlist grid through 14:50,
compares amount to the prior session at the same cutoff, preserves FLAT/unavailable states, and
excludes post-14:50 bars. All 60 dates were available: 27 UP, 33 DOWN and 0 FLAT.

The v2 Artifact persists 1,200 symbol-level Context rows and reconstructs every Context, logical
selection, return, null summary, daily excess, coverage projection and Primary Input from the
verified Dataset/MR-1 evidence. Its typed run identity and semantic reader reject content that was
modified and then covered by a newly generated checksum. The older
`mr2b-f2a-47709a63823ff4c95402` run is retained as historical evidence but is
`SUPERSEDED_FOR_F2B_INPUT` because v1 did not perform this complete semantic reconstruction.

The fixed seeds 0–255 produce same-day population-matched references without inflating the
Decision-Date sample count. Seed 17 reconciled exactly across all 6,480 daily model/endpoint/cost
rows. The frozen B1-E / 10:30 / BASE input remains `DESCRIPTIVE_INPUT_ONLY`; no bootstrap,
permutation, hypothesis promotion or multiple-testing decision is implemented. See
`docs/research/MR-2B-F2A-Conditionality-Inputs.md`.

Collision diagnostics now cover executed selections only: 5,670 executed null groups average
255.9810 unique selections and approximately 0.00744% collision; 810 CLOSE cash-locked groups
are explicitly non-applicable and do not contribute empty-selection collisions.

### MR-2B-F2B — Directional Statistical Closure

MR-2B is complete at exploratory authority. F2B run `mr2b-f2b-cfc48a658d50636610ac`
consumed the verified Dataset, MR-1 v4, and F2A v2 chain under frozen Protocol
`sha256:310d32daa26314f7d81896d3357bfbce0fd3b722ee8779111eb1c954ede87f80`.

The directional B1-E / 10:30 / BASE `UP_GREATER_THAN_DOWN` effect was
`-0.0000844753476525215`; the block-length-5 95% interval was
`[-0.002375137060807994, 0.0023412463545652395]` and the exact one-sided circular-shift
p-value was `0.5`. Chronological halves disagreed, only two of four fixed seed panels were
positive, and none of 107 Secondary comparisons survived BH FDR.

The frozen assessment is `PRIMARY_HYPOTHESIS_NOT_SUPPORTED`. The old MR-2A C1 conditionality
claim is superseded. B1-E nevertheless retains a positive descriptive full-sample net lift over
the multi-seed median, so the selected next route is to retain the transparent Candidate ranking,
avoid a Market Regime Gate, and expand historical PIT validation and Feature ablation. The
complete interpretation is recorded in `docs/research/MR-2B-Final-Assessment.md`.

### MR-2B-F2B v2 — Post-Merge Hardening

F2B v2 run `mr2b-f2b-v2-3bc505b9e92138ffa2f8` preserves the frozen direction and negative
Primary conclusion while fixing generic contract behavior. Low UP/DOWN coverage now produces a
valid immutable `INSUFFICIENT_EVIDENCE` Artifact without running bootstrap or permutation.
Competing-event missing counts are separately bound to Top-5, model-population, matched-K, and
global Target scopes. Protocol v2 owns all execution thresholds, and a versioned verifier registry
keeps historical F2B v1 evidence readable without applying v2 semantics retroactively.

The v2 actual result remains 27 UP / 33 DOWN, effect `-0.0000844753476525215`, 95% bootstrap
interval `[-0.002375137060807993, 0.0023412463545652395]`, circular-shift p-value `0.5`, and
`PRIMARY_HYPOTHESIS_NOT_SUPPORTED`. No research authority was promoted. See
`docs/research/MR-2B-F2B-v2-Post-Merge-Hardening.md`.

### MR-2B-F2B v3 — Research Artifact Identity

F2B v3 run `mr2b-f2b-v3-bb34b06f7446aa0af9e7` uses an exact, code-owned implementation
module set and excludes the extensible verifier registry from statistical identity. Historical v1
and v2 Readers remain available and unchanged. The published v2/v3 semantic comparison is
`EXACT_MATCH`; the current assessment remains `PRIMARY_HYPOTHESIS_NOT_SUPPORTED`.

PIT evidence status now has distinct v2 blocked, invalid, and reserved success Schemas. The actual
missing-input run is `pit-replication-v2-c681ed11199027ea819d` and contains no research result.
See `docs/research/Research-Artifact-Identity-V3.md`.

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
Source-aware runner infrastructure — IMPLEMENTED
Candidate positive-return directional diagnostic — IMPLEMENTED / VERIFIED
Real Xuntou REHEARSAL B0 / B1 evidence run — NEXT / PENDING INPUT
        ↓
WP-4A
Entry Path Target contracts / evidence / materializer — COMPLETE
UP_FIRST / DOWN_FIRST / TIMEOUT / explicit AMBIGUOUS
        ↓
Obtain a real, content-hashed Xuntou normalized bundle and complete the existing
WP-3 provider-backed run — NEXT
        ↓
WP-5 remains unentered: it requires its own research charter and chronological comparison.
```

The completed Tencent auxiliary experiment is a parallel `EXPLORATORY` evidence path. The new
source-aware CLI may use that path only when routing authority permits it. Neither the earlier
Tencent run nor the new routing infrastructure closes WP-3, which still requires real Xuntou
provider-backed `REHEARSAL` evidence.

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

> **The project remains an A-share Candidate Discovery → Entry → Position Lifecycle → Exit research system. Xuntou is the active primary data provider and public sources are explicit auxiliaries, but strategy/model research remains the priority. WP-3 routing, Candidate-runner and immutable-artifact infrastructure are implemented while the real Xuntou provider-backed run remains unavailable. WP-4A now provides evidence-preserving Entry path Target contracts, not an Entry model or accuracy result. The next provider evidence step is an authorized, content-hashed Xuntou REHEARSAL input and a truthful run under existing PIT/buyability limits; any Entry experiment must separately establish its charter and chronological comparison. Codex may implement bounded work packages under `AGENTS.md`; it must not reinterpret the architecture or invent missing market-data semantics.**
