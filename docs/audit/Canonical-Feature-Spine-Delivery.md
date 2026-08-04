# Canonical Feature Spine Delivery

> **Status:** CURRENT_STATUS
> **Authority:** Commit-bound delivery evidence for Canonical Market Data, Feature Bundle and Signal V2 inputs
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../architecture/13-Canonical-Market-Data-and-Feature-Spine.md, ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md
> **Code Evidence:** starting `main@9ccc751c237b060ab13a86602993d08753d5c634`; implementation checkpoint `14058a5`; gate checkpoint `1e861a7`

## 1. Delivery boundary

Delivered:

```text
verified Market Data evidence
→ CanonicalMarketBar / MarketDataDatasetArtifact
→ FeatureMaterializationRunner
→ FeatureArtifactV2 / FeatureBundleArtifact
→ SignalInputAssembler
→ SignalRunArtifactV2
→ PathForecast DATA_INSUFFICIENT
→ Entry BLOCKED_BY_MODEL_VALIDATION
```

The 16-stage graph and migration 011 were not changed. Feature production is an
independent prerequisite Run. No Opportunity, ManualTrade, Fill, order, Broker
call or trading authority is created.

## 2. Implemented contracts

- explicit Daily/1/5/15/30/60-minute Bar timeframes and Decimal OHLCV/amount;
- RAW, PIT-adjusted and research-back-adjusted versioned policies;
- deterministic partitioned Dataset package, exact checksums, atomic publish,
  selective Reader and replay;
- content-addressed Feature definitions/configurations/Feature Set;
- Price Action, MA/EMA, MACD, Volume/Amount, real-minute VWAP and
  Overheat/Extension observables;
- per-value availability, source-Bar identity, missingness and limitations;
- deterministic bounded-parallel materialization, coverage receipt and
  FeatureBundle package;
- MA/EMA/MACD/Volume Legacy adapters and independent comparison policies;
- five-factor Signal V2 assembly with exact Feature ID/output/timeframe,
  freshness and missing reasons;
- actual Feature and Signal recomputation in local and durable replay;
- formal Path sample-provider Protocol with a fail-closed unavailable default;
- structured Feature materialize/compare/replay CLIs and stable exit codes;
- frozen `uv.lock` for default/dev/postgres dependencies while retaining
  setuptools as build backend.

## 3. Replay evidence

The durable integration fixture observed:

```text
Feature Bundle ID:
  feature-bundle-26e22a85008aec678365aafe
Feature Bundle original/replayed hash:
  sha256:26e22a85008aec678365aafed24e01be671eb613dde75c206645bf70180a6dad

Signal input mapping hash:
  sha256:897e05e7d61462711e04e0b032b6082f5d2757f5c50abab441b47e3f1cfb8987
Signal original/replayed content hash:
  sha256:3d9e66641db7de9bba068c3549fee944e8a17f0e9383d73c55316d1f1639ab28

Source Signal receipt hash:
  sha256:d19e8da3dda40a7b40169160314deb495b8aa43bfee5b973f0df081765306b0b
Durable Replay report hash:
  sha256:ea3b6fcd33cbe026ee38140ec385423cde5c36fc14613cbe291e7711d499da9f
Replay status:
  STABLE
```

The Replay report contains `FEATURE_BUNDLE_PURE_RECOMPUTATION_STABLE` and
`SIGNAL_FEATURE_INPUT_REASSEMBLY_REPLAY_STABLE`. Identical Runner invocation
returns the same Run and does not republish Signal packages.

## 4. Performance evidence

The offline benchmark used 100 symbols, 250 daily sessions per symbol and 4,800
real-field synthetic 5-minute Bars. It materialized 600 Artifacts across six
families:

```text
cold Feature run       18.875838 seconds
cached verified replay  4.493092 seconds
process ru_maxrss       421,773,312 bytes
output bytes            127,261,684
```

The benchmark is an engineering fixture, not provider, PIT, model-quality or
Alpha evidence. The current deterministic JSON package size is registered as a
P2 storage-efficiency gap.

## 5. Verification at gate checkpoint

```text
uv sync --frozen --extra dev --extra postgres
  PASS

focused Feature/Market/Signal/Migration/Forecast/Lifecycle/Architecture
  490 passed, 0 skipped, 0 failed

H4/H5 focused regression
  143 passed, 0 skipped, 0 failed

uv run pytest -q
  2045 passed, 0 skipped, 0 failed
  6 pre-existing pandas PerformanceWarnings

uv run ruff check .
  PASS

uv run mypy
  PASS, 319 source files

uv run python -m build
  PASS, sdist and wheel

uv run python scripts/check_docs_links.py
  PASS

uv run pytest -q tests/scripts/test_check_docs_links.py
  8 passed, 0 skipped, 0 failed

git diff --check
  PASS
```

Remote CI and branch-protection status are not claimed by this local audit.

## 6. Remaining limitations

- qualified real Provider Market Data coverage and formal PIT are absent;
- Feature and Signal parameters are `MODEL_ASSUMPTION` and not empirically
  validated;
- Force Ratio, Chan and Tuishen observable migrations remain WP-MIG-01B;
- Path sample authority, labels, purged walk-forward, embargo, calibration and
  frozen OOS remain H9;
- Entry Model V1 remains unimplemented and Entry remains blocked;
- H7/H8, PostgreSQL parity, authentication/RBAC and Broker authority remain
  outside this delivery.

## 7. Admission statement

```text
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
formal_oos_alpha = false
shadow_ready = false
production_ready = false
trading_authority = false
```
