from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    OutcomeMarketCondition,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    BarrierOrderingOutcome,
    TargetOutcomeLabel,
    TargetedShadowOutcome,
    _build_label,
)
from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
    TargetOutcomeConflict,
)
from market_regime_alpha.application.research_evaluation.targets import (
    CorporateActionPolicy,
    OutcomeCheckpoint,
    OutcomeTargetProtocol,
    TargetDefinition,
    canonical_target_horizon,
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.market_data.contracts import (
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
)


HASH = "sha256:" + "a" * 64


def _minute_bar(
    *,
    start: datetime,
    close: Decimal,
    high: Decimal,
    low: Decimal = Decimal("9.9"),
    timeframe: Timeframe = Timeframe.MINUTE_1,
    adjustment_mode: AdjustmentMode = AdjustmentMode.RAW,
) -> CanonicalMarketBar:
    adjusted = adjustment_mode is not AdjustmentMode.RAW
    return CanonicalMarketBar.create(
        symbol="600000.SH",
        exchange=Exchange.SH,
        asset_type=AssetType.A_SHARE,
        timeframe=timeframe,
        market_date=date(2026, 8, 11),
        event_start=start,
        event_end=start + (timeframe.duration or timedelta(days=1)),
        available_at=start + (timeframe.duration or timedelta(days=1)),
        open=Decimal("10"),
        high=high,
        low=low,
        close=close,
        previous_close=Decimal("10"),
        volume=Decimal("100"),
        volume_unit=VolumeUnit.SHARES,
        amount=Decimal("1000"),
        turnover_rate=None,
        adjustment_mode=adjustment_mode,
        adjustment_factor=Decimal("1.2") if adjusted else Decimal("1"),
        adjustment_factor_id=ArtifactId("adjustment-factor") if adjusted else None,
        adjustment_factor_hash=HASH if adjusted else None,
        trading_status=TradingStatus.TRADING,
        price_limit_state=PriceLimitState.NORMAL,
        source_artifact_id=ArtifactId("source"),
        source_content_hash=HASH,
    )


def test_multi_horizon_protocol_is_content_addressed_and_round_trips() -> None:
    protocol = engineering_multi_horizon_protocol()

    assert {item.checkpoint for item in protocol.targets} == set(OutcomeCheckpoint)
    assert all(item.label_start == "FROZEN_DECISION_TIME" for item in protocol.targets)
    assert all(item.schema_version == "outcome_target_definition/v2" for item in protocol.targets)
    assert all(
        item.canonical_horizon.observation_window.end
        == item.canonical_horizon.evaluation_timestamp
        for item in protocol.targets
    )
    assert all(
        item.corporate_action_policy is CorporateActionPolicy.RAW_ONLY_FAIL_CLOSED
        for item in protocol.targets
    )
    required = {item.checkpoint: item.required_market_data for item in protocol.targets}
    assert required[OutcomeCheckpoint.OPEN] == ("FACTUAL_OUTCOME_V1",)
    assert required[OutcomeCheckpoint.TIME_1000] == ("MINUTE_1",)
    assert required[OutcomeCheckpoint.CLOSE] == ("DAILY", "MINUTE_1")
    assert OutcomeTargetProtocol.from_canonical_dict(protocol.to_canonical_dict()) == protocol
    assert "NO_TARGET_SELECTED_AS_WINNER" in protocol.limitations


def test_target_label_exposes_interval_for_purging_and_embargo() -> None:
    protocol = engineering_multi_horizon_protocol()
    target = next(item for item in protocol.targets if item.checkpoint is OutcomeCheckpoint.TIME_1030)
    label = TargetOutcomeLabel.create(
        symbol="600000.SH",
        target=RuntimeArtifactReference("OUTCOME_TARGET", target.target_id, target.target_hash),
        label_interval_start=datetime(2026, 8, 10, 6, 55, tzinfo=UTC),
        label_interval_end=datetime(2026, 8, 11, 2, 30, tzinfo=UTC),
        decision_reference_price=Decimal("10"),
        checkpoint_price=Decimal("10.2"),
        mfe=Decimal("0.03"),
        mae=Decimal("-0.01"),
        barrier_passages=(("UP_1_PERCENT", datetime(2026, 8, 11, 2, 0, tzinfo=UTC)),),
        barrier_ordering=BarrierOrderingOutcome.UP_FIRST,
        market_conditions=(OutcomeMarketCondition.TRADING,),
        availability_status=OutcomeAvailabilityStatus.COMPLETE,
        outcome_available_at=datetime(2026, 8, 11, 2, 31, tzinfo=UTC),
        reason_codes=("TARGET_COMPLETE",),
    )

    assert label.checkpoint_return == Decimal("0.02")
    assert TargetOutcomeLabel.from_canonical_dict(label.to_canonical_dict()) == label


def test_target_outcome_writer_rejects_same_dataset_id_with_wrong_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = engineering_multi_horizon_protocol()
    target = protocol.targets[0]
    decision_time = datetime(2026, 8, 10, 6, 55, tzinfo=UTC)
    available_at = datetime(2026, 8, 11, 2, 31, tzinfo=UTC)
    decision = RuntimeArtifactReference(
        "SHADOW_DECISION", ArtifactId("dataset-hash-decision"), HASH
    )
    factual = RuntimeArtifactReference(
        "FACTUAL_OUTCOME_V1", ArtifactId("dataset-hash-factual"), HASH
    )
    source_dataset = RuntimeArtifactReference(
        "MARKET_DATA_DATASET",
        ArtifactId("dataset-same-id"),
        "sha256:" + "b" * 64,
    )
    label = TargetOutcomeLabel.create(
        symbol="600000.SH",
        target=RuntimeArtifactReference(
            "OUTCOME_TARGET", target.target_id, target.target_hash
        ),
        label_interval_start=decision_time,
        label_interval_end=available_at - timedelta(minutes=1),
        decision_reference_price=Decimal("10"),
        checkpoint_price=Decimal("10.1"),
        mfe=Decimal("0.02"),
        mae=Decimal("-0.01"),
        barrier_passages=(),
        market_conditions=(OutcomeMarketCondition.TRADING,),
        availability_status=OutcomeAvailabilityStatus.COMPLETE,
        outcome_available_at=available_at,
        reason_codes=("TARGET_COMPLETE",),
    )
    outcome = TargetedShadowOutcome.create(
        shadow_decision=decision,
        factual_outcome_v1=factual,
        source_dataset=source_dataset,
        target_protocol_id=protocol.protocol_id,
        target_protocol_hash=protocol.protocol_hash,
        next_session_date=date(2026, 8, 11),
        labels=(label,),
        availability_status=OutcomeAvailabilityStatus.COMPLETE,
        outcome_available_at=available_at,
        created_at=available_at,
        reason_codes=("TARGETED_OUTCOME_COMPLETE",),
        limitations=(
            "ENGINEERING_RECORDED_ONLY",
            "FACTUAL_LABELS_ONLY",
            "NOT_ALPHA_VALIDATION",
            "NOT_PROSPECTIVE_EVIDENCE",
        ),
    )

    class Result:
        def __init__(self, row: tuple[object, ...]) -> None:
            self._row = row

        def fetchone(self) -> tuple[object, ...]:
            return self._row

    class Connection:
        def execute(self, query: str, _parameters: object) -> Result:
            if "FROM shadow_research_decision" in query:
                return Result((decision.content_hash,))
            if "FROM prospective_outcome_settlement" in query:
                return Result(
                    (
                        factual.content_hash,
                        str(decision.artifact_id),
                        str(source_dataset.artifact_id),
                        "sha256:" + "c" * 64,
                    )
                )
            if "FROM outcome_target_protocol" in query:
                return Result((protocol.protocol_hash,))
            raise AssertionError("writer reached mutation after Dataset hash mismatch")

    class Factory:
        def run_transaction(self, operation: Any) -> Any:
            return operation(Connection())

    repository = object.__new__(PostgresTargetOutcomeRepository)
    repository._factory = cast(Any, Factory())
    repository._clock = lambda: available_at
    monkeypatch.setattr(repository, "get_protocol", lambda _protocol_id: protocol)
    monkeypatch.setattr(repository, "register_protocol", lambda item: item)

    with pytest.raises(TargetOutcomeConflict, match="V1 lineage mismatch"):
        repository.settle(outcome)


def test_missing_checkpoint_is_unavailable_not_zero() -> None:
    protocol = engineering_multi_horizon_protocol()
    target = protocol.targets[0]
    label = TargetOutcomeLabel.create(
        symbol="600000.SH",
        target=RuntimeArtifactReference("OUTCOME_TARGET", target.target_id, target.target_hash),
        label_interval_start=datetime(2026, 8, 10, 6, 55, tzinfo=UTC),
        label_interval_end=datetime(2026, 8, 11, 1, 30, tzinfo=UTC),
        decision_reference_price=Decimal("10"),
        checkpoint_price=None,
        mfe=None,
        mae=None,
        barrier_passages=(),
        barrier_ordering=BarrierOrderingOutcome.NO_TOUCH,
        market_conditions=(OutcomeMarketCondition.MISSING_QUOTE,),
        availability_status=OutcomeAvailabilityStatus.UNAVAILABLE,
        outcome_available_at=datetime(2026, 8, 11, 2, 31, tzinfo=UTC),
        reason_codes=("TARGET_CHECKPOINT_UNAVAILABLE",),
    )

    assert label.checkpoint_return is None
    payload = label.to_canonical_dict()
    payload["checkpoint_return"] = "0"
    with pytest.raises(ValueError, match="return does not match"):
        TargetOutcomeLabel.from_canonical_dict(payload)


def test_target_reader_rejects_boolean_coercion_and_future_availability() -> None:
    protocol = engineering_multi_horizon_protocol()
    payload = protocol.to_canonical_dict()
    payload["targets"][0]["canonical_horizon"]["entry_window"]["start"][
        "frozen_decision_time"
    ] = "false"
    with pytest.raises(ValueError, match="boolean"):
        OutcomeTargetProtocol.from_canonical_dict(payload)

    target = protocol.targets[0]
    with pytest.raises(ValueError, match="available before interval end"):
        TargetOutcomeLabel.create(
            symbol="600000.SH",
            target=RuntimeArtifactReference(
                "OUTCOME_TARGET",
                target.target_id,
                target.target_hash,
            ),
            label_interval_start=datetime(2026, 8, 10, 6, 55, tzinfo=UTC),
            label_interval_end=datetime(2026, 8, 11, 1, 30, tzinfo=UTC),
            decision_reference_price=Decimal("10"),
            checkpoint_price=Decimal("10.1"),
            mfe=Decimal("0.01"),
            mae=Decimal("0"),
            barrier_passages=(),
            barrier_ordering=BarrierOrderingOutcome.NO_TOUCH,
            market_conditions=(OutcomeMarketCondition.TRADING,),
            availability_status=OutcomeAvailabilityStatus.COMPLETE,
            outcome_available_at=datetime(2026, 8, 11, 1, 29, tzinfo=UTC),
            reason_codes=("TARGET_COMPLETE",),
        )


def test_target_builder_excludes_bars_after_the_label_interval() -> None:
    protocol = engineering_multi_horizon_protocol()
    target = next(
        item
        for item in protocol.targets
        if item.checkpoint is OutcomeCheckpoint.TIME_1000
    )
    observation = SimpleNamespace(
        symbol="600000.SH",
        decision_reference_price=Decimal("10"),
        next_open=Decimal("10"),
        market_conditions=(OutcomeMarketCondition.TRADING,),
    )
    label = _build_label(
        decision=cast(
            Any,
            SimpleNamespace(
                decision_frozen_at=datetime(2026, 8, 10, 6, 55, tzinfo=UTC)
            ),
        ),
        target=target,
        protocol=protocol,
        symbol_observation=observation,
        bars=(
            _minute_bar(
                start=datetime(2026, 8, 11, 1, 59, tzinfo=UTC),
                close=Decimal("10.05"),
                high=Decimal("10.1"),
            ),
            _minute_bar(
                start=datetime(2026, 8, 11, 2, 0, tzinfo=UTC),
                close=Decimal("19"),
                high=Decimal("20"),
            ),
        ),
        fallback_available_at=datetime(2026, 8, 11, 2, 1, tzinfo=UTC),
        next_session_date=date(2026, 8, 11),
    )

    assert label.checkpoint_price == Decimal("10.05")
    assert label.mfe == Decimal("0.01")
    assert dict(label.barrier_passages)["UP_2_PERCENT"] is None


def test_target_builder_fails_closed_on_corporate_action_adjustment() -> None:
    protocol = engineering_multi_horizon_protocol()
    target = next(
        item
        for item in protocol.targets
        if item.checkpoint is OutcomeCheckpoint.TIME_1000
    )
    label = _build_label(
        decision=cast(
            Any,
            SimpleNamespace(
                decision_frozen_at=datetime(2026, 8, 10, 6, 55, tzinfo=UTC)
            ),
        ),
        target=target,
        protocol=protocol,
        symbol_observation=SimpleNamespace(
            symbol="600000.SH",
            decision_reference_price=Decimal("10"),
            next_open=Decimal("10"),
            market_conditions=(OutcomeMarketCondition.TRADING,),
        ),
        bars=(
            _minute_bar(
                start=datetime(2026, 8, 11, 1, 59, tzinfo=UTC),
                close=Decimal("10.05"),
                high=Decimal("10.1"),
                adjustment_mode=AdjustmentMode.PIT_ADJUSTED,
            ),
        ),
        fallback_available_at=datetime(2026, 8, 11, 2, 0, tzinfo=UTC),
        next_session_date=date(2026, 8, 11),
    )

    assert label.checkpoint_price is None
    assert label.availability_status is OutcomeAvailabilityStatus.PARTIAL
    assert OutcomeMarketCondition.CORPORATE_ACTION in label.market_conditions
    assert "CORPORATE_ACTION_POLICY_FAILED_CLOSED" in label.reason_codes


def test_same_five_minute_barrier_touches_are_not_ordered() -> None:
    protocol = engineering_multi_horizon_protocol()
    base = next(
        item
        for item in protocol.targets
        if item.checkpoint is OutcomeCheckpoint.TIME_1000
    )
    target = TargetDefinition.create(
        target_version="five-minute-ordering-v2",
        canonical_horizon=canonical_target_horizon(
            checkpoint=OutcomeCheckpoint.TIME_1000,
            barriers=base.barriers,
            compute_mfe_mae=True,
        ),
        required_market_data=("MINUTE_5",),
    )
    five_minute_protocol = OutcomeTargetProtocol.create(
        protocol_version="five-minute-ordering-v2",
        timezone_name="Asia/Shanghai",
        session_offset=1,
        targets=(target,),
        limitations=("RESEARCH_LABELS_ONLY",),
    )

    label = _build_label(
        decision=cast(
            Any,
            SimpleNamespace(
                decision_frozen_at=datetime(2026, 8, 10, 6, 55, tzinfo=UTC)
            ),
        ),
        target=target,
        protocol=five_minute_protocol,
        symbol_observation=SimpleNamespace(
            symbol="600000.SH",
            decision_reference_price=Decimal("10"),
            next_open=Decimal("10"),
            market_conditions=(OutcomeMarketCondition.TRADING,),
        ),
        bars=(
            _minute_bar(
                start=datetime(2026, 8, 11, 1, 55, tzinfo=UTC),
                close=Decimal("10"),
                high=Decimal("10.2"),
                low=Decimal("9.85"),
                timeframe=Timeframe.MINUTE_5,
            ),
        ),
        fallback_available_at=datetime(2026, 8, 11, 2, 0, tzinfo=UTC),
        next_session_date=date(2026, 8, 11),
    )

    assert label.barrier_ordering is BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE
    assert label.availability_status is OutcomeAvailabilityStatus.PARTIAL
    assert "BARRIER_ORDERING_NOT_OBSERVABLE" in label.reason_codes
