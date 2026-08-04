from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

from market_regime_alpha.application.operational_research.composite_repository import (
    composite_operational_command_hash,
)
from market_regime_alpha.application.operational_research.sqlite_composite_repository import (
    SQLiteCompositeOperationalRepository,
)
from market_regime_alpha.application.research_layer.runner import (
    PlatformResearchRunner,
)
from market_regime_alpha.application.trading_lifecycle.operational_assessment_v2 import (
    OperationalPositionAssessmentServiceV2,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FillId,
    ManualTradeId,
    ModelId,
    OpportunityId,
    PortfolioDecisionId,
    RiskDecisionId,
    TargetId,
    ThesisId,
)
from market_regime_alpha.data import TradingSession, build_trading_calendar_artifact
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from market_regime_alpha.decision import (
    InvalidationCondition,
    InvalidationKind,
    OpportunityState,
    ThesisState,
    TradingOpportunity,
    TradingThesis,
)
from market_regime_alpha.decision.opportunity import (
    TRADING_OPPORTUNITY_SCHEMA,
    transition_opportunity,
)
from market_regime_alpha.decision.sqlite_repository import (
    SQLiteDecisionLifecycleRepository,
)
from market_regime_alpha.decision.thesis import (
    TRADING_THESIS_SCHEMA,
    transition_thesis,
)
from market_regime_alpha.evidence import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    FILL_SCHEMA,
    TRACEABLE_MANUAL_TRADE_SCHEMA,
    Fill,
    FillKind,
    ManualOrderState,
    ManualTradeRecord,
    TradeSide,
)
from market_regime_alpha.execution.position_book import PositionBook
from market_regime_alpha.execution.risk_reduction import (
    OperationalExitDirectiveV2,
    RiskReductionConfirmationCommand,
    RiskReductionConfirmationPolicy,
    OperatorAuthenticationRequirement,
)
from market_regime_alpha.application.trading_lifecycle.risk_reduction_lineage import (
    build_operational_exit_directive_v2,
)
from market_regime_alpha.application.trading_lifecycle.sqlite_risk_reduction import (
    SQLiteRiskReductionManualIntentRepository,
)
from market_regime_alpha.forecasting import (
    CalibrationStatus,
    PathForecast,
    PathForecastStatus,
)
from market_regime_alpha.portfolio.risk_routes import (
    ExecutionConstraintState,
    ReducingExecutionObservation,
    RiskChangeKind,
    RiskReducingExecutionGate,
    RiskReducingGateConfiguration,
)
from market_regime_alpha.portfolio.sqlite_risk_routes import (
    SQLiteRiskRouteRepository,
)
from market_regime_alpha.position.authority import (
    PositionProjector,
    SymbolTradingSessionStatus,
    SymbolTradingState,
)
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
)
from market_regime_alpha.position.thesis_health import (
    ThesisHealthInputBundle,
    ThesisHealthObservationBuilder,
    ThesisInvalidationRuleSet,
    TimeAfterRule,
    ThesisHealthRuleConfiguration,
    thesis_health_command_hash,
)
from market_regime_alpha.research.platform_v2.configs import (
    default_research_pipeline_config,
)
from market_regime_alpha.signals import (
    ConfirmationState,
    SignalFamily,
    SignalSnapshot,
    SignalState,
)
from tests.application.operational_research.test_h5_composite_integration import (
    _evidence,
    _model,
)
from market_regime_alpha.position.assessment import (
    POSITION_LIFECYCLE_CONFIG_SCHEMA,
    PositionLifecycleConfig,
)
from tests.daily_decision.conftest import DailyDecisionFixture
from tests.position.thesis_health_fixtures import health_configuration
from tests.research.platform_v2.test_composite_input_v2 import _v2_inputs


@dataclass(frozen=True)
class ConfirmationFixture:
    repository: SQLiteRiskReductionManualIntentRepository
    command: RiskReductionConfirmationCommand
    directive: OperationalExitDirectiveV2
    book: PositionBook
    decision_id: ArtifactId
    quantity: int


def build_confirmation_fixture(
    root: Path,
    daily_decision_fixture: DailyDecisionFixture,
    *,
    action: RiskChangeKind = RiskChangeKind.EXIT,
    reduce_target_zero: bool = False,
    invalidated_thesis: bool = False,
    h4_execution_state: ExecutionConstraintState = (
        ExecutionConstraintState.EXECUTABLE
    ),
) -> ConfirmationFixture:
    database = root / "lifecycle.sqlite3"
    repository = SQLiteRiskReductionManualIntentRepository(database)
    inputs, _, composite = _v2_inputs(root / "h6", daily_decision_fixture)
    research = PlatformResearchRunner().run(
        inputs=inputs,
        configuration=default_research_pipeline_config(),
        output_root=root / "research",
        code_revision="h4-5-integration",
    ).artifact
    candidate = next(
        item
        for item in research.candidate_set.records
        if item.primary_theme_id is not None
    )
    symbol = candidate.symbol
    created_at = research.envelope.created_at
    signal = _signal(
        research,
        symbol,
        weakening=action is RiskChangeKind.REDUCE,
    )
    path = _path(research, signal, symbol)
    initial_opportunity = TradingOpportunity(
        schema_version=TRADING_OPPORTUNITY_SCHEMA,
        opportunity_id=OpportunityId("opportunity-h4-5"),
        symbol=symbol,
        candidate_set=_evidence(research.candidate_set.envelope),
        signal_snapshot=_evidence(signal.envelope),
        path_forecast=_evidence(path.envelope),
        decision_time=research.envelope.decision_time,
        signal_model=_model(signal.envelope),
        forecast_model=_model(path.envelope),
        valid_until=created_at + timedelta(days=2),
        state=OpportunityState.OPEN,
        version=0,
        created_at=created_at,
        created_by="h4-5-test",
        creation_reason="operational H6 opportunity",
        updated_at=created_at,
        last_actor="h4-5-test",
        last_reason="operational H6 opportunity",
        reason_codes=("OPPORTUNITY_CREATED",),
    )
    confirmed_opportunity = transition_opportunity(
        initial_opportunity,
        to_state=OpportunityState.CONFIRMED_TO_THESIS,
        actor="h4-5-test",
        reason="approved for H4.5 Thesis",
        changed_at=created_at + timedelta(seconds=1),
    )
    assessed_at = created_at + timedelta(seconds=5)
    invalidation_at = (
        created_at + timedelta(seconds=3)
        if action is RiskChangeKind.EXIT
        else assessed_at + timedelta(days=1)
    )
    condition = InvalidationCondition(
        condition_id="h4-5-time-exit",
        kind=InvalidationKind.TIME,
        description="operational exit fixture",
        reason_code="H4_5_TIME_EXIT",
    )
    thesis = TradingThesis(
        schema_version=TRADING_THESIS_SCHEMA,
        thesis_id=ThesisId("thesis-h4-5"),
        opportunity_id=confirmed_opportunity.opportunity_id,
        source_opportunity_version=initial_opportunity.version,
        symbol=symbol,
        supporting_evidence=tuple(
            sorted(
                (
                    confirmed_opportunity.candidate_set,
                    confirmed_opportunity.signal_snapshot,
                    confirmed_opportunity.path_forecast,
                ),
                key=lambda item: str(item.artifact_id),
            )
        ),
        invalidation_conditions=(condition,),
        time_invalidation=invalidation_at,
        state=ThesisState.APPROVED,
        version=0,
        approved_by="h4-5-test",
        approval_reason="operational H6 evidence",
        created_at=confirmed_opportunity.updated_at,
        updated_at=confirmed_opportunity.updated_at,
        last_actor="h4-5-test",
        last_reason="operational H6 evidence",
    )
    _save_decision_authority(
        database, initial_opportunity, confirmed_opportunity, thesis
    )
    if invalidated_thesis:
        invalidated = transition_thesis(
            thesis,
            to_state=ThesisState.INVALIDATED,
            actor="thesis-reviewer",
            reason="invalidation requires EXIT",
            changed_at=confirmed_opportunity.updated_at + timedelta(seconds=1),
        )
        SQLiteDecisionLifecycleRepository(database).transition_thesis(
            invalidated,
            expected_version=thesis.version,
            idempotency_key="h4-5-thesis-invalidated",
            command_hash=canonical_hash(invalidated.to_canonical_dict()),
        )
        thesis = invalidated
    rule_set = ThesisInvalidationRuleSet.create(
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.version,
        rules=(TimeAfterRule(condition.condition_id, invalidation_at),),
    )
    health_input = ThesisHealthInputBundle.create(
        thesis=thesis,
        opportunity=confirmed_opportunity,
        market_regime=research.market_regime,
        theme_rotation=research.theme_rotation,
        capital_evolution=research.capital_evolution,
        candidate_set=research.candidate_set,
        signal_snapshot=signal,
        path_forecast=path,
        price_snapshot=inputs.decision_price_snapshot,
        configuration=_health_configuration(),
        rule_set=rule_set,
        manual_evidence=(),
        prior_observation=None,
        assessed_at=assessed_at,
        actor="h4-5-test",
        reason="operational H5 exit observation",
    )
    health = ThesisHealthObservationBuilder().build(health_input)
    SQLiteThesisHealthRepository(database).save_observation(
        health,
        input_bundle=health_input,
        idempotency_key="h4-5-health",
        command_hash=thesis_health_command_hash(health_input),
    )
    _save_composite(database, root / "h6", composite)

    calendar, statuses, book, position = _seed_execution_authority(
        database=database,
        symbol=symbol,
        opportunity_id=confirmed_opportunity.opportunity_id,
        thesis_id=thesis.thesis_id,
        assessed_at=assessed_at,
    )
    execution_observation = ReducingExecutionObservation.create(
        symbol=symbol,
        session_date=assessed_at.date(),
        state=h4_execution_state,
        reference_price=10.0,
        average_daily_volume=10_000,
        source_artifact_id=ArtifactId("h4-5-execution-observation-source"),
        source_artifact_hash=_sha("a"),
        availability_time=assessed_at - timedelta(seconds=5),
        reason_code="H4_5_EXECUTABLE",
    )
    configuration = RiskReducingGateConfiguration.create(
        profile_id="h4-5-gate-v1",
        maximum_position_age_seconds=60,
        maximum_observation_age_seconds=30,
        maximum_liquidity_participation=0.1,
    )
    quantity = position.total_quantity
    risk_decision = RiskReducingExecutionGate().assess(
        action=action,
        position=position,
        target_quantity=(
            0
            if action is RiskChangeKind.EXIT or reduce_target_zero
            else quantity - 40
        ),
        order_quantity=(
            quantity
            if action is RiskChangeKind.EXIT or reduce_target_zero
            else 40
        ),
        execution_observation=execution_observation,
        configuration=configuration,
        actor="risk-operator",
        reason="confirmed H4 exit",
        assessed_at=assessed_at,
    )
    SQLiteRiskRouteRepository(database).save_reducing_decision(
        risk_decision,
        position=position,
        execution_observation=execution_observation,
        configuration=configuration,
        idempotency_key="h4-5-risk",
        command_hash=canonical_hash(
            {"command": "h4-5-risk", "decision": risk_decision.content_hash}
        ),
    )
    exit_assessment = OperationalPositionAssessmentServiceV2().assess(
        thesis=thesis,
        position=position,
        health_observation=health,
        configuration=_position_lifecycle_configuration(),
        assessed_at=assessed_at,
        actor="position-reviewer",
        reason="operational EXIT assessment",
    ).exit_assessment
    assert exit_assessment.action.value == risk_decision.action.value, (
        exit_assessment.action,
        risk_decision.action,
        health.observed_health_state,
        health.effective_health_state,
        exit_assessment.unrealized_return,
        health.missing_reason_codes,
    )
    risk_bundle = SQLiteRiskRouteRepository(
        database
    ).get_verified_reducing_decision_bundle(risk_decision.decision_id)
    health_bundle = SQLiteThesisHealthRepository(
        database
    ).get_verified_thesis_health_bundle(health.observation_id)
    directive = build_operational_exit_directive_v2(
        exit_assessment=exit_assessment,
        risk_bundle=risk_bundle,
        health_bundle=health_bundle,
        composite=composite,
        created_at=assessed_at,
    )
    repository.save_operational_exit_directive(
        directive,
        exit_assessment=exit_assessment,
        risk_reducing_decision_id=risk_decision.decision_id,
    )
    policy = RiskReductionConfirmationPolicy.create(
        profile_id="h4-5-confirmation-v1",
        builder_revision="h4.5-v1",
        maximum_decision_age_seconds=60,
        maximum_position_age_seconds=60,
        maximum_execution_observation_age_seconds=15,
        maximum_reference_price_deviation=0.02,
        operator_authentication_requirement=(
            OperatorAuthenticationRequirement.RECORDED_ACTOR_ONLY
        ),
    )
    command = RiskReductionConfirmationCommand(
        risk_reducing_decision_id=risk_decision.decision_id,
        risk_reducing_decision_hash=risk_decision.content_hash,
        exit_directive_id=directive.directive_id,
        exit_directive_hash=directive.content_hash,
        thesis_health_observation_id=health.observation_id,
        thesis_health_observation_hash=health.content_hash,
        composite_manifest_id=composite.manifest.manifest_id,
        composite_manifest_hash=composite.manifest.content_hash,
        trading_calendar=calendar,
        symbol_trading_statuses=statuses,
        execution_observation=execution_observation,
        confirmation_policy=policy,
        expected_price_lower=9.9,
        expected_price_upper=10.1,
        confirmed_at=assessed_at,
        actor="manual-operator",
        reason="confirm current risk reduction",
        idempotency_key="h4-5-confirm",
    )
    return ConfirmationFixture(
        repository=repository,
        command=command,
        directive=directive,
        book=book,
        decision_id=risk_decision.decision_id,
        quantity=quantity,
    )


def _signal(research, symbol: str, *, weakening: bool) -> SignalSnapshot:
    values = {
        "symbol": symbol,
        "signal_family": SignalFamily.TREND_CONTINUATION,
        "signal_state": SignalState.CONFIRMED_FOR_RESEARCH,
        "price_action_state": ConfirmationState.CONFIRMED,
        "volume_confirmation_state": (
            ConfirmationState.UNCONFIRMED
            if weakening
            else ConfirmationState.CONFIRMED
        ),
        "trend_confirmation_state": ConfirmationState.CONFIRMED,
        "vwap_state": ConfirmationState.CONFIRMED,
        "overheat_state": ConfirmationState.CONFIRMED,
        "signal_score": 0.8,
        "confidence": 1.0,
        "reason_codes": ("H4_5_SIGNAL",),
    }
    payload = {
        name: (
            value.value
            if hasattr(value, "value")
            else list(value)
            if isinstance(value, tuple)
            else value
        )
        for name, value in values.items()
    }
    envelope = ArtifactEnvelope.create(
        artifact_type="SIGNAL_SNAPSHOT",
        artifact_payload=payload,
        decision_date=research.envelope.decision_time.value.date(),
        decision_time=research.envelope.decision_time,
        created_at=research.envelope.created_at,
        code_revision="h4-5-integration",
        configuration_id=ArtifactId("h4-5-signal-config"),
        configuration_hash=canonical_hash({"config": "h4-5-signal"}),
        source_manifest_id=research.envelope.source_manifest_id,
        source_manifest_hash=research.envelope.source_manifest_hash,
        input_artifact_ids=(research.candidate_set.envelope.artifact_id,),
        input_content_hashes=(research.candidate_set.envelope.content_hash,),
        model_id=ModelId("h4-5-signal-model"),
        model_version="1.0.0-exploratory",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=SignalState.CONFIRMED_FOR_RESEARCH.value,
        reason_codes=("H4_5_SIGNAL",),
        limitations=("FORMAL_OOS_ALPHA_NOT_ESTABLISHED",),
    )
    return SignalSnapshot(envelope=envelope, **values)  # type: ignore[arg-type]


def _path(research, signal: SignalSnapshot, symbol: str) -> PathForecast:
    values = {
        "symbol": symbol,
        "target_id": TargetId("h4-5-path-target"),
        "forecast_horizon": "next-session-path",
        "upper_barrier_return": 0.08,
        "lower_barrier_return": -0.04,
        "expected_mfe": 0.06,
        "expected_mae": -0.03,
        "return_quantiles": (),
        "calibration_status": CalibrationStatus.NOT_CALIBRATED,
        "forecast_status": PathForecastStatus.AVAILABLE_FOR_RESEARCH,
        "usable_sample_count": 100,
        "excluded_sample_count": 0,
        "reason_codes": ("H4_5_PATH",),
    }
    payload = {
        "symbol": symbol,
        "target_id": str(values["target_id"]),
        "forecast_horizon": values["forecast_horizon"],
        "upper_barrier_return": values["upper_barrier_return"],
        "lower_barrier_return": values["lower_barrier_return"],
        "expected_mfe": values["expected_mfe"],
        "expected_mae": values["expected_mae"],
        "return_quantiles": [],
        "calibration_status": CalibrationStatus.NOT_CALIBRATED.value,
        "forecast_status": PathForecastStatus.AVAILABLE_FOR_RESEARCH.value,
        "usable_sample_count": 100,
        "excluded_sample_count": 0,
        "reason_codes": ["H4_5_PATH"],
    }
    envelope = ArtifactEnvelope.create(
        artifact_type="PATH_FORECAST",
        artifact_payload=payload,
        decision_date=research.envelope.decision_time.value.date(),
        decision_time=research.envelope.decision_time,
        created_at=research.envelope.created_at,
        code_revision="h4-5-integration",
        configuration_id=ArtifactId("h4-5-path-config"),
        configuration_hash=canonical_hash({"config": "h4-5-path"}),
        source_manifest_id=research.envelope.source_manifest_id,
        source_manifest_hash=research.envelope.source_manifest_hash,
        input_artifact_ids=(signal.envelope.artifact_id,),
        input_content_hashes=(signal.envelope.content_hash,),
        model_id=ModelId("h4-5-path-model"),
        model_version="1.0.0-exploratory",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=PathForecastStatus.AVAILABLE_FOR_RESEARCH.value,
        reason_codes=("H4_5_PATH",),
        limitations=("FORMAL_OOS_ALPHA_NOT_ESTABLISHED",),
    )
    return PathForecast(envelope=envelope, **values)  # type: ignore[arg-type]


def _save_decision_authority(
    database: Path,
    initial: TradingOpportunity,
    confirmed: TradingOpportunity,
    thesis: TradingThesis,
) -> None:
    repository = SQLiteDecisionLifecycleRepository(database)
    repository.create_opportunity(
        initial,
        idempotency_key="h4-5-opportunity-create",
        command_hash=canonical_hash(initial.to_canonical_dict()),
    )
    repository.confirm_opportunity(
        confirmed,
        thesis,
        expected_version=initial.version,
        idempotency_key="h4-5-opportunity-confirm",
        command_hash=canonical_hash(
            {
                "opportunity": confirmed.to_canonical_dict(),
                "thesis": thesis.to_canonical_dict(),
            }
        ),
    )


def _save_composite(database: Path, root: Path, composite) -> None:
    daily_path = root / "daily" / str(composite.manifest.daily_artifact_id)
    supplemental_path = (
        root
        / "supplemental"
        / str(composite.manifest.supplemental_bundle_id)
    )
    daily = load_verified_daily_decision_artifact(daily_path)
    from market_regime_alpha.application.operational_research.supplemental_artifact import (
        load_verified_supplemental_research_evidence,
    )

    supplemental = load_verified_supplemental_research_evidence(
        supplemental_path
    )
    SQLiteCompositeOperationalRepository(database).save_manifest(
        composite,
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        idempotency_key="h4-5-composite",
        command_hash=composite_operational_command_hash(
            daily=daily,
            supplemental=supplemental,
            composite=composite,
        ),
    )


def _seed_execution_authority(
    *,
    database: Path,
    symbol: str,
    opportunity_id: OpportunityId,
    thesis_id: ThesisId,
    assessed_at: datetime,
):
    prior_date = assessed_at.date() - timedelta(days=1)
    next_date = assessed_at.date() + timedelta(days=1)
    timezone = assessed_at.tzinfo
    assert timezone is not None
    at = lambda day, hour, minute=0: datetime(  # noqa: E731
        day.year, day.month, day.day, hour, minute, tzinfo=timezone
    )
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("h4-5-calendar"),
        market="CN_A_SHARE",
        calendar_version="h4-5-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(day, at(day, 15))
            for day in (prior_date, assessed_at.date(), next_date)
        ),
    )
    status = SymbolTradingSessionStatus.create(
        symbol=symbol,
        session_date=assessed_at.date(),
        state=SymbolTradingState.TRADABLE,
        source_artifact_id=ArtifactId("h4-5-status-source"),
        source_artifact_hash=_sha("b"),
        availability_time=assessed_at - timedelta(seconds=5),
        reason_code="H4_5_TRADABLE",
    )
    book = PositionBook.open(
        account_id="account-h4-5",
        symbol=symbol,
        opportunity_id=opportunity_id,
        thesis_id=thesis_id,
        thesis_version=0,
        opened_at=at(prior_date, 9, 30),
        actor="manual-operator",
        reason="existing OPEN PositionBook",
    )
    recorded = ManualTradeRecord(
        schema_version=TRACEABLE_MANUAL_TRADE_SCHEMA,
        manual_trade_id=ManualTradeId("manual-trade-h4-5-entry"),
        risk_decision_id=RiskDecisionId("risk-h4-5-entry"),
        risk_decision_hash=_sha("c"),
        portfolio_decision_id=PortfolioDecisionId("portfolio-h4-5-entry"),
        target_position_hash=_sha("d"),
        account_id=book.account_id,
        symbol=symbol,
        side=TradeSide.BUY,
        intended_quantity=100,
        expected_price_lower=9.8,
        expected_price_upper=10.2,
        state=ManualOrderState.RECORDED,
        filled_quantity=0,
        version=0,
        actor="manual-operator",
        reason="historical entry",
        created_at=at(prior_date, 10),
        updated_at=at(prior_date, 10),
        last_actor="manual-operator",
        last_reason="historical entry",
        position_book_id=book.position_book_id,
        thesis_id=thesis_id,
        opportunity_id=opportunity_id,
        post_trade_snapshot_id=ArtifactId("post-trade-h4-5-entry"),
        post_trade_snapshot_hash=_sha("e"),
    )
    fill = Fill(
        schema_version=FILL_SCHEMA,
        fill_id=FillId("fill-h4-5-entry"),
        manual_trade_id=recorded.manual_trade_id,
        account_id=book.account_id,
        symbol=symbol,
        side=TradeSide.BUY,
        quantity=100,
        price=10.0,
        fees=0.0,
        occurred_at=at(prior_date, 10, 1),
        recorded_at=at(prior_date, 10, 1) + timedelta(seconds=1),
        actor="manual-operator",
        reason="historical manual Fill",
        external_fill_id="external-h4-5-entry",
        fill_kind=FillKind.EXECUTION,
        correction_of_fill_id=None,
    )
    filled = replace(
        recorded,
        state=ManualOrderState.FILLED,
        filled_quantity=100,
        version=1,
        updated_at=fill.recorded_at,
        last_reason=fill.reason,
    )
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO position_books(
                position_book_id, account_id, symbol, opportunity_id,
                thesis_id, state, version, aggregate_json, opened_at, closed_at
            ) VALUES (?, ?, ?, ?, ?, 'OPEN', 0, ?, ?, NULL)
            """,
            (
                str(book.position_book_id),
                book.account_id,
                book.symbol,
                str(book.opportunity_id),
                str(book.thesis_id),
                _json(book.to_canonical_dict()),
                book.opened_at.isoformat(),
            ),
        )
        connection.execute(
            """
            INSERT INTO position_book_events(
                position_book_id, sequence, state, aggregate_json,
                idempotency_key, created_at
            ) VALUES (?, 0, 'OPEN', ?, 'h4-5-book-open', ?)
            """,
            (
                str(book.position_book_id),
                _json(book.to_canonical_dict()),
                book.opened_at.isoformat(),
            ),
        )
        connection.execute(
            """
            INSERT INTO manual_trade_records(
                manual_trade_id, authority_route, risk_decision_id,
                risk_reducing_decision_id,
                risk_reduction_confirmation_id, account_id, symbol, side,
                state, filled_quantity, aggregate_json, version
            ) VALUES (?, 'INCREASING', ?, NULL, NULL, ?, ?, 'BUY',
                      'FILLED', 100, ?, 1)
            """,
            (
                str(filled.manual_trade_id),
                str(filled.risk_decision_id),
                filled.account_id,
                filled.symbol,
                _json(filled.to_canonical_dict()),
            ),
        )
        for trade, key in ((recorded, "entry-recorded"), (filled, "entry-filled")):
            connection.execute(
                """
                INSERT INTO manual_trade_events(
                    manual_trade_id, sequence, state, aggregate_json,
                    idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(trade.manual_trade_id),
                    trade.version,
                    trade.state.value,
                    _json(trade.to_canonical_dict()),
                    key,
                    trade.updated_at.isoformat(),
                ),
            )
        connection.execute(
            """
            INSERT INTO traceable_manual_trade_bindings(
                manual_trade_id, position_book_id, opportunity_id, thesis_id,
                portfolio_decision_id, risk_decision_id,
                post_trade_snapshot_id, post_trade_snapshot_hash,
                target_delta_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(filled.manual_trade_id),
                str(book.position_book_id),
                str(opportunity_id),
                str(thesis_id),
                str(filled.portfolio_decision_id),
                str(filled.risk_decision_id),
                str(filled.post_trade_snapshot_id),
                filled.post_trade_snapshot_hash,
                filled.target_position_hash,
                filled.created_at.isoformat(),
            ),
        )
        connection.execute(
            """
            INSERT INTO manual_fills(
                fill_id, external_fill_id, manual_trade_id, account_id,
                symbol, fill_kind, correction_of_fill_id, fill_json,
                recorded_at, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, 'EXECUTION', NULL, ?, ?, ?)
            """,
            (
                str(fill.fill_id),
                fill.external_fill_id,
                str(fill.manual_trade_id),
                fill.account_id,
                fill.symbol,
                _json(fill.to_canonical_dict()),
                fill.recorded_at.isoformat(),
                "h4-5-entry-fill",
            ),
        )
    position = PositionProjector().project_book_t_plus_one(
        book=book,
        trades=(filled,),
        fills=(fill,),
        calendar=calendar,
        symbol_session_statuses=(status,),
        as_of=assessed_at,
    )
    return calendar, (status,), book, position


def _json(payload: dict[str, object]) -> str:
    import json

    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _position_lifecycle_configuration() -> PositionLifecycleConfig:
    return PositionLifecycleConfig.create(
        profile_id="h4-5-position-assessment-v1",
        add_minimum_return=2.0,
        weakening_return_threshold=1.0,
        exit_return_threshold=-0.99,
        enable_add_assessment=False,
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        schema_version=POSITION_LIFECYCLE_CONFIG_SCHEMA,
    )


def _health_configuration() -> ThesisHealthRuleConfiguration:
    source = health_configuration()
    values = {
        item.name: getattr(source, item.name)
        for item in fields(source)
        if item.name
        not in {"schema_version", "configuration_id", "configuration_hash"}
    }
    values["maximum_price_age_seconds"] = 1_200.0
    values["maximum_price_research_skew_seconds"] = 1_200.0
    return ThesisHealthRuleConfiguration.create(**values)
