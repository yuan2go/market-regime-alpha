"""Bounded PostgreSQL administration for Continuous Research runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousSessionPhase,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.continuous_research.replay import (
    replay_continuous_research,
)
from market_regime_alpha.application.continuous_research.report import (
    build_continuous_research_report,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.settings import DatabaseSettings


SUCCESS = 0
ARGUMENT_ERROR = 2
DATABASE_ERROR = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        help="Explicit PostgreSQL authority; environment fallback is disabled.",
    )
    parser.add_argument(
        "--application-schema",
        default="market_regime_alpha",
        help="Explicit lowercase PostgreSQL schema authority.",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--run-command", type=Path, required=True)
    admit = subparsers.add_parser("admit-tick")
    admit.add_argument("--tick-command", type=Path, required=True)
    admit.add_argument(
        "--session-phase",
        choices=tuple(item.value for item in ContinuousSessionPhase),
        required=True,
    )
    for operation in ("resume", "report", "replay"):
        command = subparsers.add_parser(operation)
        command.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    factory: PostgresConnectionFactory | None = None
    try:
        args = build_parser().parse_args(argv)
        if args.database_url is None:
            raise ValueError("explicit --database-url is required")
        settings = DatabaseSettings.from_sources(
            database_url=args.database_url,
            sqlite_path=None,
            environ={},
        )
        factory = PostgresConnectionFactory(
            settings, application_schema=args.application_schema
        )
        read_only = args.operation in {"report", "replay"}
        journal = PostgresContinuousResearchJournal(
            factory, apply_migrations=not read_only
        )
        output = _dispatch(args, journal)
        _emit(output)
        return SUCCESS
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        _emit_error("ARGUMENT_OR_IDENTITY_INVALID", exc)
        return ARGUMENT_ERROR
    except Exception as exc:
        _emit_error("POSTGRESQL_OPERATION_FAILED", exc)
        return DATABASE_ERROR
    finally:
        if factory is not None:
            factory.close()


def _dispatch(
    args: argparse.Namespace, journal: PostgresContinuousResearchJournal
) -> dict[str, Any]:
    if args.operation == "prepare":
        command = ContinuousResearchCommand.from_canonical_dict(
            _load_json_object(args.run_command)
        )
        snapshot = journal.create_or_get(command)
        return {
            "status": snapshot.status.value,
            "operation": "PREPARE",
            "run_id": str(command.run_id),
            "command_hash": command.command_hash,
            **_authority_ceiling(),
        }
    if args.operation == "admit-tick":
        command = RuntimeTickCommand.from_canonical_dict(
            _load_json_object(args.tick_command)
        )
        tick = journal.admit_tick(
            command,
            session_phase=ContinuousSessionPhase(args.session_phase),
        )
        return {
            "status": tick.status.value,
            "operation": "ADMIT_TICK",
            "run_id": str(command.run_id),
            "tick_id": str(command.tick_id),
            "tick_sequence": tick.tick_sequence,
            **_authority_ceiling(),
        }
    run_id = ArtifactId(args.run_id)
    if args.operation == "resume":
        snapshot = journal.resume(run_id)
        return {
            "status": snapshot.status.value,
            "operation": "RESUME",
            "run_id": str(run_id),
            "tick_count": len(snapshot.ticks),
            **_authority_ceiling(),
        }
    if args.operation == "report":
        return build_continuous_research_report(journal, run_id)
    if args.operation == "replay":
        return replay_continuous_research(journal, run_id).to_canonical_dict()
    raise ValueError("unsupported Continuous Research operation")


def _load_json_object(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("command file must contain a JSON object")
    return payload


def _authority_ceiling() -> dict[str, bool]:
    return {
        "entry_authority_granted": False,
        "broker_authority_granted": False,
        "daily_decision_window_summary_delivered": False,
    }


def _emit(payload: Mapping[str, Any]) -> None:
    print(
        json.dumps(
            dict(payload),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _emit_error(reason_code: str, exc: BaseException) -> None:
    _emit(
        {
            "status": "FAILED",
            "reason_code": reason_code,
            "error_type": type(exc).__name__,
            "message": "Continuous Research command failed; credentials are redacted",
            **_authority_ceiling(),
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
