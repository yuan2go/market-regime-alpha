# ADR-011: Phase E2 Selective Historical Evidence Runtime

> **Status:** HISTORICAL
> **Decision:** Selective immutable Parquet reads plus effective-dated constituent ownership
> **Approved By:** Repository owner, 2026-08-13
> **Base:** `origin/main@e586521676b5b26b98285421023334a43a019ebd`
> **Initial Migration Head:** `068`

## Context

ADR-010 established an immutable partitioned Parquet Artifact Root with
PostgreSQL identity, locator and lineage Authority. The Phase E pilot proves
that contract on six A-share symbols, but its reader verifies and decodes every
partition into Python objects before one Decision-Time materialization. That
execution shape does not scale to a multi-year cross-section. The pilot also
projects a currently retrieved Security Master backwards, so an enlarged run
would preserve a known survivorship-bias path.

Phase E2 must enlarge the real free-data corpus without creating a second
Storage Platform, a second Historical algorithm, or a weaker evidence gate.
Free provider evidence remains `EXPLORATORY`, `PIT_INCOMPLETE`,
`FORMAL_OOS=false`, `CALIBRATED=false` and has no trading authority.

## Decision

### 1. Selective package reads extend the existing owner

PostgreSQL continues to own the exact package identity, immutable locator,
logical manifest, physical package hash and every partition projection. The
Artifact Root continues to own immutable bytes only.

A selective read has two explicit phases:

1. resolve and verify the exact owner/index from PostgreSQL and the package
   manifests without decoding data rows;
2. select candidate partitions by owner, timeframe, overlapping market date
   and stable symbol bucket, verify every selected file checksum, then use
   Arrow/Parquet predicates and column projection in bounded record batches.

Every emitted record is revalidated against its stored ID/hash and physical
projection. Results are canonically sorted. The query has an enforced row
ceiling, records selected/scanned partitions, rows, bytes and maximum Arrow
batch size, and fails closed on an unbounded request or checksum divergence.
The existing full-package verifier remains the corpus qualification and
corruption-audit path; a Decision run verifies every partition that it actually
consumes.

The materializer keeps only bounded daily history plus an LRU of the few minute
sessions needed for the current Decision and T+1 Outcome. It does not change
the frozen feature, Candidate, Signal, Forecast, ablation or economics kernels.

### 2. Historical membership is a first-class frozen source fact

Phase E2 adds a Historical Constituent Snapshot basis to the existing free
Research Universe owner. Its members come from a provider response effective
at the declared historical selection date. The same member set is frozen for
the experiment range, preventing universe drift and cross-experiment
contamination. A current Security Master is never used to add historical
members.

Listing and delisting dates are retained as provider lifecycle facts with true
retrieval time and the existing retrospective/PIT-incomplete limitation. Daily
`isST` and `tradestatus` observations own historical ST and suspension state.
Industry or other classifications whose provider record is only current are
not backfilled: they remain `UNKNOWN` for earlier decisions. Historical share
facts may support market-cap calculation only when their provider publication
date is no later than the Decision time; otherwise market cap is
`NOT_ESTIMABLE`.

### 3. Real context remains in the canonical dataset and kernels

Index and ETF instruments are acquired as real provider bars alongside the
equity corpus under the same Raw -> Normalized owner chain. The existing
Decision-Time context builder and canonical kernels consume them. Missing ETF
minute history, classification, capital or execution inputs remain explicit
missingness; stock proxies and synthetic substitutions are prohibited.

The Phase E frozen methodology and thresholds are unchanged. A broader corpus
may therefore produce positive, negative, inconclusive or not-estimable layer
evidence. All four classifications remain durable.

## Industrial corpus profile

The first Phase E2 evidence run freezes a real historical CSI 300 constituent
snapshot, rather than a hand-written watchlist. Daily history supplies feature
warm-up and lifecycle/trading observations. Only the minute date range needed
by the Decision/Outcome range is acquired. This per-timeframe acquisition
window is part of the immutable request identity and is not an implicit reader
shortcut.

The intended operating envelope is hundreds of symbols and multiple years of
daily history, with minute reads bounded to the current, previous and T+1
sessions. Larger inputs must fail at the declared read ceiling instead of
falling back to a full package load.

## Alternatives considered

### Move all historical bars into PostgreSQL

Rejected. It reverses ADR-010's large-byte boundary, increases database write,
vacuum and backup cost, and does not improve the immutable package contract.

### Add DuckDB, Polars or another Historical query authority

Rejected. Those engines could scan Parquet efficiently, but introducing one as
an owner or algorithm would duplicate Authority and Runtime. Arrow already
provides the required predicate, projection and batch execution under the
existing owner.

### Keep full loading and increase machine memory

Rejected. Memory consumption would scale with total corpus size rather than
Decision-Time working set, and failure/recovery behaviour would remain
unbounded.

## Consequences

- Selective and full readers must produce identical records for the same exact
  slice; replay and resumed execution must match uninterrupted execution.
- Partition metadata needs an overlap/bucket access path in PostgreSQL and
  query observability must be persisted in Historical evidence.
- Historical membership removes the known current-master survivorship blocker,
  but free-provider publication histories remain PIT-incomplete and cannot
  unlock Formal PIT or Locked OOS.
- Missing classification, corporate-action, fill, impact or capacity history
  cannot be repaired by defaults. Evidence reports must keep the relevant
  `UNKNOWN`, `NOT_ESTIMABLE` or `ENGINEERING_ASSUMPTION` status.
