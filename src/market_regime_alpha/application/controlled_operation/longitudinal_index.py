"""Contracts for the append-only Controlled operation discovery index."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Protocol

from market_regime_alpha.application.controlled_operation.evidence_package import (
    ControlledOperationalEvidencePackage,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import require_sha256


@dataclass(frozen=True, slots=True)
class LongitudinalOperationalRecord:
    decision_date: date
    operation_run_id: ArtifactId
    universe_id: ArtifactId
    daily_dataset_id: ArtifactId
    minute_dataset_id: ArtifactId
    feature_set_id: ArtifactId
    signal_model_id: str
    signal_model_version: str
    configuration_hashes: tuple[str, ...]
    candidate_count: int
    signal_state_counts: tuple[tuple[str, int], ...]
    minute_success_count: int
    minute_failure_count: int
    deadline_status: str
    outcome_status: str
    package_id: ArtifactId
    package_hash: str
    package_locator: str
    indexed_at: datetime

    def __post_init__(self) -> None:
        require_sha256("package_hash", self.package_hash)
        if self.configuration_hashes != tuple(sorted(set(self.configuration_hashes))):
            raise ValueError("Longitudinal configuration hashes must be unique and sorted")
        for digest in self.configuration_hashes:
            require_sha256("configuration hash", digest)
        if self.signal_state_counts != tuple(sorted(set(self.signal_state_counts))):
            raise ValueError("Longitudinal Signal counts must be unique and sorted")
        if self.minute_success_count + self.minute_failure_count != self.candidate_count:
            raise ValueError("Longitudinal minute coverage counts mismatch")
        path = PurePosixPath(self.package_locator)
        if path.is_absolute() or ".." in path.parts or self.package_locator != path.as_posix():
            raise ValueError("Longitudinal package locator must be relative")
        if self.outcome_status not in {"OUTCOME_PENDING", "SETTLED"}:
            raise ValueError("Longitudinal Outcome status is invalid")


class LongitudinalOperationalIndex(Protocol):
    def append(
        self,
        *,
        package: ControlledOperationalEvidencePackage,
        package_locator: str,
    ) -> LongitudinalOperationalRecord: ...


__all__ = ["LongitudinalOperationalIndex", "LongitudinalOperationalRecord"]
