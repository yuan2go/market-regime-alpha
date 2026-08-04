# Canonical Feature Spine and Signal Inputs Implementation Plan

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Executable TDD plan for the canonical technical-feature spine
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-04-canonical-feature-spine-and-signal-inputs-design.md, ../../architecture/12-Canonical-Runtime-and-Legacy-Migration.md
> **Code Evidence:** Planning baseline `main@9ccc751c237b060ab13a86602993d08753d5c634`; checkboxes become delivery evidence only after committed code and tests exist.

## Objective and boundaries

Build one replayable vertical chain from verified Provider archives through
Canonical Market Data and Feature Bundle into non-empty Signal inputs, while
preserving the 16-stage lifecycle graph and its Entry/trading authority ceiling.

No task in this plan may add Broker, order, Fill, automatic Thesis/Opportunity,
Entry validation, H7/H8/H9 behavior, PostgreSQL or UI responsibility.

## Task 1: Freeze reproducible dependency and CI behavior

**Files:** `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`,
`docs/README.md`, tests for dependency metadata where needed.

1. Add a failing CI/config assertion that the workflow uses Python 3.12,
   `uv sync --frozen --extra dev`, docs, pytest, Ruff, mypy and build.
2. Generate `uv.lock` resolving default, dev and postgres extras without adding
   XtQuant or other platform-specific runtime packages.
3. Retain `setuptools.build_meta`; switch CI commands to `uv run` only after the
   frozen sync succeeds locally.
4. Run `uv sync --frozen --extra dev`, docs, a focused test, Ruff, mypy and build.
5. Commit `chore: lock reproducible python environment`.

## Task 2: Add canonical market-data and adjustment contracts

**Create:**

- `src/market_regime_alpha/market_data/__init__.py`
- `src/market_regime_alpha/market_data/contracts.py`
- `src/market_regime_alpha/market_data/adjustment.py`
- `tests/market_data/test_contracts.py`
- `tests/market_data/test_adjustment.py`

1. Write failing tests for Timeframe, symbol/exchange, timezone, whole-second
   time, Decimal OHLC, negative volume/amount, duplicate keys, suspension/limit
   states and immutable contracts.
2. Implement `CanonicalMarketBar`, `Timeframe`, `AssetType`, `AdjustmentMode`,
   `TradingState` and `PriceLimitState` with no I/O dependency.
3. Write failing tests for RAW, PIT factor effective/availability boundaries,
   future factor rejection and RESEARCH_BACK_ADJUSTED Decision Runtime refusal.
4. Implement content-addressed `AdjustmentFactorEvidence` and
   `PriceAdjustmentPolicy`.
5. Run focused pytest/Ruff/mypy and commit `feat: define canonical market data`.

## Task 3: Publish and read partitioned Market Data Dataset V1

**Create:**

- `src/market_regime_alpha/market_data/dataset.py`
- `src/market_regime_alpha/market_data/publisher.py`
- `src/market_regime_alpha/market_data/readers.py`
- `src/market_regime_alpha/market_data/adapters/public_archive.py`
- `tests/market_data/test_dataset.py`
- `tests/market_data/test_public_archive_adapter.py`

1. Write failing canonical round-trip, stable hash, deterministic sort,
   point-in-time, coverage and selective-load tests.
2. Implement a manifest plus JSON partitions by symbol/timeframe with fixed
   schema and canonical Decimal/time strings.
3. Write failing exact-file, missing partition, checksum/canonical/identity
   tamper, conflicting publish and interruption tests.
4. Implement sibling staging, file/directory fsync, atomic non-overwrite install,
   orphan cleanup and idempotent re-publication.
5. Implement the verified DailyLoop source-stage/replay adapter; reject unknown
   source hashes and never synthesize amount/volume/OHLC.
6. Run focused tests and commit `feat: publish canonical market datasets`.

## Task 4: Define Feature V2 configuration and output contracts

**Create:**

- `src/market_regime_alpha/features/definitions.py`
- `src/market_regime_alpha/features/configuration.py`
- `src/market_regime_alpha/features/observations.py`
- `tests/features/test_feature_definitions_v2.py`
- `tests/features/test_feature_set_configuration.py`

1. Write failing tests for canonical identity, typed parameters, unsupported
   timeframe, invalid range, duplicate feature/version, required/optional
   classification, output schema, limitation and validation status.
2. Implement `FeatureDefinitionV2`, explicit typed `FeatureConfiguration`,
   `FeatureSetConfiguration`, coverage/missingness policies and immutable
   `TechnicalFeatureObservation`.
3. Prove no eval/arbitrary class-name execution and run focused checks.
4. Commit `feat: define canonical feature set authority`.

## Task 5: Implement price action and moving-average families

**Create/modify:**

- `src/market_regime_alpha/features/technical/common.py`
- `src/market_regime_alpha/features/technical/price_action.py`
- `src/market_regime_alpha/features/technical/moving_average_v2.py`
- `tests/features/technical/test_price_action.py`
- `tests/features/technical/test_moving_average_v2.py`

1. Add reference tests for 1/3/5/10 returns, gap, range, close location,
   suspension, unavailable intraday and no future-bar usage.
2. Implement strict Decimal trailing calculations and explicit missingness.
3. Add SMA 5/10/20/60, EMA 5/10/12/20/26/60, distance, slope, alignment,
   cross and MA-distance tests including exact warm-up and prior-confirmed-bar
   cross.
4. Implement seed-first Decimal EMA and moving-average observables in O(n).
5. Test process Decimal context independence and commit
   `feat: materialize price and moving average observables`.

## Task 6: Implement MACD with an independent Decimal oracle

**Create:**

- `src/market_regime_alpha/features/technical/macd.py`
- `tests/features/technical/test_macd.py`

1. Write fixed-sequence expected EMA-fast, EMA-slow, DIF, DEA and doubled
   histogram values independently of Legacy.
2. Add cross, zero-axis, expansion/contraction, consecutive direction,
   DIF/DEA slope, divergence-candidate, warm-up, non-future and rounding tests.
3. Implement versioned periods, seed, multiplier, tolerance and missingness.
4. Assert algebraic invariants for every non-missing row and commit
   `feat: add decimal macd observables`.

## Task 7: Implement volume, VWAP and extension families

**Create:**

- `src/market_regime_alpha/features/volume_price/structure.py`
- `src/market_regime_alpha/features/technical/vwap.py`
- `src/market_regime_alpha/features/technical/extension.py`
- `tests/features/volume_price/test_structure.py`
- `tests/features/technical/test_vwap.py`
- `tests/features/technical/test_extension.py`

1. Write normal/minimum-window/missing-field/extreme-value tests for every
   requested volume, amount and turnover output.
2. Implement true-field-only ratios, percentile, expansion, agreement,
   breakout, abnormal and persistence observables.
3. Write minute-session VWAP tests covering auction/session filtering, lunch
   break, decision cutoff, zero volume and missing amount/minute data.
4. Implement cumulative real amount/volume VWAP plus distance/slope/cross.
5. Write and implement overheat/extension observables; verify none emit action
   words or decision objects.
6. Run focused suites and commit `feat: add volume vwap and extension features`.

## Task 8: Implement materialization, Feature package V2 and Bundle

**Create:**

- `src/market_regime_alpha/features/materialization.py`
- `src/market_regime_alpha/features/artifact_v2.py`
- `src/market_regime_alpha/features/bundle.py`
- `src/market_regime_alpha/features/replay_v2.py`
- `tests/features/test_materialization_runner.py`
- `tests/features/test_feature_bundle.py`
- `tests/features/test_feature_bundle_replay.py`

1. Write failing complete/partial/required/optional and per-symbol fault
   isolation tests.
2. Implement one-load grouped computation, stable output ordering, bounded
   parallelism and typed error classification.
3. Write nested-package checksum/tamper/conflict/interruption/cache tests.
4. Implement atomic V2 Feature/Bundle publication and strict selective Reader.
5. Implement deterministic receipt/idempotency/resume and semantic cache.
6. Replay from the Dataset and FeatureSet, compare all artifacts/bundle fields,
   and prove serial/parallel hashes equal.
7. Commit `feat: materialize replayable feature bundles`.

## Task 9: Extend Legacy differential coverage

**Create/modify:**

- `src/market_regime_alpha/migration/legacy/adapters/technical_features.py`
- `src/market_regime_alpha/migration/comparison/feature_families.py`
- `tests/migration/test_legacy_technical_feature_adapters.py`
- `tests/migration/test_technical_feature_differential.py`

1. Characterize and invoke actual Legacy rolling/float MA, EMA/MACD and
   comparable volume/amount paths.
2. Add family-specific policies and independent invariants; cover all seven
   differential classifications, exceptions, unsupported windows and
   float/Decimal differences.
3. Make canonical regression/unexpected difference an explicit failing result.
4. Prove Legacy adapters cannot publish or write canonical repositories.
5. Commit `feat: compare canonical technical observables`.

## Task 10: Assemble per-factor Signal V2 inputs

**Create/modify:**

- `src/market_regime_alpha/signals/input_assembly.py`
- `src/market_regime_alpha/signals/engine.py`
- `src/market_regime_alpha/signals/artifact.py`
- `tests/signals/test_input_assembly.py`
- `tests/signals/test_signal_v2_artifact.py`

1. Write configuration identity and exact five-factor mapping tests.
2. Add all/partial/none, candidate/symbol, freshness, timeframe, dataset,
   FeatureSet/config, validation, VWAP-missing and no-zero-fill tests.
3. Implement `SignalFactorInput`, `SignalObservationV2`, mapping config and
   `SignalInputAssembler`.
4. Extract shared internal threshold/state logic and implement SignalRun V2
   without constructing V1 observations.
5. Add V1 Reader compatibility, V2 lineage/tamper/replay and stable-output tests.
6. Commit `feat: assemble feature-derived signal inputs`.

## Task 11: Bind Bundle and Signal V2 into lifecycle/replay

**Modify/create:**

- `application/canonical_lifecycle/contracts.py`
- `application/canonical_lifecycle/input_manifest.py`
- `application/canonical_lifecycle/runtime_configuration.py`
- `application/canonical_lifecycle/sqlite_composition.py`
- `application/canonical_lifecycle/stages/signal_forecast.py`
- `application/canonical_lifecycle/replay.py`
- `forecasting/path.py`
- lifecycle and compatibility tests.

1. Add failing typed object/Reader/config binding tests for Market Dataset,
   Feature Bundle, FeatureSet and Signal Mapping.
2. Preserve schema/readability of historical manifests and stage order.
3. Refactor `SignalStageHandler` to load verified Research + Bundle, run the
   Assembler/Signal V2 and bind both inputs in the receipt.
4. Add `PathForecastSampleProvider` and the current explicit empty provider;
   retain DATA_INSUFFICIENT/unvalidated Entry behavior.
5. Extend durable replay so Bundle recomputation precedes Signal V2 replay.
6. Add end-to-end crash/resume/replay test proving one real factor is non-null,
   exact missing reasons, no Opportunity/ManualTrade/Fill/Broker, stable receipt
   fingerprints and Entry blocking.
7. Commit `feat: connect feature bundles to canonical signal`.

## Task 12: Add operational CLIs and benchmark

**Create/modify:**

- `src/market_regime_alpha/cli/materialize_features.py`
- `src/market_regime_alpha/cli/compare_legacy_features.py`
- `src/market_regime_alpha/cli/replay_feature_bundle.py`
- `scripts/benchmark_feature_materialization.py`
- `tests/cli/test_materialize_features.py`
- `tests/cli/test_compare_legacy_features.py`
- `tests/cli/test_replay_feature_bundle.py`
- `tests/performance/test_feature_materialization_benchmark.py`

1. Write structured JSON and stable exit-code tests before implementation.
2. Implement only explicit file/config inputs and safety declarations.
3. Test resume, partial coverage, tamper, computation/I/O failure and canonical
   regression without broad exception-to-success handling.
4. Run the offline benchmark for the required scale; record exact results in
   the delivery audit.
5. Commit `feat: operate and benchmark canonical features`.

## Task 13: Architecture enforcement and compatibility regression

**Modify/create:** architecture tests, V1 fixtures, H4/H5/H6 and canonical
lifecycle regression tests.

1. Strengthen import scanning for market_data/features/Signal Assembler and
   forbid Legacy/execution/Broker reverse dependencies.
2. Verify Feature V1, Signal V1, historical Research and lifecycle V1 Readers.
3. Run H4/H5/H6 focused tests and all canonical runtime tests.
4. Commit `test: enforce canonical feature boundaries`.

## Task 14: Documentation, final gates and delivery

**Update/add:**

- `docs/architecture/13-Canonical-Market-Data-and-Feature-Spine.md`
- `docs/architecture/decisions/ADR-005-Feature-Materialization-Precedes-Lifecycle.md`
- `docs/status/Current-State.md`
- `docs/status/Capability-Matrix.md`
- `docs/status/Gap-Register.md`
- `docs/README.md`
- `docs/audit/Canonical-Feature-Spine-Delivery.md`

1. Document actual authority, time/adjustment, Feature/Bundle/Signal mapping,
   partial coverage, replay, Legacy differences, performance and non-claims.
2. Run focused suites, then:

   ```bash
   git diff --check
   uv sync --frozen --extra dev
   uv run python scripts/check_docs_links.py
   uv run pytest
   uv run ruff check .
   uv run mypy
   uv run python -m build
   ```

3. Run traditional commands for compatibility, inspect the complete diff and
   exclude `.idea`, caches, databases, artifacts and build output.
4. Perform standards/spec code review, fix findings, create semantic checkpoint
   commits, push `feat/canonical-feature-spine-and-signal-inputs`, and open the
   requested Draft PR without merging it.
