from __future__ import annotations

import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

from market_regime_alpha.application.daily_loop import (
    DailyLoopRunner,
    DailyRunCommand,
    RunMode,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.providers.public_composite import (
    PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
    publish_source_archive,
)
from market_regime_alpha.universe.daily_exploratory import smoke_pool_policy_v1
from tests.application.daily_loop.public_fixture import DECISION, public_fixture
from tests.postgres_path_repositories import (
    PostgresDailyRunRepository,
    postgres_cli_arguments,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = PROJECT_ROOT / "scripts" / "run_exploratory_daily_loop.py"
CODE_REVISION = "772ecfb09410588b5a406ad900d793a5850e60d5"


def test_cli_semantically_replays_an_existing_run(tmp_path: Path) -> None:
    policy = smoke_pool_policy_v1()
    _, provider_result, source_manifest = public_fixture(policy=policy)
    archive = publish_source_archive(
        root=tmp_path / "fixture-archives",
        provider_result=provider_result,
        source_manifest=source_manifest,
    )
    command = DailyRunCommand(
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        run_mode=RunMode.REPLAY,
        provider_profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        universe_policy_id=str(policy.policy_id),
        model_set_id="daily-b0-b1-v1",
        configuration_identity=ArtifactId("daily-loop-cli-test-config-v1"),
        output_root=tmp_path / "runtime",
        replay_source_manifest_id=source_manifest.source_manifest_id,
    )
    runner = DailyLoopRunner(
        repository=PostgresDailyRunRepository(tmp_path / "runtime.postgres-scope"),
        code_revision=CODE_REVISION,
    )
    completed = runner.run(command, replay_archive_path=archive)
    assert completed.record.daily_run_id is not None

    process = subprocess.run(
        (
            sys.executable,
            str(SCRIPT),
            "--output-root",
            str(command.output_root),
            *postgres_cli_arguments(tmp_path / "runtime.postgres-scope"),
            "replay",
            "--run-id",
            str(completed.record.daily_run_id),
        ),
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 0, process.stderr
    payload = json.loads(process.stdout)
    assert payload["daily_run_id"] == str(completed.record.daily_run_id)
    assert payload["artifact_id"] == completed.decision_artifact.artifact_id
    assert payload["replay_hash"] == completed.decision_artifact.checksums_hash


def test_new_cli_has_no_legacy_or_broker_dependency() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "dividend_t.storage" not in source
    assert "xtquant" not in source
    assert "broker" not in source.lower()


def test_staged_cli_commands_share_one_run_request_identity(
    tmp_path: Path,
) -> None:
    namespace = runpy.run_path(str(SCRIPT), run_name="daily_loop_cli_test")
    parser = namespace["build_parser"]()
    build_command = namespace["_build_command"]
    commands = []
    for operation in (
        "prepare-history",
        "freeze-security-status",
        "freeze-decision-quote",
        "finalize-run",
    ):
        args = parser.parse_args(
            (
                "--output-root",
                str(tmp_path / "runtime"),
                operation,
                "--decision-date",
                "2025-02-03",
                "--provider-profile",
                "public-composite-live-v1",
            )
        )
        commands.append(
            build_command(
                args,
                output_root=(tmp_path / "runtime").resolve(),
            )
        )

    assert len({item.run_request_id for item in commands}) == 1
    assert all(item == commands[0] for item in commands)


def test_finalize_cli_does_not_construct_live_clients(
    tmp_path: Path,
) -> None:
    namespace = runpy.run_path(str(SCRIPT), run_name="daily_loop_cli_test")

    def forbidden_client(*args, **kwargs):
        raise AssertionError("FINALIZE_ATTEMPTED_TO_CONSTRUCT_LIVE_CLIENT")

    namespace["BaoStockHistoryClient"] = forbidden_client
    namespace["BaoStockSecurityStatusClient"] = forbidden_client
    namespace["TencentCurrentQuoteClient"] = forbidden_client

    with pytest.raises(ValueError, match="finalize requires"):
        namespace["main"](
            (
                "--output-root",
                str(tmp_path / "runtime"),
                *postgres_cli_arguments(tmp_path / "runtime.postgres-scope"),
                "finalize-run",
                "--decision-date",
                "2025-02-03",
            )
        )
