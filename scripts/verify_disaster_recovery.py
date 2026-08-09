"""Verify PostgreSQL and immutable-Artifact recovery in an isolated database."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path

from market_regime_alpha.application.runtime_operations.disaster_recovery import (
    backup_restore_verify,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.settings import (
    DATABASE_URL_ENV,
    DatabaseSettings,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create and independently restore a PostgreSQL/Artifact backup"
    )
    parser.add_argument("--database-url", default=os.getenv(DATABASE_URL_ENV))
    parser.add_argument("--database-schema", default="market_regime_alpha")
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    args = parser.parse_args()
    settings = DatabaseSettings.from_sources(
        database_url=args.database_url,
        application_schema=args.database_schema,
        environ={},
    )
    factory = PostgresConnectionFactory(
        settings,
        min_size=0,
        max_size=4,
        application_schema=args.database_schema,
    )
    try:
        result = backup_restore_verify(
            source_factory=factory,
            database_url=settings.require_database_url(),
            artifact_root=args.artifact_root.resolve(),
            backup_root=args.backup_root.resolve(),
            verified_at=datetime.now(UTC).replace(microsecond=0),
        )
    finally:
        factory.close()
    print(json.dumps(result.to_canonical_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
