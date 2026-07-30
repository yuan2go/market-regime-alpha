from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates import (
    CandidateDatasetRow,
    CandidateFeatureValue,
    CandidateResearchDataset,
    CandidateTargetValue,
    TargetObservationStatus,
    rank_candidates_by_feature,
    rank_candidates_by_transparent_composite,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    ExperimentId,
    FeatureMaterializationId,
    ModelId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data import DataEligibility
from market_regime_alpha.features import (
    LIQUIDITY_20S_ID,
    MOMENTUM_5S_ID,
    VOLATILITY_20S_ID,
)
from market_regime_alpha.platform.candidate_prediction_adapter import (
    b0_b1_model_definitions,
    publish_b0_b1_prediction_runs,
)
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    EvaluationProtocolId,
)
from market_regime_alpha.platform.multi_model_slice import (
    CompositeCandidateModelSpec,
    SingleFeatureCandidateModelSpec,
    build_default_candidate_slice_specs,
)
from market_regime_alpha.platform.prediction_artifacts import (
    PREDICTION_RUN_ARTIFACT_FILES,
    publish_prediction_run_artifact,
)
from market_regime_alpha.platform.prediction_reader import (
    load_verified_prediction_run_artifact,
)
from market_regime_alpha.research.mr1_morning_pop import MR1TargetId


SHANGHAI = ZoneInfo("Asia/Shanghai")
TARGET_ID = TargetId(MR1TargetId.NEXT_SESSION_1030_RETURN.value)
FEATURE_IDS = (MOMENTUM_5S_ID, VOLATILITY_20S_ID, LIQUIDITY_20S_ID)
MATERIALIZATION_IDS = tuple(
    FeatureMaterializationId(f"feature-materialization-prediction-{index}-v1")
    for index in range(3)
)


def _dataset() -> CandidateResearchDataset:
    symbols = (
        "000001.SZ",
        "000002.SZ",
        "000003.SZ",
        "000004.SZ",
        "000005.SZ",
    )
    values = {
        "000001.SZ": (0.30, 0.10, 10.0),
        "000002.SZ": (0.30, 0.10, 10.0),
        "000003.SZ": (0.20, 0.20, 20.0),
        "000004.SZ": (None, 0.30, 30.0),
        "000005.SZ": (0.10, 0.40, None),
    }
    rows = tuple(
        CandidateDatasetRow(
            symbol=symbol,
            feature_values=tuple(
                CandidateFeatureValue(
                    feature_id,
                    (
                        InputAvailabilityStatus.AVAILABLE
                        if value is not None
                        else InputAvailabilityStatus.MISSING
                    ),
                    value,
                )
                for feature_id, value in zip(
                    FEATURE_IDS,
                    values[symbol],
                    strict=True,
                )
            ),
            target=CandidateTargetValue(
                TARGET_ID,
                TargetObservationStatus.NOT_YET_OBSERVED,
                None,
            ),
        )
        for symbol in symbols
    )
    return CandidateResearchDataset(
        dataset_id=DatasetId("candidate-dataset-prediction-equivalence-v1"),
        source_dataset_ids=(DatasetId("source-dataset-prediction-equivalence-v1"),),
        data_eligibility=DataEligibility.EXPLORATORY,
        universe_id=UniverseId("smoke-a-share-universe-v1"),
        decision_time=DecisionTime(
            datetime(2026, 7, 24, 14, 55, tzinfo=SHANGHAI)
        ),
        population_symbols=symbols,
        target_id=TARGET_ID,
        target_materialization_artifact_id=ArtifactId(
            "target-pending-next-session-1030-v1"
        ),
        feature_definition_ids=FEATURE_IDS,
        feature_materialization_ids=MATERIALIZATION_IDS,
        rows=rows,
        limitations=("EXPLORATORY_DAILY_LOOP",),
    )


def _adapted_runs():
    dataset = _dataset()
    definitions = b0_b1_model_definitions(dataset)
    runs = publish_b0_b1_prediction_runs(
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
    return dataset, definitions, runs


def test_b0_b1_adapter_preserves_complete_legacy_ranking_semantics() -> None:
    dataset, definitions, adapted = _adapted_runs()
    specs = build_default_candidate_slice_specs(
        momentum_feature_id=MOMENTUM_5S_ID,
        volume_feature_id=LIQUIDITY_20S_ID,
        volatility_feature_id=VOLATILITY_20S_ID,
    )
    b0_spec = specs[0]
    b1_spec = specs[1]
    assert isinstance(b0_spec, SingleFeatureCandidateModelSpec)
    assert isinstance(b1_spec, CompositeCandidateModelSpec)
    direct_b0 = rank_candidates_by_feature(
        dataset,
        feature_id=b0_spec.feature_id,
        model_id=b0_spec.model_id,
        code_revision="772ecfb09410588b5a406ad900d793a5850e60d5",
        config_hash=b0_spec.config_hash,
    )
    direct_b1 = rank_candidates_by_transparent_composite(
        dataset,
        spec=b1_spec.composite,
        model_id=b1_spec.model_id,
        code_revision="772ecfb09410588b5a406ad900d793a5850e60d5",
        config_hash=b1_spec.config_hash,
    )
    by_model = {run.model_id: run for run in adapted}
    pairs = (
        (direct_b0, by_model[b0_spec.model_id], (MOMENTUM_5S_ID,)),
        (
            direct_b1,
            by_model[b1_spec.model_id],
            tuple(
                component.feature_id
                for component in b1_spec.composite.ordered_components
            ),
        ),
    )

    assert tuple(by_model) == (
        ModelId("platform-b0-momentum-v1"),
        ModelId("platform-b1-balanced-v1"),
    )
    for direct, projected, expected_feature_ids in pairs:
        direct_population = tuple(
            sorted(
                (
                    *(prediction.symbol for prediction in direct.predictions),
                    *(rejection.symbol for rejection in direct.rejections),
                )
            )
        )
        assert direct_population == dataset.population_symbols
        assert projected.population_size == direct.candidate_population_size
        assert projected.predictions == direct.predictions
        assert projected.rejections == direct.rejections
        assert tuple(
            (
                item.symbol,
                item.model_score,
                item.rank,
                item.percentile,
            )
            for item in projected.predictions
        ) == tuple(
            (
                item.symbol,
                item.model_score,
                item.rank,
                item.percentile,
            )
            for item in direct.predictions
        )
        for score in {
            item.model_score for item in direct.predictions
        }:
            direct_tie_group = tuple(
                item.symbol
                for item in direct.predictions
                if item.model_score == score
            )
            projected_tie_group = tuple(
                item.symbol
                for item in projected.predictions
                if item.model_score == score
            )
            assert projected_tie_group == direct_tie_group
        assert projected.ranking_coverage == direct.ranking_coverage
        assert projected.target_id == direct.target_id == TARGET_ID
        assert projected.dataset_id == direct.dataset_id == dataset.dataset_id
        assert projected.feature_definition_ids == expected_feature_ids
        assert projected.feature_materialization_ids == tuple(
            dataset.feature_materialization_ids[
                dataset.feature_definition_ids.index(feature_id)
            ]
            for feature_id in expected_feature_ids
        )
        assert (
            projected.model_definition_hash
            == definitions[projected.model_id].definition_hash
        )
        assert projected.data_eligibility is DataEligibility.EXPLORATORY
        assert projected.evidence_level is EvidenceLevel.EXPLORATORY

    assert tuple(item.symbol for item in direct_b0.predictions[:2]) == (
        "000001.SZ",
        "000002.SZ",
    )
    assert direct_b0.predictions[0].model_score == direct_b0.predictions[1].model_score
    assert tuple(item.symbol for item in direct_b1.predictions[:2]) == (
        "000001.SZ",
        "000002.SZ",
    )
    assert direct_b1.predictions[0].model_score == direct_b1.predictions[1].model_score


def test_b0_b1_adapter_rejects_authority_inflation() -> None:
    dataset = replace(_dataset(), data_eligibility=DataEligibility.REHEARSAL)

    with pytest.raises(ValueError, match="EXPLORATORY"):
        publish_b0_b1_prediction_runs(
            dataset,
            model_definitions=b0_b1_model_definitions(dataset),
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
            code_revision="test-revision",
        )


def test_prediction_run_identity_is_content_addressed_and_immutable() -> None:
    _, _, runs = _adapted_runs()
    first = runs[0]

    assert first == replace(first)
    assert first.prediction_run_id.value.startswith("prediction-run-")
    assert first.content_hash.startswith("sha256:")
    assert len(first.content_hash) == 71
    changed = replace(
        first,
        configuration_hash="0" * 64,
    )
    assert changed.prediction_run_id != first.prediction_run_id
    assert changed.content_hash != first.content_hash


def test_prediction_run_publisher_and_reader_verify_semantics(tmp_path: Path) -> None:
    _, definitions, runs = _adapted_runs()
    run = runs[0]
    output = publish_prediction_run_artifact(
        root=tmp_path,
        prediction_run=run,
        model_definition=definitions[run.model_id],
    )

    assert {item.name for item in output.iterdir()} == set(
        PREDICTION_RUN_ARTIFACT_FILES
    )
    verified = load_verified_prediction_run_artifact(output)
    assert verified.prediction_run == run
    assert verified.root == output.resolve()
    assert verified.model_definition["model_id"] == str(run.model_id)
    with pytest.raises(FileExistsError):
        publish_prediction_run_artifact(
            root=tmp_path,
            prediction_run=run,
            model_definition=definitions[run.model_id],
        )


def test_prediction_reader_rejects_semantic_tamper_after_checksum_rewrite(
    tmp_path: Path,
) -> None:
    _, definitions, runs = _adapted_runs()
    run = runs[0]
    output = publish_prediction_run_artifact(
        root=tmp_path,
        prediction_run=run,
        model_definition=definitions[run.model_id],
    )
    payload = json.loads((output / "prediction_run.json").read_text())
    payload["predictions"][0]["model_score"] = 999.0
    (output / "prediction_run.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    checksums = {
        path.name: f"sha256:{sha256(path.read_bytes()).hexdigest()}"
        for path in output.iterdir()
        if path.name != "SHA256SUMS.json"
    }
    (output / "SHA256SUMS.json").write_text(
        json.dumps(checksums, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="content hash"):
        load_verified_prediction_run_artifact(output)
