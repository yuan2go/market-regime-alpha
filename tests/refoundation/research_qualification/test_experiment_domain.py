from __future__ import annotations

from uuid import uuid4

import pytest

from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.research_qualification.domain.experiment import (
    ExperimentDefinition,
    ExperimentPartitionBinding,
    ExperimentRunPlan,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)


_HASH = "a" * 64


def _experiment(**changes: object) -> ExperimentDefinition:
    values: dict[str, object] = {
        "experiment_id": uuid4(),
        "experiment_code": "mr1-primary-change",
        "research_question": "Does the one declared change improve robustness?",
        "primary_change": "Replace only the volatility normalization.",
        "hypothesis": "Lower false positives without reducing coverage.",
        "target_definition_id": uuid4(),
        "target_version": 1,
        "target_definition_sha256": _HASH,
        "protocol_identity": "mr1-evaluation-v1",
        "acceptance_semantics": "Primary metric must meet its frozen threshold.",
        "code_artifact": ArtifactBinding(uuid4(), _HASH, 10),
        "config_artifact": ArtifactBinding(uuid4(), "b" * 64, 20),
        "provenance_sha256": "c" * 64,
    }
    values.update(changes)
    return ExperimentDefinition(**values)  # type: ignore[arg-type]


def test_experiment_requires_one_explicit_primary_change() -> None:
    with pytest.raises(ValueError, match="primary_change"):
        _experiment(primary_change="")


def test_experiment_partition_requires_exact_target_and_declared_purpose() -> None:
    experiment = _experiment()
    binding = ExperimentPartitionBinding(
        experiment_partition_id=uuid4(),
        experiment_id=experiment.experiment_id,
        binding_ordinal=1,
        research_partition_id=uuid4(),
        target_definition_id=experiment.target_definition_id,
        target_version=experiment.target_version,
        target_definition_sha256=experiment.target_definition_sha256,
        purpose=PartitionPurpose.LOCKED_OOS,
        partition_content_sha256="d" * 64,
    )
    assert binding.target_definition_id == experiment.target_definition_id
    with pytest.raises(ValueError, match="Target"):
        experiment.validate_partition_binding(
            ExperimentPartitionBinding(
                experiment_partition_id=uuid4(),
                experiment_id=experiment.experiment_id,
                binding_ordinal=1,
                research_partition_id=uuid4(),
                target_definition_id=uuid4(),
                target_version=1,
                target_definition_sha256=_HASH,
                purpose=PartitionPurpose.LOCKED_OOS,
                partition_content_sha256="d" * 64,
            )
        )


def test_experiment_freezes_complete_ordered_non_empty_partition_roster() -> None:
    experiment = _experiment()

    def binding(ordinal: int, purpose: PartitionPurpose) -> ExperimentPartitionBinding:
        return ExperimentPartitionBinding(
            experiment_partition_id=uuid4(),
            experiment_id=experiment.experiment_id,
            binding_ordinal=ordinal,
            research_partition_id=uuid4(),
            target_definition_id=experiment.target_definition_id,
            target_version=experiment.target_version,
            target_definition_sha256=experiment.target_definition_sha256,
            purpose=purpose,
            partition_content_sha256=f"{ordinal}" * 64,
        )

    roster = (
        binding(1, PartitionPurpose.FIT),
        binding(2, PartitionPurpose.VALIDATION),
        binding(3, PartitionPurpose.LOCKED_OOS),
    )
    experiment.validate_partition_roster(roster)
    assert len(str(experiment.partition_roster_sha256(roster))) == 64
    with pytest.raises(ValueError, match="non-empty"):
        experiment.validate_partition_roster(())
    with pytest.raises(ValueError, match="contiguous"):
        experiment.validate_partition_roster((roster[0], roster[2]))


def test_experiment_partition_roster_rejects_duplicate_binding() -> None:
    experiment = _experiment()
    partition_id = uuid4()
    first = ExperimentPartitionBinding(
        experiment_partition_id=uuid4(),
        experiment_id=experiment.experiment_id,
        binding_ordinal=1,
        research_partition_id=partition_id,
        target_definition_id=experiment.target_definition_id,
        target_version=experiment.target_version,
        target_definition_sha256=experiment.target_definition_sha256,
        purpose=PartitionPurpose.FIT,
        partition_content_sha256="d" * 64,
    )
    duplicate = ExperimentPartitionBinding(
        experiment_partition_id=uuid4(),
        experiment_id=experiment.experiment_id,
        binding_ordinal=2,
        research_partition_id=partition_id,
        target_definition_id=experiment.target_definition_id,
        target_version=experiment.target_version,
        target_definition_sha256=experiment.target_definition_sha256,
        purpose=PartitionPurpose.VALIDATION,
        partition_content_sha256="e" * 64,
    )
    with pytest.raises(ValueError, match="duplicate"):
        experiment.validate_partition_roster((first, duplicate))


def test_experiment_run_is_execution_identity_not_result() -> None:
    names = set(ExperimentRunPlan.__dataclass_fields__)
    assert names == {
        "experiment_run_id",
        "experiment_id",
        "experiment_partition_id",
        "run_identity",
        "content_sha256",
    }
