#!/usr/bin/env python3
"""Apply and verify the packaged PostgreSQL authority migrations."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.schema import (
    EXPECTED_AUTHORITY_TABLES,
    verify_postgres_authority_schema,
)
from market_regime_alpha.persistence.repository_factory import (
    add_database_arguments,
    settings_from_namespace,
)
from market_regime_alpha.persistence.settings import DatabaseBackend


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_database_arguments(parser)
    parser.add_argument("--verify-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = settings_from_namespace(args)
    if settings.backend is not DatabaseBackend.POSTGRES:
        raise ValueError("authority migrations require PostgreSQL")
    with PostgresConnectionFactory(settings) as factory:
        applied = () if args.verify_only else PostgresMigrator().apply_all(factory)
        with factory.connection(read_only=True) as connection:
            verify_postgres_authority_schema(connection)
            migration = connection.execute(
                "SELECT count(*), max(version) FROM schema_migrations"
            ).fetchone()
            server_version = connection.execute("SHOW server_version").fetchone()
            schema = connection.execute("SELECT current_schema()").fetchone()
    assert migration is not None and server_version is not None and schema is not None
    print(
        json.dumps(
            {
                "status": "PASS",
                "newly_applied_versions": [item.version for item in applied],
                "migration_count": int(migration[0]),
                "latest_migration": int(migration[1]),
                "authority_table_count": len(EXPECTED_AUTHORITY_TABLES),
                "postgres_server_version": str(server_version[0]),
                "postgres_schema": str(schema[0]),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
