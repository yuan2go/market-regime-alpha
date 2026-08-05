from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from market_regime_alpha.application.free_data_operation.service import (
    FreeDataOperationPreparation,
)
from market_regime_alpha.cli.free_data_operation import (
    free_data_operation_payload,
    prepare_main,
    run_main,
)
from market_regime_alpha.core.identity import ArtifactId


HASH = "sha256:" + "a" * 64


def test_run_cli_before_decision_fails_closed_without_provider_or_database(
    tmp_path: Path, capsys
) -> None:
    future = date.today() + timedelta(days=1)

    exit_code = run_main(
        [
            "--output-root",
            str(tmp_path / "artifacts"),
            "--runtime-configuration",
            str(tmp_path / "missing-configuration"),
            "--decision-date",
            future.isoformat(),
            "--idempotency-key",
            "future-smoke",
        ]
    )

    assert exit_code == 4
    output = capsys.readouterr().out
    assert "DECISION_TIME_NOT_REACHED" in output
    assert '"BROKER_NOT_INVOKED": true' in output
    assert '"NO_ORDER_CREATED": true' in output
    assert '"NO_FILL_CREATED": true' in output


def test_prepare_cli_is_not_blocked_by_pre_decision_clock(
    tmp_path: Path, capsys
) -> None:
    future = date.today() + timedelta(days=1)

    exit_code = prepare_main(
        [
            "--output-root",
            str(tmp_path / "artifacts"),
            "--runtime-configuration",
            str(tmp_path / "missing-configuration"),
            "--decision-date",
            future.isoformat(),
            "--idempotency-key",
            "future-prepare",
        ]
    )

    assert exit_code == 11
    output = capsys.readouterr().out
    assert "DECISION_TIME_NOT_REACHED" not in output
    assert '"runtime_status": "FAILED_CLOSED"' in output


def test_payload_names_engineering_and_authority_boundaries(tmp_path: Path) -> None:
    references = tuple(
        SimpleNamespace(kind=kind, artifact_id=ArtifactId(identity))
        for kind, identity in (
            ("FULL_SOURCE_MANIFEST", "source-manifest-test"),
            ("MARKET_DATA_DATASET", "market-data-test"),
            ("OPERATIONAL_UNIVERSE", "universe-test"),
        )
    )
    manifest_path = tmp_path / "prepared" / "prepared-id"
    preparation = FreeDataOperationPreparation(
        source=SimpleNamespace(
            acquired=SimpleNamespace(
                provider_result=SimpleNamespace(raw_payloads=())
            )
        ),
        prepared_inputs=SimpleNamespace(
            manifest=SimpleNamespace(
                manifest_id=ArtifactId("prepared-id"),
                artifacts=references,
                provider_profile_id="TENCENT_FREE_OPERATIONAL_V1",
                configuration_hash=HASH,
            ),
            manifest_path=manifest_path,
        ),
        controlled_command=SimpleNamespace(
            run_id=ArtifactId("controlled-parent"),
            decision_date=date(2026, 8, 5),
            decision_time=datetime(2026, 8, 5, 6, 55, tzinfo=timezone.utc),
            code_revision="test-revision",
            configuration_manifest_hash=HASH,
        ),
        controlled_preparation=SimpleNamespace(
            snapshot=SimpleNamespace(status=SimpleNamespace(value="STATIC_READY"), stages=()),
            universe=SimpleNamespace(symbols=("600000.SH",)),
            static_bundle=SimpleNamespace(artifact_id=ArtifactId("static-bundle-test")),
        ),
        database_authority="postgresql://user@localhost/db#schema=test",
    )

    payload = free_data_operation_payload(preparation)

    assert payload["runtime_status"] == "STATIC_READY"
    assert payload["entry_status"] == "NOT_REACHED"
    assert payload["parent_run_id"] == "controlled-parent"
    assert payload["canonical_run_id"] is None
    assert payload["source_manifest_id"] == "source-manifest-test"
    assert payload["market_data_dataset_id"] == "market-data-test"
    assert payload["universe_id"] == "universe-test"
    assert payload["TRADING_AUTHORITY_GRANTED"] is False
    assert payload["NO_POSITION_MUTATION"] is True


def test_pyproject_exposes_all_six_free_data_commands() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    for command in (
        "prepare-free-data-operation",
        "run-free-data-decision-window",
        "resume-free-data-operation",
        "replay-free-data-operation",
        "report-free-data-operation",
        "inspect-free-data-operation",
    ):
        assert f"{command} =" in pyproject
