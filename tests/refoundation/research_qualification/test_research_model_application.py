from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.research_qualification.application.research_models import (
    ModelMutationResult,
    RegisterModelVersionRequest,
    ResearchModelApplication,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_models import (
    LinearTrainingRow,
    ModelTrainingSamplePlan,
    ModelTrainingSampleState,
)
from market_regime_alpha.research_qualification.ports.model_inputs import (
    OpenModelTrainingRunRequest,
    PreparedModelTrainingInputs,
    RegisteredModelTrainingInputs,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.ports import ArtifactRecord
from market_regime_alpha.shared.hashing import sha256_bytes


def _id(value: int) -> UUID:
    return UUID(int=value)


def _binding(value: int, *, content_hash: str | None = None, size: int | None = None) -> ArtifactBinding:
    return ArtifactBinding(
        _id(value),
        content_hash or f"{value:064x}",
        value if size is None else size,
    )


def _context(key: str) -> CommandContext:
    return CommandContext(key, ActorType.WORKER, "wp17p", "RUN_MODEL_TRAINING")


class _Artifacts:
    def __init__(self) -> None:
        self.contents: list[bytes] = []

    def publish(self, content, *, media_type, context, expected_sha256=None, pin_reason_code=None):
        assert media_type == "application/json"
        assert sha256_bytes(content) == expected_sha256
        self.contents.append(content)
        return ArtifactRecord(
            artifact_id=_id(700 + len(self.contents)),
            content_sha256=expected_sha256,
            size_bytes=len(content),
            media_type=media_type,
            locator=f"sha256/{expected_sha256}",
            integrity_state="AVAILABLE",
            retention_until=None,
            pin_reason_code=pin_reason_code,
        )


class _Inputs:
    def __init__(self, request: OpenModelTrainingRunRequest, sample: ModelTrainingSamplePlan) -> None:
        self.request = request
        self.sample = sample
        content = b'{"schema":"test-training-input"}'
        self.prepared = PreparedModelTrainingInputs(
            request=request,
            samples=(
                sample,
                replace(
                    sample,
                    model_training_sample_id=_id(899),
                    ordinal=2,
                    evaluation_observation_id=_id(21),
                    evaluation_metric_observation_id=_id(22),
                    research_partition_member_id=_id(23),
                    commitment_id=_id(24),
                ),
            ),
            linear_rows=(
                LinearTrainingRow(sample.model_training_sample_id, (Decimal("1"),), Decimal("2")),
                LinearTrainingRow(_id(899), (Decimal("2"),), Decimal("4")),
            ),
            training_input_content=content,
            training_input_content_sha256=sha256_bytes(content),
        )

    def prepare(self, request):
        assert request == self.request
        return self.prepared

    def load_registered(self, model_training_run_id):
        assert model_training_run_id == self.request.model_training_run_id
        return RegisteredModelTrainingInputs(
            model_training_run_id=model_training_run_id,
            model_id=self.request.model_id,
            training_input_artifact=_binding(
                701,
                content_hash=str(self.prepared.training_input_content_sha256),
                size=len(self.prepared.training_input_content),
            ),
            feature_definition_ids=(_id(90),),
            linear_rows=self.prepared.linear_rows,
            ridge_alpha=self.request.ridge_alpha,
            random_seed=self.request.random_seed,
            code_artifact=self.request.code_artifact,
            config_artifact=self.request.config_artifact,
        )


class _Commands:
    def __init__(self) -> None:
        self.training_plan = None
        self.version_plan = None

    def register_model(self, plan, context, *, runtime_claim=None):
        raise AssertionError("not used")

    def open_training_run(self, plan, context, *, runtime_claim=None):
        self.training_plan = plan
        return ModelMutationResult("MODEL_TRAINING_RUN", plan.model_training_run_id, 1, "a" * 64, _id(801), False)

    def register_version(self, plan, context, *, runtime_claim=None):
        self.version_plan = plan
        return ModelMutationResult("MODEL_VERSION", plan.model_version_id, plan.version, "b" * 64, _id(802), False)


def test_public_model_application_derives_roster_then_fits_immutable_bytes() -> None:
    request = OpenModelTrainingRunRequest(
        model_training_run_id=_id(80),
        model_id=_id(81),
        evaluation_run_id=_id(82),
        evaluation_protocol_metric_id=_id(83),
        exploratory_backtest_run_id=_id(84),
        exploratory_backtest_arm_id=_id(85),
        exploratory_backtest_fold_id=_id(86),
        algorithm_code="deterministic_ridge",
        algorithm_version="1.0",
        algorithm_sha256="a" * 64,
        ridge_alpha=Decimal("0.01"),
        random_seed=7,
        code_artifact=_binding(87),
        config_artifact=_binding(88),
        provenance_sha256="b" * 64,
    )
    sample = ModelTrainingSamplePlan(
        model_training_sample_id=_id(800), ordinal=1,
        evaluation_observation_id=_id(1), evaluation_metric_observation_id=_id(2),
        research_partition_member_id=_id(3), commitment_id=_id(4),
        decision_run_id=_id(5), candidate_id=_id(6), instrument_id=_id(7),
        dataset_id=_id(8), dataset_manifest_artifact=_binding(9),
        market_target_outcome_revision_id=_id(10), source_outcome_metric_id=_id(11),
        evaluation_input_state="INCLUDED", state=ModelTrainingSampleState.ESTIMABLE,
        reason_code="COMPLETE_INPUT", target_value=Decimal("2"),
        feature_vector_sha256="c" * 64,
    )
    commands = _Commands()
    artifacts = _Artifacts()
    application = ResearchModelApplication(commands, _Inputs(request, sample), artifacts)  # type: ignore[arg-type]

    opened = application.open_training_run(request, _context("open-training"))
    versioned = application.fit_and_register_version(
        RegisterModelVersionRequest(_id(900), request.model_id, 1, request.model_training_run_id, "d" * 64),
        _context("fit-training"),
    )

    assert opened.aggregate_kind == "MODEL_TRAINING_RUN"
    assert commands.training_plan.sample_count == 2
    assert str(commands.training_plan.training_input_artifact.content_sha256) == sha256_bytes(artifacts.contents[0])
    assert versioned.aggregate_kind == "MODEL_VERSION"
    assert commands.version_plan.coefficient_count == 2
    assert str(commands.version_plan.fitted_model_artifact.content_sha256) == sha256_bytes(artifacts.contents[1])
