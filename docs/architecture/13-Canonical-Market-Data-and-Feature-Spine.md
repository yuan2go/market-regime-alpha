# Canonical Market Data and Feature Spine

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Canonical market-data, technical-observable and Signal-input architecture
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** 04-Data-and-Time-Semantics.md, 09-Platform-Architecture-V2.md, 12-Canonical-Runtime-and-Legacy-Migration.md, decisions/ADR-005-Feature-Materialization-Precedes-Lifecycle-V1.md
> **Code Evidence:** implementation/gate checkpoint `4f099069cde5191e46d3c242dd46788947997f9c`; `market_data/**`, `features/{spine,materialization_v2,v2_contracts}.py`, `features/technical/**`, `signals/{input_assembly,v2}.py`, `application/canonical_lifecycle/stages/signal_forecast.py`

## 1. Boundary and authority

The canonical path is:

```text
Verified Provider Archive / Source Artifact
→ CanonicalMarketBar
→ MarketDataDatasetArtifact
→ FeatureMaterializationRunner
→ FeatureArtifactV2[]
→ FeatureBundleArtifact
→ CanonicalLifecycleInputManifest
→ SignalInputAssembler
→ SignalObservationV2
→ SignalRunArtifactV2
→ PathForecast
→ EntryAssessment
```

`Feature` means a time-bounded observable. It cannot produce `BUY`, `SELL`,
`ENTER`, `ADD`, `REDUCE`, `EXIT`, an order, a position, a `ManualTrade` or a
`Fill`. `SignalRunArtifactV2` remains exploratory evidence and Entry remains
`BLOCKED_BY_MODEL_VALIDATION`.

Canonical Feature and Signal modules do not import `dividend_t`, execution or
Broker modules. Legacy execution is isolated under `migration.legacy` and its
output is comparison evidence only.

## 2. Canonical market data authority

### 2.1 Bar contract

`CanonicalMarketBar` is immutable and content-addressed. It binds normalized
symbol/exchange/asset type, explicit `Timeframe`, market date, timezone-aware
event interval and `available_at`, Decimal OHLC/amount/turnover, Decimal volume
with an explicit unit, trading/limit states, adjustment identity, and the source
Artifact ID/hash.

Validation rejects malformed OHLC relationships, negative volume/amount,
future availability, duplicate `(symbol, timeframe, event_start)` identities,
non-canonical timestamps and source/hash tampering. Missing Provider fields stay
missing; close is never copied into OHLC, volume is never synthesized, and
amount is never manufactured from a guessed volume.

Supported contract timeframes are `DAILY`, `MINUTE_1`, `MINUTE_5`,
`MINUTE_15`, `MINUTE_30` and `MINUTE_60`. A Feature declares the exact
timeframes it accepts. No automatic daily/minute substitution or implicit
resampling exists.

### 2.2 Price adjustment

`PriceAdjustmentPolicy` is versioned and distinguishes:

| Mode | Decision-runtime admission | Required evidence |
|---|---|---|
| `RAW` | Allowed | original source Artifact |
| `PIT_ADJUSTED` | Allowed only for declared scope | effective-dated factor, factor `available_at`, source ID/hash |
| `RESEARCH_BACK_ADJUSTED` | Research-only | explicit `FORMAL_PIT_NOT_ESTABLISHED` limitation |

The Reader rejects a factor that was not available by DecisionTime. Current
latest factors cannot rewrite an earlier decision view.

### 2.3 Dataset package

`MarketDataDatasetArtifact` stores a manifest plus deterministic
symbol/timeframe JSON partitions and `SHA256SUMS.json`. Rows and partitions are
sorted, schema and Decimal rendering are canonical, exact files/checksums are
verified, and publication uses same-directory staging, file/directory `fsync`
and atomic install. The Reader can select symbols/timeframes without changing
the Dataset identity. `created_at` is package production time; derived
`available_at` is the latest bound source-Bar availability and is the correct
lifecycle input-time projection.

JSON partitions are the current deterministic baseline. At larger sustained
operating scale a separately versioned columnar encoding may replace the
physical format, but it must preserve Decimal, timezone, row order, checksums
and Reader compatibility.

## 3. Feature definitions and configuration

`FeatureDefinitionV2` binds semantic Feature/version, model identity/version,
required fields, supported timeframes, minimum history, warmup/missingness,
typed outputs, validation state and limitations. `FeatureConfiguration` binds
typed/range-checked parameters and effective time. `FeatureSetConfiguration`
content-addresses the exact definitions/configurations, required/optional
classification, exact-timeframe policy and coverage policy.

No class name, expression string, `eval`, process global or hidden production
default is a Feature identity. The delivered Feature Set is explicitly
`MODEL_ASSUMPTION`, `NOT_EMPIRICALLY_VALIDATED`, `RESEARCH_ONLY`.

## 4. Delivered technical observables

All numeric output uses a local Decimal context and `ROUND_HALF_EVEN` to 12
decimal places. Missing values have no numeric payload and carry a precise
reason such as `WINDOW_NOT_READY`, `FIELD_UNAVAILABLE_*`,
`TIMEFRAME_UNSUPPORTED` or `DATA_UNAVAILABLE_TIMEFRAME`.

| Feature ID | Timeframe / minimum history | Outputs and formula summary | Legacy comparison |
|---|---|---|---|
| `technical.price_action.v1` | Daily, 11 | `return_n = close_t / close_(t-n) - 1` for 1/3/5/10; gap to real previous close; high-low range; close-location value | No Legacy authority claimed |
| `technical.intraday_price_action.v1` | real minute Bar, 1 | current-session first observed minute-Bar open to the latest close available by DecisionTime; never changes daily return windows into bar windows | No Legacy authority claimed |
| `technical.moving_average.v2` | Daily, 61 | strict trailing SMA 5/10/20/60; recursive-first-observation EMA 5/10/12/20/26/60; price distance, one-confirmed-Bar slope/cross, alignment and MA distances | MA/EMA real Legacy adapters; per-family Decimal/float tolerances |
| `technical.macd.v1` | Daily, warmup 34 | `DIF=EMA12-EMA26`; `DEA=EMA9(DIF)`; histogram `=2*(DIF-DEA)`; cross, zero axis, expansion, consecutive direction, slopes and divergence candidate | real Legacy MACD; state-vocabulary change is explicit, invariants remain mandatory |
| `technical.volume_amount_structure.v1` | Daily, 21 | real volume/amount ratios 5/10/20 using prior completed sessions excluding current; percentiles, expansion/contraction, direction agreement, breakout/abnormal state, turnover expansion and persistence | Legacy volume denominator difference is explicit; amount structure may be `NOT_COMPARABLE` |
| `technical.session_vwap.v1` | real minute Bar, 1 | cumulative `sum(amount)/sum(volume)`, price distance, VWAP slope and crossing over observed A-share regular-session Bars | no daily approximation and no Legacy authority |
| `technical.overheat_extension.v1` | Daily, 21 | 3-session return, price/SMA5/10 distance, range/gap extension, consecutive-up count, rolling-high distance and volume-price extension | observable only; not a sell signal |

Suspended or field-incomplete observations do not poison independent Features.
VWAP and intraday Price Action are optional in the initial Feature Set; the five daily families are
required. A missing required family makes the Bundle
`BLOCKED_REQUIRED_FEATURE`; any optional missing output makes coverage partial,
never complete by assertion.

## 5. Materialization, Bundle and replay

`FeatureMaterializationRunner` reads one verified Dataset, validates exact
DecisionTime and symbol coverage, groups Bar objects once by symbol/timeframe,
builds one immutable Dataset membership index, runs pure Feature computation,
publishes each Feature package and then publishes the Bundle and receipt.

The file-backed command index binds idempotency key to command hash. Same-key,
same-command reads and verifies the existing Bundle; semantic conflict fails.
Publication interruption before atomic install leaves no final package; an
installed package is immutable and reusable. Parallelism is bounded to eight
workers and `executor.map` order plus final stable sorting makes serial and
parallel Bundle hashes identical.

`FeatureBundleArtifact` binds Dataset, Feature Set, model/config identities,
symbols/timeframes, every Feature reference, coverage/missingness and authority
ceilings. The lifecycle manifest carries one Dataset and one Bundle rather than
hundreds of loose Feature references.

Replay performs real recomputation:

```text
MarketDataDataset + FeatureSet
→ recomputed FeatureArtifactV2[]
→ recomputed FeatureBundle
→ identity/hash/coverage/missingness comparison
→ SignalInputAssembler
→ shared Signal model
→ recomputed SignalRunArtifactV2
```

It does not merely reload the original Bundle. Replay reports are themselves
crash-atomically published and cannot invoke confirmation, execution, Fill,
Broker or model promotion.

## 6. Signal input assembly

The versioned `canonical-five-factor-mapping-v1` mapping is:

| Signal factor | Exact source | Timeframe | Freshness |
|---|---|---|---|
| `price_action_return` | `technical.price_action.v1:return_3` | Daily | 172800 s |
| `volume_ratio` | `technical.volume_amount_structure.v1:amount_ratio_5` | Daily | 172800 s |
| `trend_return` | `technical.moving_average.v2:price_vs_sma20_return` | Daily | 172800 s |
| `price_vs_vwap_return` | `technical.session_vwap.v1:price_vs_vwap_return` | 5 minute | 7200 s |
| `overheat_return` | `technical.overheat_extension.v1:short_return` | Daily | 172800 s |

There is no amount-to-volume fallback and no close-to-VWAP fallback. Each factor
records value or `None`, source Feature/Artifact ID/hash, timeframe,
`available_at` and missing reason. Candidate/Bundle Dataset scope, symbol,
Feature Set, configuration, freshness, validation status and exploratory
eligibility are verified before invoking the existing shared Signal rules.
The assembler receives the verified Market Data Dataset itself and reconstructs
the Bundle's Dataset, adjustment-policy and SourceManifest projection instead
of trusting self-declared Bundle fields.

The minimum factor count is currently one so the Canonical Signal can consume a
real non-empty factor while explaining the others. This is a model assumption,
not evidence that the Signal predicts returns.

## 7. Lifecycle and Forecast safety

Feature materialization is a prerequisite Run; the immutable 16-stage V1 graph
and migration 011 are unchanged. The Signal receipt binds the FeatureBundle and
mapping/configuration hashes. Same-command resume does not republish Feature or
Signal packages.

`PathForecastSampleProvider` is the H9 sample-authority Protocol. The default
provider returns no samples plus
`FORMAL_PATH_SAMPLE_PROVIDER_NOT_CONFIGURED`; therefore PathForecast remains
`DATA_INSUFFICIENT` and `NOT_CALIBRATED` even when Signal factors are non-empty.
Entry remains `BLOCKED_BY_MODEL_VALIDATION` and no Opportunity, ManualTrade,
Fill, order or Broker call is created.

## 8. Performance evidence and limitations

Offline benchmark retained at implementation/gate checkpoint `4f09906`:

| Metric | Observed value |
|---|---:|
| Symbols | 100 |
| Daily sessions / Bars | 250 / 25,000 |
| 5-minute Bars | 4,800 |
| Feature definitions / Artifacts | 7 / 700 |
| Cold Feature run | 29.502912 s |
| Cached receipt verification | 8.359181 s |
| Process `ru_maxrss` | 398,229,504 bytes |
| Dataset + output package size | 131,843,243 bytes |

The fixture is deterministic, offline and synthetic; it measures engineering
cost only. JSON/Hash package size and repeated immutable verification are the
main remaining storage/latency bottleneck. It does not establish real-provider
coverage, formal PIT, model quality, OOS Alpha, Shadow readiness or production
capacity.

## 9. Explicit authority ceiling

```text
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
formal_oos_alpha = false
production_ready = false
```
