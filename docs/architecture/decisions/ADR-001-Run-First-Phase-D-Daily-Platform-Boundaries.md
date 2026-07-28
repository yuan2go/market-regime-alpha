# ADR-001 — Run-First Phase D Daily Platform Boundaries

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Accepted architecture decision for the exploratory Phase D daily runtime  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-28  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../../audit/Run-First-Daily-Platform-Baseline-Audit.md, ../../superpowers/plans/2026-07-28-run-first-exploratory-daily-platform.md, ../05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** main@772ecfb09410588b5a406ad900d793a5850e60d5; `src/market_regime_alpha`; `tests`

## Decision status

`ACCEPTED` on 2026-07-28.

## Context

The repository has canonical identity, time, data, Calendar, Universe, Eligibility, Feature,
Candidate Dataset, B0/B1 and research Artifact components. It also has:

- a Tencent/BaoStock/local exploratory research workflow;
- an in-memory Platform Registry and Experiment Governance prototype;
- a frozen historical `daily_research` V1 package;
- an exploratory exact next-session 10:30 Target implementation;
- no recoverable canonical Phase D daily runtime.

Extending either the Tencent experiment script or historical V1 would combine responsibilities
that the current architecture deliberately separates. The daily platform must become runnable
without granting Alpha or trading authority.

## Decision

### 1. Use a new Phase D package, not a V1 mutation

New canonical daily contracts and Artifacts live in an independent package. Historical
`market_regime_alpha.daily_research` and all existing V1 tests remain byte- and behavior-stable.

A Versioned Reader Registry routes:

```text
historical V1 schema -> existing V1 Reader
Phase D schema       -> new Phase D Reader
```

The registry does not translate or rename historical V1 identities.

### 2. Application owns orchestration only

`market_regime_alpha.application.daily_loop` owns:

- commands;
- state transitions;
- stage orchestration;
- repository Protocol use;
- replay/resume flow.

It does not define Feature, Candidate, Target, Model, Universe, Dataset, Recommendation or Entry
domain semantics. New domain contracts remain in their existing bounded contexts.

### 3. Separate request and evidence-bound run identities

Two immutable identities are required:

- `RunRequestId`: computed before acquisition from normalized request semantics and used as the
  SQLite Runtime Journal primary key;
- `DailyRunId`: computed only after Source Freeze from the RunRequest payload, code revision,
  configuration identity, canonical SourceManifest and all source content hashes.

The Runtime Journal stores the latter as a mapped field. Source Freeze never replaces or mutates
the primary key.

### 4. Assign one authority to each storage class

```text
immutable content-addressed files -> Evidence Authority
SQLite                            -> Runtime Journal
Parquet/DuckDB                    -> optional Derived Query Projection
```

SQLite records state, stage receipts and Artifact locators; it cannot redefine Artifact content.
Derived projections may be recreated from verified immutable Artifacts and may be deferred from
the first delivery.

Repository boundaries are expressed as Protocols so a later PostgreSQL journal does not change
application or domain contracts.

### 5. Freeze Source before model execution

Providers may acquire, archive, normalize and declare semantics, availability, authority and
limitations. Providers do not rank Candidates or perform Entry decisions.

Source Freeze produces:

- immutable raw source Artifacts;
- canonical SourceManifest;
- complete source hash inventory;
- DataQualityReport.

No downstream Feature or model stage may execute until this evidence is frozen and verified.

### 6. Use distinct LIVE and REPLAY profiles

`public-composite-live-v1`:

- BaoStock history;
- Tencent same-day minute/quote evidence;
- no local Archive fallback.

`public-composite-replay-v1`:

- one caller-identified SourceManifest;
- immutable Archive bytes only;
- no network calls.

A local file cannot silently substitute for a failed LIVE source.

### 7. Make data blocking a verified normal terminal state

`DATA_BLOCKED` is not `FAILED`. It publishes a checksum-verified Phase D Artifact containing:

- SourceManifest;
- DataQualityReport;
- blocking reason codes;
- available upstream evidence;
- empty PredictionRun, Recommendation and EntryAssessment collections.

`FAILED` is reserved for an unexpected operational or invariant failure. A blocked Artifact is
replayable and semantically verified.

### 8. Reuse canonical Universe, Feature and Candidate contracts

The smoke loop supports only `InstrumentType.A_SHARE_STOCK`. The initial fixed 20-symbol policy is
versioned and content-addressed. Every policy symbol is reconciled as eligible or excluded with an
explicit reason.

The pipeline reuses:

- canonical PIT Universe and Eligibility shapes;
- R5 baseline Feature definitions and materializers;
- `CandidateResearchDataset`;
- existing B0/B1 scoring functions and model identities.

No new Feature, Candidate, Target, Model, Universe or Dataset ontology is introduced.

### 9. Preserve B0/B1 behavior exactly

The daily adapter uses:

- `platform-b0-momentum-v1`;
- `platform-b1-balanced-v1`;
- the existing 0.50 momentum, 0.30 volume/liquidity and 0.20 volatility-risk weights.

It publishes the full population, predictions and rejections. Equivalence tests cover population,
score, rank, tie break, coverage, Target, Dataset and Feature Materialization lineage. No model is
selected after observing outcomes.

### 10. Use the existing MR1 10:30 Target identity

`MR1TargetId.NEXT_SESSION_1030_RETURN` is the sole identity for next-trading-session 10:30 return.

Phase D adds one Adapter that:

- exposes the existing identity through TargetProtocol;
- converts existing exact-endpoint observations into RecommendationOutcome;
- supplies DailyReview settlement inputs.

It may not create another Target ID, rename the Target or substitute next-session close for a
missing 10:30 mark.

### 11. Keep Candidate and Entry separate

B0/B1 publish Candidate predictions only. Top-5 Recommendations are projected separately per
model.

`entry-plumbing-gate-v0` permits:

- `REJECT` for insufficient or incomplete evidence;
- `WAIT_CONFIRMATION` with
  `blocking_reasons=("ENTRY_MODEL_NOT_YET_VALIDATED",)` for otherwise eligible Candidates.

It never emits `ENTER`. WAIT binds Recommendation, PredictionRun and Decision Price Snapshot and
contains no entry price, size, position or order fields.

### 12. Keep T-day evidence immutable during settlement

T-day PredictionRun, Recommendation and EntryAssessment Artifacts never change. Settlement
publishes an immutable successor Artifact binding:

- DailyRunId;
- T-day Decision Artifact ID;
- the exact MR1 Target identity;
- RecommendationOutcome records;
- reconstructed DailyReviewReport.

Unresolved outcomes remain explicit.

### 13. Fix the authority ceiling

All outputs carry:

```text
DataEligibility.EXPLORATORY
EXPLORATORY_DAILY_LOOP_OPERATIONAL
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
```

Successful operation cannot promote a model, establish formal PIT, assert Alpha or grant trading
authority.

## Alternatives considered

### Wrap historical `daily_research` V1

Rejected. V1 has a different exact file set, model binding and Entry semantics. Adding Phase D
fields would change frozen Schema/ID/Reader behavior; hiding them behind optional fields would
silently overload historical identity.

### Extend the Tencent research script

Rejected. The script is a 60-date experiment, uses a retrieval-time run ID, reads local/BaoStock/
Tencent in one acquisition and writes Legacy Dividend-T output. It has no durable state machine or
T/T+1 separation.

### Build a parallel daily ontology

Rejected. New Feature, Candidate, Target, Model, Universe or Dataset entities would compete with
the canonical research spine and make equivalence unverifiable.

## Consequences

Positive:

- historical Artifacts and V1 semantics remain immutable;
- the first daily loop is recoverable and replayable;
- LIVE and REPLAY authority are inspectable;
- Provider replacement does not affect model or Entry code;
- blocked data produces evidence instead of fabricated success;
- later Xuntou shadow input can enter through the same Provider result boundary.

Costs:

- Phase D has a separate Artifact schema and Reader;
- request and final run identities require an explicit journal mapping;
- SourceManifest field lineage increases Artifact volume;
- exact MR1 10:30 settlement remains unresolved when the required endpoint is missing;
- SQLite and file publication require recovery tests across two authorities.

## Invariants

Implementation must stop rather than:

- rewrite a historical V1 Artifact;
- alter MR1 Target semantics;
- change B0/B1 score, rank, tie break or weights;
- emit a partial Recommendation after data blocking;
- let SQLite override immutable evidence;
- use local Replay bytes in LIVE;
- emit `ENTER`, order or position authority;
- import XtQuant in the Application Runner.
