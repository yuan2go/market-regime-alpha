# WP-D3.1 Real Decision Evidence Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Approved design for real security-status evidence and controlled daily acquisition
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-07-30
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../../audit/WP-D3-1-Real-Decision-Evidence-Baseline.md, ../plans/2026-07-30-wp-d3-1-real-decision-evidence.md
> **Code Evidence:** `main@2ecf4aad5096fa8e978f2b4e73b7630a87415a32`; implementation evidence is added after delivery

## Objective

For the frozen 20-symbol A-share Smoke Pool, separate History, Security Status
and Decision Quote acquisition so a real operator can prepare historical
inputs before the decision window, freeze independently sourced current status,
freeze Tencent quotes no later than 14:55 Asia/Shanghai, and finalize the
existing Phase D pipeline without network access.

The design does not guarantee that BaoStock exposes a current-day status row
before 14:55. That fact must be observed in a real decision-window run.

## Alternatives considered

### Selected: independent BaoStock current-status observation

Use exact decision-date `query_history_k_data_plus` fields
`tradestatus,isST` plus `query_stock_basic.status`. Preserve the response,
retrieval time and limitations. Accept a fact only when the response is
unambiguous and demonstrably retrieved by Decision Time.

This reuses a declared public Provider, supplies the three required facts
without inference, supports offline replay and keeps an exploratory ceiling.

### Rejected: infer status from Tencent Quote shape

The current parser exposes price and quote time only. Zero price, missing depth
or symbol naming conventions do not establish trading, ST or listing state.
This approach would convert ambiguity into false certainty.

### Rejected: static inventory or prior-session carry-forward

A maintained list or previous daily row cannot establish same-day suspension,
ST or listing status at 14:55. Prior rows remain useful audit evidence but may
not own current critical facts.

## Contracts

### SecurityStatusObservation

The Provider acquisition contract records:

```text
symbol
fact_type
value
evidence_scope
event_time
available_time
retrieved_time
decision_time
policy_effective_time
provider_id
source_artifact_id
authority_kind
quality_status
reason_codes
finality
data_eligibility
```

Fact types are the existing `TRADING_STATUS`, `ST_STATUS` and
`LISTING_STATUS`. Suspension remains a value of `TRADING_STATUS`; no competing
suspension ontology is introduced.

Allowed values are:

```text
TRADING_STATUS: TRADING | SUSPENDED | UNKNOWN
ST_STATUS: ST | NOT_ST | UNKNOWN
LISTING_STATUS: LISTED | DELISTED | UNKNOWN
```

`evidence_scope` distinguishes `PRIOR_SESSION_STATUS` from
`CURRENT_DECISION_SESSION`. Historical observations cannot be projected into
current critical facts.

### Availability rule

For a current API observation:

```text
available_time = actual successful retrieval time
```

means only “the response was observed by this time.” It does not claim an
original Provider publication timestamp. The observation is usable only when:

```text
retrieved_time <= decision_time
available_time <= decision_time
policy_effective_time <= decision_time
exact response date == decision date, where the product supplies a date
value is recognized by the published Provider contract
```

`event_time` remains `None` when the Provider supplies only a date or current
state without an event timestamp. Missing temporal evidence remains explicit.

Prior-session observations keep `available_time=None`,
`finality=UNKNOWN`, degraded quality and `PRIOR_SESSION_STATUS_ONLY`.

## Provider and authority boundary

- BaoStock History owns prior daily OHLCV and prior-session status evidence.
- BaoStock Security Status owns current trading/ST/listing observations.
- Tencent owns the Decision Quote price and quote event time.
- DailyRunCommand owns protocol Decision Time.
- DailyUniversePolicy owns membership.
- Daily Eligibility Policy owns the eligibility decision.

No Provider ranks Candidates or emits Entry/portfolio actions.

The BaoStock status client logs in once per stage, applies a bounded socket
timeout, isolates per-symbol query/parse errors, archives missing/unparsed
responses, and never falls back to a local file. If every symbol lacks usable
status evidence, the final global quality gate blocks the run.

## Stage Artifact V3

`public-source-acquisition-stage-v3` adds
`SECURITY_STATUS_SOURCE_FROZEN` and binds:

```text
run_request_id
decision_date
decision_time
provider_profile_id
universe_policy_id
acquisition_stage
raw_payload_hashes
batch semantic content
```

V1 and V2 Readers retain their exact field sets and identity algorithms.
V3 publishes the same exact three-file package with staged write, atomic
rename, non-overwrite and checksums.

SQLite continues to store only `AcquisitionStageReceipt` pointers. The
immutable stage directory is Evidence Authority.

## Runner and CLI flow

The Runner exposes:

```text
prepare_history(command)
freeze_security_status(command)
freeze_decision_quote(command)
finalize_run(command)
run(command)  # compatible composite entry
```

LIVE sequence:

```text
prepare_history
→ freeze_security_status
→ freeze_decision_quote
→ finalize_run
```

`finalize_run` performs no acquisition. It verifies three V3 scopes, composes
their bytes, projects status observations into SourceManifest V2, publishes
the Source Archive, binds `DailyRunId`, and invokes the existing downstream
pipeline.

REPLAY continues to read one caller-selected immutable Source Archive and has
no client dependency.

CLI stage commands rebuild the same deterministic `DailyRunCommand`. They
print RunRequest, stage, Artifact ID/hash and journal state. `run` remains the
composite entry; existing replay/settle/report commands remain compatible.

## Failure and recovery behavior

- An already verified receipt is reused without Provider access.
- An orphan V3 Artifact is claimed only when its full scope equals the current
  command.
- A history receipt survives status failure.
- history and status receipts survive quote failure.
- all three receipts survive a crash before Source Archive publication.
- an immutable DailyRun mapping survives a crash before the
  `SOURCE_FROZEN` journal receipt.
- cross-request, cross-date, cross-policy, cross-profile or cross-stage
  artifacts are rejected.
- repeated successful commands do not create new network calls or hashes.

Provider data insufficiency becomes explicit evidence and may produce
`DATA_BLOCKED`. Contract corruption, scope mismatch and invariant violations
become `FAILED`; neither is reclassified as success.

## Manifest, quality and eligibility

SourceManifest V2 receives current status fields only from the BaoStock status
stage. The existing Tencent quote object remains `TradingStatus.UNKNOWN`; the
Decision Price Snapshot consults the manifest's independently verified trading
fact rather than the quote placeholder.

Global checks cover source/profile/protocol/policy/stage/hash integrity and
Provider-wide unusability. Per-symbol checks exclude late/missing Price,
unknown or late Trading/ST/Listing, suspension, insufficient History,
liquidity or mapping. Every configured symbol gets one reconciliation record.

The existing minimum remains:

```text
MINIMUM_CANDIDATE_POPULATION = 5
```

Below five, the run publishes `DATA_BLOCKED` with no Prediction,
Recommendation or Entry Artifact content.

## Model and Entry invariants

The four frozen R5 Feature definitions and formulas are unchanged. B0 remains
5-session momentum. B1 remains:

```text
0.50 Momentum + 0.30 Liquidity + 0.20 Lower Volatility
```

Tests compare complete populations, Feature values, Predictions, Rejections,
scores, ranks, percentiles, tie breaks, coverage, Target, Dataset and Feature
Materialization lineage—not only Top-5.

Entry output remains `REJECT` or `WAIT_CONFIRMATION`; qualified Candidates use
only:

```text
WAIT_CONFIRMATION
("ENTRY_MODEL_NOT_YET_VALIDATED",)
```

## Acceptance boundary

Engineering completion requires the typed status product, three independent
stages, V3 Artifact/Reader, recovery, CLI, SourceManifest integration,
equivalence tests and full static/test validation.

Real closure additionally requires an observed 14:55 run where at least five
symbols have real in-window status and Quote evidence, the Phase D loop reaches
`OUTCOME_PENDING`, and an offline Archive Replay reproduces the same semantic
results. Until then the accurate runtime status is:

```text
REAL_1455_RUNTIME_VALIDATION_PENDING
PUBLIC_LIVE_STILL_DATA_BLOCKED
```

## Evidence ceiling

```text
data_eligibility = EXPLORATORY
formal_pit = NOT_ESTABLISHED
formal_oos_alpha = NOT_ESTABLISHED
trading_authority = NOT_GRANTED
```

