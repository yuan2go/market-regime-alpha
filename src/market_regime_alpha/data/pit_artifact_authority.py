"""Canonical Reader-backed Artifact authority for Formal PIT admission.

The resolver never accepts an identity merely because a caller supplied a
well-formed id/hash pair.  A supported reference is loaded through the
repository's existing strict package Reader, then its canonical identity and
physical package checksum are captured in an immutable resolution receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Protocol

from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_runtime_configuration,
    load_controlled_source_manifest,
    load_controlled_trading_calendar,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_authority import (
    PITArtifactKind,
    PITArtifactReference,
    PITContractError,
)
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.features.materialization_v2 import (
    load_verified_feature_bundle_v2,
)
from market_regime_alpha.market_data.artifacts import (
    load_verified_market_data_dataset,
)
from market_regime_alpha.market_data.contracts import (
    parse_utc_second,
    require_utc_second,
)
from market_regime_alpha.universe.operational import load_operational_universe


class PITArtifactAuthorityUnavailableError(PITContractError):
    """The referenced Artifact cannot be proven by a canonical strict Reader."""


@dataclass(frozen=True, slots=True)
class PITArtifactAuthorityResolution:
    """Durable receipt proving which Reader resolved one exact Artifact."""

    resolution_id: ArtifactId
    resolution_hash: str
    reference: PITArtifactReference
    canonical_schema: str
    reader_contract: str
    physical_checksums_hash: str
    data_eligibility: DataEligibility | None
    formal_pit_status: str | None
    effective_at: datetime | None
    available_at: datetime | None
    bound_references: tuple[PITArtifactReference, ...]
    resolved_at: datetime
    schema_version: str = "pit-artifact-authority-resolution-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "pit-artifact-authority-resolution-v1":
            raise PITContractError("unsupported PIT Artifact resolution schema")
        require_sha256("resolution_hash", self.resolution_hash)
        require_text("canonical_schema", self.canonical_schema)
        require_text("reader_contract", self.reader_contract)
        require_sha256("physical_checksums_hash", self.physical_checksums_hash)
        if self.effective_at is not None:
            require_utc_second("effective_at", self.effective_at)
        if self.available_at is not None:
            require_utc_second("available_at", self.available_at)
        require_utc_second("resolved_at", self.resolved_at)
        keys = tuple(_reference_key(item) for item in self.bound_references)
        if keys != tuple(sorted(set(keys))):
            raise PITContractError("resolution bound references must be sorted and unique")
        digest = canonical_hash(self.semantic_payload())
        if digest != self.resolution_hash:
            raise PITContractError("PIT Artifact resolution hash mismatch")
        expected_id = ArtifactId(
            f"pit-artifact-resolution-{digest.split(':', 1)[1][:24]}"
        )
        if self.resolution_id != expected_id:
            raise PITContractError("PIT Artifact resolution identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        reference: PITArtifactReference,
        canonical_schema: str,
        reader_contract: str,
        physical_checksums_hash: str,
        resolved_at: datetime,
        data_eligibility: DataEligibility | None = None,
        formal_pit_status: str | None = None,
        effective_at: datetime | None = None,
        available_at: datetime | None = None,
        bound_references: tuple[PITArtifactReference, ...] = (),
    ) -> PITArtifactAuthorityResolution:
        ordered = tuple(sorted(bound_references, key=_reference_key))
        digest = canonical_hash(
            _resolution_payload(
                reference=reference,
                canonical_schema=canonical_schema,
                reader_contract=reader_contract,
                physical_checksums_hash=physical_checksums_hash,
                data_eligibility=data_eligibility,
                formal_pit_status=formal_pit_status,
                effective_at=effective_at,
                available_at=available_at,
                bound_references=ordered,
            )
        )
        return cls(
            resolution_id=ArtifactId(
                f"pit-artifact-resolution-{digest.split(':', 1)[1][:24]}"
            ),
            resolution_hash=digest,
            reference=reference,
            canonical_schema=canonical_schema,
            reader_contract=reader_contract,
            physical_checksums_hash=physical_checksums_hash,
            data_eligibility=data_eligibility,
            formal_pit_status=formal_pit_status,
            effective_at=effective_at,
            available_at=available_at,
            bound_references=ordered,
            resolved_at=resolved_at,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _resolution_payload(
            reference=self.reference,
            canonical_schema=self.canonical_schema,
            reader_contract=self.reader_contract,
            physical_checksums_hash=self.physical_checksums_hash,
            data_eligibility=self.data_eligibility,
            formal_pit_status=self.formal_pit_status,
            effective_at=self.effective_at,
            available_at=self.available_at,
            bound_references=self.bound_references,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "resolution_id": str(self.resolution_id),
            "resolution_hash": self.resolution_hash,
            **self.semantic_payload(),
            "resolved_at": canonical_datetime(self.resolved_at),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> PITArtifactAuthorityResolution:
        expected = {
            "schema_version",
            "resolution_id",
            "resolution_hash",
            "reference",
            "canonical_schema",
            "reader_contract",
            "physical_checksums_hash",
            "data_eligibility",
            "formal_pit_status",
            "effective_at",
            "available_at",
            "bound_references",
            "resolved_at",
        }
        if set(payload) != expected:
            raise PITContractError("PIT Artifact resolution fields mismatch")
        raw_bound = payload["bound_references"]
        if not isinstance(raw_bound, list):
            raise PITContractError("PIT Artifact resolution references must be an array")
        raw_reference = payload["reference"]
        if not isinstance(raw_reference, Mapping):
            raise PITContractError("PIT Artifact resolution reference must be an object")
        return cls(
            schema_version=str(payload["schema_version"]),
            resolution_id=ArtifactId(str(payload["resolution_id"])),
            resolution_hash=str(payload["resolution_hash"]),
            reference=PITArtifactReference.from_canonical_dict(raw_reference),
            canonical_schema=str(payload["canonical_schema"]),
            reader_contract=str(payload["reader_contract"]),
            physical_checksums_hash=str(payload["physical_checksums_hash"]),
            data_eligibility=(
                None
                if payload["data_eligibility"] is None
                else DataEligibility(str(payload["data_eligibility"]))
            ),
            formal_pit_status=(
                None
                if payload["formal_pit_status"] is None
                else str(payload["formal_pit_status"])
            ),
            effective_at=_optional_time(payload["effective_at"], "effective_at"),
            available_at=_optional_time(payload["available_at"], "available_at"),
            bound_references=tuple(
                PITArtifactReference.from_canonical_dict(_object(item))
                for item in raw_bound
            ),
            resolved_at=parse_utc_second("resolved_at", payload["resolved_at"]),
        )


class PITArtifactAuthorityResolver(Protocol):
    def resolve(
        self,
        reference: PITArtifactReference,
        *,
        resolved_at: datetime,
    ) -> PITArtifactAuthorityResolution: ...


class CanonicalPITArtifactAuthorityResolver:
    """Resolve supported Artifact kinds from configured canonical package roots."""

    def __init__(
        self,
        *,
        artifact_roots: Mapping[PITArtifactKind, Path],
        feature_artifact_root: Path | None = None,
    ) -> None:
        self._roots = dict(artifact_roots)
        self._feature_artifact_root = feature_artifact_root

    def resolve(
        self,
        reference: PITArtifactReference,
        *,
        resolved_at: datetime,
    ) -> PITArtifactAuthorityResolution:
        require_utc_second("resolved_at", resolved_at)
        try:
            kind = PITArtifactKind(reference.reference_kind)
        except ValueError as exc:
            raise PITArtifactAuthorityUnavailableError(
                f"unsupported PIT Artifact authority kind: {reference.reference_kind}"
            ) from exc
        supported = {
            PITArtifactKind.SOURCE_MANIFEST,
            PITArtifactKind.MARKET_DATA_DATASET,
            PITArtifactKind.TRADING_CALENDAR,
            PITArtifactKind.UNIVERSE,
            PITArtifactKind.FEATURE_MATERIALIZATION,
            PITArtifactKind.CONFIGURATION,
        }
        if kind not in supported:
            raise PITArtifactAuthorityUnavailableError(
                f"no canonical Reader for PIT Artifact kind {kind.value}"
            )
        root = self._roots.get(kind)
        if root is None:
            raise PITArtifactAuthorityUnavailableError(
                f"no configured canonical repository for PIT Artifact kind {kind.value}"
            )
        package = root / str(reference.artifact_id)
        try:
            resolution = self._load(kind, package, reference, resolved_at)
        except PITArtifactAuthorityUnavailableError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise PITArtifactAuthorityUnavailableError(
                f"canonical Reader rejected {kind.value} {reference.artifact_id}"
            ) from exc
        if resolution.reference != reference:
            raise PITArtifactAuthorityUnavailableError(
                "canonical Reader identity differs from requested PIT Artifact reference"
            )
        return resolution

    def _load(
        self,
        kind: PITArtifactKind,
        package: Path,
        requested: PITArtifactReference,
        resolved_at: datetime,
    ) -> PITArtifactAuthorityResolution:
        physical_hash = _package_checksums_hash(package)
        if kind is PITArtifactKind.SOURCE_MANIFEST:
            manifest = load_controlled_source_manifest(package)
            reference = PITArtifactReference(
                kind.value, manifest.source_manifest_id, manifest.content_hash
            )
            bound = tuple(
                PITArtifactReference(
                    "SOURCE_ARTIFACT", source.artifact_id, source.content_hash
                )
                for source in manifest.source_artifacts
            )
            return PITArtifactAuthorityResolution.create(
                reference=reference,
                canonical_schema=manifest.schema_version,
                reader_contract="controlled-source-manifest-package-v1",
                physical_checksums_hash=physical_hash,
                data_eligibility=manifest.data_eligibility,
                available_at=manifest.decision_time.value,
                bound_references=bound,
                resolved_at=resolved_at,
            )
        if kind is PITArtifactKind.MARKET_DATA_DATASET:
            verified_dataset = load_verified_market_data_dataset(package)
            dataset = verified_dataset.artifact
            reference = PITArtifactReference(
                kind.value, ArtifactId(str(dataset.dataset_id)), dataset.content_hash
            )
            bound = tuple(
                PITArtifactReference(PITArtifactKind.SOURCE_MANIFEST.value, item_id, digest)
                for item_id, digest in dataset.source_manifest_references
            )
            return PITArtifactAuthorityResolution.create(
                reference=reference,
                canonical_schema=dataset.schema_version,
                reader_contract="verified-market-data-dataset-package",
                physical_checksums_hash=verified_dataset.checksums_hash,
                data_eligibility=dataset.data_eligibility,
                formal_pit_status=dataset.formal_pit_status.value,
                effective_at=dataset.decision_time,
                available_at=dataset.available_at,
                bound_references=bound,
                resolved_at=resolved_at,
            )
        if kind is PITArtifactKind.TRADING_CALENDAR:
            calendar = load_controlled_trading_calendar(package)
            return PITArtifactAuthorityResolution.create(
                reference=PITArtifactReference(
                    kind.value, calendar.artifact_id, calendar.content_hash
                ),
                canonical_schema=str(calendar.semantic_payload()["schema_version"]),
                reader_contract="controlled-trading-calendar-package-v1",
                physical_checksums_hash=physical_hash,
                resolved_at=resolved_at,
            )
        if kind is PITArtifactKind.UNIVERSE:
            universe = load_operational_universe(package)
            return PITArtifactAuthorityResolution.create(
                reference=PITArtifactReference(
                    kind.value,
                    ArtifactId(str(universe.universe_id)),
                    universe.content_hash,
                ),
                canonical_schema=universe.schema_version,
                reader_contract="operational-universe-package-v1",
                physical_checksums_hash=physical_hash,
                data_eligibility=universe.data_eligibility,
                formal_pit_status=universe.formal_pit_status.value,
                effective_at=universe.effective_at,
                available_at=universe.available_at,
                resolved_at=resolved_at,
            )
        if kind is PITArtifactKind.FEATURE_MATERIALIZATION:
            if self._feature_artifact_root is None:
                raise PITArtifactAuthorityUnavailableError(
                    "Feature Materialization Reader requires the canonical feature Artifact root"
                )
            verified_bundle = load_verified_feature_bundle_v2(
                package, artifact_root=self._feature_artifact_root
            )
            bundle = verified_bundle.artifact
            bound = (
                PITArtifactReference(
                    PITArtifactKind.MARKET_DATA_DATASET.value,
                    ArtifactId(str(bundle.dataset_id)),
                    bundle.dataset_hash,
                ),
                *(
                    PITArtifactReference(
                        PITArtifactKind.SOURCE_MANIFEST.value, item_id, digest
                    )
                    for item_id, digest in bundle.source_manifest_references
                ),
            )
            return PITArtifactAuthorityResolution.create(
                reference=PITArtifactReference(
                    kind.value, bundle.bundle_id, bundle.content_hash
                ),
                canonical_schema=bundle.schema_version,
                reader_contract="verified-feature-bundle-v2-package",
                physical_checksums_hash=verified_bundle.checksums_hash,
                data_eligibility=bundle.data_eligibility,
                formal_pit_status=bundle.formal_pit_status.value,
                effective_at=bundle.decision_time,
                available_at=bundle.available_at,
                bound_references=tuple(bound),
                resolved_at=resolved_at,
            )
        if kind is PITArtifactKind.CONFIGURATION:
            configuration = load_controlled_runtime_configuration(package)
            return PITArtifactAuthorityResolution.create(
                reference=PITArtifactReference(
                    kind.value,
                    configuration.configuration_id,
                    configuration.configuration_hash,
                ),
                canonical_schema=configuration.schema_version,
                reader_contract="controlled-runtime-configuration-package-v1",
                physical_checksums_hash=physical_hash,
                resolved_at=resolved_at,
            )
        raise PITArtifactAuthorityUnavailableError(
            f"no canonical Reader for PIT Artifact kind {requested.reference_kind}"
        )


def _resolution_payload(
    *,
    reference: PITArtifactReference,
    canonical_schema: str,
    reader_contract: str,
    physical_checksums_hash: str,
    data_eligibility: DataEligibility | None,
    formal_pit_status: str | None,
    effective_at: datetime | None,
    available_at: datetime | None,
    bound_references: tuple[PITArtifactReference, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "pit-artifact-authority-resolution-v1",
        "reference": reference.to_canonical_dict(),
        "canonical_schema": canonical_schema,
        "reader_contract": reader_contract,
        "physical_checksums_hash": physical_checksums_hash,
        "data_eligibility": (
            None if data_eligibility is None else data_eligibility.value
        ),
        "formal_pit_status": formal_pit_status,
        "effective_at": (
            None if effective_at is None else canonical_datetime(effective_at)
        ),
        "available_at": (
            None if available_at is None else canonical_datetime(available_at)
        ),
        "bound_references": [item.to_canonical_dict() for item in bound_references],
    }


def _package_checksums_hash(package: Path) -> str:
    content = (package / "SHA256SUMS.json").read_bytes()
    return f"sha256:{sha256(content).hexdigest()}"


def _reference_key(item: PITArtifactReference) -> tuple[str, str, str]:
    return item.reference_kind, str(item.artifact_id), item.content_hash


def _optional_time(value: object, label: str) -> datetime | None:
    return None if value is None else parse_utc_second(label, value)


def _object(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PITContractError("PIT Artifact resolution reference must be an object")
    return value


__all__ = [
    "CanonicalPITArtifactAuthorityResolver",
    "PITArtifactAuthorityResolution",
    "PITArtifactAuthorityResolver",
    "PITArtifactAuthorityUnavailableError",
]
