"""PostgreSQL owner for immutable Trading Calendar payloads."""

from __future__ import annotations

from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class TradingCalendarAuthorityConflict(ValueError):
    """The stored Calendar identity or payload diverged."""


class PostgresTradingCalendarAuthority:
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
            recorded_at = connection.execute(
                "SELECT date_trunc('second', clock_timestamp())"
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO trading_calendar_authority(
                    calendar_id, calendar_hash, source_dataset_id,
                    payload_json, recorded_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (calendar_id) DO NOTHING
                """,
                (
                    str(calendar.artifact_id),
                    calendar.content_hash,
                    str(calendar.source_dataset_id),
                    Jsonb(payload),
                    recorded_at,
                ),
            )
            row = connection.execute(
                """
                SELECT calendar_hash, source_dataset_id, payload_json
                FROM trading_calendar_authority WHERE calendar_id = %s
                """,
                (str(calendar.artifact_id),),
            ).fetchone()
            if row is None or (
                str(row[0]) != calendar.content_hash
                or str(row[1]) != str(calendar.source_dataset_id)
                or row[2] != payload
            ):
                raise TradingCalendarAuthorityConflict(
                    "Trading Calendar immutable identity conflict"
                )

        self._factory.run_transaction(operation)
        return self.get(calendar.artifact_id)

    def get(self, calendar_id: ArtifactId) -> TradingCalendarArtifact:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT calendar_hash, payload_json
                FROM trading_calendar_authority WHERE calendar_id = %s
                """,
                (str(calendar_id),),
            ).fetchone()
        if row is None or not isinstance(row[1], Mapping):
            raise KeyError(str(calendar_id))
        try:
            calendar = TradingCalendarArtifact.from_canonical_dict(dict(row[1]))
        except (KeyError, TypeError, ValueError) as exc:
            raise TradingCalendarAuthorityConflict(
                "Trading Calendar owner replay failed"
            ) from exc
        if calendar.content_hash != str(row[0]):
            raise TradingCalendarAuthorityConflict(
                "Trading Calendar owner hash mismatch"
            )
        return calendar


__all__ = [
    "PostgresTradingCalendarAuthority",
    "TradingCalendarAuthorityConflict",
]
