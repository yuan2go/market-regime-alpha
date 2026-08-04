from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.features.materialization_v2 import (
    FeatureBundleState,
    FeatureComputationFailedError,
    FeatureMaterializationRunner,
    FeatureMaterializationStatus,
    load_verified_feature_bundle_v2,
    load_verified_feature_artifact_v2,
    load_verified_feature_replay_report,
    publish_feature_bundle_v2,
    publish_feature_replay_report,
    replay_feature_bundle_v2,
)
from market_regime_alpha.features.spine import (
    FeatureConfiguration,
    FeatureSetConfiguration,
    RequiredFeatureCoveragePolicy,
)
from market_regime_alpha.features.technical.catalog import (
    VWAP_FEATURE_ID,
    canonical_technical_feature_set,
)
from market_regime_alpha.features.technical.observables import FeatureValueState
from market_regime_alpha.market_data import (
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    FormalPitStatus,
    MarketDataDatasetArtifact,
    PriceAdjustmentPolicy,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
    load_verified_market_data_dataset,
    publish_market_data_dataset,
)


UTC = timezone.utc
DECISION_TIME = datetime(2026, 8, 4, 2, 30, tzinfo=UTC)
CREATED_AT = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)
SOURCE_HASH = "sha256:" + "1" * 64
MANIFEST_HASH = "sha256:" + "9" * 64


def _daily_bars(
    count: int = 70, *, amount_missing_at: int | None = None
) -> tuple[CanonicalMarketBar, ...]:
    start = date(2026, 5, 26)
    result = []
    for index in range(count):
        market_date = start + timedelta(days=index)
        close = Decimal("10") + Decimal(index) / Decimal("100")
        previous = (
            None
            if index == 0
            else Decimal("10") + Decimal(index - 1) / Decimal("100")
        )
        event_start = datetime.combine(
            market_date, datetime.min.time(), tzinfo=UTC
        ) + timedelta(hours=1, minutes=30)
        event_end = event_start + timedelta(hours=5, minutes=30)
        result.append(
            CanonicalMarketBar.create(
                symbol="600000.SH",
                exchange=Exchange.SH,
                asset_type=AssetType.A_SHARE,
                timeframe=Timeframe.DAILY,
                market_date=market_date,
                event_start=event_start,
                event_end=event_end,
                available_at=event_end,
                open=close - Decimal("0.02"),
                high=close + Decimal("0.1"),
                low=close - Decimal("0.1"),
                close=close,
                previous_close=previous,
                volume=Decimal(100000 + index * 100),
                volume_unit=VolumeUnit.SHARES,
                amount=(
                    None
                    if index == amount_missing_at
                    else close * Decimal(100000 + index * 100)
                ),
                turnover_rate=Decimal("0.01"),
                adjustment_mode=AdjustmentMode.RAW,
                adjustment_factor=Decimal("1"),
                trading_status=TradingStatus.TRADING,
                price_limit_state=PriceLimitState.NORMAL,
                source_artifact_id=ArtifactId(f"daily-source-{index}"),
                source_content_hash=SOURCE_HASH,
            )
        )
    return tuple(result)


def _minute_bars() -> tuple[CanonicalMarketBar, ...]:
    starts = (
        datetime(2026, 8, 4, 1, 30, tzinfo=UTC),
        datetime(2026, 8, 4, 1, 35, tzinfo=UTC),
    )
    return tuple(
        CanonicalMarketBar.create(
            symbol="600000.SH",
            exchange=Exchange.SH,
            asset_type=AssetType.A_SHARE,
            timeframe=Timeframe.MINUTE_5,
            market_date=date(2026, 8, 4),
            event_start=start,
            event_end=start + timedelta(minutes=5),
            available_at=start + timedelta(minutes=5),
            open=Decimal(10 + index),
            high=Decimal(10 + index),
            low=Decimal(10 + index),
            close=Decimal(10 + index),
            previous_close=Decimal("9.9") if index == 0 else Decimal("10"),
            volume=Decimal(100 + index * 100),
            volume_unit=VolumeUnit.SHARES,
            amount=Decimal(1000 + index * 1200),
            turnover_rate=None,
            adjustment_mode=AdjustmentMode.RAW,
            adjustment_factor=Decimal("1"),
            trading_status=TradingStatus.TRADING,
            price_limit_state=PriceLimitState.NORMAL,
            source_artifact_id=ArtifactId(f"minute-source-{index}"),
            source_content_hash=SOURCE_HASH,
        )
        for index, start in enumerate(starts)
    )


def _verified_dataset(
    tmp_path: Path,
    *,
    include_minutes: bool = True,
    daily_count: int = 70,
    amount_missing_at: int | None = None,
):
    bars = (
        *_daily_bars(daily_count, amount_missing_at=amount_missing_at),
        *(_minute_bars() if include_minutes else ()),
    )
    expected_timeframes = (
        (Timeframe.DAILY, Timeframe.MINUTE_5)
        if include_minutes
        else (Timeframe.DAILY,)
    )
    artifact = MarketDataDatasetArtifact.create(
        decision_time=DECISION_TIME,
        created_at=CREATED_AT,
        bars=tuple(bars),
        expected_symbols=("600000.SH",),
        expected_timeframes=expected_timeframes,
        adjustment_policy=PriceAdjustmentPolicy.create(
            policy_version="1.0.0",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=(),
        ),
        source_manifest_references=((ArtifactId("source-manifest"), MANIFEST_HASH),),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("FORMAL_PIT_NOT_ESTABLISHED",),
    )
    package = publish_market_data_dataset(root=tmp_path / "market-data", artifact=artifact)
    return load_verified_market_data_dataset(package)


def _run(
    tmp_path: Path,
    *,
    include_minutes: bool = True,
    daily_count: int = 70,
    amount_missing_at: int | None = None,
    max_workers: int = 1,
    idempotency_key: str = "feature-run-1",
    code_revision: str = "revision-1",
    feature_set: FeatureSetConfiguration | None = None,
):
    dataset = _verified_dataset(
        tmp_path,
        include_minutes=include_minutes,
        daily_count=daily_count,
        amount_missing_at=amount_missing_at,
    )
    feature_set = feature_set or canonical_technical_feature_set(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )
    receipt = FeatureMaterializationRunner(max_workers=max_workers).run(
        verified_dataset=dataset,
        feature_set=feature_set,
        decision_time=DECISION_TIME,
        created_at=CREATED_AT,
        selected_symbols=("600000.SH",),
        code_revision=code_revision,
        output_root=tmp_path / "features",
        idempotency_key=idempotency_key,
        resume=True,
    )
    return dataset, feature_set, receipt


def test_runner_publishes_artifacts_bundle_coverage_and_receipt(tmp_path: Path) -> None:
    dataset, feature_set, receipt = _run(tmp_path)

    assert receipt.status is FeatureMaterializationStatus.COMPLETE
    assert receipt.no_order_created is True
    assert receipt.broker_not_invoked is True
    assert receipt.no_fill_created is True
    assert receipt.trading_authority == "TRADING_AUTHORITY_NOT_GRANTED"
    verified = load_verified_feature_bundle_v2(
        tmp_path / "features" / receipt.bundle_locator,
        artifact_root=tmp_path / "features" / "feature-artifacts",
    )
    assert verified.artifact.dataset_id == dataset.artifact.dataset_id
    assert verified.artifact.feature_set_id == feature_set.feature_set_id
    assert verified.artifact.state is FeatureBundleState.COMPLETE
    assert verified.artifact.required_feature_status == "COMPLETE"
    assert len(verified.artifacts) == 7
    vwap = next(
        item for item in verified.artifacts if item.artifact.feature_id == VWAP_FEATURE_ID
    )
    assert any(
        value.output_id == "price_vs_vwap_return"
        and value.state is FeatureValueState.AVAILABLE
        for value in vwap.artifact.values
    )


def test_no_minute_data_keeps_vwap_explicitly_missing(tmp_path: Path) -> None:
    _, _, receipt = _run(tmp_path, include_minutes=False)
    verified = load_verified_feature_bundle_v2(
        tmp_path / "features" / receipt.bundle_locator,
        artifact_root=tmp_path / "features" / "feature-artifacts",
    )
    vwap = next(
        item for item in verified.artifacts if item.artifact.feature_id == VWAP_FEATURE_ID
    )

    assert all(item.state is FeatureValueState.MISSING for item in vwap.artifact.values)
    assert all(
        item.missing_reason_codes == ("DATA_UNAVAILABLE_TIMEFRAME",)
        for item in vwap.artifact.values
    )
    assert receipt.status is FeatureMaterializationStatus.PARTIAL_COVERAGE
    assert verified.artifact.required_feature_status == "COMPLETE"


def test_required_family_without_warmup_blocks_complete_status(tmp_path: Path) -> None:
    _, _, receipt = _run(tmp_path, daily_count=5)
    verified = load_verified_feature_bundle_v2(
        tmp_path / "features" / receipt.bundle_locator,
        artifact_root=tmp_path / "features" / "feature-artifacts",
    )

    assert receipt.status is FeatureMaterializationStatus.BLOCKED_REQUIRED_FEATURE
    assert verified.artifact.state is FeatureBundleState.BLOCKED_REQUIRED_FEATURE
    assert verified.artifact.required_feature_status == "BLOCKED"


def test_partial_required_family_is_usable_but_bundle_remains_partial(
    tmp_path: Path,
) -> None:
    _, _, receipt = _run(tmp_path, amount_missing_at=69)
    verified = load_verified_feature_bundle_v2(
        tmp_path / "features" / receipt.bundle_locator,
        artifact_root=tmp_path / "features" / "feature-artifacts",
    )

    assert receipt.status is FeatureMaterializationStatus.PARTIAL_COVERAGE
    assert verified.artifact.required_feature_status == "COMPLETE"
    assert verified.artifact.state is FeatureBundleState.PARTIAL_COVERAGE


def test_allow_partial_policy_enforces_minimum_required_family_coverage(
    tmp_path: Path,
) -> None:
    base = canonical_technical_feature_set(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )
    policy = FeatureSetConfiguration.create(
        feature_set_version="allow-partial-threshold-test-v1",
        definitions=base.definitions,
        configurations=base.configurations,
        required_feature_ids=base.required_feature_ids,
        optional_feature_ids=base.optional_feature_ids,
        timeframe_policy=base.timeframe_policy,
        coverage_policy=RequiredFeatureCoveragePolicy.ALLOW_PARTIAL,
        minimum_required_coverage=Decimal("0.9"),
        missingness_policy=base.missingness_policy,
        validation_status=base.validation_status,
        limitations=base.limitations,
    )

    _, _, receipt = _run(tmp_path, daily_count=5, feature_set=policy)

    assert receipt.status is FeatureMaterializationStatus.BLOCKED_REQUIRED_FEATURE


def test_serial_parallel_and_restart_replay_are_hash_identical(tmp_path: Path) -> None:
    dataset_a, _, receipt_a = _run(tmp_path / "serial", max_workers=1)
    _, _, receipt_b = _run(tmp_path / "parallel", max_workers=4)

    assert receipt_a.bundle_hash == receipt_b.bundle_hash
    replay = replay_feature_bundle_v2(
        bundle_path=tmp_path / "serial" / "features" / receipt_a.bundle_locator,
        artifact_root=tmp_path / "serial" / "features" / "feature-artifacts",
        verified_dataset=dataset_a,
    )
    assert replay.original_bundle_hash == replay.replayed_bundle_hash
    assert replay.original_artifact_hashes == replay.replayed_artifact_hashes
    assert replay.semantic_match is True


def test_bundle_and_replay_report_publication_are_crash_atomic(tmp_path: Path) -> None:
    dataset, _, receipt = _run(tmp_path / "source")
    bundle = load_verified_feature_bundle_v2(
        tmp_path / "source" / "features" / receipt.bundle_locator,
        artifact_root=tmp_path / "source" / "features" / "feature-artifacts",
    )
    artifact_root = tmp_path / "source" / "features" / "feature-artifacts"

    def fail_after_staging(stage: str) -> None:
        if stage == "AFTER_STAGING_VALIDATED":
            raise RuntimeError("injected crash")

    bundle_root = tmp_path / "crash-bundles"
    with pytest.raises(RuntimeError, match="injected crash"):
        publish_feature_bundle_v2(
            root=bundle_root,
            artifact_root=artifact_root,
            bundle=bundle.artifact,
            failure_injector=fail_after_staging,
        )
    assert not (bundle_root / str(bundle.artifact.bundle_id)).exists()
    assert not tuple(bundle_root.glob(".*"))

    report = replay_feature_bundle_v2(
        bundle_path=bundle.root,
        artifact_root=artifact_root,
        verified_dataset=dataset,
    )
    report_root = tmp_path / "crash-reports"
    with pytest.raises(RuntimeError, match="injected crash"):
        publish_feature_replay_report(
            root=report_root,
            report=report,
            failure_injector=fail_after_staging,
        )
    assert not (report_root / str(report.report_id)).exists()
    assert not tuple(report_root.glob(".*"))

    package = publish_feature_replay_report(root=report_root, report=report)
    assert load_verified_feature_replay_report(package) == report


def test_same_idempotency_replays_and_semantic_conflict_is_rejected(
    tmp_path: Path,
) -> None:
    _, _, first = _run(tmp_path)
    _, _, replayed = _run(tmp_path)

    assert replayed == first
    with pytest.raises(ValueError, match="idempotency key semantic conflict"):
        _run(tmp_path, code_revision="different-revision")


def test_feature_artifact_and_bundle_tamper_are_detected(tmp_path: Path) -> None:
    _, _, receipt = _run(tmp_path)
    bundle_path = tmp_path / "features" / receipt.bundle_locator
    verified = load_verified_feature_bundle_v2(
        bundle_path,
        artifact_root=tmp_path / "features" / "feature-artifacts",
    )
    artifact_package = verified.artifacts[0].root
    artifact_json = artifact_package / "artifact.json"
    payload = json.loads(artifact_json.read_text(encoding="utf-8"))
    payload["symbol"] = "000001.SZ"
    artifact_json.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_feature_artifact_v2(artifact_package)

    checksums = bundle_path / "SHA256SUMS.json"
    checksums.write_bytes(checksums.read_bytes() + b" ")
    with pytest.raises(ValueError, match="checksum index"):
        load_verified_feature_bundle_v2(
            bundle_path,
            artifact_root=tmp_path / "features" / "feature-artifacts",
        )


def test_bundle_reconstructs_coverage_from_loaded_feature_artifacts(
    tmp_path: Path,
) -> None:
    _, _, receipt = _run(tmp_path)
    verified = load_verified_feature_bundle_v2(
        tmp_path / "features" / receipt.bundle_locator,
        artifact_root=tmp_path / "features" / "feature-artifacts",
    )
    coverage = replace(
        verified.artifact.coverage,
        available_value_count=verified.artifact.coverage.available_value_count + 1,
    )
    tampered = replace(verified.artifact, coverage=coverage)

    with pytest.raises(ValueError, match="materialized projection mismatch"):
        tampered.verify_materialized_projection(
            tuple(item.artifact for item in verified.artifacts)
        )

    with pytest.raises(ValueError, match="materialized scope mismatch"):
        verified.artifact.verify_materialized_projection(
            tuple(item.artifact for item in verified.artifacts[:-1])
        )
    with pytest.raises(ValueError, match="materialized scope mismatch"):
        verified.artifact.verify_materialized_projection(
            (*tuple(item.artifact for item in verified.artifacts), verified.artifacts[0].artifact)
        )


def test_bundle_rejects_legitimate_artifact_from_different_feature_configuration(
    tmp_path: Path,
) -> None:
    _, feature_set, receipt = _run(tmp_path / "canonical")
    canonical_bundle = load_verified_feature_bundle_v2(
        tmp_path / "canonical" / "features" / receipt.bundle_locator,
        artifact_root=tmp_path / "canonical" / "features" / "feature-artifacts",
    )
    original_configuration = feature_set.configurations[0]
    changed_parameters = tuple(
        replace(item, value="10") if item.name == "output_scale" else item
        for item in original_configuration.parameters
    )
    alternate_configuration = FeatureConfiguration.create(
        configuration_version="alternate-binding-test-v1",
        feature_id=original_configuration.feature_id,
        effective_from=original_configuration.effective_from,
        parameters=changed_parameters,
        validation_status=original_configuration.validation_status,
    )
    alternate_set = FeatureSetConfiguration.create(
        feature_set_version="alternate-binding-test-v1",
        definitions=feature_set.definitions,
        configurations=(
            alternate_configuration,
            *feature_set.configurations[1:],
        ),
        required_feature_ids=feature_set.required_feature_ids,
        optional_feature_ids=feature_set.optional_feature_ids,
        timeframe_policy=feature_set.timeframe_policy,
        coverage_policy=feature_set.coverage_policy,
        minimum_required_coverage=feature_set.minimum_required_coverage,
        missingness_policy=feature_set.missingness_policy,
        validation_status=feature_set.validation_status,
        limitations=feature_set.limitations,
    )
    _, _, alternate_receipt = _run(
        tmp_path / "alternate", feature_set=alternate_set
    )
    alternate_bundle = load_verified_feature_bundle_v2(
        tmp_path / "alternate" / "features" / alternate_receipt.bundle_locator,
        artifact_root=tmp_path / "alternate" / "features" / "feature-artifacts",
    )
    alternate = next(
        item.artifact
        for item in alternate_bundle.artifacts
        if item.artifact.feature_id == original_configuration.feature_id
    )
    artifacts = tuple(
        alternate
        if item.artifact.feature_id == original_configuration.feature_id
        else item.artifact
        for item in canonical_bundle.artifacts
    )

    with pytest.raises(ValueError, match="configuration binding mismatch"):
        canonical_bundle.artifact.verify_materialized_projection(artifacts)


def test_orphan_command_staging_file_does_not_block_retry(tmp_path: Path) -> None:
    key_hash = canonical_hash({"idempotency_key": "feature-run-1"}).split(":", 1)[1]
    command_root = tmp_path / "features" / "materialization-commands"
    command_root.mkdir(parents=True)
    orphan = command_root / f".{key_hash}.json.tmp-orphan"
    orphan.write_text("interrupted", encoding="utf-8")

    _, _, receipt = _run(tmp_path)

    assert receipt.bundle_hash.startswith("sha256:")
    # A writer cannot know whether another unique temp belongs to a live peer.
    # It therefore makes progress without deleting an unowned staging file.
    assert orphan.exists()


def test_concurrent_same_command_returns_one_identical_receipt(tmp_path: Path) -> None:
    dataset = _verified_dataset(tmp_path)
    feature_set = canonical_technical_feature_set(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )

    def run() -> object:
        return FeatureMaterializationRunner(max_workers=1).run(
            verified_dataset=dataset,
            feature_set=feature_set,
            decision_time=DECISION_TIME,
            created_at=CREATED_AT,
            selected_symbols=("600000.SH",),
            code_revision="revision-1",
            output_root=tmp_path / "features",
            idempotency_key="concurrent-command",
            resume=True,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = tuple(executor.map(lambda _: run(), range(2)))

    assert first == second


def test_arithmetic_failure_is_not_mislabeled_as_missing_data(
    tmp_path: Path, monkeypatch
) -> None:
    dataset = _verified_dataset(tmp_path)
    feature_set = canonical_technical_feature_set(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )

    def fail(**_kwargs):
        raise ArithmeticError("injected")

    monkeypatch.setattr(
        "market_regime_alpha.features.materialization_v2.compute_technical_feature",
        fail,
    )
    with pytest.raises(FeatureComputationFailedError, match="computation failed"):
        FeatureMaterializationRunner().run(
            verified_dataset=dataset,
            feature_set=feature_set,
            decision_time=DECISION_TIME,
            created_at=CREATED_AT,
            selected_symbols=("600000.SH",),
            code_revision="revision-1",
            output_root=tmp_path / "features",
            idempotency_key="failure",
            resume=True,
        )


def test_feature_bundle_detects_missing_referenced_artifact(tmp_path: Path) -> None:
    _, _, receipt = _run(tmp_path)
    bundle_path = tmp_path / "features" / receipt.bundle_locator
    verified = load_verified_feature_bundle_v2(
        bundle_path,
        artifact_root=tmp_path / "features" / "feature-artifacts",
    )
    referenced = verified.artifacts[0].root
    renamed = referenced.with_name(referenced.name + ".missing")
    referenced.rename(renamed)

    with pytest.raises(ValueError, match="referenced Feature Artifact is missing"):
        load_verified_feature_bundle_v2(
            bundle_path,
            artifact_root=tmp_path / "features" / "feature-artifacts",
        )
