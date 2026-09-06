"""Bounded exact-row guard for previously owner-reloaded Outcome price inputs."""

from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql

from market_regime_alpha.shared.hashing import canonical_json_sha256


def outcome_economic_guard(connection: psycopg.Connection[Any], revisions: tuple[UUID, ...]) -> str:
    # Explicit concrete owner tables, not a subject registry. Decimal SQL JSON
    # stays text so checking bytes cannot lose numeric precision through floats.
    rosters = []
    for table in ("market_target_outcome_revision", "market_target_outcome_source", "market_target_outcome_observation"):
        rows = connection.execute(
            sql.SQL(
                'SELECT to_jsonb(fact)::text FROM mra.{} fact WHERE market_target_outcome_revision_id = ANY(%s) ORDER BY to_jsonb(fact)::text COLLATE "C"'
            ).format(sql.Identifier(table)),
            (list(revisions),),
        ).fetchall()
        rosters.append((table, tuple(row[0] for row in rows)))
    return canonical_json_sha256(tuple(rosters))
