# Canonical Signal Authority and Operational Feature Handoff

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** WP-SIG-01A runtime, data and compatibility architecture
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** Signal-production and storage statements in 13-Canonical-Market-Data-and-Feature-Spine.md
> **Superseded By:** None
> **Related Documents:** 04-Data-and-Time-Semantics.md, 13-Canonical-Market-Data-and-Feature-Spine.md, decisions/ADR-006-Canonical-Signal-Authority-Convergence.md
> **Code Evidence:** `market_data/{minute_source,encoding_v2}.py`, `features/{encoding_v2,materialization_run,materialization_v2}.py`, `signals/{candidate_view,input_v3,policies,decimal_model,v3,governance}.py`, `application/canonical_lifecycle/{feature_handoff,replay}.py`

## 1. Canonical Signal Authority Convergence

The new canonical production chain is:

```text
Verified Daily Source Archive
+ Verified Minute Source Archive
+ Trading Calendar
→ universe-scoped MarketDataDataset
→ universe-scoped Feature materialization
→ compact FeatureBundle
→ CandidateSet subset selection
→ CandidateFeatureView
→ SignalObservationV3
→ CanonicalSignalModelV2
→ SignalRunArtifactV3
→ uncalibrated PathForecast
→ Entry BLOCKED_BY_MODEL_VALIDATION
```

The canonical lifecycle requires the Dataset, full Feature Bundle, CandidateSet,
Feature Set, Signal Mapping V2, Requirement Policy, Freshness Policy, Trading
Calendar and Signal Model Configuration V2. Runtime configuration is read from
explicit content-addressed references. Default factories are test/example and
explicit exploratory-CLI conveniences only.

`SignalRunArtifactV3` is the only new canonical Signal authority. Signal V1 and
V2 schemas, Readers and historical replay remain intact. The normal lifecycle
does not create V1 when a Feature Bundle is absent. The separately named
historical-compatibility handler is the only production surface that can run the
old float engine, and only under an explicit compatibility context.

`CanonicalSignalModelV2` uses a local Decimal context, `ROUND_HALF_EVEN`, a
versioned output scale and canonical Decimal rendering. It does not read or
modify the process-global Decimal context and does not call the old float
engine. The registered model starts in `RESEARCH` with `EXPLORATORY` evidence;
registration does not grant BACKTESTED, OOS_VALIDATED, SHADOW or ACTIVE state.

## 2. Universe Feature Bundle and Candidate Views

Feature production is scoped to a PIT Universe or an explicitly controlled
exploratory Universe. Candidate Discovery runs after the complete Feature
Bundle exists and selects a subset:

```text
CandidateSet.symbols ⊆ FeatureBundle.symbols
```

`CandidateFeatureView` is a content-addressed reference projection. It binds the
full Bundle ID/hash, CandidateSet ID/hash, Dataset ID/hash, SourceManifest,
DecisionTime and the exact selected Feature Artifact references. It does not
copy Feature payloads and is not a second Feature authority. Construction and
reading fail closed for a missing/out-of-scope Candidate, duplicate Candidate,
duplicate Feature identity, or Dataset/manifest/time mismatch. Extra Bundle
symbols cannot leak into Signal observations.

`OperationalFeatureHandoffRunner` materializes the full controlled Universe,
then projects the later CandidateSet. It eliminates the former orchestration
cycle in which Candidate Discovery had to run before a Candidate-only Bundle
could be produced.

## 3. Factor requirement and Signal semantics

`SignalFactorRequirementPolicy` has three non-overlapping modes:

- `ALL_FACTORS_REQUIRED`: every declared factor is required and the minimum is
  the complete factor count;
- `DECLARED_REQUIRED_FACTORS`: only mappings marked `required` gate execution;
- `REQUIRED_PLUS_MINIMUM_TOTAL`: declared requirements and the configured total
  minimum both gate execution.

Invalid combinations are rejected when configuration is created. The canonical
five-factor model uses `ALL_FACTORS_REQUIRED`; any missing factor produces
`DATA_INSUFFICIENT` with the exact factor reason. Unknown values never enter a
score as zero.

The V2 model uses five equal-weight factors. Score denominator is five;
confirmed contributes `+1`, unconfirmed contributes `0`, contradicted contributes
`-1`, and missing factors block before scoring. Confirmation count counts only
confirmed non-overheat factors. Overheat is an independent veto: a contradicted
overheat factor prevents a confirmed Signal and also contributes `-1` to the
diagnostic score. Confidence is the quantized known-factor count divided by
five; it is completeness metadata, not a calibrated probability. These
semantics belong to the model ID/version and cannot be relaxed without a new
model and separate H9 validation.

## 4. Trading-session-aware Signal Freshness

`SignalFactorFreshnessPolicy` supports:

- `TRADING_SESSION_DISTANCE` for daily Factors;
- `SAME_TRADING_SESSION` for intraday Factors;
- `ELAPSED_SECONDS` where bounded intraday latency is also required.

Daily Factors are evaluated against the versioned Trading Calendar and latest
completed trading session, not a fixed 172800-second duration. Weekends and
exchange holidays therefore do not cause false staleness. Missing calendars,
calendar-hash disagreement, future factors, unknown sessions and excessive
session lag fail closed. A suspended symbol may retain a last observation only
when the explicit session-lag rule permits it; suspension does not manufacture
fresh data.

Minute Factors must come from the same session and pass elapsed-time bounds.
The calendar resolves continuous morning/afternoon sessions, lunch recess and
session boundaries. Every V3 observation records calendar ID/hash, session
date, policy ID/hash, Feature `available_at`, session lag and elapsed seconds.

## 5. Operational Minute Source Archive

The Tencent DuckDB cache remains a mutable exploratory cache and is not a
DecisionTime authority. The canonical adapter is deliberately narrow:

```text
TencentMinuteSourceClient
→ exact response bytes
→ RawMinuteSourceArtifact package
→ verified Reader
→ strict cumulative-minute parser
→ canonical one-minute Bars
→ ONE_MINUTE_TO_FIVE_MINUTE_A_SHARE_V1
→ exploratory minute MarketDataDataset
```

The archive binds request identity, requested symbols/timeframe, request start,
response receipt, HTTP/content metadata, Provider date, raw SHA-256, immutable
locator and limitations. It uses an exact file set, independent checksums,
staging validation, fsync and atomic rename. Readers detect payload, manifest,
checksum, extra-file and directory-identity tampering. Acquisition failures and
invalid HTTP/HTML payloads produce immutable `RawMinuteSourceAttempt` evidence;
they never become Market Bars.

The observed Tencent endpoint labels its JSON response as `text/html`. The
adapter therefore validates the body as a strict Tencent JSON envelope before
accepting this mismatch, records
`PROVIDER_CONTENT_TYPE_MISMATCH_VALID_JSON`, and retains the original
Content-Type in lineage. A real HTML body, invalid JSON, Provider error code or
wrong-symbol envelope still becomes failed Attempt evidence and never a Source
Artifact.

Tencent cumulative LOT volume is converted through
`CANONICAL_VOLUME_SHARES_V1`, whose versioned A-share board-lot rule is explicit.
Cumulative decreases are `DATA_CONFLICT`; they are never clamped to zero. Only
an explicitly recognized session boundary can reset a cumulative series.

`ONE_MINUTE_TO_FIVE_MINUTE_A_SHARE_V1` uses left-closed/right-open windows for
the continuous A-share sessions: 09:30 belongs to `[09:30,09:35)`, 11:30 and
15:00 are closing boundaries rather than new bars, 13:00 begins the afternoon,
and 14:55 belongs to `[14:55,15:00)`. OHLC follows chronological one-minute
Bars; volume/amount are summed. Incomplete windows are withheld with explicit
coverage/missingness. Auction rows are not silently admitted.

The combined Dataset validates Dataset identity, source manifests, symbol
scope, DecisionTime, adjustment and duplicate/conflict rules. Combining an
exploratory minute source cannot promote the daily Dataset's PIT or eligibility
status.

## 6. Volume and VWAP authority

Canonical volume is `SHARES`. A LOTS source requires a versioned asset-specific
board-lot rule; unknown or unsupported assets fail closed. Conversion policy
identity remains in source lineage. Mixed/unknown units and inconsistent amount
units cannot enter VWAP.

Session VWAP is `sum(amount_CNY) / sum(volume_SHARES)` over verified minute
Bars. Zero-volume observations remain explicit; missing/zero cumulative amount
does not create a numeric VWAP. Daily-Bar approximation remains forbidden.

## 7. Feature execution and durable recovery

The unused `resume: bool` contract is replaced by:

- `START_NEW`: create a new idempotency key; an existing key is a conflict;
- `RESUME_EXISTING`: require an existing incomplete Run and resume only safe,
  uncompleted tasks;
- `RETURN_IF_COMPLETE`: return an immutable completed receipt and reject an
  incomplete Run.

The PostgreSQL Feature Materialization Run authority owns Run, Task, Attempt,
Receipt and Event state separately from the lifecycle journal. Its task key is
`symbol + feature_id + timeframe`. Native transactions, command hashes, CAS
versions, monotonic claim tokens, append-only attempts/events, immutable
completed tasks and one-snapshot reads reject concurrent/stale writers and
support exact recovery after failure. H8 may schedule this authority later but
is not implemented here.

## 8. Feature Storage Encoding V2

Logical Artifact identity and physical package bytes are separate. Canonical
logical payloads still determine Dataset, Feature and Bundle hashes. Parquet or
compressed physical files have independent checksums and an encoding version;
changing encoding cannot change model semantics.

`MarketDataPackageEncodingV2` partitions Parquet by symbol/timeframe/date range.
`FeaturePackageEncodingV2` stores shared definition/configuration registries,
compressed artifact payloads, a logical artifact index, partition lineage and
columnar Feature values. Readers push `symbols`, `feature_ids`, `output_ids` and
`timeframes` into selection instead of deserializing the whole Dataset/Bundle.

JSON V1 Readers, hashes and historical replay remain supported. Migration reads
and verifies V1 before publishing V2 and then checks logical identity equality.
New materialization defaults to V2.

## 9. Replay and safety ceiling

Durable V3 replay re-reads Market Data, recomputes the Universe Feature Bundle,
rebuilds the Candidate View, re-evaluates freshness with the bound Trading
Calendar, reassembles Factors, reruns the Decimal model and compares the Signal
Artifact plus lifecycle receipt fingerprint. Merely re-reading a stored Signal
is not replay.

PathForecast retains `UnavailablePathForecastSampleProvider`; no sample is
invented. Entry remains `BLOCKED_BY_MODEL_VALIDATION` and the authority facts
remain:

```text
entry_model_empirically_validated = false
formal_oos_alpha = false
automatic_order_execution = false
broker_integration_proven = false
production_ready = false
```

No Opportunity, automatic Thesis approval, ManualTrade, order, Fill, Broker,
H7, H8 scheduler or H9 validation is introduced by WP-SIG-01A.
