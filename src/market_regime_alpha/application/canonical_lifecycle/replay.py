"""Read-only replay verification over an existing lifecycle journal."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleRunId,
)
from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    CanonicalLifecycleInputManifestReader,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.runtime_configuration import (
    RuntimeConfigurationError,
    RuntimeConfigurationReader,
)
from market_regime_alpha.application.operational_research.composite_artifact import (
    load_verified_composite_operational_manifest,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
)
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text
from market_regime_alpha.features.artifact import replay_feature_artifact
from market_regime_alpha.forecasting.artifact import replay_path_forecast
from market_regime_alpha.migration.comparison.artifact import (
    load_verified_model_comparison_report,
)
from market_regime_alpha.research.platform_v2.reader_registry import (
    load_verified_research_artifact,
)
from market_regime_alpha.signals.artifact import replay_signal_run


class ReplayCheckStatus(str, Enum):
    REPLAY_STABLE = "REPLAY_STABLE"
    VERIFIED_READ_ONLY = "VERIFIED_READ_ONLY"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    FAILED = "FAILED"


class LifecycleReplayStatus(str, Enum):
    STABLE = "STABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class LifecycleReplayCheck:
    subject: str
    status: ReplayCheckStatus
    expected_hash: str | None
    observed_hash: str | None
    detail: str

    def __post_init__(self) -> None:
        require_text("subject", self.subject)
        if not isinstance(self.status, ReplayCheckStatus):
            raise TypeError("status must be a ReplayCheckStatus")
        if self.expected_hash is not None:
            require_sha256("expected_hash", self.expected_hash)
        if self.observed_hash is not None:
            require_sha256("observed_hash", self.observed_hash)
        require_text("detail", self.detail)
        if self.status in {
            ReplayCheckStatus.REPLAY_STABLE,
            ReplayCheckStatus.VERIFIED_READ_ONLY,
        } and (
            self.expected_hash is None
            or self.observed_hash != self.expected_hash
        ):
            raise ValueError("successful replay check must match the expected hash")

    def to_canonical_dict(self) -> dict[str, str | None]:
        return {
            "subject": self.subject,
            "status": self.status.value,
            "expected_hash": self.expected_hash,
            "observed_hash": self.observed_hash,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class LifecycleReplayReport:
    run_id: LifecycleRunId
    command_hash: str
    journal_hash: str
    status: LifecycleReplayStatus
    checks: tuple[LifecycleReplayCheck, ...]
    report_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, LifecycleRunId):
            raise TypeError("run_id must be a LifecycleRunId")
        require_sha256("command_hash", self.command_hash)
        require_sha256("journal_hash", self.journal_hash)
        if not isinstance(self.status, LifecycleReplayStatus):
            raise TypeError("status must be a LifecycleReplayStatus")
        if not isinstance(self.checks, tuple) or any(
            not isinstance(item, LifecycleReplayCheck) for item in self.checks
        ):
            raise TypeError("checks must contain LifecycleReplayCheck values")
        if self.checks != tuple(sorted(self.checks, key=lambda item: item.subject)):
            raise ValueError("replay checks must be sorted by subject")
        require_sha256("report_hash", self.report_hash)
        if self.status is not _report_status(self.checks):
            raise ValueError("replay report status does not match its checks")
        if self.report_hash != canonical_hash(self.semantic_payload()):
            raise ValueError("lifecycle replay report hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        run_id: LifecycleRunId,
        command_hash: str,
        journal_hash: str,
        checks: tuple[LifecycleReplayCheck, ...],
    ) -> LifecycleReplayReport:
        ordered = tuple(sorted(checks, key=lambda item: item.subject))
        status = _report_status(ordered)
        semantic = cls.semantic_payload_for(
            run_id=run_id,
            command_hash=command_hash,
            journal_hash=journal_hash,
            status=status,
            checks=ordered,
        )
        return cls(
            run_id=run_id,
            command_hash=command_hash,
            journal_hash=journal_hash,
            status=status,
            checks=ordered,
            report_hash=canonical_hash(semantic),
        )

    @staticmethod
    def semantic_payload_for(**values: Any) -> dict[str, Any]:
        return {
            "schema_version": "canonical-lifecycle-replay-report-v1",
            "run_id": str(values["run_id"]),
            "command_hash": values["command_hash"],
            "journal_hash": values["journal_hash"],
            "status": values["status"].value,
            "checks": [item.to_canonical_dict() for item in values["checks"]],
        }

    def semantic_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            run_id=self.run_id,
            command_hash=self.command_hash,
            journal_hash=self.journal_hash,
            status=self.status,
            checks=self.checks,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {**self.semantic_payload(), "report_hash": self.report_hash}


def verify_lifecycle_replay(
    *,
    repository: LifecycleRunRepository,
    run_id: LifecycleRunId,
) -> LifecycleReplayReport:
    """Verify an existing run without invoking Runner or any mutating service."""

    if not isinstance(run_id, LifecycleRunId):
        raise TypeError("run_id must be a LifecycleRunId")
    command = repository.get_command(run_id)
    history = repository.history(run_id)
    checks: list[LifecycleReplayCheck] = []

    if command.input_manifest_locator is not None:
        checks.append(_verify_input_manifest(command))
    for configuration_reference in command.configuration_references:
        subject = (
            f"CONFIGURATION:{configuration_reference.configuration_kind.value}:"
            f"{configuration_reference.configuration_id}"
        )
        try:
            RuntimeConfigurationReader().read(configuration_reference)
        except RuntimeConfigurationError as exc:
            checks.append(
                _failed_check(subject, configuration_reference.content_hash, exc)
            )
        else:
            checks.append(
                LifecycleReplayCheck(
                    subject=subject,
                    status=ReplayCheckStatus.VERIFIED_READ_ONLY,
                    expected_hash=configuration_reference.content_hash,
                    observed_hash=configuration_reference.content_hash,
                    detail="TYPED_CONFIGURATION_RESTORED",
                )
            )

    references: dict[tuple[str, str, str], LifecycleObjectReference] = {}
    for object_reference in command.input_references:
        references[object_reference.sort_key] = object_reference
    for stage in history.stages:
        for object_reference in stage.output_references:
            prior = references.setdefault(
                object_reference.sort_key, object_reference
            )
            if prior != object_reference:
                raise ValueError("journal contains conflicting replay references")
    checks.extend(_verify_reference(reference) for reference in references.values())

    journal_hash = canonical_hash(
        {
            "schema_version": "canonical-lifecycle-replay-journal-v1",
            "run": history.run.to_canonical_dict(),
            "stages": [item.to_canonical_dict() for item in history.stages],
            "attempts": [item.to_canonical_dict() for item in history.attempts],
            "receipts": [item.to_canonical_dict() for item in history.receipts],
            "events": [item.to_canonical_dict() for item in history.events],
            "event_payloads": list(history.event_payloads),
        }
    )
    return LifecycleReplayReport.create(
        run_id=run_id,
        command_hash=command.command_hash,
        journal_hash=journal_hash,
        checks=tuple(checks),
    )


def _verify_input_manifest(
    command: CanonicalLifecycleCommand,
) -> LifecycleReplayCheck:
    subject = f"INPUT_MANIFEST:{command.input_manifest_id}"
    assert command.input_manifest_locator is not None
    assert command.input_manifest_id is not None
    assert command.input_content_hash is not None
    try:
        manifest = CanonicalLifecycleInputManifestReader().read(
            command.input_manifest_locator,
            expected_manifest_id=command.input_manifest_id,
            expected_content_hash=command.input_content_hash,
        )
        if (
            manifest.input_references != command.input_references
            or manifest.configuration_references != command.configuration_references
            or manifest.model_references != command.model_references
        ):
            raise ValueError("input manifest no longer reconstructs stored command")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return _failed_check(subject, command.input_content_hash, exc)
    return LifecycleReplayCheck(
        subject=subject,
        status=ReplayCheckStatus.VERIFIED_READ_ONLY,
        expected_hash=command.input_content_hash,
        observed_hash=command.input_content_hash,
        detail="INPUT_MANIFEST_RESTORED",
    )


def _verify_reference(reference: LifecycleObjectReference) -> LifecycleReplayCheck:
    subject = f"OBJECT:{reference.object_type.value}:{reference.object_id}"
    if reference.locator is None:
        return LifecycleReplayCheck(
            subject=subject,
            status=ReplayCheckStatus.NOT_COMPARABLE,
            expected_hash=reference.content_hash,
            observed_hash=None,
            detail="REPOSITORY_AUTHORITY_REQUIRES_EXPLICIT_INJECTION",
        )
    verifier = _REFERENCE_VERIFIERS.get(reference.object_type)
    if verifier is None:
        return LifecycleReplayCheck(
            subject=subject,
            status=ReplayCheckStatus.NOT_COMPARABLE,
            expected_hash=reference.content_hash,
            observed_hash=None,
            detail="NO_SAFE_PURE_REPLAY_READER_REGISTERED",
        )
    try:
        object_id, observed_hash, status, detail = verifier(Path(reference.locator))
        if object_id != str(reference.object_id) or observed_hash != reference.content_hash:
            raise ValueError("replayed Artifact identity or content hash mismatch")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return _failed_check(subject, reference.content_hash, exc)
    return LifecycleReplayCheck(
        subject=subject,
        status=status,
        expected_hash=reference.content_hash,
        observed_hash=observed_hash,
        detail=detail,
    )


_VerifiedReference = tuple[str, str, ReplayCheckStatus, str]


def _composite(path: Path) -> _VerifiedReference:
    value = load_verified_composite_operational_manifest(path).manifest
    return (
        str(value.manifest_id),
        value.content_hash,
        ReplayCheckStatus.VERIFIED_READ_ONLY,
        "COMPOSITE_OPERATIONAL_MANIFEST_VERIFIED",
    )


def _source(path: Path) -> _VerifiedReference:
    payload = _read_json_object(path)
    nested = payload.get("source_manifest")
    source_payload = nested if isinstance(nested, Mapping) else payload
    value = SourceManifest.from_canonical_dict(source_payload)
    return (
        str(value.source_manifest_id),
        value.content_hash,
        ReplayCheckStatus.VERIFIED_READ_ONLY,
        "SOURCE_MANIFEST_RESTORED",
    )


def _daily(path: Path) -> _VerifiedReference:
    value = load_verified_daily_decision_artifact(path)
    return (
        value.artifact_id,
        value.bundle.content_hash,
        ReplayCheckStatus.VERIFIED_READ_ONLY,
        "DAILY_DECISION_ARTIFACT_VERIFIED",
    )


def _supplemental(path: Path) -> _VerifiedReference:
    value = load_verified_supplemental_research_evidence(path).bundle
    return (
        str(value.bundle_id),
        value.content_hash,
        ReplayCheckStatus.VERIFIED_READ_ONLY,
        "SUPPLEMENTAL_RESEARCH_EVIDENCE_VERIFIED",
    )


def _research(path: Path) -> _VerifiedReference:
    value = load_verified_research_artifact(path).artifact
    return (
        str(value.artifact_id),
        value.content_hash,
        ReplayCheckStatus.VERIFIED_READ_ONLY,
        "PLATFORM_RESEARCH_ARTIFACT_VERIFIED",
    )


def _signal(path: Path) -> _VerifiedReference:
    value = replay_signal_run(path).artifact
    return (
        str(value.artifact_id),
        value.envelope.content_hash,
        ReplayCheckStatus.REPLAY_STABLE,
        "SIGNAL_PURE_REPLAY_STABLE",
    )


def _forecast(path: Path) -> _VerifiedReference:
    value = replay_path_forecast(path).artifact
    return (
        str(value.artifact_id),
        value.forecast.envelope.content_hash,
        ReplayCheckStatus.REPLAY_STABLE,
        "PATH_FORECAST_PURE_REPLAY_STABLE",
    )


def _feature(path: Path) -> _VerifiedReference:
    value = replay_feature_artifact(path).artifact
    return (
        str(value.artifact_id),
        value.content_hash,
        ReplayCheckStatus.REPLAY_STABLE,
        "FEATURE_PURE_REPLAY_STABLE",
    )


def _comparison(path: Path) -> _VerifiedReference:
    value = load_verified_model_comparison_report(path).report
    return (
        str(value.comparison_id),
        value.report_hash,
        ReplayCheckStatus.VERIFIED_READ_ONLY,
        "MODEL_COMPARISON_REPORT_VERIFIED_NOT_RECOMPUTED",
    )


_REFERENCE_VERIFIERS: dict[
    LifecycleObjectType, Callable[[Path], _VerifiedReference]
] = {
    LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST: _composite,
    LifecycleObjectType.SOURCE_MANIFEST: _source,
    LifecycleObjectType.DAILY_DECISION_ARTIFACT: _daily,
    LifecycleObjectType.SUPPLEMENTAL_RESEARCH_EVIDENCE: _supplemental,
    LifecycleObjectType.PLATFORM_RESEARCH_ARTIFACT: _research,
    LifecycleObjectType.SIGNAL_ARTIFACT: _signal,
    LifecycleObjectType.PATH_FORECAST_ARTIFACT: _forecast,
    LifecycleObjectType.FEATURE_ARTIFACT: _feature,
    LifecycleObjectType.MODEL_COMPARISON_REPORT: _comparison,
}


def _read_json_object(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read replay JSON: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("replay JSON root must be an object")
    return payload


def _failed_check(
    subject: str,
    expected_hash: str,
    exc: Exception,
) -> LifecycleReplayCheck:
    message = str(exc) or repr(exc)
    return LifecycleReplayCheck(
        subject=subject,
        status=ReplayCheckStatus.FAILED,
        expected_hash=expected_hash,
        observed_hash=None,
        detail=f"{type(exc).__name__}: {message}",
    )


def _report_status(
    checks: tuple[LifecycleReplayCheck, ...]
) -> LifecycleReplayStatus:
    if any(item.status is ReplayCheckStatus.FAILED for item in checks):
        return LifecycleReplayStatus.FAILED
    if any(item.status is ReplayCheckStatus.NOT_COMPARABLE for item in checks):
        return LifecycleReplayStatus.NOT_COMPARABLE
    return LifecycleReplayStatus.STABLE
