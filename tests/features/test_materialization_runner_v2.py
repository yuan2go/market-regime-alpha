from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3

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
    migrate_feature_bundle_encoding_v1_to_v2,
    publish_feature_artifact_v2,
    publish_feature_bundle_v2,
    publish_feature_replay_report,
    replay_feature_bundle_v2,
)
from market_regime_alpha.features.encoding_v2 import read_feature_values_v2
from market_regime_alpha.features.materialization_run import (
    FeatureMaterializationExecutionMode,
    FeatureMaterializationRunStatus,
    FeatureMaterializationTaskSpec,
    FeatureMaterializationTaskStatus,
    SQLiteFeatureMaterializationRunRepository,
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
    execution_mode: FeatureMaterializationExecutionMode = (
        FeatureMaterializationExecutionMode.START_NEW
    ),
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
        execution_mode=execution_mode,
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


def test_prepared_feature_execution_context_is_built_once_per_run(
    tmp_path: Path, monkeypatch
) -> None:
    from market_regime_alpha.features import materialization_v2 as module

    original = module._verified_dataset_membership
    calls = 0

    def counted(dataset):
        nonlocal calls
        calls += 1
        return original(dataset)

    monkeypatch.setattr(module, "_verified_dataset_membership", counted)
    dataset = _verified_dataset(tmp_path)
    feature_set = canonical_technical_feature_set(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )
    FeatureMaterializationRunner(max_workers=4, task_batch_size=2).run(
        verified_dataset=dataset,
        feature_set=feature_set,
        decision_time=DECISION_TIME,
        created_at=CREATED_AT,
        selected_symbols=("600000.SH",),
        code_revision="revision-1",
        output_root=tmp_path / "features",
        idempotency_key="prepared-once",
        execution_mode=FeatureMaterializationExecutionMode.START_NEW,
    )

    assert calls == 1


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
    _, _, replayed = _run(
        tmp_path,
        execution_mode=FeatureMaterializationExecutionMode.RETURN_IF_COMPLETE,
    )

    assert replayed == first
    with pytest.raises(ValueError, match="idempotency key semantic conflict"):
        _run(
            tmp_path,
            code_revision="different-revision",
            execution_mode=FeatureMaterializationExecutionMode.RETURN_IF_COMPLETE,
        )


def test_feature_artifact_and_bundle_tamper_are_detected(tmp_path: Path) -> None:
    _, _, receipt = _run(tmp_path)
    bundle_path = tmp_path / "features" / receipt.bundle_locator
    verified = load_verified_feature_bundle_v2(
        bundle_path,
        artifact_root=tmp_path / "features" / "feature-artifacts",
    )
    artifact_package = verified.artifacts[0].root
    artifact_payload = artifact_package / "artifact.json.zlib"
    artifact_payload.write_bytes(artifact_payload.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_feature_artifact_v2(artifact_package)

    values = bundle_path / "values.parquet"
    values.write_bytes(values.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_feature_bundle_v2(
            bundle_path,
            artifact_root=tmp_path / "features" / "feature-artifacts",
        )


def test_feature_json_v1_migrates_to_columnar_v2_and_selects_without_hash_change(
    tmp_path: Path,
) -> None:
    _, _, receipt = _run(tmp_path / "source")
    source = load_verified_feature_bundle_v2(
        tmp_path / "source" / "features" / receipt.bundle_locator,
        artifact_root=tmp_path / "source" / "features" / "feature-artifacts",
    )
    v1_artifacts = tmp_path / "v1-artifacts"
    for item in source.artifacts:
        publish_feature_artifact_v2(
            root=v1_artifacts,
            artifact=item.artifact,
            encoding_version="feature-artifact-package-json-v1",
        )
    v1_bundle = publish_feature_bundle_v2(
        root=tmp_path / "v1-bundles",
        artifact_root=v1_artifacts,
        bundle=source.artifact,
        encoding_version="feature-bundle-package-json-v1",
    )
    loaded_v1 = load_verified_feature_bundle_v2(
        v1_bundle, artifact_root=v1_artifacts
    )
    v2_artifacts = tmp_path / "v2-artifacts"
    v2_bundle = migrate_feature_bundle_encoding_v1_to_v2(
        source_bundle_path=v1_bundle,
        source_artifact_root=v1_artifacts,
        target_bundle_root=tmp_path / "v2-bundles",
        target_artifact_root=v2_artifacts,
    )
    loaded_v2 = load_verified_feature_bundle_v2(
        v2_bundle, artifact_root=v2_artifacts
    )
    first = source.artifacts[0].artifact
    first_output = first.values[0].output_id
    selection = read_feature_values_v2(
        v2_bundle,
        symbols=(first.symbol,),
        feature_ids=(first.feature_id,),
        output_ids=(first_output,),
        timeframes=(first.timeframe,),
    )

    assert loaded_v1.artifact.content_hash == loaded_v2.artifact.content_hash
    assert loaded_v1.artifact.bundle_id == loaded_v2.artifact.bundle_id
    assert tuple(item.artifact.content_hash for item in loaded_v1.artifacts) == tuple(
        item.artifact.content_hash for item in loaded_v2.artifacts
    )
    assert len(selection.rows) == 1
    assert selection.rows[0]["symbol"] == first.symbol
    assert selection.rows[0]["output_id"] == first_output
    (v2_bundle / "unexpected.tmp").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="exact file set mismatch"):
        read_feature_values_v2(v2_bundle)


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


def test_concurrent_start_new_has_one_winner_and_one_explicit_conflict(
    tmp_path: Path,
) -> None:
    dataset = _verified_dataset(tmp_path)
    feature_set = canonical_technical_feature_set(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )

    def run() -> object:
        try:
            return FeatureMaterializationRunner(max_workers=1).run(
                verified_dataset=dataset,
                feature_set=feature_set,
                decision_time=DECISION_TIME,
                created_at=CREATED_AT,
                selected_symbols=("600000.SH",),
                code_revision="revision-1",
                output_root=tmp_path / "features",
                idempotency_key="concurrent-command",
                execution_mode=FeatureMaterializationExecutionMode.START_NEW,
            )
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = tuple(executor.map(lambda _: run(), range(2)))

    results = (first, second)
    assert sum(not isinstance(item, str) for item in results) == 1
    assert any(item == "Feature materialization run already exists" for item in results)


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
            execution_mode=FeatureMaterializationExecutionMode.START_NEW,
        )


def test_failed_materialization_resumes_exact_tasks_without_republishing_completed(
    tmp_path: Path, monkeypatch
) -> None:
    from market_regime_alpha.features import materialization_v2 as module

    original = module.compute_technical_feature
    calls = 0

    def fail_once(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ArithmeticError("first task interrupted")
        return original(**kwargs)

    monkeypatch.setattr(module, "compute_technical_feature", fail_once)
    with pytest.raises(FeatureComputationFailedError, match="computation failed"):
        _run(tmp_path, idempotency_key="resumable-failure")
    monkeypatch.setattr(module, "compute_technical_feature", original)

    _, _, receipt = _run(
        tmp_path,
        idempotency_key="resumable-failure",
        execution_mode=FeatureMaterializationExecutionMode.RESUME_EXISTING,
    )
    assert receipt.status in {
        FeatureMaterializationStatus.COMPLETE,
        FeatureMaterializationStatus.PARTIAL_COVERAGE,
    }
    repository = SQLiteFeatureMaterializationRunRepository(
        tmp_path / "features" / "materialization-run.sqlite3"
    )
    snapshot = repository.snapshot(1)
    assert snapshot.status is FeatureMaterializationRunStatus.COMPLETE
    assert all(
        status is FeatureMaterializationTaskStatus.COMPLETE
        for _, status, _, _ in snapshot.tasks
    )
    assert any(event_type == "RUN_RESUMED" for _, event_type, _, _ in snapshot.events)
    assert any(event_type == "TASK_FAILED" for _, event_type, _, _ in snapshot.events)


def test_materialization_repository_claim_cas_stale_recovery_and_history(
    tmp_path: Path,
) -> None:
    path = tmp_path / "run.sqlite3"
    repository = SQLiteFeatureMaterializationRunRepository(path)
    tasks = (
        FeatureMaterializationTaskSpec(
            symbol="600000.SH", feature_id="feature-a", timeframe=Timeframe.DAILY
        ),
        FeatureMaterializationTaskSpec(
            symbol="600001.SH", feature_id="feature-a", timeframe=Timeframe.DAILY
        ),
    )
    snapshot = repository.prepare(
        idempotency_key="repository-cas",
        command_hash=SOURCE_HASH,
        tasks=tasks,
        mode=FeatureMaterializationExecutionMode.START_NEW,
    )
    first = repository.claim_next(run_id=snapshot.run_id)
    second = repository.claim_next(run_id=snapshot.run_id)
    assert first is not None and second is not None
    assert first.task_key != second.task_key
    assert repository.claim_next(run_id=snapshot.run_id) is None
    repository.complete_task(
        first, artifact_id="artifact-a", artifact_hash=MANIFEST_HASH
    )
    with pytest.raises(ValueError, match="stale.*writer"):
        repository.complete_task(
            first, artifact_id="artifact-a", artifact_hash=MANIFEST_HASH
        )

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE feature_materialization_task SET claimed_at = ? "
            "WHERE run_id = ? AND task_key = ?",
            ("2000-01-01T00:00:00+00:00", snapshot.run_id, second.task_key),
        )
    recovered = repository.claim_next(
        run_id=snapshot.run_id, stale_after=timedelta(seconds=1)
    )
    assert recovered is not None
    assert recovered.task_key == second.task_key
    assert recovered.claim_token != second.claim_token
    assert recovered.attempt_number == 2
    with pytest.raises(ValueError, match="stale.*writer"):
        repository.fail_task(second, error_message="stale writer")
    repository.complete_task(
        recovered, artifact_id="artifact-b", artifact_hash=MANIFEST_HASH
    )
    rebuilt = SQLiteFeatureMaterializationRunRepository(path).snapshot(snapshot.run_id)
    assert all(
        status is FeatureMaterializationTaskStatus.COMPLETE
        for _, status, _, _ in rebuilt.tasks
    )
    event_types = tuple(item[1] for item in rebuilt.events)
    assert event_types.count("TASK_CLAIMED") == 3
    assert "STALE_CLAIM_RECOVERED" in event_types
    with pytest.raises(ValueError, match="already exists"):
        repository.prepare(
            idempotency_key="repository-cas",
            command_hash=SOURCE_HASH,
            tasks=tasks,
            mode=FeatureMaterializationExecutionMode.START_NEW,
        )
    with pytest.raises(ValueError, match="semantic conflict"):
        repository.prepare(
            idempotency_key="repository-cas",
            command_hash=MANIFEST_HASH,
            tasks=tasks,
            mode=FeatureMaterializationExecutionMode.RESUME_EXISTING,
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
