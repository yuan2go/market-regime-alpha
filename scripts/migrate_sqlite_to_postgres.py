#!/usr/bin/env python3
"""Import quiescent SQLite authorities into an empty PostgreSQL authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from market_regime_alpha.persistence.migration_manifest import (
    SQLiteMigrationManifest,
)
from market_regime_alpha.persistence.repository_factory import (
    add_database_arguments,
    settings_from_namespace,
)
from market_regime_alpha.persistence.sqlite_to_postgres import (
    SQLiteToPostgresMigrationError,
    SQLiteToPostgresMigrator,
)


EXIT_SUCCESS = 0
EXIT_CONFIGURATION_ERROR = 2
EXIT_MIGRATION_FAILED = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/postgres-migration"),
    )
    add_database_arguments(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        manifest = SQLiteMigrationManifest.from_json(args.manifest.resolve())
        settings = settings_from_namespace(args)
        migrator = SQLiteToPostgresMigrator()
        plan = migrator.plan(manifest, settings)
        report = migrator.execute(plan, args.output_root.resolve())
    except SQLiteToPostgresMigrationError as exc:
        _emit_error("MIGRATION_FAILED", exc)
        return EXIT_MIGRATION_FAILED
    except (OSError, TypeError, ValueError) as exc:
        _emit_error("CONFIGURATION_REJECTED", exc)
        return EXIT_CONFIGURATION_ERROR
    print(
        json.dumps(
            {
                "status": report.result,
                "report_id": report.report_id,
                "report_hash": report.content_hash,
                "source_row_count": report.source_row_count,
                "target_row_count": report.target_row_count,
                "source_count": len(report.sources),
                "table_count": len(report.tables),
                "NO_SQLITE_SOURCE_MUTATION": True,
                "NO_DUAL_WRITE": True,
                "NO_BROKER_AUTHORITY": True,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return EXIT_SUCCESS


def _emit_error(reason_code: str, exc: Exception) -> None:
    print(
        json.dumps(
            {
                "status": "FAILED",
                "reason_code": reason_code,
                "error": f"{type(exc).__name__}:{exc}",
                "NO_SQLITE_SOURCE_MUTATION": True,
                "NO_DUAL_WRITE": True,
                "NO_BROKER_AUTHORITY": True,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
