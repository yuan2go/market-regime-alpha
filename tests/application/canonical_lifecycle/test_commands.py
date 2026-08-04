from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationKind,
    LifecycleConfigurationReference,
    LifecycleModelVersionReference,
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
    LifecycleRetryState,
    LifecycleRun,
    configuration_manifest_hash,
    model_version_manifest_hash,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
)
from market_regime_alpha.core.identity import ArtifactId, ModelId


UTC = timezone.utc
AS_OF = datetime(2026, 8, 4, 6, 55, tzinfo=UTC)


def _hash(char: str) -> str:
    return "sha256:" + char * 64


def _configuration(char: str = "b") -> LifecycleConfigurationReference:
    return LifecycleConfigurationReference(
        configuration_kind=LifecycleConfigurationKind.GENERIC,
        configuration_id=ArtifactId(f"configuration-{char}"),
        configuration_version="1.0.0",
        content_hash=_hash(char),
        locator=f"configurations/configuration-{char}.json",
    )


def _model(char: str = "c") -> LifecycleModelVersionReference:
    return LifecycleModelVersionReference(
        model_id=ModelId(f"model-{char}"),
        model_version="1.0.0",
        content_hash=_hash(char),
    )


def _command(
    *,
    run_type: LifecycleRunType = LifecycleRunType.CANONICAL_DECISION_LIFECYCLE,
    as_of_time: datetime = AS_OF,
    idempotency_key: str = "request-1",
    input_hash: str = _hash("a"),
    inputs: tuple[LifecycleObjectReference, ...] | None = None,
    configurations: tuple[LifecycleConfigurationReference, ...] | None = None,
    models: tuple[LifecycleModelVersionReference, ...] | None = None,
    stop_after_stage: LifecycleStageName | None = None,
    output_directory: Path = Path("artifacts/lifecycle"),
    authority_database_locator: Path | None = None,
    resume_run_id: object = None,
    resume_command_hash: str | None = None,
    source_run_id: object = None,
    source_command_hash: str | None = None,
    source_history_hash: str | None = None,
    replay_report_hash: str | None = None,
    schema_version: str = CanonicalLifecycleCommand.SCHEMA_VERSION,
) -> CanonicalLifecycleCommand:
    from market_regime_alpha.application.canonical_lifecycle.contracts import (
        LifecycleRunId,
    )

    if resume_run_id is not None and not isinstance(resume_run_id, LifecycleRunId):
        raise TypeError("test resume_run_id must be LifecycleRunId")
    if source_run_id is not None and not isinstance(source_run_id, LifecycleRunId):
        raise TypeError("test source_run_id must be LifecycleRunId")
    if run_type is LifecycleRunType.REPLAY and source_run_id is None:
        source_run_id = LifecycleRunId("lifecycle-run-source-1")
        source_command_hash = _hash("0")
        source_history_hash = _hash("1")
        replay_report_hash = _hash("2")
    return CanonicalLifecycleCommand(
        run_type=run_type,
        decision_date=as_of_time.astimezone(
            timezone(timedelta(hours=8))
        ).date(),
        as_of_time=as_of_time,
        idempotency_key=idempotency_key,
        input_manifest_id=ArtifactId("input-manifest-1"),
        input_content_hash=input_hash,
        input_manifest_locator=Path("artifacts/input-manifest-1.json"),
        input_references=(
            _canonical_input_references() if inputs is None else inputs
        ),
        configuration_references=(
            (_configuration(),) if configurations is None else configurations
        ),
        model_references=(_model(),) if models is None else models,
        stop_after_stage=stop_after_stage,
        output_directory=output_directory,
        authority_database_locator=authority_database_locator,
        resume_run_id=resume_run_id,
        resume_command_hash=resume_command_hash,
        source_run_id=source_run_id,
        source_command_hash=source_command_hash,
        source_history_hash=source_history_hash,
        replay_report_hash=replay_report_hash,
        schema_version=schema_version,
    )


def _risk_reference(
    object_type: LifecycleObjectType,
    reader_kind: LifecycleReaderKind,
    char: str,
    *,
    locator: str | None = None,
) -> LifecycleObjectReference:
    return LifecycleObjectReference(
        object_type=object_type,
        object_id=LifecycleObjectId(f"{object_type.value.lower()}-1"),
        content_hash=_hash(char),
        reader_kind=reader_kind,
        locator=locator,
        available_at=AS_OF,
    )


def _risk_references() -> tuple[LifecycleObjectReference, ...]:
    return tuple(
        sorted(
            (
                _risk_reference(
                    LifecycleObjectType.RISK_REDUCING_DECISION,
                    LifecycleReaderKind.RISK_REDUCTION_REPOSITORY,
                    "1",
                ),
                _risk_reference(
                    LifecycleObjectType.POSITION_BOOK,
                    LifecycleReaderKind.POSITION_BOOK_REPOSITORY,
                    "2",
                ),
                _risk_reference(
                    LifecycleObjectType.OPERATIONAL_EXIT_DIRECTIVE,
                    LifecycleReaderKind.OPERATIONAL_EXIT_DIRECTIVE_REPOSITORY,
                    "3",
                ),
                _risk_reference(
                    LifecycleObjectType.TRADING_CALENDAR_ARTIFACT,
                    LifecycleReaderKind.TRADING_CALENDAR_ARTIFACT_READER,
                    "4",
                    locator="artifacts/calendar-1",
                ),
                _risk_reference(
                    LifecycleObjectType.THESIS_HEALTH_OBSERVATION,
                    LifecycleReaderKind.THESIS_HEALTH_REPOSITORY,
                    "5",
                ),
                _risk_reference(
                    LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST,
                    LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER,
                    "6",
                    locator="artifacts/composite-1",
                ),
                _risk_reference(
                    LifecycleObjectType.REDUCING_EXECUTION_OBSERVATION,
                    LifecycleReaderKind.REDUCING_EXECUTION_OBSERVATION_READER,
                    "7",
                    locator="artifacts/reducing-observation-1.json",
                ),
                _risk_reference(
                    LifecycleObjectType.SYMBOL_TRADING_SESSION_STATUS_SET,
                    LifecycleReaderKind.SYMBOL_TRADING_SESSION_STATUS_READER,
                    "8",
                    locator="artifacts/session-statuses-1.json",
                ),
                _risk_reference(
                    LifecycleObjectType.RISK_REDUCTION_CONFIRMATION_POLICY,
                    LifecycleReaderKind.RISK_REDUCTION_CONFIRMATION_POLICY_READER,
                    "9",
                    locator="artifacts/confirmation-policy-1.json",
                ),
            ),
            key=lambda item: item.sort_key,
        )
    )


def _canonical_input_references() -> tuple[LifecycleObjectReference, ...]:
    return tuple(
        sorted(
            (
                _risk_reference(
                    LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST,
                    LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER,
                    "d",
                    locator="artifacts/composite-1",
                ),
                _risk_reference(
                    LifecycleObjectType.SOURCE_MANIFEST,
                    LifecycleReaderKind.SOURCE_MANIFEST_READER,
                    "e",
                    locator="artifacts/source-manifest-1.json",
                ),
            ),
            key=lambda item: item.sort_key,
        )
    )


def _risk_command(
    references: tuple[LifecycleObjectReference, ...] | None = None,
) -> CanonicalLifecycleCommand:
    return CanonicalLifecycleCommand(
        run_type=LifecycleRunType.RISK_REDUCTION_CONTINUATION,
        decision_date=date(2026, 8, 4),
        as_of_time=AS_OF,
        idempotency_key="risk-request-1",
        input_manifest_id=None,
        input_content_hash=None,
        input_manifest_locator=None,
        input_references=(
            _risk_references() if references is None else references
        ),
        configuration_references=(_configuration(),),
        model_references=(),
        stop_after_stage=None,
        output_directory=Path("artifacts/lifecycle"),
        authority_database_locator=None,
    )


def test_command_round_trip_and_deterministic_run_identity() -> None:
    command = _command()
    restored = CanonicalLifecycleCommand.from_canonical_dict(
        command.to_canonical_dict()
    )
    assert restored == command
    assert restored.command_hash == command.command_hash
    assert restored.run_id == command.run_id


def test_legacy_v2_command_round_trip_preserves_original_hash_semantics() -> None:
    command = _command(
        schema_version=CanonicalLifecycleCommand.LEGACY_SCHEMA_VERSION
    )
    payload = command.to_canonical_dict()
    assert payload["schema_version"] == "canonical-lifecycle-command-v2"
    assert "source_run_id" not in payload
    assert "replay_report_hash" not in payload

    restored = CanonicalLifecycleCommand.from_canonical_dict(payload)

    assert restored == command
    assert restored.command_hash == command.command_hash
    assert restored.run_id == command.run_id


def test_output_and_resume_controls_do_not_change_semantic_command_hash() -> None:
    original = _command()
    controlled = _command(
        stop_after_stage=LifecycleStageName.SIGNAL,
        output_directory=Path("other-output"),
    )
    resume = _command(
        stop_after_stage=LifecycleStageName.PATH_FORECAST,
        output_directory=Path("replay-output"),
        resume_run_id=original.run_id,
        resume_command_hash=original.command_hash,
    )
    assert controlled.command_hash == original.command_hash
    assert controlled.run_id == original.run_id
    assert resume.command_hash == original.command_hash
    assert resume.run_id == original.run_id
    assert resume.is_resume


def test_semantic_fields_each_change_command_hash() -> None:
    original = _command()
    variants = (
        _command(run_type=LifecycleRunType.REPLAY),
        _command(as_of_time=AS_OF + timedelta(days=1)),
        _command(input_hash=_hash("9")),
        _command(
            inputs=tuple(
                replace(item, content_hash=_hash("f"))
                if item.object_type is LifecycleObjectType.SOURCE_MANIFEST
                else item
                for item in _canonical_input_references()
            )
        ),
        _command(configurations=(_configuration("8"),)),
        _command(models=(_model("7"),)),
        _command(authority_database_locator=Path("authority/domain.sqlite3")),
    )
    assert all(item.command_hash != original.command_hash for item in variants)


def test_idempotency_key_changes_run_identity_but_not_command_hash() -> None:
    first = _command(idempotency_key="request-1")
    second = _command(idempotency_key="request-2")
    assert first.command_hash == second.command_hash
    assert first.run_id != second.run_id


def test_resume_rejects_any_semantic_or_idempotency_mutation() -> None:
    original = _command()
    with pytest.raises(ValueError, match="original command identity"):
        _command(
            input_hash=_hash("9"),
            resume_run_id=original.run_id,
            resume_command_hash=original.command_hash,
        )
    with pytest.raises(ValueError, match="run ID"):
        _command(
            idempotency_key="other-key",
            resume_run_id=original.run_id,
            resume_command_hash=original.command_hash,
        )


def test_resume_identity_checks_the_persisted_run() -> None:
    original = _command()
    resume = _command(
        resume_run_id=original.run_id,
        resume_command_hash=original.command_hash,
    )
    configs = original.configuration_references
    models = original.model_references
    run = LifecycleRun(
        run_id=original.run_id,
        idempotency_key=original.idempotency_key,
        command_hash=original.command_hash,
        run_type=original.run_type,
        decision_date=original.decision_date,
        as_of_time=original.as_of_time,
        status=LifecycleRunStatus.CREATED,
        current_stage=LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
        input_manifest_id=original.input_manifest_id,
        input_content_hash=original.input_content_hash,
        completed_stages=(),
        configuration_references=configs,
        configuration_manifest_hash=configuration_manifest_hash(configs),
        model_references=models,
        model_version_manifest_hash=model_version_manifest_hash(models),
        retry_state=LifecycleRetryState.NOT_REQUIRED,
        failure_reason=None,
        blocker_reason=None,
        created_at=AS_OF,
        updated_at=AS_OF,
        completed_at=None,
        version=1,
        claim_token=0,
    )
    resume.assert_resume_identity(run)
    with pytest.raises(ValueError, match="persisted run"):
        resume.assert_resume_identity(replace(run, input_content_hash=_hash("9")))


def test_risk_continuation_names_all_durable_prerequisites() -> None:
    command = _risk_command()
    assert {item.object_type for item in command.input_references} == {
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
    assert all(
        item.locator is None
        for item in command.input_references
        if item.reader_kind
        in {
            LifecycleReaderKind.RISK_REDUCTION_REPOSITORY,
            LifecycleReaderKind.POSITION_BOOK_REPOSITORY,
            LifecycleReaderKind.OPERATIONAL_EXIT_DIRECTIVE_REPOSITORY,
            LifecycleReaderKind.THESIS_HEALTH_REPOSITORY,
        }
    )
    assert CanonicalLifecycleCommand.from_canonical_dict(
        command.to_canonical_dict()
    ) == command


def test_risk_continuation_rejects_missing_prerequisite() -> None:
    with pytest.raises(ValueError, match="missing prerequisites"):
        _risk_command(_risk_references()[:-1])


def test_risk_continuation_rejects_two_references_of_one_type() -> None:
    references = _risk_references()
    risk = next(
        item
        for item in references
        if item.object_type is LifecycleObjectType.RISK_REDUCING_DECISION
    )
    duplicate = replace(
        risk,
        object_id=LifecycleObjectId("risk-reducing-decision-2"),
        content_hash=_hash("a"),
    )
    ambiguous = tuple(sorted((*references, duplicate), key=lambda item: item.sort_key))
    with pytest.raises(ValueError, match="exactly one"):
        _risk_command(ambiguous)


def test_full_lifecycle_requires_recoverable_composite_and_source_inputs() -> None:
    inputs = _canonical_input_references()
    with pytest.raises(ValueError, match="exactly one composite root"):
        _command(
            inputs=tuple(
                item
                for item in inputs
                if item.object_type
                is not LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST
            )
        )
    with pytest.raises(ValueError, match="at least one source manifest"):
        _command(
            inputs=tuple(
                item
                for item in inputs
                if item.object_type is not LifecycleObjectType.SOURCE_MANIFEST
            )
        )


def test_command_rejects_naive_fractional_and_non_utc_as_of() -> None:
    for invalid in (
        AS_OF.replace(tzinfo=None),
        AS_OF.replace(microsecond=1),
        AS_OF.astimezone(timezone(timedelta(hours=8))),
    ):
        with pytest.raises(ValueError):
            _command(as_of_time=invalid)


def test_command_reader_rejects_hash_and_id_tamper() -> None:
    payload = _command().to_canonical_dict()
    payload["command_hash"] = _hash("0")
    with pytest.raises(ValueError, match="command_hash mismatch"):
        CanonicalLifecycleCommand.from_canonical_dict(payload)

    payload = _command().to_canonical_dict()
    payload["run_id"] = "lifecycle-run-tampered"
    with pytest.raises(ValueError, match="run_id mismatch"):
        CanonicalLifecycleCommand.from_canonical_dict(payload)
