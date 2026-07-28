from __future__ import annotations

from dataclasses import dataclass

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
    ExperimentId,
    ModelId,
    TargetId,
)
from market_regime_alpha.data.daily_quality import (
    DataQualityReport,
    evaluate_daily_data_quality,
)
from market_regime_alpha.daily_decision.snapshot import (
    DecisionPriceSnapshot,
    build_decision_price_snapshot,
)
from market_regime_alpha.features.daily_pipeline import (
    materialize_public_daily_baseline_features,
)
from market_regime_alpha.platform.candidate_prediction_adapter import (
    b0_b1_model_definitions,
    publish_b0_b1_prediction_runs,
)
from market_regime_alpha.platform.contracts import EvaluationProtocolId
from market_regime_alpha.platform.prediction_run import PredictionRun
from market_regime_alpha.research.mr1_morning_pop import MR1TargetId
from market_regime_alpha.universe.daily_exploratory import (
    DailyUniverseReconciliation,
    reconcile_daily_universe,
    smoke_pool_policy_v1,
)
from tests.application.daily_loop.public_fixture import public_fixture


@dataclass(frozen=True)
class DailyDecisionFixture:
    reconciliation: DailyUniverseReconciliation
    quality_report: DataQualityReport
    decision_snapshot: DecisionPriceSnapshot
    prediction_runs: tuple[PredictionRun, PredictionRun]
    source_manifest: object


@pytest.fixture
def daily_decision_fixture() -> DailyDecisionFixture:
    policy = smoke_pool_policy_v1()
    _, provider_result, source_manifest = public_fixture(policy=policy)
    reconciliation = reconcile_daily_universe(
        policy=policy,
        source_manifest=source_manifest,
        provider_result=provider_result,
    )
    feature_result = materialize_public_daily_baseline_features(
        reconciliation=reconciliation,
        provider_result=provider_result,
        code_revision="772ecfb09410588b5a406ad900d793a5850e60d5",
        config_hash="sha256:" + "2" * 64,
    )
    by_feature = {
        item.definition_id: {
            observation.symbol: observation
            for observation in item.observations
        }
        for item in feature_result.materializations
    }
    feature_ids = tuple(item.feature_id for item in feature_result.definitions)
    target_id = TargetId(MR1TargetId.NEXT_SESSION_1030_RETURN.value)
    dataset = CandidateResearchDataset(
        dataset_id=DatasetId("daily-decision-fixture-dataset"),
        source_dataset_ids=(reconciliation.dataset_contract.dataset_id,),
        data_eligibility=reconciliation.dataset_contract.eligibility,
        universe_id=reconciliation.population.universe_id,
        decision_time=reconciliation.population.decision_time,
        population_symbols=reconciliation.population.symbols,
        target_id=target_id,
        target_materialization_artifact_id=ArtifactId(
            "daily-decision-pending-target"
        ),
        feature_definition_ids=feature_ids,
        feature_materialization_ids=tuple(
            item.materialization_id for item in feature_result.materializations
        ),
        rows=tuple(
            CandidateDatasetRow(
                symbol=symbol,
                feature_values=tuple(
                    CandidateFeatureValue(
                        feature_id=feature_id,
                        status=by_feature[feature_id][symbol].status,
                        value=by_feature[feature_id][symbol].value,
                    )
                    for feature_id in feature_ids
                ),
                target=CandidateTargetValue(
                    target_id=target_id,
                    status=TargetObservationStatus.NOT_YET_OBSERVED,
                    value=None,
                ),
            )
            for symbol in reconciliation.population.symbols
        ),
        limitations=("FIXTURE_REPLAY_ONLY",),
    )
    definitions = b0_b1_model_definitions(dataset)
    prediction_runs = publish_b0_b1_prediction_runs(
        dataset,
        model_definitions=definitions,
        evaluation_protocol_id=EvaluationProtocolId(
            "daily-b0-b1-1030-evaluation-v1"
        ),
        experiment_protocol_ids={
            ModelId("platform-b0-momentum-v1"): ExperimentId(
                "daily-b0-frozen-experiment-v1"
            ),
            ModelId("platform-b1-balanced-v1"): ExperimentId(
                "daily-b1-frozen-experiment-v1"
            ),
        },
        code_revision="772ecfb09410588b5a406ad900d793a5850e60d5",
    )
    quality_report = evaluate_daily_data_quality(
        manifest=source_manifest,
        required_symbols=policy.symbols,
    )
    decision_snapshot = build_decision_price_snapshot(
        provider_result=provider_result,
        source_manifest=source_manifest,
    )
    return DailyDecisionFixture(
        reconciliation=reconciliation,
        quality_report=quality_report,
        decision_snapshot=decision_snapshot,
        prediction_runs=prediction_runs,
        source_manifest=source_manifest,
    )
