from __future__ import annotations

from dataclasses import replace
from datetime import timedelta, timezone
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
)
from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.runtime_configuration import (
    RuntimeConfigurationReader,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunType,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    CanonicalLifecycleInputManifest,
    LifecycleAuthorityCeiling,
)
from market_regime_alpha.cli.replay_canonical_lifecycle import (
    EXIT_STABLE,
    main as replay_main,
)
from market_regime_alpha.cli.run_canonical_lifecycle import (
    EXIT_RUNTIME_FAILED,
    EXIT_SUCCESS,
    EXIT_VALIDATION_ERROR,
    _runner,
    main as lifecycle_main,
)
from market_regime_alpha.evidence.canonical import canonical_datetime
from tests.application.canonical_lifecycle.test_research_stages import (
    StageFixture,
    _stage_fixture,
)
from tests.application.canonical_lifecycle.test_decision_risk_stages import (
    confirmation_fixture as confirmation_fixture,
    _risk_configuration_references,
    _risk_continuation_as_of,
    _risk_references,
)
from tests.execution.risk_reduction_confirmation_support import ConfirmationFixture


def _write_restartable_manifest(tmp_path: Path) -> tuple[Path, StageFixture]:
    fixture = _stage_fixture(tmp_path / "evidence")
    configurations = {
        str(fixture.research_configuration.configuration_id): (
            fixture.research_configuration.to_canonical_dict()
        ),
        str(fixture.signal_configuration.configuration_id): (
            fixture.signal_configuration.to_canonical_dict()
        ),
        str(fixture.forecast_configuration.configuration_id): (
            fixture.forecast_configuration.to_canonical_dict()
        ),
    }
    references = []
    for reference in fixture.configuration_references:
        path = tmp_path / "configurations" / f"{reference.configuration_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(configurations[str(reference.configuration_id)], sort_keys=True),
            encoding="utf-8",
        )
        references.append(replace(reference, locator=str(path)))
    configuration_references = tuple(
        sorted(references, key=lambda item: item.sort_key)
    )
    fixture = replace(
        fixture,
        configuration_references=configuration_references,
    )
    manifest = CanonicalLifecycleInputManifest.create(
        decision_date=fixture.decision_date,
        as_of_time=fixture.as_of_time,
        created_at=fixture.as_of_time + timedelta(seconds=1),
        input_references=fixture.initial_references,
        configuration_references=configuration_references,
        model_references=fixture.model_references,
        authority_ceiling=LifecycleAuthorityCeiling(),
        limitations=("ENTRY_MODEL_NOT_EMPIRICALLY_VALIDATED",),
    )
    path = tmp_path / "input-manifest.json"
    path.write_text(
        json.dumps(manifest.to_canonical_dict(), sort_keys=True),
        encoding="utf-8",
    )
    return path, fixture


def _new_run_args(
    *,
    manifest: Path,
    fixture: StageFixture,
    database: Path,
    output: Path,
    idempotency_key: str = "cli-lifecycle-1",
) -> list[str]:
    return [
        "--input-manifest",
        str(manifest),
        "--decision-date",
        fixture.decision_date.isoformat(),
        "--as-of",
        canonical_datetime(fixture.as_of_time),
        "--idempotency-key",
        idempotency_key,
        "--database",
        str(database),
        "--output-dir",
        str(output),
    ]


def test_cli_runs_real_readers_models_then_stops_at_entry_validation(
    tmp_path: Path, capsys
) -> None:
    manifest, fixture = _write_restartable_manifest(tmp_path)
    database = tmp_path / "runtime.sqlite3"
    output = tmp_path / "runtime"
    args = _new_run_args(
        manifest=manifest,
        fixture=fixture,
        database=database,
        output=output,
    )
    assert lifecycle_main(args) == EXIT_SUCCESS
    first = json.loads(capsys.readouterr().out)
    assert first["status"] == "BLOCKED_BY_MODEL_VALIDATION"
    assert first["completed_stages"] == [
        "VERIFY_COMPOSITE_EVIDENCE",
        "PLATFORM_RESEARCH",
        "SIGNAL",
        "PATH_FORECAST",
    ]
    assert first["stage_statuses"]["ENTRY_ASSESSMENT"] == "BLOCKED"
    assert first["MANUAL_CONFIRMATION_REQUIRED"] is False
    assert first["MANUAL_TRADE_CREATED"] is False
    assert first["NO_ORDER_CREATED"] is True
    assert first["BROKER_NOT_INVOKED"] is True
    assert first["NO_FILL_CREATED"] is True
    with sqlite3.connect(database) as connection:
        attempt_count = connection.execute(
            "SELECT COUNT(*) FROM lifecycle_attempts"
        ).fetchone()[0]

    assert lifecycle_main(args) == EXIT_SUCCESS
    replayed = json.loads(capsys.readouterr().out)
    assert replayed["run_id"] == first["run_id"]
    assert replayed["command_hash"] == first["command_hash"]
    assert replayed["attempted_stages"] == []
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM lifecycle_attempts"
        ).fetchone()[0] == attempt_count

    assert lifecycle_main(
        [
            "--resume-run-id",
            first["run_id"],
            "--database",
            str(database),
        ]
    ) == EXIT_SUCCESS
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["run_id"] == first["run_id"]
    assert resumed["attempted_stages"] == []


def test_cli_failed_stage_can_resume_without_repeating_settled_stages(
    tmp_path: Path, capsys
) -> None:
    manifest_path, fixture = _invalid_artifact_manifest(tmp_path)
    database = tmp_path / "runtime.sqlite3"
    output = tmp_path / "runtime"
    args = _new_run_args(
        manifest=manifest_path,
        fixture=fixture,
        database=database,
        output=output,
        idempotency_key="cli-failure-1",
    )
    assert lifecycle_main(args) == EXIT_RUNTIME_FAILED
    first = json.loads(capsys.readouterr().out)
    assert first["status"] == "FAILED"
    assert first["current_stage"] == "VERIFY_COMPOSITE_EVIDENCE"
    assert first["completed_stages"] == []
    assert first["MANUAL_CONFIRMATION_REQUIRED"] is False
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM lifecycle_attempts"
        ).fetchone() == (1,)

    assert lifecycle_main(
        [
            "--resume-run-id",
            first["run_id"],
            "--database",
            str(database),
        ]
    ) == EXIT_RUNTIME_FAILED
    second = json.loads(capsys.readouterr().out)
    assert second["run_id"] == first["run_id"]
    assert second["completed_stages"] == []
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM lifecycle_attempts"
        ).fetchone() == (2,)


def test_cli_rejects_configuration_locator_and_content_tamper_before_journal_write(
    tmp_path: Path, capsys
) -> None:
    manifest_path, fixture = _write_restartable_manifest(tmp_path)
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    config_path = Path(manifest_payload["configuration_references"][0]["locator"])
    config_path.write_text("{}", encoding="utf-8")
    database = tmp_path / "runtime.sqlite3"
    assert lifecycle_main(
        _new_run_args(
            manifest=manifest_path,
            fixture=fixture,
            database=database,
            output=tmp_path / "runtime",
        )
    ) == EXIT_VALIDATION_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "REJECTED"
    assert payload["BROKER_NOT_INVOKED"] is True
    assert not database.exists()


def test_replay_cli_is_current_time_independent_and_never_invokes_runner(
    tmp_path: Path, capsys
) -> None:
    manifest, fixture = _write_restartable_manifest(tmp_path)
    database = tmp_path / "runtime.sqlite3"
    args = _new_run_args(
        manifest=manifest,
        fixture=fixture,
        database=database,
        output=tmp_path / "runtime",
        idempotency_key="cli-replay-1",
    )
    assert lifecycle_main(args) == EXIT_SUCCESS
    run = json.loads(capsys.readouterr().out)
    with sqlite3.connect(database) as connection:
        attempts_before = connection.execute(
            "SELECT COUNT(*) FROM lifecycle_attempts"
        ).fetchone()[0]

    replay_args = [
        "--database",
        str(database),
        "--replay-run-id",
        run["run_id"],
    ]
    assert lifecycle_main(replay_args) == EXIT_SUCCESS
    first_text = capsys.readouterr().out
    assert lifecycle_main(replay_args) == EXIT_SUCCESS
    second_text = capsys.readouterr().out
    assert first_text == second_text
    payload = json.loads(first_text)
    assert payload["replay_status"] == "STABLE"
    assert payload["REPORT_HASH_STABLE"] is True
    assert payload["RUNNER_INVOKED"] is False
    assert payload["MANUAL_TRADE_CREATED"] is False
    assert payload["BROKER_NOT_INVOKED"] is True
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM lifecycle_attempts"
        ).fetchone()[0] == attempts_before

    assert replay_main(
        ["--database", str(database), "--run-id", run["run_id"]]
    ) == EXIT_STABLE
    standalone = json.loads(capsys.readouterr().out)
    assert standalone["report_hash"] == payload["report_hash"]


def test_risk_continuation_resume_uses_only_explicit_authority_database(
    confirmation_fixture: ConfirmationFixture,
    tmp_path: Path,
    capsys,
) -> None:
    references = _risk_references(confirmation_fixture, tmp_path)
    as_of = _risk_continuation_as_of(confirmation_fixture)
    configuration_references = _risk_configuration_references(
        confirmation_fixture,
        references,
        tmp_path,
    )
    command = CanonicalLifecycleCommand(
        run_type=LifecycleRunType.RISK_REDUCTION_CONTINUATION,
        decision_date=as_of.astimezone(ZoneInfo("Asia/Shanghai")).date(),
        as_of_time=as_of.astimezone(timezone.utc),
        idempotency_key="cli-risk-resume-1",
        input_manifest_id=None,
        input_content_hash=None,
        input_manifest_locator=None,
        input_references=references,
        configuration_references=configuration_references,
        model_references=(),
        stop_after_stage=None,
        output_directory=tmp_path / "risk-output",
        authority_database_locator=confirmation_fixture.repository.path,
    )
    journal_path = tmp_path / "risk-journal.sqlite3"
    repository = SQLiteLifecycleRunRepository(journal_path)
    runner = _runner(
        repository=repository,
        command=command,
        manifest=None,
        configurations=RuntimeConfigurationReader().read_all(
            command.configuration_references
        ),
    )
    initial = runner.run(command)
    assert initial.run.status.value == "WAITING_FOR_MANUAL_CONFIRMATION"

    before = _authority_row_counts(confirmation_fixture.repository.path)
    assert lifecycle_main(
        [
            "--resume-run-id",
            str(command.run_id),
            "--database",
            str(journal_path),
            "--authority-database",
            str(confirmation_fixture.repository.path),
        ]
    ) == EXIT_SUCCESS
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "WAITING_FOR_MANUAL_CONFIRMATION"
    assert payload["MANUAL_CONFIRMATION_REQUIRED"] is True
    assert payload["MANUAL_TRADE_CREATED"] is False
    assert payload["NO_ORDER_CREATED"] is True
    assert payload["BROKER_NOT_INVOKED"] is True
    assert payload["NO_FILL_CREATED"] is True
    assert _authority_row_counts(confirmation_fixture.repository.path) == before


def _authority_row_counts(path: Path) -> tuple[int, int, int]:
    with sqlite3.connect(path) as connection:
        return (
            connection.execute(
                "SELECT COUNT(*) FROM risk_reduction_confirmation_attempts"
            ).fetchone()[0],
            connection.execute(
                "SELECT COUNT(*) FROM manual_trade_records"
            ).fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM manual_fills").fetchone()[0],
        )


def _invalid_artifact_manifest(tmp_path: Path) -> tuple[Path, StageFixture]:
    _, fixture = _write_restartable_manifest(tmp_path / "fixture")
    available_at = fixture.as_of_time
    references = tuple(
        sorted(
            (
                LifecycleObjectReference(
                    object_type=LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST,
                    object_id=LifecycleObjectId("invalid-composite"),
                    content_hash="sha256:" + "1" * 64,
                    reader_kind=(
                        LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER
                    ),
                    locator=str(tmp_path / "missing-composite"),
                    available_at=available_at,
                ),
                LifecycleObjectReference(
                    object_type=LifecycleObjectType.SOURCE_MANIFEST,
                    object_id=LifecycleObjectId("invalid-source"),
                    content_hash="sha256:" + "2" * 64,
                    reader_kind=LifecycleReaderKind.SOURCE_MANIFEST_READER,
                    locator=str(tmp_path / "missing-source.json"),
                    available_at=available_at,
                ),
            ),
            key=lambda item: item.sort_key,
        )
    )
    manifest = CanonicalLifecycleInputManifest.create(
        decision_date=fixture.decision_date,
        as_of_time=fixture.as_of_time,
        created_at=fixture.as_of_time + timedelta(seconds=1),
        input_references=references,
        configuration_references=(),
        model_references=(),
        authority_ceiling=LifecycleAuthorityCeiling(),
        limitations=("INVALID_ARTIFACT_TEST",),
    )
    path = tmp_path / "invalid-input-manifest.json"
    path.write_text(json.dumps(manifest.to_canonical_dict()), encoding="utf-8")
    return path, replace(
        fixture,
        initial_references=references,
        configuration_references=(),
        model_references=(),
    )
