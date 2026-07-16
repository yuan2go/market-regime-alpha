from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market_regime_alpha.candidates.dataset import (
    CandidateDatasetRow,
    CandidateFeatureValue,
    CandidateResearchDataset,
    CandidateTargetValue,
    TargetObservationStatus,
)
from market_regime_alpha.candidates.directional_accuracy import (
    R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC,
)
from market_regime_alpha.candidates.rehearsal_opportunity_targets import (
    R5_NEXT_SESSION_MFE_TARGET_ID,
)
from market_regime_alpha.candidates.rehearsal_targets import (
    R5_NEXT_SESSION_RETURN_TARGET_ID,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureMaterializationId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.data import DataEligibility
from market_regime_alpha.features.rehearsal_baselines import (
    LIQUIDITY_20S_ID,
    MOMENTUM_5S_ID,
    PRICE_VS_MA20_ID,
    VOLATILITY_20S_ID,
)
from market_regime_alpha.research.r5_baseline_runner import (
    DirectionalAccuracyApplicability,
    candidate_evaluation_record,
    r5_b1_fixed_specs,
    run_r5_target_baselines,
)


TZ = ZoneInfo("Asia/Shanghai")
TARGET_ID = R5_NEXT_SESSION_RETURN_TARGET_ID
FEATURE_IDS = (
    MOMENTUM_5S_ID,
    VOLATILITY_20S_ID,
    LIQUIDITY_20S_ID,
    PRICE_VS_MA20_ID,
)


def _dataset(
    day: int,
    *,
    target_id: TargetId = TARGET_ID,
) -> CandidateResearchDataset:
    decision_time = DecisionTime(datetime(2026, 7, 13 + day, 14, 55, tzinfo=TZ))
    symbols = ("000001.SZ", "600000.SH")
    return CandidateResearchDataset(
        dataset_id=DatasetId(f"candidate-test-{day}-{target_id}"),
        source_dataset_ids=(DatasetId(f"source-test-{day}"),),
        data_eligibility=DataEligibility.REHEARSAL,
        universe_id=UniverseId(f"universe-test-{day}"),
        decision_time=decision_time,
        population_symbols=symbols,
        target_id=target_id,
        target_materialization_artifact_id=ArtifactId(f"target-test-{day}"),
        feature_definition_ids=FEATURE_IDS,
        feature_materialization_ids=tuple(
            FeatureMaterializationId(f"fm-test-{day}-{index}")
            for index in range(len(FEATURE_IDS))
        ),
        rows=tuple(
            CandidateDatasetRow(
                symbol=symbol,
                feature_values=tuple(
                    CandidateFeatureValue(
                        feature_id=feature_id,
                        status=InputAvailabilityStatus.AVAILABLE,
                        value=(symbol_index + 1) * (feature_index + 1) + day / 10,
                    )
                    for feature_index, feature_id in enumerate(FEATURE_IDS)
                ),
                target=CandidateTargetValue(
                    target_id=target_id,
                    status=TargetObservationStatus.AVAILABLE,
                    value=float(symbol_index + day),
                    observed_at=AvailabilityTime(
                        decision_time.value + timedelta(days=1, hours=1)
                    ),
                ),
            )
            for symbol_index, symbol in enumerate(symbols)
        ),
    )


def test_fixed_b1_specs_match_the_declared_ablation_ladder() -> None:
    specs = r5_b1_fixed_specs()

    assert tuple(specs) == ("B1-A", "B1-B", "B1-C", "B1-D", "B1-E")
    assert tuple(component.feature_id for component in specs["B1-A"].components) == (
        MOMENTUM_5S_ID,
    )
    assert PRICE_VS_MA20_ID not in {
        component.feature_id for component in specs["B1-D"].components
    }
    assert PRICE_VS_MA20_ID in {
        component.feature_id for component in specs["B1-E"].components
    }


def test_shared_runner_evaluates_four_b0_and_five_b1_models() -> None:
    result = run_r5_target_baselines(
        datasets=(_dataset(0), _dataset(1)),
        code_revision="abc123",
        config_hash="sha256:config",
        model_identity_prefix="xuntou-rehearsal",
        panel_limitations=("TEST_REHEARSAL",),
    )

    assert result.target_id == TARGET_ID
    assert result.panel.slice_count == 2
    assert result.panel.data_eligibility is DataEligibility.REHEARSAL
    assert tuple(item.name for item in result.b0_evaluations) == (
        "B0-feature-r5-momentum-5s-v1",
        "B0-feature-r5-volatility-20s-v1",
        "B0-feature-r5-log-median-amount-20s-v1",
        "B0-feature-r5-price-vs-ma20-v1",
    )
    assert tuple(item.name for item in result.b1_evaluations) == (
        "B1-A",
        "B1-B",
        "B1-C",
        "B1-D",
        "B1-E",
    )
    assert all(
        str(item.evaluation.model_id).startswith("xuntou-rehearsal-")
        for item in (*result.b0_evaluations, *result.b1_evaluations)
    )
    assert all(
        item.directional_accuracy.status
        is DirectionalAccuracyApplicability.APPLICABLE
        for item in (*result.b0_evaluations, *result.b1_evaluations)
    )
    assert all(
        item.directional_accuracy.spec_id
        == R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC.spec_id
        for item in (*result.b0_evaluations, *result.b1_evaluations)
    )
    assert all(
        item.directional_accuracy.evaluation is not None
        and item.directional_accuracy.reason is None
        for item in (*result.b0_evaluations, *result.b1_evaluations)
    )


def test_shared_runner_marks_mfe_directional_accuracy_not_applicable() -> None:
    result = run_r5_target_baselines(
        datasets=(_dataset(0, target_id=R5_NEXT_SESSION_MFE_TARGET_ID),),
        code_revision="abc123",
        config_hash="sha256:config",
        model_identity_prefix="test-mfe",
    )

    for item in (*result.b0_evaluations, *result.b1_evaluations):
        assert (
            item.directional_accuracy.status
            is DirectionalAccuracyApplicability.NOT_APPLICABLE
        )
        assert item.directional_accuracy.spec_id is None
        assert item.directional_accuracy.evaluation is None
        assert (
            item.directional_accuracy.reason
            == "TARGET_SEMANTICS_NOT_POSITIVE_CLOSE_RETURN"
        )
    record = candidate_evaluation_record(result.b1_evaluations[0])
    assert record["directional_accuracy"] == {
        "status": "NOT_APPLICABLE",
        "spec_id": None,
        "reason": "TARGET_SEMANTICS_NOT_POSITIVE_CLOSE_RETURN",
        "metrics": None,
    }


def test_evaluation_record_is_json_ready_and_does_not_select_a_winner() -> None:
    result = run_r5_target_baselines(
        datasets=(_dataset(0),),
        code_revision="abc123",
        config_hash="sha256:config",
        model_identity_prefix="test-baseline",
    )

    record = candidate_evaluation_record(result.b1_evaluations[-1])

    assert record["name"] == "B1-E"
    assert record["feature_ids"] == [
        str(MOMENTUM_5S_ID),
        str(LIQUIDITY_20S_ID),
        str(VOLATILITY_20S_ID),
        str(PRICE_VS_MA20_ID),
    ]
    assert "winner" not in record
    assert "probability" not in record
    assert record["directional_accuracy"]["status"] == "APPLICABLE"
    assert (
        record["directional_accuracy"]["spec_id"]
        == R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC.spec_id
    )
    assert record["directional_accuracy"]["reason"] is None
    assert record["directional_accuracy"]["metrics"]["slice_count"] == 1
