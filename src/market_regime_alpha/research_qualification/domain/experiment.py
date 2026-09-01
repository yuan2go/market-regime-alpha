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
    research_partition_id: UUID
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: ContentHash | str
    purpose: PartitionPurpose
    partition_content_sha256: ContentHash | str

    def __post_init__(self) -> None:
        if isinstance(self.target_version, bool) or self.target_version < 1:
            raise ValueError("target_version must be positive")
        object.__setattr__(
            self, "target_definition_sha256", ContentHash(str(self.target_definition_sha256))
        )
        object.__setattr__(
            self, "partition_content_sha256", ContentHash(str(self.partition_content_sha256))
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
