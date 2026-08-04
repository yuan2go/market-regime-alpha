"""Content-addressed inputs accepted by the canonical lifecycle.

The manifest never embeds an Artifact payload.  Every controlled locator is
bound to an expected object identity, SHA-256 digest, exact Reader kind, and
availability timestamp so orchestration cannot silently substitute data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationReference,
    LifecycleModelVersionReference,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
    configuration_manifest_hash,
    model_version_manifest_hash,
    parse_utc_second,
    require_utc_second,
    validate_lifecycle_object_references,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_unique_text,
)


CANONICAL_LIFECYCLE_INPUT_MANIFEST_SCHEMA = "canonical-lifecycle-input-manifest-v1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


_READER_BY_OBJECT_TYPE: dict[LifecycleObjectType, LifecycleReaderKind] = {
    LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST: (
        LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER
    ),
    LifecycleObjectType.SOURCE_MANIFEST: LifecycleReaderKind.SOURCE_MANIFEST_READER,
    LifecycleObjectType.DAILY_DECISION_ARTIFACT: (
        LifecycleReaderKind.DAILY_DECISION_ARTIFACT_READER
    ),
    LifecycleObjectType.SUPPLEMENTAL_RESEARCH_EVIDENCE: (
        LifecycleReaderKind.SUPPLEMENTAL_RESEARCH_EVIDENCE_READER
    ),
    LifecycleObjectType.PLATFORM_RESEARCH_ARTIFACT: (
        LifecycleReaderKind.PLATFORM_RESEARCH_ARTIFACT_READER
    ),
    LifecycleObjectType.SIGNAL_ARTIFACT: LifecycleReaderKind.SIGNAL_ARTIFACT_READER,
    LifecycleObjectType.PATH_FORECAST_ARTIFACT: (
        LifecycleReaderKind.PATH_FORECAST_ARTIFACT_READER
    ),
    LifecycleObjectType.ENTRY_ASSESSMENT: (
        LifecycleReaderKind.DECISION_LIFECYCLE_REPOSITORY
    ),
    LifecycleObjectType.OPPORTUNITY: (
        LifecycleReaderKind.DECISION_LIFECYCLE_REPOSITORY
    ),
    LifecycleObjectType.THESIS: LifecycleReaderKind.DECISION_LIFECYCLE_REPOSITORY,
    LifecycleObjectType.PORTFOLIO_DECISION: (
        LifecycleReaderKind.PORTFOLIO_RISK_REPOSITORY
    ),
    LifecycleObjectType.RISK_DECISION: (
        LifecycleReaderKind.PORTFOLIO_RISK_REPOSITORY
    ),
    LifecycleObjectType.RISK_REDUCING_DECISION: (
        LifecycleReaderKind.RISK_REDUCTION_REPOSITORY
    ),
    LifecycleObjectType.OPERATIONAL_EXIT_DIRECTIVE: (
        LifecycleReaderKind.OPERATIONAL_EXIT_DIRECTIVE_REPOSITORY
    ),
    LifecycleObjectType.REDUCING_EXECUTION_OBSERVATION: (
        LifecycleReaderKind.REDUCING_EXECUTION_OBSERVATION_READER
    ),
    LifecycleObjectType.SYMBOL_TRADING_SESSION_STATUS_SET: (
        LifecycleReaderKind.SYMBOL_TRADING_SESSION_STATUS_READER
    ),
    LifecycleObjectType.RISK_REDUCTION_CONFIRMATION_POLICY: (
        LifecycleReaderKind.RISK_REDUCTION_CONFIRMATION_POLICY_READER
    ),
    LifecycleObjectType.RISK_REDUCTION_CONFIRMATION: (
        LifecycleReaderKind.RISK_REDUCTION_REPOSITORY
    ),
    LifecycleObjectType.MANUAL_TRADE: LifecycleReaderKind.MANUAL_TRADE_REPOSITORY,
    LifecycleObjectType.FILL: LifecycleReaderKind.MANUAL_FILL_LEDGER,
    LifecycleObjectType.POSITION_SNAPSHOT: (
        LifecycleReaderKind.POSITION_SNAPSHOT_REPOSITORY
    ),
    LifecycleObjectType.POSITION_BOOK: LifecycleReaderKind.POSITION_BOOK_REPOSITORY,
    LifecycleObjectType.TRADING_CALENDAR_ARTIFACT: (
        LifecycleReaderKind.TRADING_CALENDAR_ARTIFACT_READER
    ),
    LifecycleObjectType.THESIS_HEALTH_OBSERVATION: (
        LifecycleReaderKind.THESIS_HEALTH_REPOSITORY
    ),
    LifecycleObjectType.HOLDING_ASSESSMENT: (
        LifecycleReaderKind.HOLDING_ASSESSMENT_REPOSITORY
    ),
    LifecycleObjectType.EXIT_ASSESSMENT: (
        LifecycleReaderKind.EXIT_ASSESSMENT_REPOSITORY
    ),
    LifecycleObjectType.OUTCOME_REVIEW: (
        LifecycleReaderKind.OUTCOME_REVIEW_REPOSITORY
    ),
    LifecycleObjectType.FEATURE_ARTIFACT: LifecycleReaderKind.FEATURE_ARTIFACT_READER,
    LifecycleObjectType.MODEL_COMPARISON_REPORT: (
        LifecycleReaderKind.MODEL_COMPARISON_REPORT_READER
    ),
}

_LOCATOR_REQUIRED_READERS = frozenset(
    {
        LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER,
        LifecycleReaderKind.SOURCE_MANIFEST_READER,
        LifecycleReaderKind.DAILY_DECISION_ARTIFACT_READER,
        LifecycleReaderKind.SUPPLEMENTAL_RESEARCH_EVIDENCE_READER,
        LifecycleReaderKind.PLATFORM_RESEARCH_ARTIFACT_READER,
        LifecycleReaderKind.SIGNAL_ARTIFACT_READER,
        LifecycleReaderKind.PATH_FORECAST_ARTIFACT_READER,
        LifecycleReaderKind.TRADING_CALENDAR_ARTIFACT_READER,
        LifecycleReaderKind.REDUCING_EXECUTION_OBSERVATION_READER,
        LifecycleReaderKind.SYMBOL_TRADING_SESSION_STATUS_READER,
        LifecycleReaderKind.RISK_REDUCTION_CONFIRMATION_POLICY_READER,
        LifecycleReaderKind.FEATURE_ARTIFACT_READER,
        LifecycleReaderKind.MODEL_COMPARISON_REPORT_READER,
    }
)


@dataclass(frozen=True, slots=True)
class LifecycleAuthorityCeiling:
    """Explicit non-inflating authority inherited by every lifecycle stage."""

    data_eligibility: DataEligibility = DataEligibility.EXPLORATORY
    formal_pit: str = "FORMAL_PIT_NOT_ESTABLISHED"
    formal_oos_alpha: str = "FORMAL_OOS_ALPHA_NOT_ESTABLISHED"
    trading_authority: str = "TRADING_AUTHORITY_NOT_GRANTED"
    automatic_order_execution: bool = False
    broker_integration_proven: bool = False
    entry_model_empirically_validated: bool = False
    production_ready: bool = False

    def __post_init__(self) -> None:
        if self.data_eligibility not in {
            DataEligibility.UNQUALIFIED,
            DataEligibility.EXPLORATORY,
        }:
            raise ValueError("lifecycle input authority cannot exceed EXPLORATORY")
        expected = {
            "formal_pit": "FORMAL_PIT_NOT_ESTABLISHED",
            "formal_oos_alpha": "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "trading_authority": "TRADING_AUTHORITY_NOT_GRANTED",
        }
        for name, value in expected.items():
            if getattr(self, name) != value:
                raise ValueError(f"lifecycle input authority cannot inflate {name}")
        for name in (
            "automatic_order_execution",
            "broker_integration_proven",
            "entry_model_empirically_validated",
            "production_ready",
        ):
            value = getattr(self, name)
            if not isinstance(value, bool) or value:
                raise ValueError(f"{name} must remain false")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "data_eligibility": self.data_eligibility.value,
            "formal_pit": self.formal_pit,
            "formal_oos_alpha": self.formal_oos_alpha,
            "trading_authority": self.trading_authority,
            "automatic_order_execution": self.automatic_order_execution,
            "broker_integration_proven": self.broker_integration_proven,
            "entry_model_empirically_validated": (
                self.entry_model_empirically_validated
            ),
            "production_ready": self.production_ready,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> LifecycleAuthorityCeiling:
        expected = {
            "data_eligibility",
            "formal_pit",
            "formal_oos_alpha",
            "trading_authority",
            "automatic_order_execution",
            "broker_integration_proven",
            "entry_model_empirically_validated",
            "production_ready",
        }
        if set(payload) != expected:
            raise ValueError("LifecycleAuthorityCeiling fields mismatch")
        return cls(
            data_eligibility=DataEligibility(_text(payload, "data_eligibility")),
            formal_pit=_text(payload, "formal_pit"),
            formal_oos_alpha=_text(payload, "formal_oos_alpha"),
            trading_authority=_text(payload, "trading_authority"),
            automatic_order_execution=_boolean(payload, "automatic_order_execution"),
            broker_integration_proven=_boolean(payload, "broker_integration_proven"),
            entry_model_empirically_validated=_boolean(
                payload, "entry_model_empirically_validated"
            ),
            production_ready=_boolean(payload, "production_ready"),
        )


@dataclass(frozen=True, slots=True)
class CanonicalLifecycleInputManifest:
    manifest_id: ArtifactId
    content_hash: str
    decision_date: date
    as_of_time: datetime
    created_at: datetime
    input_references: tuple[LifecycleObjectReference, ...]
    configuration_references: tuple[LifecycleConfigurationReference, ...]
    configuration_manifest_hash: str
    model_references: tuple[LifecycleModelVersionReference, ...]
    model_version_manifest_hash: str
    authority_ceiling: LifecycleAuthorityCeiling
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.manifest_id, ArtifactId):
            raise TypeError("manifest_id must be an ArtifactId")
        require_sha256("content_hash", self.content_hash)
        if type(self.decision_date) is not date:
            raise TypeError("decision_date must be a date")
        require_utc_second("as_of_time", self.as_of_time)
        if self.as_of_time.astimezone(_SHANGHAI).date() != self.decision_date:
            raise ValueError("decision_date must match the Asia/Shanghai as-of date")
        require_utc_second("created_at", self.created_at)
        if self.created_at < self.as_of_time:
            raise ValueError("input manifest cannot predate as_of_time")
        if not self.input_references:
            raise ValueError("input_references must not be empty")
        validate_lifecycle_object_references(
            "input_references", self.input_references
        )
        for reference in self.input_references:
            validate_lifecycle_reader_binding(reference)
            validate_lifecycle_locator_policy(reference)
            if reference.available_at > self.as_of_time:
                raise ValueError("input was not available by as_of_time")
        root_count = sum(
            reference.object_type
            is LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST
            for reference in self.input_references
        )
        if root_count != 1:
            raise ValueError("manifest requires exactly one composite operational root")
        if not any(
            reference.object_type is LifecycleObjectType.SOURCE_MANIFEST
            for reference in self.input_references
        ):
            raise ValueError("manifest must bind at least one source manifest")
        expected_configuration_hash = configuration_manifest_hash(
            self.configuration_references
        )
        require_sha256("configuration_manifest_hash", self.configuration_manifest_hash)
        if self.configuration_manifest_hash != expected_configuration_hash:
            raise ValueError("configuration manifest hash mismatch")
        _reject_version_reference_ambiguity(
            "configuration references", self.configuration_references
        )
        expected_model_hash = model_version_manifest_hash(self.model_references)
        require_sha256("model_version_manifest_hash", self.model_version_manifest_hash)
        if self.model_version_manifest_hash != expected_model_hash:
            raise ValueError("model version manifest hash mismatch")
        _reject_version_reference_ambiguity("model references", self.model_references)
        if not isinstance(self.authority_ceiling, LifecycleAuthorityCeiling):
            raise TypeError("authority_ceiling must be a LifecycleAuthorityCeiling")
        if not isinstance(self.limitations, tuple):
            raise TypeError("limitations must be a tuple")
        require_unique_text("limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("limitations must be sorted")
        expected_hash = canonical_hash(self.semantic_payload())
        expected_id = ArtifactId(
            f"canonical-lifecycle-input-{expected_hash.split(':', 1)[1][:24]}"
        )
        if self.content_hash != expected_hash or self.manifest_id != expected_id:
            raise ValueError("CanonicalLifecycleInputManifest identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        decision_date: date,
        as_of_time: datetime,
        created_at: datetime,
        input_references: tuple[LifecycleObjectReference, ...],
        configuration_references: tuple[LifecycleConfigurationReference, ...],
        model_references: tuple[LifecycleModelVersionReference, ...],
        authority_ceiling: LifecycleAuthorityCeiling,
        limitations: tuple[str, ...],
    ) -> CanonicalLifecycleInputManifest:
        ordered_inputs = tuple(sorted(input_references, key=lambda item: item.sort_key))
        ordered_configurations = tuple(
            sorted(configuration_references, key=lambda item: item.sort_key)
        )
        ordered_models = tuple(sorted(model_references, key=lambda item: item.sort_key))
        ordered_limitations = tuple(sorted(limitations))
        configuration_hash = configuration_manifest_hash(ordered_configurations)
        model_hash = model_version_manifest_hash(ordered_models)
        semantic = cls.semantic_payload_for(
            decision_date=decision_date,
            as_of_time=as_of_time,
            created_at=created_at,
            input_references=ordered_inputs,
            configuration_references=ordered_configurations,
            configuration_manifest_hash=configuration_hash,
            model_references=ordered_models,
            model_version_manifest_hash=model_hash,
            authority_ceiling=authority_ceiling,
            limitations=ordered_limitations,
        )
        digest = canonical_hash(semantic)
        return cls(
            manifest_id=ArtifactId(
                f"canonical-lifecycle-input-{digest.split(':', 1)[1][:24]}"
            ),
            content_hash=digest,
            decision_date=decision_date,
            as_of_time=as_of_time,
            created_at=created_at,
            input_references=ordered_inputs,
            configuration_references=ordered_configurations,
            configuration_manifest_hash=configuration_hash,
            model_references=ordered_models,
            model_version_manifest_hash=model_hash,
            authority_ceiling=authority_ceiling,
            limitations=ordered_limitations,
        )

    @staticmethod
    def semantic_payload_for(**values: Any) -> dict[str, Any]:
        return {
            "schema_version": CANONICAL_LIFECYCLE_INPUT_MANIFEST_SCHEMA,
            "decision_date": values["decision_date"].isoformat(),
            "as_of_time": canonical_datetime(values["as_of_time"]),
            "created_at": canonical_datetime(values["created_at"]),
            "input_references": [
                item.to_canonical_dict() for item in values["input_references"]
            ],
            "configuration_references": [
                item.to_canonical_dict()
                for item in values["configuration_references"]
            ],
            "configuration_manifest_hash": values["configuration_manifest_hash"],
            "model_references": [
                item.to_canonical_dict() for item in values["model_references"]
            ],
            "model_version_manifest_hash": values["model_version_manifest_hash"],
            "authority_ceiling": values["authority_ceiling"].to_canonical_dict(),
            "limitations": list(values["limitations"]),
        }

    def semantic_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            decision_date=self.decision_date,
            as_of_time=self.as_of_time,
            created_at=self.created_at,
            input_references=self.input_references,
            configuration_references=self.configuration_references,
            configuration_manifest_hash=self.configuration_manifest_hash,
            model_references=self.model_references,
            model_version_manifest_hash=self.model_version_manifest_hash,
            authority_ceiling=self.authority_ceiling,
            limitations=self.limitations,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": str(self.manifest_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CanonicalLifecycleInputManifest:
        expected = {
            "schema_version", "manifest_id", "content_hash", "decision_date",
            "as_of_time", "created_at", "input_references",
            "configuration_references", "configuration_manifest_hash",
            "model_references", "model_version_manifest_hash", "authority_ceiling",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("CanonicalLifecycleInputManifest fields mismatch")
        if payload["schema_version"] != CANONICAL_LIFECYCLE_INPUT_MANIFEST_SCHEMA:
            raise ValueError("unsupported CanonicalLifecycleInputManifest schema")
        return cls(
            manifest_id=ArtifactId(_text(payload, "manifest_id")),
            content_hash=_text(payload, "content_hash"),
            decision_date=_date_value(payload["decision_date"], "decision_date"),
            as_of_time=parse_utc_second("as_of_time", payload["as_of_time"]),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            input_references=tuple(
                LifecycleObjectReference.from_canonical_dict(item)
                for item in _object_array(payload, "input_references")
            ),
            configuration_references=tuple(
                LifecycleConfigurationReference.from_canonical_dict(item)
                for item in _object_array(payload, "configuration_references")
            ),
            configuration_manifest_hash=_text(payload, "configuration_manifest_hash"),
            model_references=tuple(
                LifecycleModelVersionReference.from_canonical_dict(item)
                for item in _object_array(payload, "model_references")
            ),
            model_version_manifest_hash=_text(payload, "model_version_manifest_hash"),
            authority_ceiling=LifecycleAuthorityCeiling.from_canonical_dict(
                _object(payload, "authority_ceiling")
            ),
            limitations=_string_array(payload, "limitations"),
        )


@dataclass(frozen=True, slots=True)
class CanonicalLifecycleInputManifestReader:
    """Strict JSON Reader that verifies both package expectation and content ID."""

    def read(
        self,
        path: Path,
        *,
        expected_manifest_id: ArtifactId | None = None,
        expected_content_hash: str | None = None,
    ) -> CanonicalLifecycleInputManifest:
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")
        if expected_manifest_id is not None and not isinstance(
            expected_manifest_id, ArtifactId
        ):
            raise TypeError("expected_manifest_id must be an ArtifactId or None")
        if expected_content_hash is not None:
            require_sha256("expected_content_hash", expected_content_hash)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"cannot read lifecycle input manifest: {path}") from exc
        try:
            payload = json.loads(raw, object_pairs_hook=_reject_duplicate_json_keys)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError("lifecycle input manifest is not strict JSON") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("lifecycle input manifest root must be an object")
        manifest = CanonicalLifecycleInputManifest.from_canonical_dict(payload)
        if expected_manifest_id is not None and manifest.manifest_id != expected_manifest_id:
            raise ValueError("lifecycle input manifest expected identity mismatch")
        if (
            expected_content_hash is not None
            and manifest.content_hash != expected_content_hash
        ):
            raise ValueError("lifecycle input manifest expected hash mismatch")
        return manifest


def validate_lifecycle_reader_binding(
    reference: LifecycleObjectReference,
) -> None:
    """Reject a generic or incorrect Reader for a typed lifecycle object."""

    if not isinstance(reference, LifecycleObjectReference):
        raise TypeError("reference must be a LifecycleObjectReference")
    expected = _READER_BY_OBJECT_TYPE[reference.object_type]
    if reference.reader_kind is not expected:
        raise ValueError(
            f"{reference.object_type.value} requires Reader kind {expected.value}"
        )


def validate_lifecycle_locator_policy(
    reference: LifecycleObjectReference,
) -> None:
    """Require locators only for file/package Readers, never injected repositories."""

    if not isinstance(reference, LifecycleObjectReference):
        raise TypeError("reference must be a LifecycleObjectReference")
    locator_required = reference.reader_kind in _LOCATOR_REQUIRED_READERS
    if locator_required and reference.locator is None:
        raise ValueError(f"{reference.reader_kind.value} requires a controlled locator")
    if not locator_required and reference.locator is not None:
        raise ValueError(
            f"{reference.reader_kind.value} uses an injected repository and forbids locator"
        )


def _reject_version_reference_ambiguity(
    label: str,
    references: tuple[
        LifecycleConfigurationReference | LifecycleModelVersionReference, ...
    ],
) -> None:
    ids: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for reference in references:
        identity = (
            str(reference.configuration_id)
            if isinstance(reference, LifecycleConfigurationReference)
            else str(reference.model_id)
        )
        prior_hash = ids.setdefault(identity, reference.content_hash)
        if prior_hash != reference.content_hash:
            raise ValueError(f"{label} maps one ID to conflicting hashes")
        prior_id = hashes.setdefault(reference.content_hash, identity)
        if prior_id != identity:
            raise ValueError(f"{label} maps one hash to different IDs")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload[key]
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _object(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload[key]
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _object_array(
    payload: Mapping[str, Any], key: str
) -> tuple[Mapping[str, Any], ...]:
    value = payload[key]
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{key} must be an array of objects")
    return tuple(value)


def _string_array(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload[key]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be an array of strings")
    return tuple(value)


def _date_value(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{label} is not canonical")
    return parsed
