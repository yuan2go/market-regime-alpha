# Canonical Feature Spine and Signal Inputs Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Approved implementation design for the canonical market-data and technical-feature spine
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../../architecture/04-Data-and-Time-Semantics.md, ../../architecture/10-Production-Decision-Lifecycle.md, ../../architecture/12-Canonical-Runtime-and-Legacy-Migration.md, ../../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md
> **Code Evidence:** Design baseline `main@9ccc751c237b060ab13a86602993d08753d5c634`; implementation evidence must be attached by the delivery audit.

## 1. Decision and non-claims

The feature spine is a separate, deterministic input-preparation run. It does
not add a seventeenth stage to the V1 lifecycle graph. Its verified output is
bound into `CanonicalLifecycleInputManifest` and consumed only by the existing
Signal stage.

```text
verified Provider archive
  -> CanonicalMarketDataDataset
  -> FeatureMaterializationRunner
  -> FeatureBundleArtifact
  -> SignalInputAssembler
  -> SignalRunArtifact V2
  -> PathForecast (no invented samples)
  -> Entry remains BLOCKED_BY_MODEL_VALIDATION
```

The delivery establishes engineering mechanics, not model evidence:

```text
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
formal_oos_alpha = false
production_ready = false
```

No Feature may create a Signal state directly, a trade action, target position,
ManualTrade, Fill, Broker Order, or actual Position.

## 2. Current-code findings

1. DailyLoop freezes full daily `PublicBar` rows and exact raw Provider payloads
   in `HISTORY_SOURCE_FROZEN`; the final Source Replay Archive binds the
   `PublicCompositeProviderResult` and `SourceManifest`. This is the current
   controlled historical source from which canonical daily bars can be built.
2. The Daily Decision package embeds legacy `FeatureMaterialization` values but
   does not expose the frozen OHLCV history as a canonical feature dataset.
3. H6 `ResearchDailyBar` contains only `close` and `amount`; H6 is a composite
   authority index, not a complete OHLCV archive. It cannot supply range, gap,
   volume, turnover, or true VWAP inputs by itself.
4. Minute bars currently live behind Provider/local archive adapters in
   `data_sources/a_share_bars.py`. Those DataFrame paths are not canonical
   authority: they use float values, can access the network, and one normalizer
   fills missing amount with `close * volume`. Canonical materialization must
   consume a previously frozen, hashed archive through an explicit adapter and
   must never use that fallback.
5. Signal V1 consumes exactly five metrics: `price_action_return`,
   `volume_ratio`, `trend_return`, `price_vs_vwap_return`, and
   `overheat_return`. The first four use minimum thresholds; overheat is
   contradicted at or above its maximum. Any unknown factor currently makes the
   snapshot `DATA_INSUFFICIENT`.
6. `SignalStageHandler` currently constructs all five fields as `None` with
   `H6_SIGNAL_FACTOR_INPUTS_NOT_AVAILABLE`.
7. PathForecast already binds the exact `SignalSnapshot`; the lifecycle passes
   `samples=()` and therefore correctly remains `DATA_INSUFFICIENT` and
   uncalibrated.
8. Durable lifecycle replay dispatches by `LifecycleObjectType`. Existing
   Feature replay recomputes only the SMA V1 package; Signal replay recomputes
   from stored V1 observations rather than from a Feature Bundle.
9. Feature V1 publication is a three-file exact package, but its semantic
   Reader and replay registry are hard-coded to
   `technical.simple-moving-average`.
10. durable Model Governance can own immutable model definitions and lifecycle
    status, but it is not a Feature configuration store. Feature and FeatureSet
    configurations therefore remain immutable content-addressed inputs and are
    also referenced by lifecycle configuration/model manifests.
11. Legacy moving averages use pandas `rolling`; Legacy MACD uses float,
    seed-first `adjust=False` recursion and a doubled histogram; Tuishen and
    volume structure use pandas/float semantics. These differences require
    family-specific comparison policies.
12. `PublicBar` is a useful Provider-normalized input but is float-based and
    omits exchange, asset type, timeframe, prior close, turnover, adjustment
    evidence and source hash. No existing type satisfies the canonical bar
    contract.

## 3. Bounded contexts and dependency direction

New responsibility is divided into four deep seams:

```text
market_data
  owns canonical bar, adjustment, dataset package and selective Reader

features
  owns executable V2 definitions/configuration, pure computations,
  materialization receipt, bundle package and replay

signals
  owns factor mapping, per-factor lineage/missingness and Signal V2 assembly

migration.legacy
  owns lossy adapters and comparison with real Legacy implementations
```

Allowed dependencies:

```text
Provider archive -> market_data -> features -> signals -> lifecycle
migration.legacy -> dividend_t
migration.comparison -> canonical feature + migration.legacy adapter
```

Forbidden dependencies include `market_data/features/signals/lifecycle ->
dividend_t`, Feature computation to a Repository/network/Broker, and Legacy
adapters writing canonical artifacts.

## 4. Canonical market-data authority

### 4.1 Contracts

`CanonicalMarketBar` is immutable and includes:

- normalized symbol, exchange and asset type;
- explicit `Timeframe` (`DAILY`, `MINUTE_1`, `MINUTE_5`, `MINUTE_15`,
  `MINUTE_30`, `MINUTE_60`);
- market date, timezone-aware event start/end and availability time;
- Decimal OHLC and optional previous close;
- integer/Decimal volume with explicit unit, optional Decimal amount and
  turnover rate;
- versioned adjustment mode and factor evidence;
- trading and limit state;
- exact source Artifact ID and SHA-256 hash.

Validation rejects non-canonical symbols/times, OHLC violations, negative
quantities, duplicate `(symbol,timeframe,event_end)` keys, future availability,
unsupported resampling, and inconsistent adjustment evidence. Rows are sorted
by `(symbol,timeframe,event_end)`.

### 4.2 Adjustment

`PriceAdjustmentPolicy` is content-addressed and distinguishes `RAW`,
`PIT_ADJUSTED`, and `RESEARCH_BACK_ADJUSTED`.

- Decision Runtime accepts only RAW or factors whose effective time and
  `available_at` are no later than DecisionTime.
- RESEARCH_BACK_ADJUSTED remains exploratory/non-formal-PIT and is rejected by
  lifecycle Signal assembly.
- A factor binds effective date, availability, source ID/hash and value.
- No current factor may rewrite a prior DecisionTime history window.

### 4.3 Dataset package

`MarketDataDatasetArtifact` is content-addressed and stores a small canonical
manifest plus deterministic JSON partitions by symbol/timeframe. Decimal and
timestamps are canonical strings; columns and rows have fixed order. A checksum
index covers every file. The Reader verifies exact files, checksums, manifest
identity, every row and aggregate coverage, and selectively loads requested
symbols/timeframes.

Publication uses a sibling staging directory, fsyncs files/directories, and
atomically installs the final content-derived directory without overwrite.
Staging cleanup and interruption are retry-safe.

The first adapter loads verified DailyLoop source-stage or replay packages and
maps real Provider OHLCV only. Missing previous close, turnover, minute bars or
adjustment factors remain explicit missing fields. H6 itself is not treated as
an OHLCV provider.

## 5. Feature definitions and configuration

Historical `FeatureDefinition` and FeatureArtifact V1 remain readable. New
execution uses independent V2 schemas:

- `FeatureDefinitionV2`: feature/version/model/version, required fields,
  supported timeframes, minimum history, warm-up/missingness policy, output
  kind/schema, validation status and limitations;
- `FeatureConfiguration`: typed canonical parameters, effective-from time,
  validation status, configuration ID/hash;
- `FeatureSetConfiguration`: sorted definition/configuration bindings,
  required/optional classification, timeframe/coverage/missingness policies,
  feature-set ID/hash.

Definitions describe semantics; they never contain Python source, expressions,
class names as sole identity, `eval`, or dynamic imports. Parameter schemas are
implemented by explicit constructors and range checks.

All production-like defaults are prohibited. The repository may publish one
explicit `research-only-v1` configuration factory for tests/CLI convenience;
the resulting full content-addressed configuration is always persisted and
bound as an input, and remains `MODEL_ASSUMPTION` /
`NOT_EMPIRICALLY_VALIDATED`.

## 6. Technical feature computation

`FeatureMaterializationRunner` loads one verified dataset once, groups bars by
symbol/timeframe, and evaluates registered pure computers from the immutable
FeatureSet. It emits one V2 Feature Artifact per Feature Definition across the
selected population, then one Bundle, Coverage Report and Receipt.

The shared observation contract records symbol, feature ID, timeframe,
event/availability time, Decimal or typed-state value, and one explicit missing
reason. Missing values never carry a numeric value. Family algorithms use a
private Decimal context (`prec=34`, `ROUND_HALF_EVEN`) so process-global Decimal
settings cannot alter results.

Initial families and required semantics:

- Price action: 1/3/5/10-session returns, intraday return when a real decision
  price/minute close exists, gap, high-low range, close-location value.
- Moving averages: SMA 5/10/20/60; EMA 5/10/12/20/26/60 using versioned
  seed-first recursion; price distance, slope, alignment, cross and MA distance.
- MACD: DIF, DEA, doubled histogram, cross, zero-axis, histogram direction and
  persistence, DIF/DEA slope, and divergence-candidate observable. Cross uses
  the previous confirmed bar; divergence is never a buy/sell instruction.
- Volume/amount: 5/10/20 ratios, percentiles, expansion/contraction,
  price-volume agreement, breakout confirmation, abnormal volume, turnover
  expansion and persistence. Each field is independently missing when its true
  source is absent.
- VWAP: cumulative session VWAP and derived distance/slope/cross only from real
  minute amount and volume at or before DecisionTime. Zero volume or absent
  minute data is missing; daily approximation is forbidden.
- Overheat/extension: short return, SMA distances, range/gap extension,
  consecutive up sessions, rolling-high distance and volume-price extension.

Every algorithm is O(history) per symbol/family. Cached trailing sums and one
pass EMA avoid quadratic windows. Serial and bounded-parallel modes sort output
after isolated symbol calculations and must produce identical hashes.

### 6.1 Status and coverage

Per observation and per feature distinguish `DATA_UNAVAILABLE`,
`FIELD_UNAVAILABLE`, `WINDOW_NOT_READY`, `TIMEFRAME_UNSUPPORTED`,
`SOURCE_TAMPERED`, `CONFIGURATION_INVALID`, and `COMPUTATION_FAILED`.
Bundle status is `COMPLETE` or `PARTIAL_COVERAGE`; a missing required feature
fails according to the exact Coverage Policy and is never relabelled complete.

## 7. Feature bundle and materialization receipt

`FeatureBundleArtifact` binds dataset ID/hash, FeatureSet ID/hash, DecisionTime,
created time, population/timeframes, every Feature Artifact ID/hash, model and
configuration references, coverage/missingness summaries, required-feature
status, data eligibility, formal-PIT limitation and authority ceiling.

The package contains the bundle index and immutable Feature packages under a
deterministic nested layout. One checksum index covers all files. The Reader
can select a symbol/feature, detects missing/tampered nested artifacts, and
reconstructs every typed reference without trusting projection summaries.

`FeatureMaterializationReceipt` binds the semantic command (dataset,
FeatureSet, population, DecisionTime, code revision), Bundle identity/hash,
coverage hashes and explicit safety declarations. The deterministic run ID and
idempotency key support retry/resume and content-addressed cache reuse. A
partial failure never creates a COMPLETE receipt.

## 8. Signal input and Signal Artifact V2

`SignalInputMappingConfiguration` contains one explicit source Feature ID for
each of the five factors, required-factor set, minimum count, maximum age,
allowed timeframe, validation/data-eligibility gates and research limitations.
There is no fallback chain inside code. In particular, missing amount ratio is
not replaced by volume ratio, and missing VWAP is not replaced by close.

`SignalFactorInput` records:

```text
factor name
value or None
Feature Artifact ID/hash
Feature ID
available_at
missing reason
```

`SignalObservationV2` contains exactly five Factor inputs and binds the
CandidateSet and Feature Bundle. `SignalInputAssembler` validates Candidate
coverage, dataset/config/timeframe/freshness and artifact identities. It does
not select a Signal state.

Signal V1 Reader remains supported. `run_signal_model_v2()` reuses one shared
internal five-factor decision function; it does not manufacture a V1
observation. SignalRun V2 and each SignalSnapshot bind the Feature Bundle and
exact factor Feature Artifact IDs/hashes. Threshold and state semantics of the
existing Signal model remain unchanged.

## 9. Lifecycle and PathForecast integration

The V1 stage order remains unchanged. Add typed manifest references and Reader
bindings for `MARKET_DATA_DATASET` and `FEATURE_BUNDLE`, plus configuration
kinds for FeatureSet and Signal Input Mapping. A canonical research run requires
exactly one verified Feature Bundle whose DecisionTime equals lifecycle as-of,
whose dataset/source lineage is valid, and whose FeatureSet/model/configuration
references are covered by the command manifests.

`SignalStageHandler` loads Platform Research and Feature Bundle, invokes the
Assembler, then Signal V2. It never reads raw data, recomputes Features,
imports Legacy, or uses the network. Without a Feature Bundle it fails closed;
the compatibility-only V1 stage fixture can explicitly exercise the former H6
missing path but the new operational CLI cannot create that path.

PathForecast continues binding the exact SignalSnapshot. Add a read-only
`PathForecastSampleProvider` Protocol for later H9. The current implementation
returns an explicit empty sample result and retains `DATA_INSUFFICIENT`,
`NOT_CALIBRATED`/data-insufficient calibration, and no probability claim.

## 10. Replay

Feature replay loads the exact source Dataset and FeatureSet from Bundle replay
metadata, recomputes all Feature Artifacts and the Bundle, then compares IDs,
hashes, observations, coverage, missingness, model/configuration references and
semantic fingerprint.

Signal replay must use the recomputed Feature Bundle, run the Assembler and
existing Signal decision logic, and compare the original Signal V2 Artifact.
Loading the stored Bundle alone is not model replay.

Lifecycle durable replay registers Dataset and Bundle Readers. For a Signal V2
reference it executes Feature replay before Signal replay. Replay remains
audit-only and cannot confirm H4.5, create a ManualTrade/Fill, call a Broker, or
promote a model.

## 11. Legacy differential evidence

Adapters for Moving Average, EMA, MACD and comparable Volume/Amount Structure
live only in `migration.legacy`. They invoke current Legacy functions and
surface pandas/float semantics, unsupported parameters/timeframes, lossy input
conversion and structured exceptions.

Each family has its own content-addressed policy with exact fields, per-output
tolerances, expected semantic changes, known defects and independent canonical
invariants. `CANONICAL_REGRESSION` or any unexpected difference makes the CLI
and delivery gate fail. Legacy output is comparison evidence only and never a
Signal input authority.

## 12. CLI and exit codes

Add module CLIs:

```text
python -m market_regime_alpha.cli.materialize_features
python -m market_regime_alpha.cli.compare_legacy_features
python -m market_regime_alpha.cli.replay_feature_bundle
python -m market_regime_alpha.cli.run_canonical_lifecycle
```

All emit stable JSON containing status, identities/hashes, coverage,
missingness/comparison/factor coverage, limitations and:

```text
NO_ORDER_CREATED=true
BROKER_NOT_INVOKED=true
NO_FILL_CREATED=true
TRADING_AUTHORITY_NOT_GRANTED=true
```

Exit codes distinguish argument error, tamper, business data insufficiency,
computation failure, canonical regression, repository/I/O, partial coverage and
success. Data insufficiency is a typed result rather than a generic traceback.

## 13. Dependency lock and CI

Setuptools remains the build backend. `uv.lock` resolves default, dev and
postgres extras on Python 3.12. CI installs with a frozen lock and runs docs,
pytest, Ruff, the existing mypy target, and build through `uv run`. Broker- or
Windows-only runtimes remain outside default dependencies.

## 14. Performance target

An offline benchmark uses deterministic generated canonical bars (no network)
for 100-300 symbols, at least 250 daily sessions and a configurable minute
slice. It reports symbol/session/minute counts, feature count, cold/cached
elapsed time, peak memory when available and output bytes. It verifies cache
reuse and stable hashes. Determinism and Decimal semantics take priority over
throughput; any future float vectorization requires a new version and Decimal
reference comparison.

## 15. Compatibility, rollback and forward repair

- Existing FeatureDefinition/FeatureArtifact/SignalRun V1 Readers and fixtures
  remain readable.
- No migration or stage-order change is required; new values extend typed input
  enums and Reader dispatch.
- A failed rollout stops producing new V2 packages. Immutable V1/V2 packages
  remain readable and are never rewritten.
- Orphan staging directories are removed only after validation of their exact
  scoped prefix. A published package without a receipt is adopted after full
  verification; a receipt pointing to missing/tampered content fails closed.
- Old lifecycle runs replay through their original V1 bindings. New runs cannot
  silently omit or replace the Feature Bundle.

## 16. Acceptance evidence

Completion requires focused tests for contracts, algorithms, tamper, atomic
publication, partial coverage, serial/parallel determinism, differential
classification, V1 compatibility, Signal factor lineage, lifecycle recovery
and feature/signal recomputation. The repository-wide docs, pytest, Ruff, mypy,
build and frozen-lock commands must pass at the final commit. A benchmark result
and exact final commit-bound delivery audit are required.
