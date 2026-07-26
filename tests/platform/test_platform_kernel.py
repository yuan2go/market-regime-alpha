from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates.dataset import (
    CandidateDatasetRow,
    CandidateFeatureValue,
    CandidateResearchDataset,
    CandidateTargetValue,
    TargetObservationStatus,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    ModelId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    EvaluationProtocolId,
    MetricId,
    ModelDefinition,
    ModelLifecycleStatus,
    ModelRole,
    ResearchHypothesisId,
)
from market_regime_alpha.platform.experiment_governance import (
    ExperimentBudget,
    ExperimentGovernance,
    FrozenExperimentProtocol,
    PrimaryChangeDimension,
    ResearchHypothesis,
)
from market_regime_alpha.platform.model_registry import ModelRegistry
from market_regime_alpha.platform.multi_model_slice import (
    build_default_candidate_slice_specs,
    run_multi_model_candidate_slice,
)
from market_regime_alpha.platform.target_evaluation import (
    EvaluationProtocol,
    MissingTargetPolicy,
    PriceMark,
    ReturnBasis,
    TargetKind,
    TargetProtocol,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _dataset() -> CandidateResearchDataset:
    momentum = FeatureDefinitionId("feature-momentum-5d-v1")
    volume = FeatureDefinitionId("feature-amount-expansion-5d-v1")
    volatility = FeatureDefinitionId("feature-volatility-10d-v1")
    feature_ids = (momentum, volume, volatility)
    symbols = ("000001.SZ", "000002.SZ", "600000.SH", "600519.SH", "601318.SH", "601919.SH")
    values = {
        "000001.SZ": (0.08, 1.10, 0.025),
        "000002.SZ": (0.02, 1.80, 0.045),
        "600000.SH": (0.05, 1.20, 0.018),
        "600519.SH": (0.09, 0.80, 0.022),
        "601318.SH": (0.03, 1.40, 0.020),
        "601919.SH": (0.07, 2.10, 0.055),
    }
    target_id = TargetId("target-next-session-1030-relative-return-v1")
    rows = tuple(
        CandidateDatasetRow(
            symbol=symbol,
            feature_values=tuple(
                CandidateFeatureValue(feature_id, InputAvailabilityStatus.AVAILABLE, value)
                for feature_id, value in zip(feature_ids, values[symbol], strict=True)
            ),
            target=CandidateTargetValue(target_id, TargetObservationStatus.NOT_YET_OBSERVED, None),
        )
        for symbol in symbols
    )
    return CandidateResearchDataset(
        dataset_id=DatasetId("candidate-dataset-test-v1"),
        source_dataset_ids=(DatasetId("source-dataset-test-v1"),),
        data_eligibility=DataEligibility.EXPLORATORY,
        universe_id=UniverseId("liquid-a-share-test-v1"),
        decision_time=DecisionTime(datetime(2026, 7, 24, 14, 50, tzinfo=SHANGHAI)),
        population_symbols=symbols,
        target_id=target_id,
        target_materialization_artifact_id=ArtifactId("target-materialization-test-v1"),
        feature_definition_ids=feature_ids,
        feature_materialization_ids=tuple(
            FeatureMaterializationId(f"materialization-{index}-v1") for index in range(3)
        ),
        rows=rows,
    )


def test_target_and_evaluation_protocols_are_content_addressable() -> None:
    dataset = _dataset()
    target = TargetProtocol(
        target_id=dataset.target_id,
        name="next session 10:30 relative return",
        version="1.0.0",
        kind=TargetKind.RELATIVE_RETURN,
        decision_time_convention="14:50 Asia/Shanghai",
        horizon="next session 10:30",
        start_mark=PriceMark.DECISION_PRICE,
        end_mark=PriceMark.NEXT_1030,
        return_basis=ReturnBasis.BENCHMARK_RELATIVE,
        availability_rule="next-session 10:30 final minute mark available after 10:30",
        adjustment_rule="same adjustment basis for instrument and benchmark",
        missing_policy=MissingTargetPolicy.EXCLUDE_WITH_REASON,
        universe_id=dataset.universe_id,
        benchmark_ref="000300.SH",
    )
    protocol = EvaluationProtocol(
        protocol_id=EvaluationProtocolId("candidate-next-1030-evaluation-v1"),
        version="1.0.0",
        model_role=ModelRole.CANDIDATE,
        target_id=target.target_id,
        universe_id=dataset.universe_id,
        primary_metric_id=MetricId("top-k-net-relative-return-v1"),
        secondary_metric_ids=(MetricId("rank-ic-v1"), MetricId("top-k-positive-rate-v1")),
        risk_metric_ids=(MetricId("top-k-mae-v1"),),
        robustness_metric_ids=(MetricId("walk-forward-stability-v1"),),
        top_k_values=(5, 10, 20),
        baseline_model_ids=(ModelId("platform-b0-momentum-v1"),),
        cost_model_ref="a-share-manual-base-cost-v1",
        split_protocol_ref="chronological-walk-forward-v1",
        minimum_decision_dates=60,
        minimum_symbol_coverage=0.95,
        pass_conditions=("primary metric positive after costs",),
        failure_conditions=("top-k does not outperform matched-k",),
    )
    assert len(target.protocol_hash) == 64
    assert len(protocol.protocol_hash) == 64


def test_model_registry_requires_evidence_and_approval_for_active() -> None:
    dataset = _dataset()
    feature_id = dataset.feature_definition_ids[0]
    model = ModelDefinition(
        model_id=ModelId("candidate-model-test-v1"),
        name="candidate model test",
        version="1.0.0",
        family="candidate-baseline",
        role=ModelRole.CANDIDATE,
        target_id=dataset.target_id,
        universe_id=dataset.universe_id,
        feature_ids=(feature_id,),
        implementation_ref="market_regime_alpha.candidates.baselines:rank_candidates_by_feature",
        parameter_hash="sha256:test",
        decision_time_convention="14:50 Asia/Shanghai",
        horizon="next session 10:30",
        supported_data_grades=(EvidenceLevel.EXPLORATORY, EvidenceLevel.FORMAL_RESEARCH),
    )
    registry = ModelRegistry()
    registry.register(model)
    now = datetime(2026, 7, 25, 9, 0, tzinfo=SHANGHAI)
    registry.transition(model.model_id, to_status=ModelLifecycleStatus.RESEARCH, changed_at=now, reason="research start")
    registry.transition(model.model_id, to_status=ModelLifecycleStatus.BACKTESTED, changed_at=now, reason="backtest complete")
    registry.transition(
        model.model_id,
        to_status=ModelLifecycleStatus.OOS_VALIDATED,
        changed_at=now,
        reason="oos passed",
        evidence_refs=("artifact:oos-v1",),
        evidence_level=EvidenceLevel.FORMAL_RESEARCH,
    )
    registry.transition(
        model.model_id,
        to_status=ModelLifecycleStatus.SHADOW,
        changed_at=now,
        reason="shadow start",
        evidence_refs=("artifact:oos-v1",),
    )
    registry.transition(
        model.model_id,
        to_status=ModelLifecycleStatus.PROMOTION_CANDIDATE,
        changed_at=now,
        reason="shadow passed",
        evidence_refs=("artifact:shadow-v1",),
        evidence_level=EvidenceLevel.SHADOW_EVIDENCE,
    )
    with pytest.raises(ValueError, match="approval_ref"):
        registry.transition(
            model.model_id,
            to_status=ModelLifecycleStatus.ACTIVE,
            changed_at=now,
            reason="activate",
            evidence_refs=("artifact:shadow-v1",),
        )


def test_experiment_governance_enforces_access_budget() -> None:
    dataset = _dataset()
    hypothesis = ResearchHypothesis(
        hypothesis_id=ResearchHypothesisId("hypothesis-volume-adds-value-v1"),
        statement="Adding volume expansion improves candidate ranking.",
        rationale="Volume expansion may confirm demand.",
        expected_result="Top-K net relative return exceeds the parent model.",
        counter_evidence=("Volume may reflect distribution.",),
        invalidation_condition="No OOS improvement after costs.",
    )
    protocol = FrozenExperimentProtocol(
        hypothesis=hypothesis,
        model_id=ModelId("platform-b2-volume-momentum-v1"),
        parent_model_id=ModelId("platform-b0-momentum-v1"),
        dataset_id=dataset.dataset_id,
        universe_id=dataset.universe_id,
        target_ids=(dataset.target_id,),
        evaluation_protocol_id=EvaluationProtocolId("candidate-next-1030-evaluation-v1"),
        feature_ids=dataset.feature_definition_ids[:2],
        parameter_variants=((('momentum_weight', '0.45'), ('volume_weight', '0.55')),),
        primary_change=PrimaryChangeDimension.FEATURE_SET,
        comparison_model_ids=(ModelId("platform-b0-momentum-v1"),),
        sample_split_ref="chronological-walk-forward-v1",
        cost_model_ref="a-share-manual-base-cost-v1",
        code_revision="test-revision",
        environment_ref="pytest",
        budget=ExperimentBudget(max_validation_accesses=1),
    )
    governance = ExperimentGovernance()
    experiment_id = governance.register(protocol)
    governance.record_validation_access(experiment_id)
    with pytest.raises(ValueError, match="budget exhausted"):
        governance.record_validation_access(experiment_id)


def test_first_multi_model_vertical_slice_runs_three_comparable_models() -> None:
    dataset = _dataset()
    specs = build_default_candidate_slice_specs(
        momentum_feature_id=dataset.feature_definition_ids[0],
        volume_feature_id=dataset.feature_definition_ids[1],
        volatility_feature_id=dataset.feature_definition_ids[2],
    )
    result = run_multi_model_candidate_slice(
        dataset,
        model_specs=specs,
        code_revision="test-revision",
        top_k_values=(3, 5),
    )
    assert len(result.results) == 3
    assert result.population_size == 6
    assert all(item.ranking_coverage == 1.0 for item in result.results)
    assert len(result.overlaps) == 6
    assert all(len(item.predictions) == 6 for item in result.results)
