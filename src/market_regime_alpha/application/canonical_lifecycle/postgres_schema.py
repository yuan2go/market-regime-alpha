"""Catalog verification for the PostgreSQL canonical lifecycle journal."""

from __future__ import annotations

from typing import Any

import psycopg

from market_regime_alpha.persistence.postgres.schema import (
    verify_postgres_authority_schema,
)


LIFECYCLE_TABLES = frozenset(
    {
        "lifecycle_attempts",
        "lifecycle_events",
        "lifecycle_runs",
        "lifecycle_stage_receipts",
        "lifecycle_stages",
    }
)
LIFECYCLE_TRIGGERS = frozenset(
    {
        "lifecycle_attempts_completion_only",
        "lifecycle_attempts_no_delete",
        "lifecycle_events_no_delete",
        "lifecycle_events_no_update",
        "lifecycle_runs_identity_immutable",
        "lifecycle_runs_no_delete",
        "lifecycle_stage_receipts_no_delete",
        "lifecycle_stage_receipts_no_update",
        "lifecycle_stages_no_delete",
        "lifecycle_terminal_stages_immutable",
    }
)


def verify_postgres_lifecycle_schema(
    connection: psycopg.Connection[Any],
) -> None:
    """Fail closed unless migration 011's tables and guards are present."""

    verify_postgres_authority_schema(connection)
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema()"
        )
    }
    triggers = {
        str(row[0])
        for row in connection.execute(
            "SELECT trigger_name FROM information_schema.triggers "
            "WHERE trigger_schema = current_schema()"
        )
    }
    missing_tables = sorted(LIFECYCLE_TABLES - tables)
    missing_triggers = sorted(LIFECYCLE_TRIGGERS - triggers)
    if missing_tables or missing_triggers:
        raise RuntimeError(
            "PostgreSQL lifecycle schema is incomplete: "
            f"tables={missing_tables}, triggers={missing_triggers}"
        )


__all__ = [
    "LIFECYCLE_TABLES",
    "LIFECYCLE_TRIGGERS",
    "verify_postgres_lifecycle_schema",
]
