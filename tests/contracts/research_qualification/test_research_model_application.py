from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.research_qualification.application.research_models import (
    ModelMutationResult,
    RegisterModelVersionRequest,
    ResearchModelApplication,
)
from market_regime_alpha.infrastructure.models import DeterministicRidgeTrainer
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_models import (
    LinearTrainingRow,
    ModelDependencyVersion,
    ModelExecutionEnvironment,
    ModelScalarParameter as FrozenScalarParameter,
    ModelScalarType as FrozenScalarType,
    ModelTrainingReproducibility,
    ModelTrainingSamplePlan,
    ModelTrainingSampleState,
)
from market_regime_alpha.research_qualification.ports.model_inputs import (
    OpenModelTrainingRunRequest,
    PreparedModelTrainingInputs,
    RegisteredModelTrainingInputs,
    RegisteredReproducibleModelTrainingInputs,
    ReproducibleModelTrainingRunRequest,
    PreparedReproducibleModelTrainingInputs,
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
            algorithm_code=self.request.algorithm_code,
            algorithm_version=self.request.algorithm_version,
            implementation_sha256=self.request.algorithm_sha256,
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

    def open_reproducible_training_run(self, plan, context, *, runtime_claim=None):
        self.training_plan = plan
        return ModelMutationResult(
            "MODEL_TRAINING_RUN",
            plan.training_run.model_training_run_id,
            1,
            "c" * 64,
            _id(803),
            False,
        )


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
        model_training_sample_id=_id(800),
        ordinal=1,
        evaluation_observation_id=_id(1),
        evaluation_metric_observation_id=_id(2),
        research_partition_member_id=_id(3),
        commitment_id=_id(4),
        decision_run_id=_id(5),
        candidate_id=_id(6),
        instrument_id=_id(7),
        dataset_id=_id(8),
        dataset_manifest_artifact=_binding(9),
        market_target_outcome_revision_id=_id(10),
        source_outcome_metric_id=_id(11),
        evaluation_input_state="INCLUDED",
        state=ModelTrainingSampleState.ESTIMABLE,
        reason_code="COMPLETE_INPUT",
        target_value=Decimal("2"),
        feature_vector_sha256="c" * 64,
    )
    commands = _Commands()
    artifacts = _Artifacts()
    application = ResearchModelApplication(
        commands,
        _Inputs(request, sample),  # type: ignore[arg-type]
        artifacts,
        DeterministicRidgeTrainer(),
    )

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


def test_reproducible_model_path_uses_db_cutoff_environment_and_exact_typed_parameters() -> None:
    legacy_request = OpenModelTrainingRunRequest(
        model_training_run_id=_id(180),
        model_id=_id(181),
        evaluation_run_id=_id(182),
        evaluation_protocol_metric_id=_id(183),
        exploratory_backtest_run_id=_id(184),
        exploratory_backtest_arm_id=_id(185),
        exploratory_backtest_fold_id=_id(186),
        algorithm_code="deterministic_ridge",
        algorithm_version="1.0",
        algorithm_sha256="a" * 64,
        ridge_alpha=Decimal("0.25"),
        random_seed=23,
        code_artifact=_binding(187),
        config_artifact=_binding(188),
        provenance_sha256="b" * 64,
    )
    environment = ModelExecutionEnvironment(
        python_implementation="cpython",
        python_version="3.13.7",
        runtime_code="uv",
        runtime_version="0.8.13",
        uv_lock_sha256="c" * 64,
        dependencies=(ModelDependencyVersion(1, "project", "0.1.0", "d" * 64),),
    )
    hyperparameters = (
        FrozenScalarParameter(
            1,
            "ridge_alpha",
            FrozenScalarType.DECIMAL,
            decimal_value=Decimal("0.25"),
        ),
    )
    request = ReproducibleModelTrainingRunRequest(
        training=legacy_request,
        environment=environment,
        hyperparameters=hyperparameters,
    )
    sample = ModelTrainingSamplePlan(
        model_training_sample_id=_id(880),
        ordinal=1,
        evaluation_observation_id=_id(101),
        evaluation_metric_observation_id=_id(102),
        research_partition_member_id=_id(103),
        commitment_id=_id(104),
        decision_run_id=_id(105),
        candidate_id=_id(106),
        instrument_id=_id(107),
        dataset_id=_id(108),
        dataset_manifest_artifact=_binding(109),
        market_target_outcome_revision_id=_id(110),
        source_outcome_metric_id=_id(111),
        evaluation_input_state="INCLUDED",
        state=ModelTrainingSampleState.ESTIMABLE,
        reason_code="COMPLETE_INPUT",
        target_value=Decimal("2"),
        feature_vector_sha256="e" * 64,
    )
    reproducibility = ModelTrainingReproducibility(
        model_training_run_id=legacy_request.model_training_run_id,
        training_knowledge_cutoff=datetime(2026, 2, 1, tzinfo=UTC),
        implementation_sha256=legacy_request.algorithm_sha256,
        environment=environment,
        hyperparameters=hyperparameters,
    )

    class Inputs(_Inputs):
        def prepare_reproducible(self, actual_request):
            assert actual_request == request
            return PreparedReproducibleModelTrainingInputs(
                training=self.prepared,
                reproducibility=reproducibility,
            )

        def load_registered_reproducible(self, model_training_run_id):
            assert model_training_run_id == legacy_request.model_training_run_id
            return RegisteredReproducibleModelTrainingInputs(
                training=self.load_registered(model_training_run_id),
                reproducibility=reproducibility,
            )

    commands = _Commands()
    artifacts = _Artifacts()
    application = ResearchModelApplication(
        commands,  # type: ignore[arg-type]
        Inputs(legacy_request, sample),  # type: ignore[arg-type]
        artifacts,
        DeterministicRidgeTrainer(),
    )

    opened = application.open_reproducible_training_run(
        request,
        _context("open-reproducible-training"),
    )
    versioned = application.fit_and_register_reproducible_version(
        RegisterModelVersionRequest(
            _id(990),
            legacy_request.model_id,
            1,
            legacy_request.model_training_run_id,
            "f" * 64,
        ),
        _context("fit-reproducible-training"),
    )

    assert opened.aggregate_kind == "MODEL_TRAINING_RUN"
    assert commands.training_plan.reproducibility == reproducibility
    assert versioned.aggregate_kind == "MODEL_VERSION"
    assert commands.version_plan.coefficient_count == 2
