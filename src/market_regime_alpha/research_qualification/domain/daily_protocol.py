"""Versioned post-close Feature/Target definitions, with no execution policy."""

from datetime import time
from uuid import UUID, uuid5

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding, FeatureDefinition
from market_regime_alpha.research_qualification.domain.targets import (
    TargetAlgorithmBinding,
    TargetCheckpoint,
    TargetDefinition,
    TargetMetricDefinition,
    TargetMetricDependency,
)
from market_regime_alpha.research_qualification.domain.target_vocabulary import (
    TargetAvailabilityRule,
    TargetBarTimeframe,
    TargetCheckpointRole,
    TargetCompletionRule,
    TargetDependencyRole,
    TargetFinalityRule,
    TargetInstrumentScope,
    TargetMarketScope,
    TargetMetricKind,
    TargetMetricUnit,
    TargetPriceBasis,
    TargetReferenceRule,
    TargetTimingRule,
    TargetValueField,
    TargetValueType,
)
from market_regime_alpha.research_qualification.domain.vocabulary import (
    FeatureAvailabilityRule,
    FeatureIntervalUnit,
    FeatureMissingnessPolicy,
    FeatureSourceRequirement,
    FeatureValueType,
)


def daily_feature_definition(identity: UUID, code: ArtifactBinding, config: ArtifactBinding) -> FeatureDefinition:
    return FeatureDefinition(
        identity,
        "session_open_close_move_v1",
        1,
        FeatureValueType.DECIMAL,
        "RATIO",
        1,
        FeatureIntervalUnit.TRADING_SESSION,
        1,
        FeatureIntervalUnit.TRADING_SESSION,
        0,
        FeatureIntervalUnit.TRADING_SESSION,
        (FeatureSourceRequirement.MARKET_BAR_REVISION,),
        FeatureAvailabilityRule.DECISION_VISIBLE_AT_OR_BEFORE,
        FeatureMissingnessPolicy.EXPLICIT_STATUS,
        "session_open_close_move_v1",
        "1",
        code.content_sha256,
        code,
        config,
    )


def daily_target_definition(identity: UUID, code: ArtifactBinding, config: ArtifactBinding) -> TargetDefinition:
    algorithm = TargetAlgorithmBinding("observation_return", "1", code.content_sha256, code, config)
    checkpoints = tuple(
        TargetCheckpoint(
            target_checkpoint_id=uuid5(identity, name),
            target_definition_id=identity,
            checkpoint_code=name,
            ordinal=ordinal,
            role=role,
            session_offset=offset,
            timing_rule=TargetTimingRule.SESSION_LOCAL_BAR_END,
            local_time=time(15),
            timezone_name="Asia/Shanghai",
            timeframe=TargetBarTimeframe.DAILY,
            price_basis=TargetPriceBasis.RAW_UNADJUSTED,
            value_field=value_field,
            reference_rule=(
                TargetReferenceRule.EXACT_COMPLETED_SESSION_DAILY_BAR
                if role is TargetCheckpointRole.DECISION_REFERENCE
                else TargetReferenceRule.EXACT_SESSION_BAR
            ),
            availability_rule=TargetAvailabilityRule.EXACT_REVISION_OR_SOURCE_GAP,
            finality_rule=TargetFinalityRule.RECORD_UNKNOWN,
        )
        for ordinal, (name, role, offset, value_field) in enumerate(
            (
                ("input_session_close", TargetCheckpointRole.DECISION_REFERENCE, 0, TargetValueField.CLOSE),
                ("next_session_open", TargetCheckpointRole.OUTCOME_OBSERVATION, 1, TargetValueField.OPEN),
                ("next_session_close", TargetCheckpointRole.OUTCOME_OBSERVATION, 1, TargetValueField.CLOSE),
            ),
            1,
        )
    )
    metric = TargetMetricDefinition(
        uuid5(identity, "next_session_intraday_return"),
        identity,
        "next_session_intraday_return",
        1,
        TargetMetricKind.OBSERVATION_RETURN,
        TargetValueType.DECIMAL,
        TargetMetricUnit.RATIO,
        TargetCompletionRule.REQUIRED,
        algorithm,
    )
    dependencies = tuple(
        TargetMetricDependency(
            uuid5(identity, f"observation:{ordinal}"),
            identity,
            metric.target_metric_definition_id,
            checkpoint.target_checkpoint_id,
            ordinal,
            TargetDependencyRole.OBSERVATION,
        )
        for ordinal, checkpoint in enumerate(checkpoints[1:], 1)
    )
    return TargetDefinition(
        identity,
        "daily_close_next_session_intraday_v1",
        1,
        None,
        TargetInstrumentScope.A_SHARE_EQUITY,
        TargetMarketScope.SSE_SZSE,
        algorithm,
        checkpoints,
        (metric,),
        dependencies,
    )


def daily_evaluation_protocol(
    identity: UUID, target: TargetDefinition, model_use_id: UUID, population_count: int, code: ArtifactBinding, config: ArtifactBinding
):
    """Descriptive prediction metrics on the complete daily commitment roster."""
    from market_regime_alpha.research_qualification.domain.evaluation import EvaluationProtocolPlan, ProtocolMetricDefinition
    from market_regime_alpha.research_qualification.domain.evaluation_formula import (
        BacktestFormulaCode,
        BacktestMetricSurface,
        EvaluationFormulaDefinition,
        EvaluationFormulaParameter,
        FormulaParameterType,
    )
    from market_regime_alpha.research_qualification.domain.research_vocabulary import (
        AcceptanceOperator,
        EvaluationReducer,
        EvaluationSliceKind,
        EvaluationSourceKind,
        EvaluationSourceMeasure,
        MetricDirection,
        PartitionPurpose,
        SourceMetricValueType,
    )

    metric = target.metrics[0]
    recipes = (
        ("prediction_pair_coverage", BacktestFormulaCode.COVERAGE_RATE),
        ("bias", BacktestFormulaCode.PREDICTIVE_BIAS),
        ("mae", BacktestFormulaCode.PREDICTIVE_MAE),
        ("rmse", BacktestFormulaCode.PREDICTIVE_RMSE),
        ("daily_rank_ic", BacktestFormulaCode.RANK_IC),
    )
    metrics = []
    for ordinal, (role, name, formula_code) in enumerate(
        ((role, name, formula) for role in ("MODEL", "RULE_BASELINE") for name, formula in recipes), 1
    ):
        name = role.lower() + "_" + name
        mid = uuid5(identity, name)
        parameters = [
            EvaluationFormulaParameter(
                uuid5(mid, "model-use"), 1, "experimental_model_use_id", FormulaParameterType.TEXT, text_value=str(model_use_id)
            ),
            EvaluationFormulaParameter(uuid5(mid, "role"), 2, "forecast_role", FormulaParameterType.TEXT, text_value=role),
        ]
        if formula_code is BacktestFormulaCode.COVERAGE_RATE:
            parameters.append(
                EvaluationFormulaParameter(
                    uuid5(mid, "denominator"), 3, "expected_roster_size", FormulaParameterType.INTEGER, integer_value=population_count
                )
            )
        formula = EvaluationFormulaDefinition(
            mid, formula_code, 1, 38, "ROUND_HALF_EVEN", tuple(parameters), BacktestMetricSurface.SIGNAL_FORECAST
        )
        metrics.append(
            ProtocolMetricDefinition(
                mid,
                name,
                ordinal,
                metric.target_metric_definition_id,
                metric.metric_code,
                SourceMetricValueType.DECIMAL,
                EvaluationReducer.MEAN_DECIMAL,
                EvaluationSliceKind.ALL_MEMBERS,
                None,
                MetricDirection.DESCRIPTIVE,
                1,
                AcceptanceOperator.NONE,
                None,
                source_kind=EvaluationSourceKind.EXPERIMENTAL_FORECAST_OUTCOME_PAIR,
                source_measure=EvaluationSourceMeasure.FORECAST_POINT_VS_TARGET,
                formula=formula,
            )
        )
    return EvaluationProtocolPlan(
        identity,
        "daily_" + identity.hex,
        1,
        target.target_definition_id,
        target.version,
        target.content_sha256,
        PartitionPurpose.DISCOVERY,
        "DESCRIPTIVE_EXPERIMENTAL_PREDICTION_ONLY",
        tuple(metrics),
        code,
        config,
        config.content_sha256,
    )
