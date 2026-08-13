# ADR-012: Phase E3 Longitudinal Historical Evidence Runtime

> **Status:** CURRENT_ARCHITECTURE
> **Decision:** Effective-dated constituent owners, owner-resolved historical business facts, and bounded incremental research aggregation
> **Approved By:** Repository owner, 2026-08-13
> **Base:** `origin/main@796b868c55bc9a3e58e427cbbfbba101a5936606`
> **Initial Migration Head:** `070`

## Context

Phase E2 proves the canonical Historical Runtime on one 300-stock CSI 300
cohort and 19 Decision Sessions. Its Parquet reads are selective, but four
longitudinal limits remain in executable code: one constituent snapshot is
projected across the whole run; full Daily history is materialized in one
Python graph; Forecast reloads all prior Outcome components; and Evidence,
Ablation and the Challenger reload all Panel owners and observations at once.
Industry, published shares and corporate actions have no consumed owner, while
raw-price returns can silently cross an ex-right or ex-dividend event.

Free Provider history remains retrospective and PIT-incomplete. Phase E3 must
not turn effective dates or publication dates into Formal availability, lower
the Forecast sample floor, change Signal thresholds, or create a second
Historical algorithm or storage Authority.

## Decision

### 1. Longitudinal membership reuses the Free Research Universe owner

Each distinct Provider effective date is an immutable Historical Constituent
Snapshot. One immutable Historical Constituent Timeline maps every queried
trading session in the requested range to its exact Provider effective date,
binds every cohort, and retains the range-scan Source Manifest. A Historical
Research Command binds that timeline and every cohort required by its range.
At each DecisionTime, the materializer selects the unique latest cohort
whose effective date is not later than the session and whose next cohort is
later than the session. Gaps, overlaps, duplicate effective dates and a first
cohort after the run start fail closed.

Corpus acquisition accepts the exact cohort owner set and acquires the union of
their included symbols. Scope construction uses only the active cohort. A
current Security Master may contribute retrieved lifecycle dates but never add
a historical member or classification.

### 2. Historical business facts are one consumed owner in the same boundary

The Free Research Universe bounded context owns an immutable Historical
Security Facts Set with exact raw Source Manifest lineage. Facts are normalized
only when the Provider exposes an effective or publication date:

- Industry uses the Provider classification and effective update date.
- Total and liquid shares use the financial statement publication date; a
  Decision can consume only a row published no later than that Decision.
- Adjustment factors and dividend/split/rights fields retain their event and
  announcement dates.
- Daily bar ST/trading status remains the trading-eligibility observation.

Successful Provider calls are written to content-verified query checkpoints
before the next call. Recovery reuses only a checkpoint whose request identity,
request/retrieval instants, response content and full checkpoint hash match;
concurrent writers atomically accept and revalidate one durable winner.
Corrupted checkpoints fail closed. Missing, malformed, conflicting or undated
corporate-action rows are persisted as interval coverage gaps, and affected
raw-return labels remain `UNKNOWN` or `NOT_ESTIMABLE`. Retrieval remains the
true per-response later retrieval time and every fact
remains `EXPLORATORY` and `PIT_INCOMPLETE`.

Raw-price labels whose Decision-to-Outcome interval intersects a corporate
action are not silently interpreted as ordinary returns. The unchanged Phase E
raw-price experiment marks those labels and Strategy Economics
`NOT_ESTIMABLE`. A total-return or adjusted-price definition would require a
new frozen Experiment and is outside this decision.

### 3. Longitudinal reads and evidence are bounded by session batches

Daily history is read through bounded rolling date windows with an LRU keyed by
owner and session; no multi-year Daily package graph is retained. Minute reads
keep the existing previous/current/T+1 LRU.

Historical component repositories expose deterministic keyset batches. The
canonical Ablation implementation gains an incremental accumulator used by
both tuple and streaming entry points, so Historical Evidence processes one
session cross-section at a time. It retains only fixed-dimension sufficient
statistics, prior top-k weights and the running equity peak/drawdown. The
Challenger builds bounded training/validation matrices from streamed Panel
batches under its frozen temporal split. Forecast prior samples are resolved
from the PostgreSQL Outcome-label projection by run, symbol, target and
`trading_date < DecisionTime`, instead of loading the full run Outcome graph.
Signal state/confirmation reasons, Forecast status/sample counts,
target/corporate-action exclusions and month/quarter/year plus regime slices
are incrementally aggregated into durable Research Evidence.

Incremental checkpoints are content-addressed and append-only. Resume reuses
the same completed owner rows; replay recomputes from exact source hashes.
Batch size, interruption point or process boundary cannot affect canonical
ordering or result identity.

Host peak RSS and wall time are operational measurements rather than semantic
research inputs: putting them inside a content-addressed Evidence identity
would make identical replay depend on host scheduling. Corpus Summary records
the deterministic memory bounds (batch size and maximum session cross-section)
while the checked-in execution report records `/usr/bin/time -lp` RSS and wall
time beside exact run/evidence identities.

### 4. Economics inputs are explicit and versioned

The frozen Strategy policy continues to distinguish empirical observations,
rule inputs and engineering assumptions. Historical stamp-duty rules and other
reliable dated rules may be owner-resolved. Broker commission, slippage,
impact, fillability and capacity remain `ENGINEERING_ASSUMPTION` until their
own empirical inputs exist. No default is upgraded merely because it is
plausible.

## Rejected alternatives

- A separate longitudinal-universe service or query engine would duplicate the
  existing owner and Modular Monolith boundaries.
- One fully repeated 300-row membership snapshot per session would erase
  cohort provenance and expand Authority rows without new facts.
- Back-adjusting the current frozen target would change experiment semantics
  after seeing Phase E2 results.
- Increasing memory ceilings would not make recovery or multi-year execution
  bounded.

## Evidence ceiling

Successful Phase E3 execution is Historical Research engineering evidence
only. Free Provider data remains `EXPLORATORY`, `PIT_INCOMPLETE`,
`FORMAL_OOS=false`, `CALIBRATED=false`, with no Production or trading
authority.
