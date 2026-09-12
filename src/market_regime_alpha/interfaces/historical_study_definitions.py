"""Concrete daily research definitions, registered through their original owners."""

from uuid import UUID, uuid5

from market_regime_alpha.research_qualification.domain import evaluation as E, evaluation_formula as F, research_vocabulary as V
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.targets import TargetDefinition


def prediction_protocol(identity: UUID, code_name: str, purpose: V.PartitionPurpose,
                        target: TargetDefinition, code: ArtifactBinding, config: ArtifactBinding,
                        provenance: str) -> E.EvaluationProtocolPlan:
    recipes = (("label_mean", "MEAN"),) if purpose is V.PartitionPurpose.FIT else (
        ("bias", "PREDICTIVE_BIAS"), ("mae", "PREDICTIVE_MAE"), ("rmse", "PREDICTIVE_RMSE"),
        ("rank_ic", "RANK_IC"), ("daily_ic_mean", "MEAN"), ("daily_ic_std", "SAMPLE_STDDEV"), ("icir", "ICIR"))
    metrics = []
    for ordinal, (name, formula) in enumerate(recipes, 1):
        mid = uuid5(identity, name)
        parameters = ((F.EvaluationFormulaParameter(uuid5(mid, "input_series"), 1, "input_series",
            F.FormulaParameterType.TEXT, text_value="group_rank_ic"),)
            if name in {"daily_ic_mean", "daily_ic_std", "icir"} else ())
        definition = F.EvaluationFormulaDefinition(mid, F.BacktestFormulaCode[formula], 1, 38, "ROUND_HALF_EVEN", parameters, F.BacktestMetricSurface.SIGNAL_FORECAST)
        metrics.append(E.ProtocolMetricDefinition(mid, name, ordinal, target.metrics[0].target_metric_definition_id,
            target.metrics[0].metric_code, V.SourceMetricValueType.DECIMAL, V.EvaluationReducer.MEAN_DECIMAL,
            V.EvaluationSliceKind.ALL_MEMBERS, None, V.MetricDirection.DESCRIPTIVE, 1, V.AcceptanceOperator.NONE, None,
            source_kind=V.EvaluationSourceKind.OUTCOME_METRIC if purpose is V.PartitionPurpose.FIT else V.EvaluationSourceKind.FORECAST_OUTCOME_PAIR,
            source_measure=V.EvaluationSourceMeasure.TARGET_VALUE if purpose is V.PartitionPurpose.FIT else V.EvaluationSourceMeasure.FORECAST_POINT_VS_TARGET,
            formula=definition))
    return E.EvaluationProtocolPlan(identity, code_name, 1, target.target_definition_id, target.version,
        target.content_sha256, purpose, "EXPLORATORY_PREDICTION_ONLY_NO_TRADING_RETURN", tuple(metrics), code, config, provenance)
