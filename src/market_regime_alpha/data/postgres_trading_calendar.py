"""Canonical Calendar payload snapshot anchored to the existing PIT owner."""

from __future__ import annotations

from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_artifact_authority import (
    PITArtifactAuthorityResolution,
)
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class TradingCalendarSnapshotConflict(ValueError):
    """The PIT owner receipt and Calendar snapshot diverged."""


class PostgresPITTradingCalendarSnapshotRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def record(self, calendar: TradingCalendarArtifact) -> TradingCalendarArtifact:
        payload = calendar.to_canonical_dict()

        def operation(connection: Any) -> None:
            resolution_row = connection.execute(
                """
                SELECT resolution_id, resolution_hash, payload_json, resolved_at
                FROM pit_artifact_authority_resolution
                WHERE reference_kind = 'TRADING_CALENDAR'
                  AND artifact_id = %s AND artifact_hash = %s
                """,
                (str(calendar.artifact_id), calendar.content_hash),
            ).fetchone()
            if resolution_row is None or not isinstance(resolution_row[2], Mapping):
                raise TradingCalendarSnapshotConflict(
                    "Canonical Trading Calendar PIT owner is missing"
                )
            try:
                resolution = PITArtifactAuthorityResolution.from_canonical_dict(
                    dict(resolution_row[2])
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise TradingCalendarSnapshotConflict(
                    "Canonical Trading Calendar PIT owner replay failed"
                ) from exc
            if (
                str(resolution.resolution_id) != str(resolution_row[0])
                or resolution.resolution_hash != str(resolution_row[1])
                or resolution.reference.reference_kind != "TRADING_CALENDAR"
                or resolution.reference.artifact_id != calendar.artifact_id
                or resolution.reference.content_hash != calendar.content_hash
            ):
                raise TradingCalendarSnapshotConflict(
                    "Canonical Trading Calendar PIT owner binding mismatch"
                )
            snapshotted_at = connection.execute(
                "SELECT date_trunc('second', clock_timestamp())"
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO pit_trading_calendar_canonical_snapshot(
                    resolution_id, resolution_hash,
                    calendar_id, calendar_hash, source_dataset_id,
                    payload_json, snapshotted_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (resolution_id) DO NOTHING
                """,
                (
                    str(resolution.resolution_id),
                    resolution.resolution_hash,
                    str(calendar.artifact_id),
                    calendar.content_hash,
                    str(calendar.source_dataset_id),
                    Jsonb(payload),
                    snapshotted_at,
                ),
            )
            row = connection.execute(
                """
                SELECT resolution_hash, calendar_hash,
                       source_dataset_id, payload_json
                FROM pit_trading_calendar_canonical_snapshot
                WHERE resolution_id = %s
                """,
                (str(resolution.resolution_id),),
            ).fetchone()
            if row is None or (
                str(row[0]) != resolution.resolution_hash
                or str(row[1]) != calendar.content_hash
                or str(row[2]) != str(calendar.source_dataset_id)
                or row[3] != payload
            ):
                raise TradingCalendarSnapshotConflict(
                    "Trading Calendar canonical snapshot identity conflict"
                )

        self._factory.run_transaction(operation)
        return self.get(calendar.artifact_id)

    def get(self, calendar_id: ArtifactId) -> TradingCalendarArtifact:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT calendar_hash, payload_json
                FROM pit_trading_calendar_canonical_snapshot
                WHERE calendar_id = %s
                """,
                (str(calendar_id),),
            ).fetchone()
        if row is None or not isinstance(row[1], Mapping):
            raise KeyError(str(calendar_id))
        try:
            calendar = TradingCalendarArtifact.from_canonical_dict(dict(row[1]))
        except (KeyError, TypeError, ValueError) as exc:
            raise TradingCalendarSnapshotConflict(
                "Trading Calendar canonical snapshot replay failed"
            ) from exc
        if calendar.content_hash != str(row[0]):
            raise TradingCalendarSnapshotConflict(
                "Trading Calendar canonical snapshot hash mismatch"
            )
        return calendar


__all__ = [
    "PostgresPITTradingCalendarSnapshotRepository",
    "TradingCalendarSnapshotConflict",
]
