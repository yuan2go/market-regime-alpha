"""Contracts for the append-only Controlled operation discovery index."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol

from market_regime_alpha.application.controlled_operation.evidence_package import (
    ControlledOperationalEvidencePackage,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import require_sha256


ARTIFACT_ROOT_LOCATOR_PREFIX = "artifact-root-v1"


def encode_artifact_root_locator(*, artifact_root: Path, path: Path) -> str:
    """Encode one immutable Artifact path against the configured global root."""

    root = artifact_root.resolve()
    resolved = path.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("Longitudinal package must be below Artifact root")
    return f"{ARTIFACT_ROOT_LOCATOR_PREFIX}/{resolved.relative_to(root).as_posix()}"


def resolve_artifact_root_locator(*, artifact_root: Path, locator: str) -> Path:
    """Resolve only the explicit global-root locator contract, never discovery."""

    pure = PurePosixPath(locator)
    if (
        pure.is_absolute()
        or ".." in pure.parts
        or len(pure.parts) < 2
        or pure.parts[0] != ARTIFACT_ROOT_LOCATOR_PREFIX
        or locator != pure.as_posix()
    ):
        raise ValueError(
            "Longitudinal package locator is not ARTIFACT_ROOT_V1 authoritative"
        )
    root = artifact_root.resolve()
    resolved = (root / Path(*pure.parts[1:])).resolve()
    if root not in resolved.parents:
        raise ValueError("Longitudinal package locator escapes Artifact root")
    return resolved


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
        if (
            path.is_absolute()
            or ".." in path.parts
            or len(path.parts) < 2
            or path.parts[0] != ARTIFACT_ROOT_LOCATOR_PREFIX
            or self.package_locator != path.as_posix()
        ):
            raise ValueError(
                "Longitudinal package locator must use artifact-root-v1"
            )
        if self.outcome_status not in {"OUTCOME_PENDING", "SETTLED"}:
            raise ValueError("Longitudinal Outcome status is invalid")


@dataclass(frozen=True, slots=True)
class ControlledPackageLocatorRecord:
    """Authoritative locator for one immutable pending or settled package."""

    package_id: ArtifactId
    package_hash: str
    operation_run_id: ArtifactId
    package_status: str
    package_locator: str
    created_at: datetime

    def __post_init__(self) -> None:
        require_sha256("package_hash", self.package_hash)
        if self.package_status not in {"OUTCOME_PENDING", "SETTLED"}:
            raise ValueError("Controlled package locator status is invalid")
        path = PurePosixPath(self.package_locator)
        if (
            path.is_absolute()
            or ".." in path.parts
            or len(path.parts) < 2
            or path.parts[0] != ARTIFACT_ROOT_LOCATOR_PREFIX
            or self.package_locator != path.as_posix()
        ):
            raise ValueError(
                "Controlled package locator must use artifact-root-v1"
            )


class LongitudinalOperationalIndex(Protocol):
    def record_package_locator(
        self,
        *,
        package: ControlledOperationalEvidencePackage,
        package_locator: str,
    ) -> ControlledPackageLocatorRecord: ...

    def append(
        self,
        *,
        package: ControlledOperationalEvidencePackage,
        package_locator: str,
    ) -> LongitudinalOperationalRecord: ...


__all__ = [
    "ARTIFACT_ROOT_LOCATOR_PREFIX",
    "ControlledPackageLocatorRecord",
    "LongitudinalOperationalIndex",
    "LongitudinalOperationalRecord",
    "encode_artifact_root_locator",
    "resolve_artifact_root_locator",
]
