# Canonical Feature Spine Delivery

> **Status:** CURRENT_STATUS
> **Authority:** Commit-bound delivery evidence for Canonical Market Data, Feature Bundle and Signal V2 inputs
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../architecture/13-Canonical-Market-Data-and-Feature-Spine.md, ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md
> **Code Evidence:** starting `main@9ccc751c237b060ab13a86602993d08753d5c634`; implementation/gate checkpoint `72c8ed940d8b9d43788d6f2898ab081dc98bdc10`

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
  feature-bundle-c9da2f0305b5c58c680af58e
Feature Bundle original/replayed hash:
  sha256:c9da2f0305b5c58c680af58ee90856f69a2fd696bceff23899552e5c694a970c

Signal input mapping hash:
  sha256:897e05e7d61462711e04e0b032b6082f5d2757f5c50abab441b47e3f1cfb8987
Signal original/replayed content hash:
  sha256:6273b6b07eb610380e97cf8b0c027e41604207bac212d955e24c4535c2cdab56

Source Signal receipt hash:
  sha256:96d7bade4f9c9d60532a1612567e79124fe1fb8be2a493411bdcff42a4980efe
Durable Replay report hash:
  sha256:bcdfd37abefecb09e8bbec2e2de2855bbc909edb2e97999a341aeb5d4a2b7a0e
Replay status:
  STABLE
```

The Replay report contains `FEATURE_BUNDLE_PURE_RECOMPUTATION_STABLE` and
`SIGNAL_FEATURE_INPUT_REASSEMBLY_REPLAY_STABLE`. Identical Runner invocation
returns the same Run and does not republish Signal packages.

## 4. Performance evidence

The offline benchmark used 100 symbols, 250 daily sessions per symbol and 4,800
real-field synthetic 5-minute Bars. It materialized 700 Artifacts across seven
versioned Feature definitions:

```text
cold Feature run       29.502912 seconds
cached verified replay  8.359181 seconds
process ru_maxrss       398,229,504 bytes
output bytes            131,843,243
```

The benchmark is an engineering fixture, not provider, PIT, model-quality or
Alpha evidence. The current deterministic JSON package size is registered as a
P2 storage-efficiency gap.

## 5. Verification at gate checkpoint

```text
uv sync --frozen --extra dev --extra postgres
  PASS

focused Feature/Market/Signal/Migration/Forecast/Lifecycle/Architecture
  503 passed, 0 skipped, 0 failed

H4/H5 focused regression
  143 passed, 0 skipped, 0 failed

uv run pytest -q
  2058 passed, 0 skipped, 0 failed
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

The Bundle Reader reconstructs the exact FeatureSet × symbol projection from
loaded Feature Artifacts. Signal assembly additionally loads the verified
Dataset and validates Dataset/hash, adjustment policy and SourceManifest
projection. The `feature-bundle-v1`, `signal-observation-v2` and canonical Bar
schemas are new, unreleased contracts introduced and finalized on this feature
branch; no previously merged package authority was rewritten, while the
pre-existing historical Feature/Signal V1 Readers remain intact.

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
