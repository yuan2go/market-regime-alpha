"""PostgreSQL owner for exploratory full-market Research Universe snapshots."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.universe.research import FreeResearchUniverseSnapshot


class PostgresFreeResearchUniverseRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def publish(
        self, snapshot: FreeResearchUniverseSnapshot
    ) -> FreeResearchUniverseSnapshot:
        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO free_data_research_universe_snapshot(
                    snapshot_id, snapshot_hash, as_of_date, known_at,
                    provider_id, source_manifest_id, source_manifest_hash,
                    raw_archive_id, evidence_origin, data_eligibility,
                    evidence_ceiling, formal_pit, security_master_count,
                    included_count, unknown_count, payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    false, %s, %s, %s, %s, %s
                )
                ON CONFLICT (snapshot_id) DO NOTHING
                """,
                (
                    str(snapshot.snapshot_id),
                    snapshot.snapshot_hash,
                    snapshot.as_of_date,
                    snapshot.known_at,
                    snapshot.provider_id,
                    str(snapshot.source_manifest_reference.artifact_id),
                    snapshot.source_manifest_reference.content_hash,
                    snapshot.raw_archive_id,
                    snapshot.evidence_origin.value,
                    snapshot.data_eligibility.value,
                    snapshot.evidence_ceiling.value,
                    snapshot.security_master_count,
                    snapshot.included_count,
                    snapshot.unknown_count,
                    Jsonb(snapshot.to_canonical_dict()),
                    snapshot.known_at,
                ),
            )
            stored = connection.execute(
                "SELECT snapshot_hash FROM free_data_research_universe_snapshot "
                "WHERE snapshot_id = %s",
                (str(snapshot.snapshot_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != snapshot.snapshot_hash:
                raise ValueError("Research Universe snapshot identity conflict")
            for item in snapshot.records:
                connection.execute(
                    """
                    INSERT INTO free_data_research_universe_member(
                        snapshot_id, symbol, membership_status,
                        listing_status, payload_json
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (snapshot_id, symbol) DO NOTHING
                    """,
                    (
                        str(snapshot.snapshot_id),
                        item.symbol,
                        item.membership_status.value,
                        item.listing_status.value,
                        Jsonb(item.to_canonical_dict()),
                    ),
                )
            count = connection.execute(
                "SELECT count(*) FROM free_data_research_universe_member "
                "WHERE snapshot_id = %s",
                (str(snapshot.snapshot_id),),
            ).fetchone()
            if count is None or int(count[0]) != snapshot.security_master_count:
                raise ValueError("Research Universe member set is incomplete")

        self._factory.run_transaction(operation)
        return self.get(snapshot.snapshot_id)

    def get(self, snapshot_id: ArtifactId) -> FreeResearchUniverseSnapshot:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT snapshot_hash, payload_json "
                "FROM free_data_research_universe_snapshot "
                "WHERE snapshot_id = %s",
                (str(snapshot_id),),
            ).fetchone()
            members = connection.execute(
                "SELECT payload_json FROM free_data_research_universe_member "
                "WHERE snapshot_id = %s ORDER BY symbol",
                (str(snapshot_id),),
            ).fetchall()
        if row is None or not isinstance(row[1], dict):
            raise KeyError(str(snapshot_id))
        snapshot = FreeResearchUniverseSnapshot.from_canonical_dict(row[1])
        if str(row[0]) != snapshot.snapshot_hash:
            raise ValueError("Research Universe owner hash diverged")
        stored_members = tuple(item[0] for item in members)
        expected_members = tuple(item.to_canonical_dict() for item in snapshot.records)
        if stored_members != expected_members:
            raise ValueError("Research Universe member projection diverged")
        return snapshot

    def latest_known_at(
        self, *, as_of_date: date, known_at: datetime
    ) -> FreeResearchUniverseSnapshot:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT snapshot_id
                FROM free_data_research_universe_snapshot
                WHERE as_of_date = %s AND known_at <= %s
                ORDER BY known_at DESC, snapshot_id DESC
                LIMIT 1
                """,
                (as_of_date, known_at),
            ).fetchone()
        if row is None:
            raise KeyError("Research Universe was not known at that time")
        return self.get(ArtifactId(str(row[0])))


__all__ = ["PostgresFreeResearchUniverseRepository"]
