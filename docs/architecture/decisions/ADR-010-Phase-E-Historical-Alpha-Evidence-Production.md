# ADR-010: Phase E Historical Alpha Evidence Production

> **Status:** CURRENT_ARCHITECTURE
> **Decision:** PostgreSQL Authority with a content-addressed immutable Artifact Root
> **Approved By:** Repository owner, 2026-08-12
> **Base:** `origin/main@8cd363d6b203df5413d20369f5d48100620c4246`
> **Initial Migration Head:** `067`

## Objective

Use the existing Research OS to produce a real, replayable historical Alpha
corpus. Phase E closes the active-materialization gap between a frozen free-data
archive and the Phase D owner/replay, ablation, Strategy Economics, Portfolio,
Performance, Model and Research Validation capabilities.

Phase E is exploratory evidence production. It does not establish Formal PIT,
Formal OOS, calibrated probabilities, Alpha proof, Strategy proof, Production
Admission, broker authority, or trading authority.

## Authority and storage boundary

PostgreSQL remains the only business Authority. It owns:

- immutable owner identity and content hash;
- exact Artifact Root locator and physical package hash;
- schema, normalization and kernel versions;
- provider request, retrieval and availability metadata;
- coverage, missingness and typed failure facts;
- corpus, session, experiment and predecessor lineage;
- materialization, outcome, ablation, economics, model and evidence results.

The Artifact Root stores immutable bytes only. A directory, Parquet file,
manifest file or checksum file is never selected directly and is never
Authority. Every read starts from an exact PostgreSQL owner reference, resolves
its `artifact-root-v1` locator, verifies the package and physical hashes, and
then compares the decoded logical identity with the owner. Directory scans,
`latest` aliases, filename guessing, implicit provider substitution and fallback
to a different package are prohibited.

## Evidence layers

The pipeline has three explicit immutable layers:

```text
RAW_PROVIDER_ARCHIVE
  -> NORMALIZED_HISTORICAL_DATASET
  -> HISTORICAL_RESEARCH_MATERIALIZATION
```

`RAW_PROVIDER_ARCHIVE` preserves the provider-returned fields and rows, exact
request parameters, true request/retrieval times, provider errors and the fact
that BaoStock library results are re-encoded rather than transport bytes.

`NORMALIZED_HISTORICAL_DATASET` is a deterministic derivation from one or more
exact Raw owners under one normalization version. It preserves raw lineage,
trading status, ST observations, adjustment basis, parsing failures, duplicate
facts and missing fields. Normalization changes create a new immutable Dataset;
they do not mutate a prior Dataset.

`HISTORICAL_RESEARCH_MATERIALIZATION` contains Decision-Time features and the
canonical State, Dynamic Pool, Candidate, Signal and Forecast kernel results,
plus typed T+1 Outcomes and Research Panel rows. Its manifest binds the exact
Dataset, configuration, code revision, experiment and session identities.

## Immutable publication protocol

Every large package uses one bounded publication procedure:

1. create a private staging directory beneath the configured Artifact Root;
2. write provider payloads or normalized Parquet shards and canonical manifests;
3. validate schema, sort order, uniqueness, coverage and temporal boundaries;
4. compute logical owner identity and every physical file checksum;
5. fsync the staged tree and atomically install it at its content identity;
6. register the immutable PostgreSQL owner in a short transaction;
7. reload the owner, resolve its exact locator, verify all hashes, and compare the
   decoded logical identity before reporting success.

An interruption before step 5 leaves only removable staging state. An
interruption after step 5 but before step 6 leaves a deterministic unregistered
package; retry derives the same identity, verifies it and completes owner
registration. An existing package or owner is reusable only after full identity
verification. Conflicts and corruption fail closed.

PostgreSQL writes use exact unique keys and `ON CONFLICT` only where the existing
row is compared with the complete immutable payload. Artifact I/O never occurs
inside a database transaction. Foreign-key lookup paths and exact replay paths
receive matching composite indexes.

## Columnar layout and access paths

Physical layout follows the two real consumers: cross-sectional Decision-Time
scans and symbol-scoped T+1 path reads. It must not create symbol-by-day files.

```text
daily/year=YYYY/bucket=BB/part.parquet
minute_5/year=YYYY/month=MM/bucket=BB/part.parquet
```

The bucket is a deterministic stable hash of canonical symbol. Rows are sorted
by `market_date, symbol, event_start`; Parquet statistics and dictionary
encoding support date and symbol filters. Daily shards are annual; five-minute
shards are monthly. The package manifest records the exact row count, symbol
count, date range, missingness and checksum of every shard. Bucket count is a
versioned normalization parameter and cannot change inside one Dataset owner.

## Retrospective time semantics

Free historical rows retrieved in 2026 were not known to this system on their
historical trading dates. Phase E therefore records two distinct clocks:

- `event_start/event_end`: when the market observation occurred;
- `requested_at/retrieved_at`: when the provider evidence became available to
  this Research OS.

Historical Decision-Time materialization may select only rows whose
`event_end <= DecisionTime`. Outcome materialization may additionally select
only the canonical next-session rows required by the Target/Horizon. No Outcome
value or T+1 bar is present in the Feature/State/Candidate/Signal/Forecast input
view.

This is an explicit `RETROSPECTIVE_EVENT_TIME` research basis. It never rewrites
`retrieved_at` as historical `available_at` and never passes the Live/Formal PIT
availability gate. Every affected owner carries at least:

- `EXPLORATORY`;
- `PIT_INCOMPLETE`;
- `FORMAL_PIT_NOT_ESTABLISHED`;
- `FORMAL_OOS_FALSE`;
- `CALIBRATED_FALSE`;
- `NO_TRADING_AUTHORITY`.

Canonical computation kernels are split, where necessary, from their Live
authority adapters. The strict Live adapters keep their existing availability
checks. The Historical adapter calls the same deterministic numerical kernels
under the explicit retrospective envelope and cannot publish a Live or Formal
owner.

## Historical corpus and replay

A corpus command freezes Dataset, Universe policy, DecisionTime profile,
configurations, Target/Horizon, experiment, code revision and requested session
range. Its PostgreSQL journal leases bounded partition/session work and records
exact predecessor references. Claims are fenced; completion is idempotent;
failed/missing rows are durable facts rather than silently filled values.

The active materializer creates Decision-Time owners instead of requiring them
to pre-exist. The existing Historical Research runner remains the chronological
session/replay boundary and resolves the resulting owners by exact reference.
Replay rebuilds each logical result from the owner-resolved Dataset and frozen
configuration, then compares hashes. Resume and uninterrupted execution must
produce the same ordered owner references and corpus hash.

## Alpha and economics evidence

The existing Phase D ablation and Strategy Economics kernels are authoritative
for their computations, not for research claims. Phase E supplies them with
owner-resolved panel rows and persists their complete results, including
`NEGATIVE`, `INCONCLUSIVE` and `NOT_ESTIMABLE` classifications.

The canonical nested ablation path is:

```text
Price -> +Volume -> +Market Regime -> +ETF -> +Theme -> +Capital
      -> +Dynamic Pool -> +Candidate -> +Signal -> +Forecast
```

Economics keeps Entry distinct from Holding/Exit and evaluates T+1 Open, 09:45,
10:00, 10:30, 11:30 and Close with A-share suspension, price-limit, 100-share
lot, ADV, commission, stamp duty, slippage and impact constraints. Uncalibrated
fill, cost and impact parameters are persisted as `ENGINEERING_ASSUMPTION`, not
empirical facts. Gross, cost and net use one reconcilable ledger.

## Owner-resolved exploratory model boundary

The corpus owner may be reloaded into a deterministic training matrix and an
exploratory regularized-linear challenger. The caller supplies only exact corpus,
feature, target and training-configuration references; it cannot submit a matrix
and label it owner-derived.

These challengers remain `EXPLORATORY`, `PIT_INCOMPLETE`,
`FORMAL_MODEL_QUALIFIED=false`, `FORMAL_OOS=false`, and `CALIBRATED=false`.
Existing Formal PIT and Locked OOS gates are unchanged and cannot consume a
Phase E free-data corpus.

## Rejected alternatives

- Giant PostgreSQL Daily/5m bar tables: rejected because large immutable market
  payloads are not the semantic Authority facts consumed by research owners.
- Artifact directories as Authority: rejected because filesystem discovery
  cannot establish owner identity, lineage or qualification.
- A second Historical Candidate/Signal/Forecast implementation: rejected because
  it would create algorithm drift and invalidate Live/Historical comparison.
- A generic object-storage or Authority framework: rejected because Phase E has
  only three concrete artifact families and existing locator semantics suffice.

## Verification boundary

Phase E acceptance requires one real frozen free-data run through Decision-Time
materialization, T+1 Outcome, Ablation, Strategy Economics, Performance,
Research Evidence and replay. Validation must include corruption, interruption,
resume, idempotency, concurrency, cross-experiment isolation, no-future-input
and gross/cost/net reconciliation tests plus the repository's full quality gate.

Local execution proves only local exploratory engineering evidence. GitHub
Actions is `CI_NOT_RUN` unless it actually executes, and no empirical result is
promoted beyond the stored evidence classification.
