from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from market_regime_alpha.infrastructure.postgres.repositories.research_evaluations import (
    PostgresEvaluationRepository,
)
from market_regime_alpha.research_qualification.domain.evaluation import (
    ProtocolMetricDefinition,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    AcceptanceOperator,
    CandidateDisposition,
    EvaluationReducer,
    EvaluationSourceKind,
    EvaluationSourceMeasure,
    EvaluationSliceKind,
    ExploratoryBacktestArmKind,
    MetricDirection,
    SourceMetricValueType,
)


def _metric(
    source_kind: EvaluationSourceKind,
    source_measure: EvaluationSourceMeasure,
    reducer: EvaluationReducer | None = None,
) -> ProtocolMetricDefinition:
    boolean_source = source_kind in {
        EvaluationSourceKind.CANDIDATE_DISPOSITION,
        EvaluationSourceKind.SIGNAL_STATUS,
        EvaluationSourceKind.RISK_DECISION,
    } or source_measure is EvaluationSourceMeasure.CANDIDATE_HIT
    return ProtocolMetricDefinition(
        evaluation_protocol_metric_id=uuid4(),
        metric_code="pilot-metric",
        ordinal=1,
        source_target_metric_definition_id=uuid4(),
        source_metric_code="simple-return",
        source_value_type=(
            SourceMetricValueType.BOOLEAN
            if boolean_source
            else SourceMetricValueType.DECIMAL
        ),
        source_kind=source_kind,
        source_measure=source_measure,
        reducer=reducer or (
            EvaluationReducer.TRUE_RATE
            if boolean_source
            else EvaluationReducer.MEAN_DECIMAL
        ),
        slice_kind=EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM,
        candidate_disposition=None,
        backtest_arm_kind=ExploratoryBacktestArmKind.MODEL_CHALLENGER,
        direction=MetricDirection.DESCRIPTIVE,
        minimum_estimable_count=1,
        acceptance_operator=AcceptanceOperator.NONE,
        acceptance_threshold=None,
    )


def _source(
    *,
    decision_time: datetime,
    outcome: Decimal | None = Decimal("0.10"),
    forecast: Decimal | None = Decimal("0.05"),
    forecast_status: str = "AVAILABLE",
    signal_status: str = "PRESENT",
    weight: Decimal = Decimal("0.40"),
    risk_status: str = "AUTHORIZED",
    instrument_id: UUID | None = None,
    arm_id: UUID | None = None,
) -> tuple[object, ...]:
    identities = [uuid4() for _ in range(21)]
    return (
        identities[0],  # EvaluationObservation
        identities[1],  # PartitionMember
        identities[2],  # OutcomeRevision
        CandidateDisposition.SELECTED.value,
        identities[3],  # OutcomeMetric
        "COMPLETE" if outcome is not None else "UNAVAILABLE",
        outcome,
        None,
        identities[4],  # Commitment
        identities[5],  # DecisionRun
        identities[6],  # Candidate
        instrument_id or identities[7],
        decision_time,
        identities[8],  # BacktestRun
        arm_id or identities[9],  # BacktestArm
        identities[10],  # Fold
        identities[11],  # FoldSession
        ExploratoryBacktestArmKind.MODEL_CHALLENGER.value,
        identities[12],  # StrategyVersion
        identities[13],  # PortfolioPolicy
        identities[14],  # RiskPolicy
        3,
        "a" * 64,
        Decimal("16"),
        identities[15],  # Signal
        signal_status,
        identities[16],  # Forecast
        forecast_status,
        identities[17],  # ForecastEstimate
        forecast,
        identities[18],  # Proposal
        identities[19],  # Line
        "INCLUDED",
        weight,
        identities[20],  # RiskDecision
        risk_status,
        "DECIMAL",  # Outcome value type
        Decimal("0.75"),  # Candidate composite score
        1,  # Candidate competition rank
        uuid4(),  # CandidateSet
    )


def _repository() -> PostgresEvaluationRepository:
    return PostgresEvaluationRepository(None, id_factory=uuid4)  # type: ignore[arg-type]


def test_forecast_source_retains_exact_prediction_and_outcome_pair() -> None:
    metric = _metric(
        EvaluationSourceKind.FORECAST_OUTCOME_PAIR,
        EvaluationSourceMeasure.FORECAST_POINT_VS_TARGET,
        EvaluationReducer.SPEARMAN_RANK_CORRELATION,
    )

    resolved = _repository()._resolve_metric_inputs(  # noqa: SLF001
        metric,
        [_source(decision_time=datetime(2026, 1, 5, 2, 30, tzinfo=UTC))],
    )

    assert resolved[0].input.decimal_value == Decimal("0.05")
    assert resolved[0].input.secondary_decimal_value == Decimal("0.10")
    assert resolved[0].input.source_value_status == "COMPLETE"


def test_candidate_source_retains_score_and_outcome_before_context_gate() -> None:
    metric = _metric(
        EvaluationSourceKind.CANDIDATE_OUTCOME_PAIR,
        EvaluationSourceMeasure.CANDIDATE_SCORE_VS_TARGET,
        EvaluationReducer.SPEARMAN_RANK_CORRELATION,
    )

    resolved = _repository()._resolve_metric_inputs(  # noqa: SLF001
        metric,
        [_source(decision_time=datetime(2026, 1, 5, 2, 30, tzinfo=UTC))],
    )

    assert resolved[0].input.decimal_value == Decimal("0.75")
    assert resolved[0].input.secondary_decimal_value == Decimal("0.10")
    assert resolved[0].input.source_value_status == "COMPLETE"


def test_candidate_top_k_metric_retains_unselected_member_as_unavailable() -> None:
    metric = _metric(
        EvaluationSourceKind.CANDIDATE_OUTCOME_PAIR,
        EvaluationSourceMeasure.CANDIDATE_TOP_K_RETURN,
    )
    row = list(_source(decision_time=datetime(2026, 1, 5, 2, 30, tzinfo=UTC)))
    row[3] = CandidateDisposition.RANKED_NOT_SELECTED.value

    resolved = _repository()._resolve_metric_inputs(  # noqa: SLF001
        metric,
        [tuple(row)],
    )

    assert resolved[0].input.decimal_value is None
    assert resolved[0].input.source_value_status == "UNAVAILABLE"


def test_portfolio_net_return_uses_risk_gate_turnover_and_assumed_cost() -> None:
    metric = _metric(
        EvaluationSourceKind.PORTFOLIO_OUTCOME,
        EvaluationSourceMeasure.NET_PORTFOLIO_RETURN_ASSUMED_COST,
    )
    instrument_id = uuid4()
    arm_id = uuid4()
    start = datetime(2026, 1, 5, 2, 30, tzinfo=UTC)

    resolved = _repository()._resolve_metric_inputs(  # noqa: SLF001
        metric,
        [
            _source(
                decision_time=start,
                weight=Decimal("0.40"),
                instrument_id=instrument_id,
                arm_id=arm_id,
            ),
            _source(
                decision_time=start + timedelta(days=1),
                weight=Decimal("0.10"),
                instrument_id=instrument_id,
                arm_id=arm_id,
            ),
        ],
    )

    assert [item.turnover for item in resolved] == [Decimal("0.40"), Decimal("0.30")]
    assert resolved[0].gross_return == Decimal("0.040")
    assert resolved[0].net_return == Decimal("0.03936")
    assert resolved[1].net_return == Decimal("0.00952")


def test_risk_unknown_is_retained_as_not_estimable_source() -> None:
    metric = _metric(
        EvaluationSourceKind.RISK_DECISION,
        EvaluationSourceMeasure.RISK_REJECTED,
    )

    resolved = _repository()._resolve_metric_inputs(  # noqa: SLF001
        metric,
        [
            _source(
                decision_time=datetime(2026, 1, 5, 2, 30, tzinfo=UTC),
                risk_status="UNKNOWN",
            )
        ],
    )

    assert resolved[0].input.decimal_value is None
    assert resolved[0].input.boolean_value is None
    assert resolved[0].input.source_value_status == "UNAVAILABLE"


def test_risk_rejection_is_a_boolean_true_rate_input() -> None:
    metric = _metric(
        EvaluationSourceKind.RISK_DECISION,
        EvaluationSourceMeasure.RISK_REJECTED,
    )

    resolved = _repository()._resolve_metric_inputs(  # noqa: SLF001
        metric,
        [
            _source(
                decision_time=datetime(2026, 1, 5, 2, 30, tzinfo=UTC),
                risk_status="REJECTED",
            )
        ],
    )

    assert resolved[0].input.decimal_value is None
    assert resolved[0].input.boolean_value is True
    assert resolved[0].input.source_value_status == "COMPLETE"
