from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_models import (
    ModelTrainingSamplePlan,
    ModelTrainingSampleState,
    ModelTrainingRunPlan,
    ModelVersionPlan,
    ResearchModelPlan,
)


def _id(value: int) -> UUID:
    return UUID(int=value)


def _artifact(value: int) -> ArtifactBinding:
    return ArtifactBinding(_id(value), f"{value:064x}", value)


def _model() -> ResearchModelPlan:
    return ResearchModelPlan(
        model_id=_id(1),
        model_code="wp17p_ridge",
        target_definition_id=_id(2),
        target_version=1,
        target_definition_sha256="a" * 64,
        feature_definitions=((_id(3), "b" * 64), (_id(4), "c" * 64)),
        code_artifact=_artifact(5),
        config_artifact=_artifact(6),
        provenance_sha256="d" * 64,
    )


def _sample(ordinal: int, *, estimable: bool = True) -> ModelTrainingSamplePlan:
    base = ordinal * 20
    return ModelTrainingSamplePlan(
        model_training_sample_id=_id(base + 1),
        ordinal=ordinal,
        evaluation_observation_id=_id(base + 2),
        evaluation_metric_observation_id=_id(base + 3),
        research_partition_member_id=_id(base + 4),
        commitment_id=_id(base + 5),
        decision_run_id=_id(base + 6),
        candidate_id=_id(base + 7),
        instrument_id=_id(base + 8),
        dataset_id=_id(base + 9),
        dataset_manifest_artifact=_artifact(base + 10),
        market_target_outcome_revision_id=_id(base + 11),
        source_outcome_metric_id=_id(base + 12),
        state=(
            ModelTrainingSampleState.ESTIMABLE
            if estimable
            else ModelTrainingSampleState.NOT_ESTIMABLE
        ),
        reason_code="COMPLETE_INPUT" if estimable else "FEATURE_MISSING",
        target_value=Decimal("0.01") if estimable else None,
        feature_vector_sha256=(f"{base + 13:064x}" if estimable else None),
    )


def _training_run() -> ModelTrainingRunPlan:
    return ModelTrainingRunPlan(
        model_training_run_id=_id(100),
        model_id=_id(1),
        evaluation_run_id=_id(101),
        evaluation_protocol_metric_id=_id(102),
        exploratory_backtest_run_id=_id(103),
        exploratory_backtest_arm_id=_id(104),
        exploratory_backtest_fold_id=_id(105),
        algorithm_code="deterministic_ridge",
        algorithm_version="1.0",
        algorithm_sha256="e" * 64,
        ridge_alpha=Decimal("0.01"),
        random_seed=17,
        training_input_artifact=_artifact(106),
        code_artifact=_artifact(107),
        config_artifact=_artifact(108),
        provenance_sha256="f" * 64,
        samples=(_sample(1), _sample(2, estimable=False), _sample(3)),
    )


def test_model_family_freezes_target_and_ordered_feature_roster() -> None:
    model = _model()

    assert model.feature_count == 2
    assert len(str(model.feature_roster_sha256)) == 64
    assert len(str(model.content_sha256)) == 64

    with pytest.raises(ValueError, match="unique and ordered"):
        ResearchModelPlan(
            model_id=_id(1),
            model_code="wp17p_ridge",
            target_definition_id=_id(2),
            target_version=1,
            target_definition_sha256="a" * 64,
            feature_definitions=((_id(3), "b" * 64), (_id(3), "b" * 64)),
            code_artifact=_artifact(5),
            config_artifact=_artifact(6),
            provenance_sha256="d" * 64,
        )


def test_training_sample_preserves_not_estimable_members() -> None:
    missing = _sample(1, estimable=False)

    assert missing.target_value is None
    assert missing.feature_vector_sha256 is None

    with pytest.raises(ValueError, match="cannot contain target or feature values"):
        ModelTrainingSamplePlan(
            **{
                **{
                    name: getattr(missing, name)
                    for name in missing.__dataclass_fields__
                    if name not in {"content_sha256", "target_value"}
                },
                "target_value": Decimal("1"),
            }
        )


def test_training_run_freezes_complete_sample_roster() -> None:
    run = _training_run()

    assert run.sample_count == 3
    assert run.estimable_count == 2
    assert len(str(run.sample_roster_sha256)) == 64

    with pytest.raises(ValueError, match="ordinals must be contiguous"):
        ModelTrainingRunPlan(
            **{
                **{
                    name: getattr(run, name)
                    for name in run.__dataclass_fields__
                    if name
                    not in {
                        "content_sha256",
                        "sample_count",
                        "estimable_count",
                        "sample_roster_sha256",
                        "samples",
                    }
                },
                "samples": (_sample(1), _sample(3)),
            }
        )


def test_model_version_binds_exact_completed_training_artifacts() -> None:
    plan = ModelVersionPlan(
        model_version_id=_id(200),
        model_id=_id(1),
        version=1,
        model_training_run_id=_id(100),
        training_input_artifact=_artifact(106),
        fitted_model_artifact=_artifact(201),
        coefficient_count=3,
        fitted_model_sha256=_artifact(201).content_sha256,
        code_artifact=_artifact(107),
        config_artifact=_artifact(108),
        provenance_sha256="2" * 64,
    )

    assert len(str(plan.content_sha256)) == 64
