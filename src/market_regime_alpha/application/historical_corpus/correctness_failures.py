"""Typed failure-detail artifacts under Historical Evidence authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any, Mapping

from market_regime_alpha.application.research_evaluation.target_semantics import (
    TargetSemanticResult,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import (
    canonical_decimal,
    parse_canonical_decimal,
)


FAILURE_DETAIL_SCHEMA = "alpha-correctness-failure-detail/v1"
FAILURE_INDEX_SCHEMA = "alpha-correctness-failure-index/v1"
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True, slots=True)
class FailureSourceBinding:
    source_role: str
    reference: ValidationArtifactReference

    def __post_init__(self) -> None:
        require_text("source_role", self.source_role)

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "source_role": self.source_role,
            "reference": self.reference.to_canonical_dict(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> FailureSourceBinding:
        return cls(
            source_role=str(payload["source_role"]),
            reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["reference"])
            ),
        )


@dataclass(frozen=True, slots=True)
class AlphaCorrectnessFailureDetail:
    detail_id: ArtifactId
    detail_hash: str
    decision_session: date
    decision_time: datetime
    target_session: date
    target_window_end: datetime
    symbol: str
    classification: str
    discrepancy_code: str
    predecessor_label_reference: ValidationArtifactReference
    predecessor_component_reference: ValidationArtifactReference
    predecessor_availability_status: str
    predecessor_decision_reference_price: Decimal | None
    predecessor_checkpoint_price: Decimal | None
    predecessor_checkpoint_return: Decimal | None
    predecessor_mfe: Decimal | None
    predecessor_mae: Decimal | None
    materializer_result: TargetSemanticResult
    checker_result: TargetSemanticResult
    source_bindings: tuple[FailureSourceBinding, ...]
    normalization_revision: str
    semantic_revision: str
    analysis_code_sha: str
    schema_version: str = FAILURE_DETAIL_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != FAILURE_DETAIL_SCHEMA:
            raise ValueError("unsupported correctness failure-detail schema")
        require_sha256("detail_hash", self.detail_hash)
        for label, value in (
            ("symbol", self.symbol),
            ("classification", self.classification),
            ("discrepancy_code", self.discrepancy_code),
            ("predecessor_availability_status", self.predecessor_availability_status),
            ("normalization_revision", self.normalization_revision),
            ("semantic_revision", self.semantic_revision),
        ):
            require_text(label, value)
        if not _GIT_SHA.fullmatch(self.analysis_code_sha):
            raise ValueError("failure detail analysis code must be an exact Git SHA")
        if (
            self.decision_time.tzinfo is None
            or self.target_window_end.tzinfo is None
            or self.target_session <= self.decision_session
            or self.target_window_end <= self.decision_time
        ):
            raise ValueError("failure detail temporal boundary is invalid")
        if (
            self.materializer_result.symbol != self.symbol
            or self.checker_result.symbol != self.symbol
            or self.materializer_result.decision_time != self.decision_time
            or self.checker_result.decision_time != self.decision_time
            or self.materializer_result.target_session != self.target_session
            or self.checker_result.target_session != self.target_session
        ):
            raise ValueError("failure detail semantic projection drifted")
        ordered = tuple(
            sorted(
                self.source_bindings,
                key=lambda item: (
                    item.source_role,
                    item.reference.artifact_kind,
                    str(item.reference.artifact_id),
                    item.reference.content_hash,
                ),
            )
        )
        if self.source_bindings != ordered or len(ordered) != len(set(ordered)):
            raise ValueError("failure detail source bindings must be unique and sorted")
        digest = canonical_hash(self.identity_payload())
        if digest != self.detail_hash or self.detail_id != ArtifactId(
            f"alpha-correctness-failure-detail:{digest[7:]}"
        ):
            raise ValueError("correctness failure-detail identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> AlphaCorrectnessFailureDetail:
        normalized = dict(values)
        normalized["source_bindings"] = tuple(
            sorted(
                values["source_bindings"],
                key=lambda item: (
                    item.source_role,
                    item.reference.artifact_kind,
                    str(item.reference.artifact_id),
                    item.reference.content_hash,
                ),
            )
        )
        normalized.setdefault("schema_version", FAILURE_DETAIL_SCHEMA)
        digest = canonical_hash(_detail_payload(**normalized))
        return cls(
            detail_id=ArtifactId(
                f"alpha-correctness-failure-detail:{digest[7:]}"
            ),
            detail_hash=digest,
            **normalized,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "ALPHA_CORRECTNESS_FAILURE_DETAIL",
            self.detail_id,
            self.detail_hash,
        )

    def identity_payload(self) -> dict[str, object]:
        return _detail_payload(
            **{
                name: getattr(self, name)
                for name in _detail_value_names()
            }
        )

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "detail_id": str(self.detail_id),
            "detail_hash": self.detail_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> AlphaCorrectnessFailureDetail:
        return cls(
            detail_id=ArtifactId(str(payload["detail_id"])),
            detail_hash=str(payload["detail_hash"]),
            decision_session=date.fromisoformat(str(payload["decision_session"])),
            decision_time=_instant(payload["decision_time"]),
            target_session=date.fromisoformat(str(payload["target_session"])),
            target_window_end=_instant(payload["target_window_end"]),
            symbol=str(payload["symbol"]),
            classification=str(payload["classification"]),
            discrepancy_code=str(payload["discrepancy_code"]),
            predecessor_label_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["predecessor_label_reference"])
            ),
            predecessor_component_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["predecessor_component_reference"])
            ),
            predecessor_availability_status=str(
                payload["predecessor_availability_status"]
            ),
            predecessor_decision_reference_price=_optional_decimal(
                payload["predecessor_decision_reference_price"]
            ),
            predecessor_checkpoint_price=_optional_decimal(
                payload["predecessor_checkpoint_price"]
            ),
            predecessor_checkpoint_return=_optional_decimal(
                payload["predecessor_checkpoint_return"]
            ),
            predecessor_mfe=_optional_decimal(payload["predecessor_mfe"]),
            predecessor_mae=_optional_decimal(payload["predecessor_mae"]),
            materializer_result=TargetSemanticResult.from_canonical_dict(
                _mapping(payload["materializer_result"])
            ),
            checker_result=TargetSemanticResult.from_canonical_dict(
                _mapping(payload["checker_result"])
            ),
            source_bindings=tuple(
                FailureSourceBinding.from_canonical_dict(item)
                for item in _mappings(payload["source_bindings"])
            ),
            normalization_revision=str(payload["normalization_revision"]),
            semantic_revision=str(payload["semantic_revision"]),
            analysis_code_sha=str(payload["analysis_code_sha"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class AlphaCorrectnessFailureIndex:
    index_id: ArtifactId
    index_hash: str
    source_run_reference: ValidationArtifactReference
    source_evidence_reference: ValidationArtifactReference
    experiment_reference: ValidationArtifactReference
    target_protocol_reference: ValidationArtifactReference
    calendar_reference: ValidationArtifactReference
    raw_owner_reference: ValidationArtifactReference
    normalized_owner_reference: ValidationArtifactReference
    normalization_revision: str
    analysis_code_sha: str
    semantic_revision: str
    details: tuple[AlphaCorrectnessFailureDetail, ...]
    created_at: datetime
    schema_version: str = FAILURE_INDEX_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != FAILURE_INDEX_SCHEMA:
            raise ValueError("unsupported correctness failure-index schema")
        require_sha256("index_hash", self.index_hash)
        if self.source_run_reference.artifact_kind != "HISTORICAL_RESEARCH_RUN":
            raise ValueError("failure index requires a Historical run")
        if self.source_evidence_reference.artifact_kind != (
            "HISTORICAL_ALPHA_CORRECTNESS_EVIDENCE"
        ):
            raise ValueError("failure index requires correctness Evidence")
        expected_kinds = (
            (self.experiment_reference, "RESEARCH_EXPERIMENT_DEFINITION"),
            (self.target_protocol_reference, "OUTCOME_TARGET_PROTOCOL"),
            (self.calendar_reference, "TRADING_CALENDAR"),
            (self.raw_owner_reference, "RAW_PROVIDER_ARCHIVE"),
            (self.normalized_owner_reference, "NORMALIZED_DATASET"),
        )
        if any(item.artifact_kind != kind for item, kind in expected_kinds):
            raise ValueError("failure index owner kind mismatch")
        require_text("normalization_revision", self.normalization_revision)
        require_text("semantic_revision", self.semantic_revision)
        if not _GIT_SHA.fullmatch(self.analysis_code_sha):
            raise ValueError("failure index analysis code must be an exact Git SHA")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("failure index creation time must be timezone-aware")
        ordered = tuple(
            sorted(
                self.details,
                key=lambda item: (
                    item.decision_session,
                    item.symbol,
                    str(item.detail_id),
                ),
            )
        )
        if self.details != ordered or len(ordered) != len(set(ordered)):
            raise ValueError("failure index details must be unique and sorted")
        if any(
            item.normalization_revision != self.normalization_revision
            or item.semantic_revision != self.semantic_revision
            or item.analysis_code_sha != self.analysis_code_sha
            for item in self.details
        ):
            raise ValueError("failure detail revision drifted from its index")
        digest = canonical_hash(self.identity_payload())
        if digest != self.index_hash or self.index_id != ArtifactId(
            f"alpha-correctness-failure-index:{digest[7:]}"
        ):
            raise ValueError("correctness failure-index identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> AlphaCorrectnessFailureIndex:
        normalized = dict(values)
        normalized["details"] = tuple(
            sorted(
                values["details"],
                key=lambda item: (
                    item.decision_session,
                    item.symbol,
                    str(item.detail_id),
                ),
            )
        )
        normalized.setdefault("schema_version", FAILURE_INDEX_SCHEMA)
        digest = canonical_hash(_index_payload(**normalized))
        return cls(
            index_id=ArtifactId(f"alpha-correctness-failure-index:{digest[7:]}"),
            index_hash=digest,
            **normalized,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "ALPHA_CORRECTNESS_FAILURE_INDEX", self.index_id, self.index_hash
        )

    def identity_payload(self) -> dict[str, object]:
        return _index_payload(
            source_run_reference=self.source_run_reference,
            source_evidence_reference=self.source_evidence_reference,
            experiment_reference=self.experiment_reference,
            target_protocol_reference=self.target_protocol_reference,
            calendar_reference=self.calendar_reference,
            raw_owner_reference=self.raw_owner_reference,
            normalized_owner_reference=self.normalized_owner_reference,
            normalization_revision=self.normalization_revision,
            analysis_code_sha=self.analysis_code_sha,
            semantic_revision=self.semantic_revision,
            details=self.details,
            created_at=self.created_at,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "index_id": str(self.index_id),
            "index_hash": self.index_hash,
            "detail_count": len(self.details),
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> AlphaCorrectnessFailureIndex:
        details = tuple(
            AlphaCorrectnessFailureDetail.from_canonical_dict(item)
            for item in _mappings(payload["details"])
        )
        if int(payload["detail_count"]) != len(details):
            raise ValueError("failure index detail count mismatch")
        return cls(
            index_id=ArtifactId(str(payload["index_id"])),
            index_hash=str(payload["index_hash"]),
            source_run_reference=_reference(payload["source_run_reference"]),
            source_evidence_reference=_reference(
                payload["source_evidence_reference"]
            ),
            experiment_reference=_reference(payload["experiment_reference"]),
            target_protocol_reference=_reference(
                payload["target_protocol_reference"]
            ),
            calendar_reference=_reference(payload["calendar_reference"]),
            raw_owner_reference=_reference(payload["raw_owner_reference"]),
            normalized_owner_reference=_reference(
                payload["normalized_owner_reference"]
            ),
            normalization_revision=str(payload["normalization_revision"]),
            analysis_code_sha=str(payload["analysis_code_sha"]),
            semantic_revision=str(payload["semantic_revision"]),
            details=details,
            created_at=_instant(payload["created_at"]),
            schema_version=str(payload["schema_version"]),
        )


def _detail_value_names() -> tuple[str, ...]:
    return (
        "decision_session",
        "decision_time",
        "target_session",
        "target_window_end",
        "symbol",
        "classification",
        "discrepancy_code",
        "predecessor_label_reference",
        "predecessor_component_reference",
        "predecessor_availability_status",
        "predecessor_decision_reference_price",
        "predecessor_checkpoint_price",
        "predecessor_checkpoint_return",
        "predecessor_mfe",
        "predecessor_mae",
        "materializer_result",
        "checker_result",
        "source_bindings",
        "normalization_revision",
        "semantic_revision",
        "analysis_code_sha",
        "schema_version",
    )


def _detail_payload(**values: Any) -> dict[str, object]:
    return {
        "schema_version": values["schema_version"],
        "decision_session": values["decision_session"].isoformat(),
        "decision_time": canonical_datetime(values["decision_time"]),
        "target_session": values["target_session"].isoformat(),
        "target_window_end": canonical_datetime(values["target_window_end"]),
        "symbol": values["symbol"],
        "classification": values["classification"],
        "discrepancy_code": values["discrepancy_code"],
        "predecessor_label_reference": values[
            "predecessor_label_reference"
        ].to_canonical_dict(),
        "predecessor_component_reference": values[
            "predecessor_component_reference"
        ].to_canonical_dict(),
        "predecessor_availability_status": values[
            "predecessor_availability_status"
        ],
        "predecessor_decision_reference_price": _decimal(
            values["predecessor_decision_reference_price"]
        ),
        "predecessor_checkpoint_price": _decimal(
            values["predecessor_checkpoint_price"]
        ),
        "predecessor_checkpoint_return": _decimal(
            values["predecessor_checkpoint_return"]
        ),
        "predecessor_mfe": _decimal(values["predecessor_mfe"]),
        "predecessor_mae": _decimal(values["predecessor_mae"]),
        "materializer_result": values["materializer_result"].to_canonical_dict(),
        "checker_result": values["checker_result"].to_canonical_dict(),
        "source_bindings": [
            item.to_canonical_dict() for item in values["source_bindings"]
        ],
        "normalization_revision": values["normalization_revision"],
        "semantic_revision": values["semantic_revision"],
        "analysis_code_sha": values["analysis_code_sha"],
    }


def _index_payload(**values: Any) -> dict[str, object]:
    return {
        "schema_version": values["schema_version"],
        "source_run_reference": values[
            "source_run_reference"
        ].to_canonical_dict(),
        "source_evidence_reference": values[
            "source_evidence_reference"
        ].to_canonical_dict(),
        "experiment_reference": values["experiment_reference"].to_canonical_dict(),
        "target_protocol_reference": values[
            "target_protocol_reference"
        ].to_canonical_dict(),
        "calendar_reference": values["calendar_reference"].to_canonical_dict(),
        "raw_owner_reference": values["raw_owner_reference"].to_canonical_dict(),
        "normalized_owner_reference": values[
            "normalized_owner_reference"
        ].to_canonical_dict(),
        "normalization_revision": values["normalization_revision"],
        "analysis_code_sha": values["analysis_code_sha"],
        "semantic_revision": values["semantic_revision"],
        "details": [item.to_canonical_dict() for item in values["details"]],
        "created_at": canonical_datetime(values["created_at"]),
    }


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else canonical_decimal(value)


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else parse_canonical_decimal("value", value)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("correctness failure payload must be an object")
    return value


def _mappings(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise TypeError("correctness failure payload must be an object array")
    return tuple(_mapping(item) for item in value)


def _reference(value: object) -> ValidationArtifactReference:
    return ValidationArtifactReference.from_canonical_dict(_mapping(value))


def _instant(value: object) -> datetime:
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("correctness failure instant must be timezone-aware")
    return result


__all__ = [
    "AlphaCorrectnessFailureDetail",
    "AlphaCorrectnessFailureIndex",
    "FAILURE_DETAIL_SCHEMA",
    "FAILURE_INDEX_SCHEMA",
    "FailureSourceBinding",
]
