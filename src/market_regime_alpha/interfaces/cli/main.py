"""Small `mra` command tree over the sole target composition root."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from io import TextIOBase
import json
import os
from pathlib import Path
import sys
from typing import Mapping, Sequence
from uuid import UUID

import psycopg

from market_regime_alpha.bootstrap import (
    TargetSettings,
    apply_database_recreate,
    bootstrap_application,
    bootstrap_database,
    load_recreate_plan,
    make_recreate_authorization,
    plan_database_recreate,
    verify_database,
)
from market_regime_alpha.shared.errors import MraError


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIOBase | None = None,
    stderr: TextIOBase | None = None,
) -> int:
    output = sys.stdout if stdout is None else stdout
    error_output = sys.stderr if stderr is None else stderr
    try:
        arguments = _parser().parse_args(argv)
        settings = TargetSettings.from_environ(os.environ if environ is None else environ)
        payload = _dispatch(arguments, settings)
        output.write(json.dumps(_json_value(payload), sort_keys=True) + "\n")
        return 0
    except (MraError, ValueError, OSError, psycopg.Error) as exc:
        error_output.write(
            json.dumps(
                {"error_type": type(exc).__name__, "message": str(exc)},
                sort_keys=True,
            )
            + "\n"
        )
        return 2


def _dispatch(arguments: argparse.Namespace, settings: TargetSettings) -> object:
    if arguments.area == "db":
        if arguments.db_command == "bootstrap":
            return bootstrap_database(settings)
        if arguments.db_command == "verify":
            return verify_database(settings)
        if arguments.db_command == "recreate-plan":
            plan = plan_database_recreate(
                settings,
                make_recreate_authorization(
                    expected_database_name=arguments.expected_database_name,
                    expected_database_oid=arguments.expected_database_oid,
                    operator_id=arguments.operator_id,
                    reason=arguments.reason,
                    backup_attestation=arguments.backup_attestation,
                ),
            )
            if arguments.output is not None:
                arguments.output.write_text(plan.to_json(), encoding="utf-8")
            return plan
        if arguments.db_command == "recreate-apply":
            plan = load_recreate_plan(arguments.plan.read_text(encoding="utf-8"))
            return apply_database_recreate(
                settings,
                plan,
                challenge=arguments.challenge,
                operator_id=arguments.operator_id,
            )
    if arguments.area == "runtime":
        with bootstrap_application(settings) as application:
            if arguments.runtime_command == "inspect":
                return application.runtime.inspect_run(arguments.run_id)
            if arguments.runtime_command == "recover":
                recovered = application.runtime.recover_expired(
                    actor_id=arguments.actor_id,
                    reason_code="LEASE_EXPIRED",
                )
                return {"recovered_attempt_ids": recovered}
    raise ValueError("command is not implemented")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mra")
    areas = parser.add_subparsers(dest="area", required=True)

    database = areas.add_parser("db")
    database_commands = database.add_subparsers(dest="db_command", required=True)
    database_commands.add_parser("bootstrap")
    database_commands.add_parser("verify")
    recreate_plan = database_commands.add_parser("recreate-plan")
    recreate_plan.add_argument("--expected-database-name", required=True)
    recreate_plan.add_argument("--expected-database-oid", required=True, type=int)
    recreate_plan.add_argument("--operator-id", required=True)
    recreate_plan.add_argument("--reason", required=True)
    recreate_plan.add_argument("--backup-attestation", required=True)
    recreate_plan.add_argument("--output", type=Path)
    recreate_apply = database_commands.add_parser("recreate-apply")
    recreate_apply.add_argument("--plan", required=True, type=Path)
    recreate_apply.add_argument("--challenge", required=True)
    recreate_apply.add_argument("--operator-id", required=True)

    runtime = areas.add_parser("runtime")
    runtime_commands = runtime.add_subparsers(dest="runtime_command", required=True)
    inspect = runtime_commands.add_parser("inspect")
    inspect.add_argument("--run-id", required=True, type=UUID)
    recover = runtime_commands.add_parser("recover")
    recover.add_argument("--actor-id", required=True)
    return parser


def _json_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_value(item) for item in value]
    if isinstance(value, (UUID, datetime, date, Path)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


__all__ = ["main"]
