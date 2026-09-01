"""Immutable ex-ante Experiment declarations and bindings."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")


def _required(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} is required")


@dataclass(frozen=True, slots=True)
class ExperimentPartitionBinding:
    experiment_partition_id: UUID
    experiment_id: UUID
    binding_ordinal: int
    research_partition_id: UUID
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: ContentHash | str
    purpose: PartitionPurpose
    partition_content_sha256: ContentHash | str
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.binding_ordinal, bool) or self.binding_ordinal < 1:
            raise ValueError("binding_ordinal must be positive")
        if isinstance(self.target_version, bool) or self.target_version < 1:
            raise ValueError("target_version must be positive")
        object.__setattr__(
            self, "target_definition_sha256", ContentHash(str(self.target_definition_sha256))
        )
        object.__setattr__(
            self, "partition_content_sha256", ContentHash(str(self.partition_content_sha256))
        )
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "binding_ordinal": self.binding_ordinal,
                        "experiment_id": self.experiment_id,
                        "experiment_partition_id": self.experiment_partition_id,
                        "partition_content_sha256": str(
                            self.partition_content_sha256
                        ),
                        "partition_purpose": self.purpose,
                        "research_partition_id": self.research_partition_id,
                        "target_definition_id": self.target_definition_id,
                        "target_definition_sha256": str(
                            self.target_definition_sha256
                        ),
                        "target_version": self.target_version,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ExperimentDefinition:
    experiment_id: UUID
    experiment_code: str
    research_question: str
    primary_change: str
    hypothesis: str
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: ContentHash | str
    protocol_identity: str
    acceptance_semantics: str
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.experiment_code):
            raise ValueError("experiment_code has an invalid format")
        for name in (
            "research_question",
            "primary_change",
            "hypothesis",
            "protocol_identity",
            "acceptance_semantics",
        ):
            _required(name, str(getattr(self, name)))
        if isinstance(self.target_version, bool) or self.target_version < 1:
            raise ValueError("target_version must be positive")
        target_hash = ContentHash(str(self.target_definition_sha256))
        provenance_hash = ContentHash(str(self.provenance_sha256))
        object.__setattr__(self, "target_definition_sha256", target_hash)
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "acceptance_semantics": self.acceptance_semantics,
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "experiment_code": self.experiment_code,
                        "hypothesis": self.hypothesis,
                        "primary_change": self.primary_change,
                        "protocol_identity": self.protocol_identity,
                        "provenance_sha256": provenance_hash,
                        "research_question": self.research_question,
                        "target_definition_id": self.target_definition_id,
                        "target_definition_sha256": target_hash,
                        "target_version": self.target_version,
                    }
                )
            ),
        )

    def validate_partition_binding(self, binding: ExperimentPartitionBinding) -> None:
        if binding.experiment_id != self.experiment_id:
            raise ValueError("Experiment binding identity does not match")
        expected = (
            self.target_definition_id,
            self.target_version,
            self.target_definition_sha256,
        )
        actual = (
            binding.target_definition_id,
            binding.target_version,
            binding.target_definition_sha256,
        )
        if actual != expected:
            raise ValueError("Experiment and Partition Target do not match exactly")

    def validate_partition_roster(
        self, bindings: tuple[ExperimentPartitionBinding, ...]
    ) -> None:
        if not bindings:
            raise ValueError("Experiment Partition roster must be non-empty")
        expected_ordinals = tuple(range(1, len(bindings) + 1))
        actual_ordinals = tuple(binding.binding_ordinal for binding in bindings)
        if actual_ordinals != expected_ordinals:
            raise ValueError("Experiment Partition binding ordinals must be contiguous")
        partition_ids = tuple(binding.research_partition_id for binding in bindings)
        binding_ids = tuple(binding.experiment_partition_id for binding in bindings)
        if len(set(partition_ids)) != len(partition_ids) or len(set(binding_ids)) != len(
            binding_ids
        ):
            raise ValueError("Experiment Partition roster contains a duplicate binding")
        for binding in bindings:
            self.validate_partition_binding(binding)

    def partition_roster_sha256(
        self, bindings: tuple[ExperimentPartitionBinding, ...]
    ) -> ContentHash:
        self.validate_partition_roster(bindings)
        return ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "binding_ordinal": binding.binding_ordinal,
                        "content_sha256": str(binding.content_sha256),
                        "experiment_partition_id": binding.experiment_partition_id,
                        "research_partition_id": binding.research_partition_id,
                    }
                    for binding in bindings
                )
            )
        )


@dataclass(frozen=True, slots=True)
class ExperimentRunPlan:
    experiment_run_id: UUID
    experiment_id: UUID
    experiment_partition_id: UUID
    run_identity: str
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        _required("run_identity", self.run_identity)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "experiment_id": self.experiment_id,
                        "experiment_partition_id": self.experiment_partition_id,
                        "run_identity": self.run_identity,
                    }
                )
            ),
        )


__all__ = [
    "ExperimentDefinition",
    "ExperimentPartitionBinding",
    "ExperimentRunPlan",
]
