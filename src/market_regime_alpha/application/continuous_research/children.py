"""Auditable references to existing Continuous Research child services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.journal import (
    ChildReferenceDisposition,
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
)
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second


CONTINUOUS_CHILD_REFERENCE_SCHEMA = "continuous-child-reference-v1"


@dataclass(frozen=True, slots=True)
class ContinuousChildReference:
    schema_version: str
    reference_hash: str
    trading_date: date
    run_id: ArtifactId
    tick_id: ArtifactId
    tick_sequence: int
    provider_attempt_id: int
    source_manifest_id: ArtifactId
    source_manifest_hash: str
    evidence_commit_id: ArtifactId
    evidence_commit_hash: str
    decision_id: ArtifactId
    decision_hash: str
    child_kind: ContinuousChildKind
    reference_disposition: ChildReferenceDisposition
    child_run_id: ArtifactId
    child_receipt_id: ArtifactId
    child_receipt_hash: str
    child_artifact_id: ArtifactId | None
    child_artifact_hash: str | None
    input_references: tuple[RuntimeArtifactReference, ...]
    aggregate_input_hash: str
    configuration_references: tuple[RuntimeArtifactReference, ...]
    configuration_set_hash: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.schema_version != CONTINUOUS_CHILD_REFERENCE_SCHEMA:
            raise ValueError("unsupported Continuous Child Reference schema")
        for label, integer_value in (
            ("tick_sequence", self.tick_sequence),
            ("provider_attempt_id", self.provider_attempt_id),
        ):
            if (
                isinstance(integer_value, bool)
                or not isinstance(integer_value, int)
                or integer_value < 1
            ):
                raise ValueError(f"{label} must be a positive integer")
        for label, content_hash in (
            ("reference_hash", self.reference_hash),
            ("source_manifest_hash", self.source_manifest_hash),
            ("evidence_commit_hash", self.evidence_commit_hash),
            ("decision_hash", self.decision_hash),
            ("child_receipt_hash", self.child_receipt_hash),
            ("aggregate_input_hash", self.aggregate_input_hash),
            ("configuration_set_hash", self.configuration_set_hash),
        ):
            require_sha256(label, content_hash)
        if (self.child_artifact_id is None) != (self.child_artifact_hash is None):
            raise ValueError("child Artifact identity and hash must be paired")
        if self.child_artifact_hash is not None:
            require_sha256("child_artifact_hash", self.child_artifact_hash)
        _require_references("input", self.input_references)
        _require_references("configuration", self.configuration_references)
        if not self.input_references:
            raise ValueError("child reference requires input Artifacts")
        if not self.configuration_references:
            raise ValueError("child reference requires configuration versions")
        if canonical_hash(_reference_payload(self.input_references)) != self.aggregate_input_hash:
            raise ValueError("aggregate input hash mismatch")
        if (
            canonical_hash(_reference_payload(self.configuration_references))
            != self.configuration_set_hash
        ):
            raise ValueError("configuration set hash mismatch")
        require_utc_second("created_at", self.created_at)
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        trading_date: date,
        run_id: ArtifactId,
        tick_id: ArtifactId,
        tick_sequence: int,
        provider_attempt_id: int,
        source_manifest_id: ArtifactId,
        source_manifest_hash: str,
        evidence_commit_id: ArtifactId,
        evidence_commit_hash: str,
        decision_id: ArtifactId,
        decision_hash: str,
        child_kind: ContinuousChildKind,
        reference_disposition: ChildReferenceDisposition,
        child_run_id: ArtifactId,
        child_receipt_id: ArtifactId,
        child_receipt_hash: str,
        child_artifact_id: ArtifactId | None,
        child_artifact_hash: str | None,
        input_references: tuple[RuntimeArtifactReference, ...],
        configuration_references: tuple[RuntimeArtifactReference, ...],
        created_at: datetime,
    ) -> ContinuousChildReference:
        inputs = _sorted_references(input_references)
        configurations = _sorted_references(configuration_references)
        aggregate_input_hash = canonical_hash(_reference_payload(inputs))
        configuration_set_hash = canonical_hash(_reference_payload(configurations))
        values: dict[str, Any] = {
            "trading_date": trading_date,
            "run_id": run_id,
            "tick_id": tick_id,
            "tick_sequence": tick_sequence,
            "provider_attempt_id": provider_attempt_id,
            "source_manifest_id": source_manifest_id,
            "source_manifest_hash": source_manifest_hash,
            "evidence_commit_id": evidence_commit_id,
            "evidence_commit_hash": evidence_commit_hash,
            "decision_id": decision_id,
            "decision_hash": decision_hash,
            "child_kind": child_kind,
            "reference_disposition": reference_disposition,
            "child_run_id": child_run_id,
            "child_receipt_id": child_receipt_id,
            "child_receipt_hash": child_receipt_hash,
            "child_artifact_id": child_artifact_id,
            "child_artifact_hash": child_artifact_hash,
            "input_references": inputs,
            "aggregate_input_hash": aggregate_input_hash,
            "configuration_references": configurations,
            "configuration_set_hash": configuration_set_hash,
        }
        digest = canonical_hash(_child_semantic_payload(**values))
        return cls(
            schema_version=CONTINUOUS_CHILD_REFERENCE_SCHEMA,
            reference_hash=digest,
            created_at=created_at,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _child_semantic_payload(
            trading_date=self.trading_date,
            run_id=self.run_id,
            tick_id=self.tick_id,
            tick_sequence=self.tick_sequence,
            provider_attempt_id=self.provider_attempt_id,
            source_manifest_id=self.source_manifest_id,
            source_manifest_hash=self.source_manifest_hash,
            evidence_commit_id=self.evidence_commit_id,
            evidence_commit_hash=self.evidence_commit_hash,
            decision_id=self.decision_id,
            decision_hash=self.decision_hash,
            child_kind=self.child_kind,
            reference_disposition=self.reference_disposition,
            child_run_id=self.child_run_id,
            child_receipt_id=self.child_receipt_id,
            child_receipt_hash=self.child_receipt_hash,
            child_artifact_id=self.child_artifact_id,
            child_artifact_hash=self.child_artifact_hash,
            input_references=self.input_references,
            aggregate_input_hash=self.aggregate_input_hash,
            configuration_references=self.configuration_references,
            configuration_set_hash=self.configuration_set_hash,
        )

    def verify_identity(self) -> None:
        if canonical_hash(self.semantic_payload()) != self.reference_hash:
            raise ValueError("Continuous Child Reference hash mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "reference_hash": self.reference_hash,
            **self.semantic_payload(),
            "created_at": canonical_datetime(self.created_at),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ContinuousChildReference:
        expected = {
            "schema_version",
            "reference_hash",
            "trading_date",
            "run_id",
            "tick_id",
            "tick_sequence",
            "provider_attempt_id",
            "source_manifest_id",
            "source_manifest_hash",
            "evidence_commit_id",
            "evidence_commit_hash",
            "decision_id",
            "decision_hash",
            "child_kind",
            "reference_disposition",
            "child_run_id",
            "child_receipt_id",
            "child_receipt_hash",
            "child_artifact_id",
            "child_artifact_hash",
            "input_references",
            "aggregate_input_hash",
            "configuration_references",
            "configuration_set_hash",
            "created_at",
        }
        if set(payload) != expected:
            raise ValueError("Continuous Child Reference fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            reference_hash=str(payload["reference_hash"]),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            run_id=ArtifactId(str(payload["run_id"])),
            tick_id=ArtifactId(str(payload["tick_id"])),
            tick_sequence=_integer(payload["tick_sequence"], "tick_sequence"),
            provider_attempt_id=_integer(
                payload["provider_attempt_id"], "provider_attempt_id"
            ),
            source_manifest_id=ArtifactId(str(payload["source_manifest_id"])),
            source_manifest_hash=str(payload["source_manifest_hash"]),
            evidence_commit_id=ArtifactId(str(payload["evidence_commit_id"])),
            evidence_commit_hash=str(payload["evidence_commit_hash"]),
            decision_id=ArtifactId(str(payload["decision_id"])),
            decision_hash=str(payload["decision_hash"]),
            child_kind=ContinuousChildKind(str(payload["child_kind"])),
            reference_disposition=ChildReferenceDisposition(
                str(payload["reference_disposition"])
            ),
            child_run_id=ArtifactId(str(payload["child_run_id"])),
            child_receipt_id=ArtifactId(str(payload["child_receipt_id"])),
            child_receipt_hash=str(payload["child_receipt_hash"]),
            child_artifact_id=(
                None
                if payload["child_artifact_id"] is None
                else ArtifactId(str(payload["child_artifact_id"]))
            ),
            child_artifact_hash=(
                None
                if payload["child_artifact_hash"] is None
                else str(payload["child_artifact_hash"])
            ),
            input_references=_references(payload["input_references"]),
            aggregate_input_hash=str(payload["aggregate_input_hash"]),
            configuration_references=_references(
                payload["configuration_references"]
            ),
            configuration_set_hash=str(payload["configuration_set_hash"]),
            created_at=parse_utc_second("created_at", payload["created_at"]),
        )


def _child_semantic_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTINUOUS_CHILD_REFERENCE_SCHEMA,
        "trading_date": values["trading_date"].isoformat(),
        "run_id": str(values["run_id"]),
        "tick_id": str(values["tick_id"]),
        "tick_sequence": values["tick_sequence"],
        "provider_attempt_id": values["provider_attempt_id"],
        "source_manifest_id": str(values["source_manifest_id"]),
        "source_manifest_hash": values["source_manifest_hash"],
        "evidence_commit_id": str(values["evidence_commit_id"]),
        "evidence_commit_hash": values["evidence_commit_hash"],
        "decision_id": str(values["decision_id"]),
        "decision_hash": values["decision_hash"],
        "child_kind": values["child_kind"].value,
        "reference_disposition": values["reference_disposition"].value,
        "child_run_id": str(values["child_run_id"]),
        "child_receipt_id": str(values["child_receipt_id"]),
        "child_receipt_hash": values["child_receipt_hash"],
        "child_artifact_id": (
            None
            if values["child_artifact_id"] is None
            else str(values["child_artifact_id"])
        ),
        "child_artifact_hash": values["child_artifact_hash"],
        "input_references": [
            item.to_canonical_dict() for item in values["input_references"]
        ],
        "aggregate_input_hash": values["aggregate_input_hash"],
        "configuration_references": [
            item.to_canonical_dict() for item in values["configuration_references"]
        ],
        "configuration_set_hash": values["configuration_set_hash"],
    }


def _reference_payload(
    references: tuple[RuntimeArtifactReference, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "continuous-reference-set-v1",
        "references": [item.to_canonical_dict() for item in references],
    }


def _reference_key(reference: RuntimeArtifactReference) -> tuple[str, str, str]:
    return (
        reference.reference_kind,
        str(reference.artifact_id),
        reference.content_hash,
    )


def _sorted_references(
    references: tuple[RuntimeArtifactReference, ...],
) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(sorted(set(references), key=_reference_key))


def _require_references(
    label: str, references: tuple[RuntimeArtifactReference, ...]
) -> None:
    keys = tuple(_reference_key(item) for item in references)
    if keys != tuple(sorted(set(keys))):
        raise ValueError(f"{label} references must be unique and sorted")


def _references(value: object) -> tuple[RuntimeArtifactReference, ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError("references must be an object array")
    return tuple(RuntimeArtifactReference.from_canonical_dict(item) for item in value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


__all__ = ["CONTINUOUS_CHILD_REFERENCE_SCHEMA", "ContinuousChildReference"]
