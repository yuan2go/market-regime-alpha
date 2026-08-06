"""Deterministic create, resume, and replay commands for the lifecycle runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationReference,
    LifecycleModelVersionReference,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleRun,
    LifecycleRunId,
    configuration_manifest_hash,
    model_version_manifest_hash,
    parse_utc_second,
    require_utc_second,
    validate_lifecycle_object_references,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    validate_lifecycle_locator_policy,
    validate_lifecycle_reader_binding,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunType,
    LifecycleStageName,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)


_SHANGHAI = ZoneInfo("Asia/Shanghai")
_RISK_CONTINUATION_REQUIRED_TYPES = frozenset(
    {
        LifecycleObjectType.RISK_REDUCING_DECISION,
        LifecycleObjectType.POSITION_BOOK,
        LifecycleObjectType.OPERATIONAL_EXIT_DIRECTIVE,
        LifecycleObjectType.TRADING_CALENDAR_ARTIFACT,
        LifecycleObjectType.THESIS_HEALTH_OBSERVATION,
        LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST,
        LifecycleObjectType.REDUCING_EXECUTION_OBSERVATION,
        LifecycleObjectType.SYMBOL_TRADING_SESSION_STATUS_SET,
        LifecycleObjectType.RISK_REDUCTION_CONFIRMATION_POLICY,
    }
)

_CONTROLLED_DECISION_TIME_REQUIRED_TYPES = frozenset(
    {
        LifecycleObjectType.MARKET_DATA_DATASET,
        LifecycleObjectType.FEATURE_BUNDLE,
        LifecycleObjectType.OPERATIONAL_UNIVERSE,
        LifecycleObjectType.STATIC_UNIVERSE_FEATURE_BUNDLE,
        LifecycleObjectType.CANDIDATE_INTRADAY_FEATURE_OVERLAY,
        LifecycleObjectType.SOURCE_MANIFEST,
        LifecycleObjectType.SUPPLEMENTAL_RESEARCH_EVIDENCE,
        LifecycleObjectType.TRADING_CALENDAR_ARTIFACT,
    }
)


@dataclass(frozen=True, slots=True)
class CanonicalLifecycleCommand:
    """One evidence-bound lifecycle request plus non-semantic execution controls."""

    SCHEMA_VERSION = "canonical-lifecycle-command-v3"
    LEGACY_SCHEMA_VERSION = "canonical-lifecycle-command-v2"

    run_type: LifecycleRunType
    decision_date: date
    as_of_time: datetime
    idempotency_key: str
    input_manifest_id: ArtifactId | None
    input_content_hash: str | None
    input_manifest_locator: Path | None
    input_references: tuple[LifecycleObjectReference, ...]
    configuration_references: tuple[LifecycleConfigurationReference, ...]
    model_references: tuple[LifecycleModelVersionReference, ...]
    stop_after_stage: LifecycleStageName | None
    output_directory: Path
    resume_run_id: LifecycleRunId | None = None
    resume_command_hash: str | None = None
    source_run_id: LifecycleRunId | None = None
    source_command_hash: str | None = None
    source_history_hash: str | None = None
    replay_report_hash: str | None = None
    schema_version: str = field(default=SCHEMA_VERSION, repr=False)
    command_hash: str = field(init=False)
    run_id: LifecycleRunId = field(init=False)
    configuration_manifest_hash: str = field(init=False)
    model_version_manifest_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version not in {
            self.LEGACY_SCHEMA_VERSION,
            self.SCHEMA_VERSION,
        }:
            raise ValueError("unsupported CanonicalLifecycleCommand schema")
        if not isinstance(self.run_type, LifecycleRunType):
            raise TypeError("run_type must be a LifecycleRunType")
        if type(self.decision_date) is not date:
            raise TypeError("decision_date must be a date")
        require_utc_second("as_of_time", self.as_of_time)
        if self.as_of_time.astimezone(_SHANGHAI).date() != self.decision_date:
            raise ValueError("decision_date must match the Asia/Shanghai as-of date")
        require_text("idempotency_key", self.idempotency_key)
        if (self.input_manifest_id is None) != (self.input_content_hash is None):
            raise ValueError("input manifest identity and hash must be paired")
        if (self.input_manifest_id is None) != (self.input_manifest_locator is None):
            raise ValueError("input manifest identity and locator must be paired")
        if self.input_content_hash is not None:
            require_sha256("input_content_hash", self.input_content_hash)
        if self.input_manifest_locator is not None:
            if not isinstance(self.input_manifest_locator, Path):
                raise TypeError("input_manifest_locator must be a Path or None")
            object.__setattr__(
                self,
                "input_manifest_locator",
                self.input_manifest_locator.resolve(),
            )
        if not self.input_references:
            raise ValueError("input_references must not be empty")
        validate_lifecycle_object_references("input_references", self.input_references)
        for reference in self.input_references:
            validate_lifecycle_reader_binding(reference)
            validate_lifecycle_locator_policy(reference)
            if reference.available_at > self.as_of_time:
                raise ValueError("continuation input was not available by as_of_time")
        explicit_prerequisite_replay = (
            self.run_type is LifecycleRunType.REPLAY
            and self.input_manifest_id is None
        )
        explicit_controlled_operation = (
            self.run_type is LifecycleRunType.CANONICAL_DECISION_LIFECYCLE
            and self.input_manifest_id is None
            and any(
                item.object_type in _CONTROLLED_DECISION_TIME_REQUIRED_TYPES
                for item in self.input_references
            )
        )
        if (
            self.run_type is LifecycleRunType.RISK_REDUCTION_CONTINUATION
            or explicit_prerequisite_replay
        ):
            if self.input_manifest_id is not None:
                raise ValueError(
                    f"{self.run_type.value} uses explicit prerequisite references"
                )
            present_types = {item.object_type for item in self.input_references}
            missing = _RISK_CONTINUATION_REQUIRED_TYPES - present_types
            if missing:
                names = ", ".join(sorted(item.value for item in missing))
                raise ValueError(f"risk continuation is missing prerequisites: {names}")
            counts = {
                object_type: sum(
                    item.object_type is object_type
                    for item in self.input_references
                )
                for object_type in present_types
            }
            duplicates = {
                object_type for object_type, count in counts.items() if count != 1
            }
            if duplicates:
                names = ", ".join(sorted(item.value for item in duplicates))
                raise ValueError(
                    f"risk continuation requires exactly one reference per type: {names}"
                )
        elif explicit_controlled_operation:
            expected_counts = {
                object_type: (
                    2
                    if object_type
                    in {
                        LifecycleObjectType.MARKET_DATA_DATASET,
                        LifecycleObjectType.FEATURE_BUNDLE,
                    }
                    else 1
                )
                for object_type in _CONTROLLED_DECISION_TIME_REQUIRED_TYPES
            }
            actual_counts = {
                object_type: sum(
                    item.object_type is object_type for item in self.input_references
                )
                for object_type in {
                    item.object_type for item in self.input_references
                }
            }
            controlled_missing = {
                object_type
                for object_type, count in expected_counts.items()
                if actual_counts.get(object_type, 0) < count
            }
            unexpected = set(actual_counts) - set(expected_counts)
            invalid_counts = {
                object_type
                for object_type, count in expected_counts.items()
                if actual_counts.get(object_type, 0) != count
            }
            if controlled_missing or unexpected or invalid_counts:
                names = ", ".join(
                    sorted(
                        item.value
                        for item in controlled_missing | unexpected | invalid_counts
                    )
                )
                raise ValueError(
                    "controlled decision-time lifecycle requires the exact "
                    "prerequisite type/cardinality contract: "
                    f"{names}"
                )
        else:
            if self.input_manifest_id is None:
                raise ValueError(f"{self.run_type.value} requires an input manifest")
            root_count = sum(
                item.object_type is LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST
                for item in self.input_references
            )
            if root_count != 1:
                raise ValueError(
                    f"{self.run_type.value} requires exactly one composite root"
                )
            if not any(
                item.object_type is LifecycleObjectType.SOURCE_MANIFEST
                for item in self.input_references
            ):
                raise ValueError(
                    f"{self.run_type.value} requires at least one source manifest"
                )
        configuration_hash = configuration_manifest_hash(
            self.configuration_references
        )
        model_hash = model_version_manifest_hash(self.model_references)
        _reject_reference_ambiguity(
            "configuration references", self.configuration_references
        )
        _reject_reference_ambiguity("model references", self.model_references)
        object.__setattr__(self, "configuration_manifest_hash", configuration_hash)
        object.__setattr__(self, "model_version_manifest_hash", model_hash)
        if self.stop_after_stage is not None and not isinstance(
            self.stop_after_stage, LifecycleStageName
        ):
            raise TypeError("stop_after_stage must be a LifecycleStageName or None")
        if not isinstance(self.output_directory, Path):
            raise TypeError("output_directory must be a Path")
        object.__setattr__(self, "output_directory", self.output_directory.resolve())
        if (self.resume_run_id is None) != (self.resume_command_hash is None):
            raise ValueError("resume run identity and original command hash must be paired")
        if self.resume_run_id is not None and not isinstance(
            self.resume_run_id, LifecycleRunId
        ):
            raise TypeError("resume_run_id must be a LifecycleRunId or None")
        if self.resume_command_hash is not None:
            require_sha256("resume_command_hash", self.resume_command_hash)
        if (self.source_run_id is None) != (self.source_command_hash is None):
            raise ValueError("source run identity and command hash must be paired")
        if self.source_run_id is not None and not isinstance(
            self.source_run_id, LifecycleRunId
        ):
            raise TypeError("source_run_id must be a LifecycleRunId or None")
        if self.source_command_hash is not None:
            require_sha256("source_command_hash", self.source_command_hash)
        if (
            self.schema_version == self.SCHEMA_VERSION
            and self.run_type is LifecycleRunType.REPLAY
        ):
            if self.source_run_id is None:
                raise ValueError("REPLAY requires source run identity")
            if self.source_history_hash is None or self.replay_report_hash is None:
                raise ValueError("REPLAY requires source history and report hashes")
            require_sha256("source_history_hash", self.source_history_hash)
            require_sha256("replay_report_hash", self.replay_report_hash)
        elif self.source_run_id is not None:
            raise ValueError("only REPLAY may carry source run identity")
        elif self.source_history_hash is not None or self.replay_report_hash is not None:
            raise ValueError("only REPLAY may carry replay evidence hashes")
        command_hash = canonical_hash(self.semantic_payload())
        run_identity_hash = canonical_hash(
            {
                "schema_version": "canonical-lifecycle-run-identity-v1",
                "idempotency_key": self.idempotency_key,
                "command_hash": command_hash,
            }
        )
        run_id = LifecycleRunId(
            f"lifecycle-run-{run_identity_hash.split(':', 1)[1][:24]}"
        )
        object.__setattr__(self, "command_hash", command_hash)
        object.__setattr__(self, "run_id", run_id)
        if self.source_run_id == run_id:
            raise ValueError("REPLAY source run cannot be the replay run itself")
        if self.resume_command_hash is not None and self.resume_command_hash != command_hash:
            raise ValueError("resume command does not preserve original command identity")
        if self.resume_run_id is not None and self.resume_run_id != run_id:
            raise ValueError("resume run ID does not match idempotent command identity")

    @property
    def is_resume(self) -> bool:
        return self.resume_run_id is not None

    def semantic_payload(self) -> dict[str, Any]:
        """Return only evidence and model semantics, excluding execution controls."""

        payload = {
            "schema_version": self.schema_version,
            "run_type": self.run_type.value,
            "decision_date": self.decision_date.isoformat(),
            "as_of_time": canonical_datetime(self.as_of_time),
            "input_manifest_id": (
                str(self.input_manifest_id) if self.input_manifest_id else None
            ),
            "input_content_hash": self.input_content_hash,
            "input_manifest_locator": (
                str(self.input_manifest_locator)
                if self.input_manifest_locator is not None
                else None
            ),
            "input_references": [
                item.to_canonical_dict() for item in self.input_references
            ],
            "configuration_references": [
                item.to_canonical_dict() for item in self.configuration_references
            ],
            "configuration_manifest_hash": self.configuration_manifest_hash,
            "model_references": [
                item.to_canonical_dict() for item in self.model_references
            ],
            "model_version_manifest_hash": self.model_version_manifest_hash,
            "authority_database_locator": None,
        }
        if self.schema_version == self.SCHEMA_VERSION:
            payload.update(
                {
                    "source_run_id": (
                        str(self.source_run_id)
                        if self.source_run_id is not None
                        else None
                    ),
                    "source_command_hash": self.source_command_hash,
                    "source_history_hash": self.source_history_hash,
                    "replay_report_hash": self.replay_report_hash,
                }
            )
        return payload

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "idempotency_key": self.idempotency_key,
            "stop_after_stage": (
                self.stop_after_stage.value if self.stop_after_stage else None
            ),
            "output_directory": str(self.output_directory),
            "resume_run_id": str(self.resume_run_id) if self.resume_run_id else None,
            "resume_command_hash": self.resume_command_hash,
            "command_hash": self.command_hash,
            "run_id": str(self.run_id),
        }

    def assert_resume_identity(self, run: LifecycleRun) -> None:
        """Prove a resume command cannot mutate the persisted run semantics."""

        if not isinstance(run, LifecycleRun):
            raise TypeError("run must be a LifecycleRun")
        if not self.is_resume:
            raise ValueError("command is not a resume command")
        if (
            run.run_id != self.resume_run_id
            or run.idempotency_key != self.idempotency_key
            or run.command_hash != self.command_hash
            or run.run_type is not self.run_type
            or run.decision_date != self.decision_date
            or run.as_of_time != self.as_of_time
            or run.input_manifest_id != self.input_manifest_id
            or run.input_content_hash != self.input_content_hash
            or run.configuration_manifest_hash != self.configuration_manifest_hash
            or run.model_version_manifest_hash != self.model_version_manifest_hash
            or run.source_run_id != self.source_run_id
            or run.source_command_hash != self.source_command_hash
            or run.source_history_hash != self.source_history_hash
            or run.replay_report_hash != self.replay_report_hash
        ):
            raise ValueError("resume command does not identify the persisted run")

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CanonicalLifecycleCommand:
        base_expected = {
            "schema_version", "run_type", "decision_date", "as_of_time",
            "idempotency_key", "input_manifest_id", "input_content_hash",
            "input_manifest_locator",
            "input_references", "configuration_references",
            "configuration_manifest_hash", "model_references",
            "model_version_manifest_hash", "stop_after_stage", "output_directory",
            "authority_database_locator",
            "resume_run_id", "resume_command_hash", "command_hash", "run_id",
        }
        schema_version = payload.get("schema_version")
        if schema_version == cls.SCHEMA_VERSION:
            expected = base_expected | {
                "source_run_id",
                "source_command_hash",
                "source_history_hash",
                "replay_report_hash",
            }
        elif schema_version == cls.LEGACY_SCHEMA_VERSION:
            expected = base_expected
        else:
            raise ValueError("unsupported CanonicalLifecycleCommand schema")
        if set(payload) != expected:
            raise ValueError("CanonicalLifecycleCommand fields mismatch")
        input_manifest_id = _optional_text(payload, "input_manifest_id")
        stop_after_stage = _optional_text(payload, "stop_after_stage")
        resume_run_id = _optional_text(payload, "resume_run_id")
        input_manifest_locator = _optional_text(payload, "input_manifest_locator")
        if payload["authority_database_locator"] is not None:
            raise ValueError("database authority locators are no longer supported")
        source_run_id = (
            _optional_text(payload, "source_run_id")
            if schema_version == cls.SCHEMA_VERSION
            else None
        )
        source_command_hash = (
            _optional_text(payload, "source_command_hash")
            if schema_version == cls.SCHEMA_VERSION
            else None
        )
        source_history_hash = (
            _optional_text(payload, "source_history_hash")
            if schema_version == cls.SCHEMA_VERSION
            else None
        )
        replay_report_hash = (
            _optional_text(payload, "replay_report_hash")
            if schema_version == cls.SCHEMA_VERSION
            else None
        )
        result = cls(
            run_type=LifecycleRunType(_text(payload, "run_type")),
            decision_date=_date_value(payload["decision_date"], "decision_date"),
            as_of_time=parse_utc_second("as_of_time", payload["as_of_time"]),
            idempotency_key=_text(payload, "idempotency_key"),
            input_manifest_id=(
                ArtifactId(input_manifest_id) if input_manifest_id else None
            ),
            input_content_hash=_optional_text(payload, "input_content_hash"),
            input_manifest_locator=(
                Path(input_manifest_locator) if input_manifest_locator else None
            ),
            input_references=tuple(
                LifecycleObjectReference.from_canonical_dict(item)
                for item in _object_array(payload, "input_references")
            ),
            configuration_references=tuple(
                LifecycleConfigurationReference.from_canonical_dict(item)
                for item in _object_array(payload, "configuration_references")
            ),
            model_references=tuple(
                LifecycleModelVersionReference.from_canonical_dict(item)
                for item in _object_array(payload, "model_references")
            ),
            stop_after_stage=(
                LifecycleStageName(stop_after_stage) if stop_after_stage else None
            ),
            output_directory=Path(_text(payload, "output_directory")),
            resume_run_id=LifecycleRunId(resume_run_id) if resume_run_id else None,
            resume_command_hash=_optional_text(payload, "resume_command_hash"),
            source_run_id=(
                LifecycleRunId(source_run_id) if source_run_id else None
            ),
            source_command_hash=source_command_hash,
            source_history_hash=source_history_hash,
            replay_report_hash=replay_report_hash,
            schema_version=str(schema_version),
        )
        for label, actual in (
            ("configuration_manifest_hash", result.configuration_manifest_hash),
            ("model_version_manifest_hash", result.model_version_manifest_hash),
            ("command_hash", result.command_hash),
        ):
            if _text(payload, label) != actual:
                raise ValueError(f"CanonicalLifecycleCommand {label} mismatch")
        if _text(payload, "run_id") != str(result.run_id):
            raise ValueError("CanonicalLifecycleCommand run_id mismatch")
        return result


def _reject_reference_ambiguity(
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


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload[key]
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value


def _object_array(
    payload: Mapping[str, Any], key: str
) -> tuple[Mapping[str, Any], ...]:
    value = payload[key]
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{key} must be an array of objects")
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
