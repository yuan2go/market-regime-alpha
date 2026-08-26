from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalListingStatus,
    HistoricalNormalizedBar,
    HistoricalTradingStatus,
)
from market_regime_alpha.application.historical_corpus.correctness_failures import (
    AlphaCorrectnessFailureDetail,
    AlphaCorrectnessFailureIndex,
    FailureSourceBinding,
)
from market_regime_alpha.application.historical_corpus.correctness_failure_indexer import (
    HistoricalCorrectnessFailureIndexer,
)
from market_regime_alpha.application.historical_corpus.historical_target_semantics import (
    evaluate_historical_target_semantics,
)
from market_regime_alpha.application.historical_corpus.alpha_correctness import (
    AlphaCorrectnessStatus,
    PhysicalSourceVerification,
    reproduce_t_plus_one_1030_target_v2,
)
from market_regime_alpha.application.research_evaluation.target_semantics import (
    BarrierOrderingOutcome,
    TargetSemanticSpecification,
    TargetSemanticStatus,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetOutcomeLabel,
    build_target_outcome_label_from_semantic_result,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeCheckpoint,
    exploratory_five_minute_multi_horizon_protocol,
    exploratory_five_minute_multi_horizon_protocol_v2,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data.contracts import Timeframe


SHANGHAI = ZoneInfo("Asia/Shanghai")
RETRIEVED_AT = datetime(2026, 8, 25, tzinfo=UTC)
RAW_REQUEST = ValidationArtifactReference(
    "RAW_PROVIDER_REQUEST",
    ArtifactId("raw-request-target-semantics"),
    canonical_hash({"request": "target-semantics"}),
)


def _bar(
    market_date: date,
    start_time: time,
    *,
    row: int,
    close: str | None = "10",
    timeframe: Timeframe = Timeframe.MINUTE_5,
    trading_status: HistoricalTradingStatus = HistoricalTradingStatus.TRADING,
) -> HistoricalNormalizedBar:
    event_start = (
        datetime.combine(market_date, start_time, UTC)
        if timeframe is Timeframe.DAILY
        else datetime.combine(market_date, start_time, SHANGHAI).astimezone(UTC)
    )
    duration = timeframe.duration or timedelta(hours=15)
    price = None if close is None else Decimal(close)
    return HistoricalNormalizedBar.create(
        symbol="600000.SH",
        timeframe=timeframe,
        market_date=market_date,
        event_start=event_start,
        event_end=event_start + duration,
        retrieved_at=RETRIEVED_AT,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal("0") if price is None else Decimal("100"),
        amount=None if price is None else price * Decimal("100"),
        adjustment_basis="BAOSTOCK_ADJUSTFLAG_3_RAW",
        trading_status=trading_status,
        st_status=None,
        listing_status=HistoricalListingStatus.UNKNOWN,
        raw_request_reference=RAW_REQUEST,
        raw_row_number=row,
        missing_fields=("close", "high", "low", "open") if price is None else (),
        limitations=("PIT_INCOMPLETE",),
    )


def _target_bars(target_session: date, *, start_row: int = 100) -> tuple[HistoricalNormalizedBar, ...]:
    return tuple(
        _bar(
            target_session,
            (datetime.combine(target_session, time(9, 30)) + timedelta(minutes=5 * index)).time(),
            row=start_row + index,
            close=str(Decimal("10") + Decimal(index) / Decimal("100")),
        )
        for index in range(12)
    )


def _protocol_target():
    protocol = exploratory_five_minute_multi_horizon_protocol_v2()
    target = next(
        item
        for item in protocol.targets
        if item.checkpoint is OutcomeCheckpoint.TIME_1030
    )
    assert protocol.target_semantic_specification is not None
    return protocol, target


def test_target_semantic_specification_v1_is_content_addressed_and_round_trips() -> None:
    protocol, _ = _protocol_target()
    specification = protocol.target_semantic_specification
    assert specification is not None

    assert specification.semantic_revision == (
        "wp-alpha-correctness-02-target-semantics/v1"
    )
    assert specification.schema_version == "target-semantic-specification/v1"
    assert TargetSemanticSpecification.from_canonical_dict(
        specification.to_canonical_dict()
    ) == specification
    assert protocol.protocol_version == "phase-e-free-5m-exploratory-v2"


def test_protocol_v1_identity_remains_immutable() -> None:
    protocol = exploratory_five_minute_multi_horizon_protocol()

    assert protocol.protocol_hash == (
        "sha256:6718c60fc274d65b69d14eb954ebb71be71605835ae0460289b628085d522fd5"
    )
    assert protocol.schema_version == "outcome-target-protocol/v1"
    assert "schema_version" not in protocol.to_canonical_dict()


def test_missing_exact_decision_reference_preserves_complete_target_path() -> None:
    protocol, target = _protocol_target()
    specification = protocol.target_semantic_specification
    assert specification is not None
    decision_session = date(2025, 1, 6)
    target_session = date(2025, 1, 7)
    decision_time = datetime.combine(
        decision_session, time(14, 55), SHANGHAI
    ).astimezone(UTC)
    diagnostic_daily = _bar(
        date(2025, 1, 3),
        time(0),
        row=1,
        close="7.22",
        timeframe=Timeframe.DAILY,
        trading_status=HistoricalTradingStatus.SUSPENDED,
    )

    result = evaluate_historical_target_semantics(
        specification=specification,
        target=target,
        symbol="600000.SH",
        decision_time=decision_time,
        next_session_date=target_session,
        source_bars=(diagnostic_daily, *_target_bars(target_session)),
    )

    assert result.decision_reference_status is TargetSemanticStatus.UNAVAILABLE
    assert result.outcome_window_status is TargetSemanticStatus.COMPLETE
    assert result.checkpoint_observation_status is TargetSemanticStatus.COMPLETE
    assert result.checkpoint_return_status is TargetSemanticStatus.UNAVAILABLE
    assert result.mfe_status is TargetSemanticStatus.UNAVAILABLE
    assert result.mae_status is TargetSemanticStatus.UNAVAILABLE
    assert result.decision_reference_price is None
    assert result.checkpoint_price == Decimal("10.11")
    assert result.checkpoint_return is None
    assert result.mfe is None
    assert result.mae is None
    assert len(result.outcome_source_references) == 12
    assert result.diagnostic_source_references == (diagnostic_daily.reference,)
    assert "DECISION_EXACT_1455_BAR_MISSING" in result.reason_codes
    assert "DIAGNOSTIC_PREVIOUS_SESSION_DAILY_CLOSE_IGNORED" in result.reason_codes
    assert "OUTCOME_GRID_COMPLETE" in result.reason_codes


def test_unpriced_exact_placeholder_is_unavailable_and_never_a_fallback() -> None:
    protocol, target = _protocol_target()
    specification = protocol.target_semantic_specification
    assert specification is not None
    decision_session = date(2025, 2, 7)
    target_session = date(2025, 2, 10)
    decision_time = datetime.combine(
        decision_session, time(14, 55), SHANGHAI
    ).astimezone(UTC)
    placeholder = _bar(
        decision_session,
        time(14, 50),
        row=2,
        close=None,
        trading_status=HistoricalTradingStatus.SUSPENDED,
    )
    previous_daily = _bar(
        date(2025, 2, 6),
        time(0),
        row=1,
        close="17.78",
        timeframe=Timeframe.DAILY,
        trading_status=HistoricalTradingStatus.SUSPENDED,
    )

    result = evaluate_historical_target_semantics(
        specification=specification,
        target=target,
        symbol="600000.SH",
        decision_time=decision_time,
        next_session_date=target_session,
        source_bars=(previous_daily, placeholder, *_target_bars(target_session)),
    )

    assert result.decision_reference_status is TargetSemanticStatus.UNAVAILABLE
    assert result.decision_source_references == (placeholder.reference,)
    assert result.diagnostic_source_references == (previous_daily.reference,)
    assert "DECISION_EXACT_1455_BAR_UNPRICED_PLACEHOLDER" in result.reason_codes
    assert "DECISION_EXACT_1455_BAR_SUSPENDED" in result.reason_codes
    assert result.checkpoint_return is None


def test_complete_reference_and_grid_produce_reference_dependent_metrics() -> None:
    protocol, target = _protocol_target()
    specification = protocol.target_semantic_specification
    assert specification is not None
    decision_session = date(2025, 1, 6)
    target_session = date(2025, 1, 7)
    decision_time = datetime.combine(
        decision_session, time(14, 55), SHANGHAI
    ).astimezone(UTC)
    decision_bar = _bar(
        decision_session,
        time(14, 50),
        row=1,
        close="10",
    )

    result = evaluate_historical_target_semantics(
        specification=specification,
        target=target,
        symbol="600000.SH",
        decision_time=decision_time,
        next_session_date=target_session,
        source_bars=(decision_bar, *_target_bars(target_session)),
    )

    assert result.decision_reference_status is TargetSemanticStatus.COMPLETE
    assert result.outcome_window_status is TargetSemanticStatus.COMPLETE
    assert result.checkpoint_return_status is TargetSemanticStatus.COMPLETE
    assert result.mfe_status is TargetSemanticStatus.COMPLETE
    assert result.mae_status is TargetSemanticStatus.COMPLETE
    assert result.decision_reference_price == Decimal("10")
    assert result.checkpoint_return == Decimal("0.011")
    assert result.mfe == Decimal("0.011")
    assert result.mae == Decimal("0")

    with pytest.raises(ValueError, match="barrier ambiguity/status mismatch"):
        replace(
            result,
            barrier_ordering=BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE,
        )
    with pytest.raises(ValueError, match="outcome coverage is invalid"):
        replace(result, outcome_window_start=decision_time)


def test_open_target_window_ends_when_its_source_bar_becomes_observable() -> None:
    protocol, _ = _protocol_target()
    specification = protocol.target_semantic_specification
    assert specification is not None
    target = next(
        item
        for item in protocol.targets
        if item.checkpoint is OutcomeCheckpoint.OPEN
    )
    decision_session = date(2025, 1, 6)
    target_session = date(2025, 1, 7)
    decision_time = datetime.combine(
        decision_session, time(14, 55), SHANGHAI
    ).astimezone(UTC)
    decision_bar = _bar(decision_session, time(14, 50), row=1, close="10")
    opening_bar = _bar(target_session, time(9, 30), row=2, close="10.2")

    result = evaluate_historical_target_semantics(
        specification=specification,
        target=target,
        symbol="600000.SH",
        decision_time=decision_time,
        next_session_date=target_session,
        source_bars=(decision_bar, opening_bar),
    )

    assert result.outcome_window_start == datetime.combine(
        target_session, time(9, 30), SHANGHAI
    ).astimezone(UTC)
    assert result.outcome_window_end == datetime.combine(
        target_session, time(9, 35), SHANGHAI
    ).astimezone(UTC)
    assert result.barrier_passages == (
        ("DOWN_1_PERCENT", None),
        ("UP_1_PERCENT", result.outcome_window_end),
        ("UP_2_PERCENT", result.outcome_window_end),
    )
    assert result.barrier_status is TargetSemanticStatus.COMPLETE
    assert result.barrier_ordering is BarrierOrderingOutcome.UP_FIRST


def test_partial_path_can_retain_exact_checkpoint_but_not_path_metrics() -> None:
    protocol, target = _protocol_target()
    specification = protocol.target_semantic_specification
    assert specification is not None
    decision_session = date(2025, 1, 6)
    target_session = date(2025, 1, 7)
    decision_time = datetime.combine(
        decision_session, time(14, 55), SHANGHAI
    ).astimezone(UTC)
    decision_bar = _bar(decision_session, time(14, 50), row=1)
    target_bars = _target_bars(target_session)

    result = evaluate_historical_target_semantics(
        specification=specification,
        target=target,
        symbol="600000.SH",
        decision_time=decision_time,
        next_session_date=target_session,
        source_bars=(decision_bar, *target_bars[1:]),
    )

    assert result.outcome_window_status is TargetSemanticStatus.PARTIAL
    assert result.checkpoint_observation_status is TargetSemanticStatus.COMPLETE
    assert result.checkpoint_return_status is TargetSemanticStatus.COMPLETE
    assert result.mfe_status is TargetSemanticStatus.UNAVAILABLE
    assert result.mae_status is TargetSemanticStatus.UNAVAILABLE
    assert result.checkpoint_return == Decimal("0.011")
    assert result.mfe is None
    assert result.mae is None
    assert "OUTCOME_GRID_PARTIAL" in result.reason_codes


def test_target_label_v3_round_trip_retains_unavailable_reference_and_path() -> None:
    protocol, target = _protocol_target()
    specification = protocol.target_semantic_specification
    assert specification is not None
    decision_session = date(2025, 1, 6)
    target_session = date(2025, 1, 7)
    decision_time = datetime.combine(
        decision_session, time(14, 55), SHANGHAI
    ).astimezone(UTC)
    result = evaluate_historical_target_semantics(
        specification=specification,
        target=target,
        symbol="600000.SH",
        decision_time=decision_time,
        next_session_date=target_session,
        source_bars=_target_bars(target_session),
    )

    label = build_target_outcome_label_from_semantic_result(
        target=target,
        semantic_result=result,
        outcome_available_at=RETRIEVED_AT,
    )

    assert label.schema_version == "target-outcome-label/v3"
    assert label.decision_reference_price is None
    assert label.checkpoint_price == Decimal("10.11")
    assert label.checkpoint_return is None
    assert label.semantic_result == result
    assert TargetOutcomeLabel.from_canonical_dict(label.to_canonical_dict()) == label

    checksum = canonical_hash({"physical": "target-semantics"})
    checksums = (("normalized.parquet", checksum),)
    normalized_reference = ValidationArtifactReference(
        "NORMALIZED_DATASET",
        ArtifactId("normalized-target-semantics"),
        canonical_hash({"normalized": "target-semantics"}),
    )
    physical_hash = canonical_hash({"physical-package": "target-semantics"})
    physical = PhysicalSourceVerification(
        normalized_owner_reference=normalized_reference,
        physical_hash=physical_hash,
        checksums=checksums,
        checksums_hash=canonical_hash(
            {"checksums": [list(item) for item in checksums]}
        ),
        normalized_bar_count=12,
        normalized_bar_manifest_hash=canonical_hash(
            {
                "normalized_owner_reference": normalized_reference.to_canonical_dict(),
                "physical_hash": physical_hash,
                "normalized_bar_count": 12,
            }
        ),
    )
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("target-semantics-calendar"),
        market="A_SHARE",
        calendar_version="target-semantics-calendar/v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            TradingSession(
                decision_session,
                datetime.combine(decision_session, time(15), SHANGHAI),
            ),
            TradingSession(
                target_session,
                datetime.combine(target_session, time(15), SHANGHAI),
            ),
        ),
    )
    reproduced = reproduce_t_plus_one_1030_target_v2(
        label=label,
        protocol=protocol,
        trading_calendar=calendar,
        source_bars=_target_bars(target_session),
        physical_verification=physical,
    )

    assert reproduced.status is AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED
    assert reproduced.discrepancies == ()
    assert reproduced.semantic_result == reproduced.persisted_semantic_result


def test_typed_failure_detail_and_index_are_content_addressed() -> None:
    protocol, target = _protocol_target()
    specification = protocol.target_semantic_specification
    assert specification is not None
    decision_session = date(2025, 1, 6)
    target_session = date(2025, 1, 7)
    decision_time = datetime.combine(
        decision_session, time(14, 55), SHANGHAI
    ).astimezone(UTC)
    target_bars = _target_bars(target_session)
    semantic_result = evaluate_historical_target_semantics(
        specification=specification,
        target=target,
        symbol="600000.SH",
        decision_time=decision_time,
        next_session_date=target_session,
        source_bars=target_bars,
    )
    label_reference = ValidationArtifactReference(
        "TARGET_OUTCOME_LABEL",
        ArtifactId("predecessor-target-label"),
        canonical_hash({"label": "predecessor"}),
    )
    component_reference = ValidationArtifactReference(
        "HISTORICAL_SESSION_COMPONENT",
        ArtifactId("predecessor-outcome-component"),
        canonical_hash({"component": "predecessor"}),
    )
    detail = AlphaCorrectnessFailureDetail.create(
        decision_session=decision_session,
        decision_time=decision_time,
        target_session=target_session,
        target_window_end=semantic_result.outcome_window_end,
        symbol="600000.SH",
        classification="PREDECESSOR_FALSE_FAILURE",
        discrepancy_code="PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE",
        predecessor_label_reference=label_reference,
        predecessor_component_reference=component_reference,
        predecessor_availability_status="AVAILABLE",
        predecessor_decision_reference_price=Decimal("7.22"),
        predecessor_checkpoint_price=Decimal("10.11"),
        predecessor_checkpoint_return=Decimal("0.400277008310249307"),
        predecessor_mfe=Decimal("0.400277008310249307"),
        predecessor_mae=Decimal("0.385041551246537396"),
        materializer_result=semantic_result,
        checker_result=semantic_result,
        source_bindings=(
            FailureSourceBinding("OUTCOME_BAR", target_bars[0].reference),
        ),
        normalization_revision="baostock-historical-normalization/v1",
        semantic_revision=specification.semantic_revision,
        analysis_code_sha="a" * 40,
    )
    index = AlphaCorrectnessFailureIndex.create(
        source_run_reference=ValidationArtifactReference(
            "HISTORICAL_RESEARCH_RUN",
            ArtifactId("predecessor-run"),
            canonical_hash({"run": "predecessor"}),
        ),
        source_evidence_reference=ValidationArtifactReference(
            "HISTORICAL_ALPHA_CORRECTNESS_EVIDENCE",
            ArtifactId("predecessor-correctness-evidence"),
            canonical_hash({"evidence": "predecessor"}),
        ),
        experiment_reference=ValidationArtifactReference(
            "RESEARCH_EXPERIMENT_DEFINITION",
            ArtifactId("predecessor-experiment"),
            canonical_hash({"experiment": "predecessor"}),
        ),
        target_protocol_reference=ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL",
            protocol.protocol_id,
            protocol.protocol_hash,
        ),
        calendar_reference=ValidationArtifactReference(
            "TRADING_CALENDAR",
            ArtifactId("predecessor-calendar"),
            canonical_hash({"calendar": "predecessor"}),
        ),
        raw_owner_reference=ValidationArtifactReference(
            "RAW_PROVIDER_ARCHIVE",
            ArtifactId("predecessor-raw-owner"),
            canonical_hash({"raw": "predecessor"}),
        ),
        normalized_owner_reference=ValidationArtifactReference(
            "NORMALIZED_DATASET",
            ArtifactId("predecessor-normalized-owner"),
            canonical_hash({"normalized": "predecessor"}),
        ),
        normalization_revision="baostock-historical-normalization/v1",
        analysis_code_sha="a" * 40,
        semantic_revision=specification.semantic_revision,
        details=(detail,),
        created_at=RETRIEVED_AT,
    )

    assert AlphaCorrectnessFailureDetail.from_canonical_dict(
        detail.to_canonical_dict()
    ) == detail
    assert AlphaCorrectnessFailureIndex.from_canonical_dict(
        index.to_canonical_dict()
    ) == index
    assert index.details == (detail,)

    class ExistingRepository:
        def get_for_source(self, **values):
            assert values == {
                "run_id": index.source_run_reference.artifact_id,
                "evidence_id": index.source_evidence_reference.artifact_id,
                "semantic_revision": specification.semantic_revision,
            }
            return index

        def put(self, _value):
            raise AssertionError("idempotent reload must not write")

    indexer = HistoricalCorrectnessFailureIndexer(
        journal=object(),  # type: ignore[arg-type]
        components=object(),  # type: ignore[arg-type]
        corpus=object(),  # type: ignore[arg-type]
        evidence=object(),  # type: ignore[arg-type]
        historical_facts=object(),  # type: ignore[arg-type]
        failures=ExistingRepository(),  # type: ignore[arg-type]
    )
    calendar = SimpleNamespace(
        artifact_id=index.calendar_reference.artifact_id,
        content_hash=index.calendar_reference.content_hash,
    )
    assert indexer.build_and_persist(
        predecessor_run_id=index.source_run_reference.artifact_id,
        predecessor_evidence_id=index.source_evidence_reference.artifact_id,
        corrected_target_protocol=protocol,
        trading_calendar=calendar,  # type: ignore[arg-type]
        analysis_code_sha=index.analysis_code_sha,
        created_at=RETRIEVED_AT + timedelta(days=1),
    ) == index
    with pytest.raises(ValueError, match="conflicts with request"):
        indexer.build_and_persist(
            predecessor_run_id=index.source_run_reference.artifact_id,
            predecessor_evidence_id=index.source_evidence_reference.artifact_id,
            corrected_target_protocol=protocol,
            trading_calendar=calendar,  # type: ignore[arg-type]
            analysis_code_sha="b" * 40,
            created_at=RETRIEVED_AT + timedelta(days=1),
        )
