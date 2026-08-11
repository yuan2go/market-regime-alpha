from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
)
from market_regime_alpha.application.research_evaluation.targets import (
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.calibration import (
    CalibrationMethod,
    CalibrationProtocol,
)
from market_regime_alpha.application.research_validation.calibration_qualification import (
    CalibrationQualificationPolicy,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationPartition,
    EvaluationWindow,
    FormalEvaluationProtocol,
    MultipleTestingMethod,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
)
from market_regime_alpha.application.research_validation.entry_qualification import (
    EntryResearchModel,
    EntryResearchVariant,
)
from market_regime_alpha.application.research_validation.postgres_calibration_qualification import (
    PostgresCalibrationQualificationAuthority,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    PostgresFormalProtocolRepository,
)
from market_regime_alpha.application.research_validation.postgres_phase_c_gates import (
    PostgresPhaseCGateAuthority,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.application.research_validation.qualification import (
    QualificationOutcome,
)
from market_regime_alpha.application.research_validation.phase_c_gates import (
    EntryHoldingExitQualificationPolicy,
    PhaseCStageOutcome,
)
from market_regime_alpha.application.strategy_shadow.contracts import (
    HoldingRuleKind,
    StrategyShadowPolicy,
    strategy_shadow_artifact_payload,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    PortfolioWeightingMethod,
    ShadowParameterProvenance,
    ShadowPortfolioPolicy,
    build_shadow_portfolio,
)
from market_regime_alpha.application.strategy_shadow.postgres_portfolio import (
    PostgresShadowPortfolioRepository,
)
from market_regime_alpha.application.strategy_shadow.postgres_repository import (
    PostgresStrategyShadowRepository,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


NOW = datetime(2026, 8, 11, 8, tzinfo=UTC)


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def test_calibration_owner_records_real_missing_oos_as_blocked(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    targets = engineering_multi_horizon_protocol()
    PostgresTargetOutcomeRepository(postgres_factory).register_protocol(targets)
    calibration = CalibrationProtocol.create(
        protocol_version="phase-c5-postgres-v1",
        method=CalibrationMethod.PLATT_LOGISTIC,
        minimum_fit_samples=2,
    )
    PostgresResearchValidationRepository(
        postgres_factory
    ).record_calibration_protocol(calibration, recorded_at=NOW)
    target = targets.targets[0]
    policy = CalibrationQualificationPolicy.create(
        policy_version="phase-c5-v1",
        target_protocol_reference=ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL", targets.protocol_id, targets.protocol_hash
        ),
        target_reference=ValidationArtifactReference(
            "OUTCOME_TARGET", target.target_id, target.target_hash
        ),
        barrier_id=target.barriers[0].barrier_id,
        calibration_protocol_reference=ValidationArtifactReference(
            "CALIBRATION_PROTOCOL",
            calibration.protocol_id,
            calibration.protocol_hash,
        ),
        minimum_oos_samples=2,
        maximum_brier=Decimal("0.25"),
        maximum_log_loss=Decimal("0.70"),
        maximum_ece=Decimal("0.10"),
        minimum_coverage=Decimal("0.90"),
        locked_at=NOW,
    )
    authority = PostgresCalibrationQualificationAuthority(postgres_factory)
    authority.record_policy(policy)
    entry_model = EntryResearchModel.create(
        model_version="phase-c6-entry-v1",
        variant=EntryResearchVariant.CANDIDATE_FORECAST,
        score_threshold=Decimal("0.6"),
    )
    validation = PostgresResearchValidationRepository(postgres_factory)
    validation.record(
        artifact_id=ArtifactId(str(entry_model.model_id)),
        artifact_hash=entry_model.model_hash,
        artifact_kind="ENTRY_RESEARCH_MODEL",
        evidence_authority="ENGINEERING_ONLY",
        payload=entry_model.identity_payload(),
        created_at=NOW,
    )
    strategy_policy = StrategyShadowPolicy.create(
        policy_version="phase-c6-strategy-v1",
        rule_kinds=(HoldingRuleKind.FIXED_TIME,),
        fixed_horizon_sessions=1,
        trailing_drawdown=None,
        protection_return=None,
        participation_rate=Decimal("0.1"),
    )
    PostgresStrategyShadowRepository(postgres_factory).save_policy(
        strategy_policy, created_at=NOW
    )
    portfolio_policy = ShadowPortfolioPolicy.create(
        policy_version="phase-c6-portfolio-v1",
        top_k=1,
        weighting_method=PortfolioWeightingMethod.EQUAL_WEIGHT,
        lot_size=100,
        t_plus_one=True,
        parameters={
            name: (Decimal(value), ShadowParameterProvenance.ENGINEERING_ASSUMPTION)
            for name, value in {
                "commission_bps": "2",
                "slippage_bps": "5",
                "impact_bps": "3",
                "exit_cost_bps": "2",
                "max_participation_rate": "0.1",
            }.items()
        },
        created_at=NOW,
    )
    portfolio = build_shadow_portfolio(
        policy=portfolio_policy,
        research_reference=_reference("RESEARCH_PANEL_V2", "phase-c6-panel"),
        candidate_reference=_reference("CANDIDATE_SET", "phase-c6-candidates"),
        initial_cash=Decimal("100000"),
        created_at=NOW,
    )
    PostgresShadowPortfolioRepository(postgres_factory).save_portfolio(
        policy=portfolio_policy, portfolio=portfolio
    )
    entry_policy = EntryHoldingExitQualificationPolicy.create(
        policy_version="phase-c6-v1",
        entry_model_reference=ValidationArtifactReference(
            "ENTRY_RESEARCH_MODEL",
            ArtifactId(str(entry_model.model_id)),
            entry_model.model_hash,
        ),
        strategy_policy_reference=ValidationArtifactReference(
            "STRATEGY_SHADOW_POLICY",
            strategy_policy.policy_id,
            strategy_policy.policy_hash,
        ),
        portfolio_policy_reference=ValidationArtifactReference(
            "SHADOW_PORTFOLIO_POLICY",
            portfolio_policy.policy_id,
            portfolio_policy.policy_hash,
        ),
        minimum_samples=20,
        minimum_hit_rate=Decimal("0.55"),
        minimum_cost_adjusted_return=Decimal("0.001"),
        maximum_mean_mae=Decimal("-0.05"),
        required_exit_rule_coverage=(HoldingRuleKind.FIXED_TIME,),
        allowed_result_provenance=(
            ShadowParameterProvenance.CALIBRATED_PARAMETER,
            ShadowParameterProvenance.OBSERVED_FACT,
        ),
        locked_at=NOW,
    )
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("phase-c5-calendar-source"),
        market="XSHG-XSHE",
        calendar_version="phase-c5-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                trade_date=date(2026, 1, day),
                session_close=datetime(2026, 1, day, 7, tzinfo=UTC),
            )
            for day in range(5, 31)
        ),
    )
    evaluation = FormalEvaluationProtocol.create(
        protocol_version="phase-c5-evaluation-v1",
        target_protocol=targets,
        windows=(
            EvaluationWindow("train", EvaluationPartition.TRAIN, date(2026, 1, 5), date(2026, 1, 12), 1),
            EvaluationWindow("validation", EvaluationPartition.VALIDATION, date(2026, 1, 13), date(2026, 1, 20), 1),
            EvaluationWindow("locked-oos", EvaluationPartition.LOCKED_OOS, date(2026, 1, 21), date(2026, 1, 30), 1),
        ),
        bootstrap_iterations=100,
        confidence_level=Decimal("0.95"),
        multiple_testing_method=MultipleTestingMethod.BONFERRONI,
        locked_at=NOW,
    )
    protocol = FormalResearchProtocol.create(
        protocol_version="phase-c5-v1",
        target_protocol=targets,
        trading_calendar=calendar,
        evaluation_protocol=evaluation,
        universe_reference=_reference("UNIVERSE", "universe-v1"),
        dataset_reference=_reference("DATASET", "dataset-v1"),
        historical_sample_dataset_reference=_reference(
            "HISTORICAL_SAMPLE_DATASET", "sample-dataset-v1"
        ),
        feature_reference=_reference("FEATURE_DEFINITION_SET", "features-v1"),
        factor_reference=_reference("FACTOR_CATALOG", "factors-v1"),
        model_reference=_reference("MODEL_VERSION_LINEAGE", "model-v1"),
        threshold_policy_reference=_reference("THRESHOLD_POLICY", "threshold-v1"),
        formal_oos_qualification_policy_reference=_reference(
            "FORMAL_OOS_QUALIFICATION_POLICY", "formal-oos-v1"
        ),
        cost_policy_reference=entry_policy.portfolio_policy_reference,
        calibration_policy_reference=ValidationArtifactReference(
            "CALIBRATION_POLICY", policy.policy_id, policy.policy_hash
        ),
        strategy_policy_reference=entry_policy.strategy_policy_reference,
        entry_holding_exit_qualification_policy_reference=ValidationArtifactReference(
            "ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY",
            entry_policy.policy_id,
            entry_policy.policy_hash,
        ),
        locked_at=NOW,
    )
    PostgresFormalProtocolRepository(postgres_factory).record_protocol(
        protocol=protocol,
        target_protocol=targets,
        evaluation_protocol=evaluation,
        component_payloads={
            role: (
                calendar.semantic_payload()
                if role == "trading_calendar_reference"
                else policy.identity_payload()
                if role == "calibration_policy_reference"
                else portfolio_policy.identity_payload()
                if role == "cost_policy_reference"
                else strategy_shadow_artifact_payload(strategy_policy)
                if role == "strategy_policy_reference"
                else entry_policy.identity_payload()
                if role == "entry_holding_exit_qualification_policy_reference"
                else {
                    "kind": reference.artifact_kind,
                    "name": str(reference.artifact_id),
                }
            )
            for role, reference in protocol.component_references().items()
        },
    )

    decision = authority.qualify(
        policy=policy,
        formal_protocol_id=protocol.protocol_id,
        calibration_artifact_id=None,
        actor="phase-c-test",
        reason="resolve C5 against PostgreSQL evidence",
        idempotency_key="phase-c5-blocked",
    )
    replayed = authority.qualify(
        policy=policy,
        formal_protocol_id=protocol.protocol_id,
        calibration_artifact_id=None,
        actor="phase-c-test",
        reason="resolve C5 against PostgreSQL evidence",
        idempotency_key="phase-c5-blocked",
    )

    assert replayed == decision
    assert decision.outcome is QualificationOutcome.BLOCKED
    assert decision.calibrated is False
    assert decision.reason_codes == ("FORMAL_OOS_QUALIFICATION_MISSING",)

    gates = PostgresPhaseCGateAuthority(postgres_factory)
    strategy = gates.resolve_entry_holding_exit(
        formal_protocol_id=protocol.protocol_id,
        policy=entry_policy,
        actor="phase-c-test",
        reason="resolve C6 against PostgreSQL evidence",
        idempotency_key="phase-c6-blocked",
    )
    admission = gates.resolve_production_admission(
        formal_protocol_id=protocol.protocol_id,
        governance_version="phase-c8-v1",
        actor="phase-c-test",
        reason="resolve C8 against PostgreSQL evidence",
        idempotency_key="phase-c8-blocked",
    )
    execution = gates.resolve_controlled_execution(
        formal_protocol_id=protocol.protocol_id,
        actor="phase-c-test",
        reason="resolve C9 against PostgreSQL evidence",
        idempotency_key="phase-c9-blocked",
    )

    assert strategy.outcome is PhaseCStageOutcome.BLOCKED
    with postgres_factory.connection(read_only=True) as connection:
        stored_entry_policy = connection.execute(
            "SELECT policy_hash FROM entry_holding_exit_qualification_policy"
        ).fetchone()
    assert stored_entry_policy == (entry_policy.policy_hash,)
    assert admission.production_authorized is False
    assert execution.outcome is PhaseCStageOutcome.BLOCKED
    assert "BROKER_CONTRACT_MISSING" in execution.reason_codes
