# Tencent Composite Exploratory R5 Design

> **Status:** APPROVED DESIGN
> **Date:** 2026-07-16
> **Authority ceiling:** `EXPLORATORY`
> **Primary objective:** Run one bounded 20-symbol, 60-decision-time Candidate experiment with Tencent current-session data plus explicitly identified local/BaoStock history, then refresh the same `dividend_t` watchlist.

## 1. Decision Summary

The first Tencent-backed operation will use:

```text
Tencent current-session minute data and latest quote
        +
identified local 5-minute cache
        +
BaoStock historical backfill when local history is incomplete
```

The sources remain separate in provenance. Tencent does not silently replace Xuntou in the canonical provider hierarchy, and BaoStock does not overwrite valid Tencent current-session evidence.

The first run is bounded to:

```text
Universe                 existing 20-symbol dividend_t watchlist
Decision Times           latest 60 common eligible sessions
Warm-up                   at least 21 earlier sessions
Failure policy            isolate an invalid symbol and retain its reason
Minimum successful scope  at least 16 of 20 symbols
Run order                 R5-compatible Candidate run, then dividend_t refresh
```

## 2. Authority Boundary

The composite source cannot currently establish historical provider availability, point-in-time universe membership, price-adjustment revision history, or formal 5-minute bar-label/finality semantics. Therefore the run must not construct or claim a canonical provider-backed `REHEARSAL` result.

The output is an R5-contract-compatible `EXPLORATORY` research run. It may reuse Candidate Population, Feature, Target, ranking, evaluation, and experiment-identity contracts where their validation rules permit `EXPLORATORY` data, but it must not inflate the source into:

```text
ProviderRehearsalMarketArtifact
FORMAL_RESEARCH
verified historical PIT evidence
calibrated probability
Alpha evidence
trading authority
```

The watchlist is a current convenience population backfilled over the selected sessions. Every result must retain the limitation:

```text
CURRENT_WATCHLIST_BACKFILL_BIAS
```

## 3. Non-Goals

This work will not:

- change Xuntou's status as the primary canonical R5 provider;
- silently fill an Xuntou field with Tencent or BaoStock data;
- implement broad Tencent endpoint coverage;
- infer ST, suspension, historical membership, listing age, price-limit regime, or buyability when the composite sources do not prove them;
- promote `dividend_t` Legacy state or action contracts into the R5 kernel;
- implement Entry, Position Lifecycle, Exit, Portfolio, or broker execution;
- tune B0/B1 semantics or claim improved Alpha from one exploratory run.

## 4. Considered Approaches

### 4.1 Selected: R5-compatible exploratory composite run

Build one identified composite acquisition and quality boundary, retain row-level source lineage, generate an `EXPLORATORY` multi-date Candidate panel, evaluate B0/B1, and then refresh `dividend_t` from the same acquired data.

This provides useful operating evidence without inventing provider semantics.

### 4.2 Deferred: adapter-only strict provider bundle

Build a Tencent normalized bundle validator but do not run historical Candidate experiments until a historical availability/finality sidecar exists.

This is semantically strict but does not satisfy the requested first operation.

### 4.3 Rejected: force a `REHEARSAL` artifact

Assign historical `available_at` and bar finality from convenient timestamp assumptions and build `ProviderRehearsalMarketArtifact` immediately.

This is rejected because it would convert unverified public-source semantics into stronger authority.

## 5. Data Flow

```text
20-symbol watchlist
        ↓
Tencent current 1-minute data / latest quote
        +
local 5-minute history
        +
BaoStock gap backfill
        ↓
Composite acquisition bundle
source row + retrieval time + locator + content hash
        ↓
Normalization and source-precedence rules
        ↓
Quality gate and per-symbol disposition
        ↓
Latest 60 common Decision Times + 21-session warm-up
        ↓
R5-compatible EXPLORATORY Candidate slices and panel
        ↓
four baseline Features + Return / MFE / MAE Targets
        ↓
B0 / B1 ranking and descriptive evaluation
        ↓
identified exploratory run artifact and report
        ↓
same composite data refreshes dividend_t snapshot
```

## 6. Component Boundaries

### 6.1 Composite acquisition

The acquisition component coordinates existing Tencent, local-cache, and BaoStock readers. It returns raw source partitions and acquisition metadata; it does not create Features, rankings, or trading actions.

Each source partition must retain:

```text
provider identity
product / endpoint identity
retrieved_at
source locator
content hash or deterministic payload hash
requested symbol and time range
raw row count
normalized row count
source limitations
```

### 6.2 Normalization and precedence

Normalized rows use the existing A-share bar schema where possible. Source precedence is explicit:

1. Valid Tencent current-session rows own the current session.
2. Valid local-cache rows own historical timestamps already present locally.
3. BaoStock fills only missing historical timestamps.
4. Conflicting non-identical rows are recorded; the lower-priority row is not silently selected as equivalent evidence.

Duplicates, malformed timestamps, non-positive prices, invalid OHLC relationships, and decreasing cumulative Tencent volume/amount must produce explicit quality findings.

### 6.3 Conservative Decision-Time reference

The public and cached 5-minute sources do not prove whether their timestamp labels the start or end of a bar. The exploratory run therefore uses a versioned one-full-bar-lag convention:

```text
Decision Time: 14:55 Asia/Shanghai
Reference row: latest valid 5-minute row with source timestamp <= 14:50
Reference price: normalized close of that row
Convention ID: tencent-composite-1455-one-full-5m-lag-v1
```

This is an exploratory project convention, not a provider availability or exact 14:55 price claim. A session without a qualifying row is unavailable for that symbol and Decision Time.

Tencent 1-minute data may be retained for diagnostics and the later `dividend_t` refresh. It does not retroactively strengthen historical 5-minute availability semantics.

### 6.4 Quality gate

The quality gate emits a deterministic disposition for every requested symbol:

```text
ACCEPTED
REJECTED_INSUFFICIENT_WARMUP
REJECTED_INSUFFICIENT_DECISION_DATES
REJECTED_HISTORY_GAP
REJECTED_TIMESTAMP_SEMANTICS
REJECTED_INVALID_PRICE
REJECTED_SOURCE_CONFLICT
REJECTED_FETCH_FAILURE
```

The run succeeds only when:

- at least 16 of 20 symbols are accepted;
- the accepted symbols share at least 60 common Decision Dates with a following target session;
- every accepted Decision Date has at least 21 earlier sessions for Feature warm-up;
- no critical semantic or source-identity violation remains unresolved.

Rejected symbols remain in `quality.json` and the human-readable report. They must not be converted into weak signals or zero-valued Features.

### 6.5 Exploratory Candidate runner

The runner uses the accepted symbols and latest 60 common sessions to build identified Candidate slices. It records the current-watchlist backfill bias and all composite-source limitations.

For every Decision Time it materializes the existing four baseline Features:

```text
5-session momentum
20-session realized volatility
20-session log median amount
Decision reference price versus prior MA20
```

It materializes the existing next-session Target family:

```text
Close Return
MFE
MAE
```

It runs the existing B0 single-feature ranker and B1 transparent composite ranker without changing their scoring semantics. Evaluation remains descriptive: ranking coverage, target coverage, Rank IC, and Top-K target summaries.

### 6.6 Dividend T refresh

After the Candidate run completes, the same accepted composite data is passed through the existing `dividend_t` refresh path. The refresh must preserve its own Legacy semantics and produce a before/after comparison for:

```text
row count and symbol coverage
latest bar timestamp
source identity
signal / timing action
1-day / 3-day / 5-day displayed upside values
support / resistance / stop fields
data-insufficient or execution-gate state
```

Candidate rank and `dividend_t` action are reported separately. Neither output overrides the other.

## 7. Error Handling

Network calls use bounded retries with a recorded attempt history. Empty payload, timeout, schema change, parsing failure, short history, and source conflict are distinct errors.

The implementation may repair deterministic parser, unit, merge, or contract defects discovered by tests. It must not repair a missing source fact by inserting a fabricated value or by copying retrieval time into historical availability time.

One rejected symbol does not abort the run. Falling below 16 accepted symbols, losing 60 common Decision Dates, or encountering a critical semantic violation fails the run before B0/B1 evaluation.

## 8. Run Artifacts

Each run writes to an identified, non-overwriting directory below:

```text
data/processed/tencent_composite_exploratory/<run_id>/
```

Minimum outputs:

```text
manifest.json
quality.json
source_conflicts.json
candidate_panel_summary.json
b0_b1_evaluation.json
candidate_report.md
dividend_t_refresh.json
```

The manifest includes code revision, configuration hash, watchlist hash, source hashes, accepted/rejected symbols, Decision-Time convention, Feature/Target/Model identities, and authority ceiling.

## 9. Verification Strategy

Verification proceeds from deterministic fixtures to bounded live access:

1. fixture tests for Tencent minute/quote parsing, units, timestamps, and cumulative-to-interval conversion;
2. fixture tests for source precedence, conflict retention, deduplication, and gap detection;
3. contract tests proving that the composite run cannot emit authority above `EXPLORATORY`;
4. one-symbol live Tencent smoke test;
5. 20-symbol acquisition and quality-gate run;
6. 60-Decision-Time B0/B1 exploratory run;
7. `dividend_t` refresh and before/after comparison;
8. focused affected-area tests;
9. full `pytest`, `ruff`, and `mypy` commands when the environment permits.

Every command and result is reported exactly. A focused pass does not become an all-tests-pass claim, and live-source failures are separated from code failures.

## 10. Acceptance Criteria

The work is complete when:

- the composite acquisition, normalization, quality, and run boundaries are independently testable;
- every accepted row and artifact retains explicit source provenance;
- the authority ceiling is enforced as `EXPLORATORY`;
- at least 16 of the 20 requested symbols pass the live quality gate;
- one identified 60-Decision-Time Candidate panel is produced;
- B0 and B1 descriptive results are generated without changing model semantics;
- the same accepted data refreshes the 20-symbol `dividend_t` snapshot;
- rejected symbols and all limitations are visible in machine-readable and human-readable outputs;
- relevant tests and quality commands have actual recorded results;
- current R5 status documentation records this exploratory auxiliary-source capability without changing Xuntou's primary-provider decision.

## 11. Stop Conditions

Stop and report before proceeding if:

- Tencent response semantics require guessing a result-affecting field beyond the declared exploratory convention;
- fewer than 16 symbols retain sufficient evidence after bounded retries and backfill;
- fewer than 60 common eligible Decision Dates remain;
- a proposed fix would silently substitute one provider for another;
- an implementation would require promoting Legacy `dividend_t` objects into the R5 kernel;
- completing the run would require claiming historical PIT, formal buyability, or exact availability evidence that the sources do not provide.
