"""Explicit read-only inspection of retained historical identities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from market_regime_alpha.application.continuous_research.postgres_journal import PostgresContinuousResearchJournal
from market_regime_alpha.application.continuous_research.replay import replay_continuous_research
from market_regime_alpha.application.continuous_research.report import build_continuous_research_report
from market_regime_alpha.application.shadow_research.operations import ResearchShadowOperations
from market_regime_alpha.application.state_system.repository import StateSystemIntegrityError, decode_and_verify_pool
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.settings import DatabaseSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url")
    parser.add_argument("--application-schema", default="market_regime_alpha")
    commands = parser.add_subparsers(dest="operation", required=True)
    for name in ("runtime-report", "runtime-replay"):
        command = commands.add_parser(name)
        command.add_argument("--run-id", required=True)
    report = commands.add_parser("shadow-report")
    report.add_argument("--session-id", required=True)
    replay = commands.add_parser("shadow-replay")
    replay.add_argument("--decision-id", required=True)
    pool = commands.add_parser("verify-pool")
    pool.add_argument("--artifact", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        database = None
        if args.operation == "verify-pool":
            result = decode_and_verify_pool(args.artifact.read_text(encoding="utf-8"))
        else:
            if not args.database_url:
                raise ValueError("explicit --database-url is required")
            settings = DatabaseSettings.from_sources(database_url=args.database_url, environ={})
            with PostgresConnectionFactory(
                settings, application_schema=args.application_schema, read_only=True,
            ) as factory:
                PostgresMigrator().verify_current(factory)
                with factory.connection() as connection:
                    identity = connection.execute(
                        "SELECT current_database(), oid, current_schema() FROM pg_database WHERE datname=current_database()"
                    ).fetchone()
                if identity is None:
                    raise ValueError("database identity is unavailable")
                database = {"name": identity[0], "oid": identity[1], "schema": identity[2]}
                if args.operation in {"runtime-report", "runtime-replay"}:
                    journal = PostgresContinuousResearchJournal(factory, apply_migrations=False)
                    run_id = ArtifactId(args.run_id)
                    result = (
                        build_continuous_research_report(journal, run_id)
                        if args.operation == "runtime-report"
                        else replay_continuous_research(journal, run_id).to_canonical_dict()
                    )
                else:
                    shadow = ResearchShadowOperations(factory)
                    result = (
                        shadow.report(ArtifactId(args.session_id))
                        if args.operation == "shadow-report"
                        else shadow.replay(ArtifactId(args.decision_id)).to_canonical_dict()
                    )
        print(json.dumps({
            "scope": "HISTORICAL_READ_ONLY", "current_execution_authority": False,
            "database": database, "result": result,
        }, sort_keys=True, default=str))
        return 0
    except (ValueError, TypeError, KeyError, OSError, StateSystemIntegrityError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc), "current_execution_authority": False}, sort_keys=True))
        return 2
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__, "current_execution_authority": False}, sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
