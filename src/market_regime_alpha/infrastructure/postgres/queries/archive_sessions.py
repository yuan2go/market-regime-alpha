"""Exact normalized trading-session rosters for archive bar disposition."""

from __future__ import annotations

from datetime import date

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.market.ports.session_roster import ArchiveTradingSession
from market_regime_alpha.shared.identity import TradingSessionId


class PostgresArchiveTradingSessionReadPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def sessions(
        self,
        *,
        exchange: str,
        start_date: date,
        end_date: date,
    ) -> tuple[ArchiveTradingSession, ...]:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT session_id, exchange, session_date, open_at,
                       break_start_at, break_end_at, close_at
                FROM mra.trading_session
                WHERE exchange = %s
                  AND session_date BETWEEN %s AND %s
                ORDER BY session_date, session_id
                """,
                (exchange, start_date, end_date),
            ).fetchall()
        sessions = tuple(
            ArchiveTradingSession(
                session_id=TradingSessionId(row[0]),
                exchange=str(row[1]),
                session_date=row[2],
                open_at=row[3],
                break_start_at=row[4],
                break_end_at=row[5],
                close_at=row[6],
            )
            for row in rows
        )
        if len({item.session_date for item in sessions}) != len(sessions):
            raise ValueError("archive calendar has ambiguous Sessions for one date")
        return sessions

    def exact(
        self,
        *,
        exchange: str,
        session_id: TradingSessionId,
    ) -> ArchiveTradingSession:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT session_id, exchange, session_date, open_at,
                       break_start_at, break_end_at, close_at
                FROM mra.trading_session
                WHERE session_id = %s AND exchange = %s
                """,
                (session_id.value, exchange),
            ).fetchone()
        if row is None:
            raise ValueError("exact Session is absent from exchange calendar")
        return ArchiveTradingSession(
            session_id=TradingSessionId(row[0]),
            exchange=str(row[1]),
            session_date=row[2],
            open_at=row[3],
            break_start_at=row[4],
            break_end_at=row[5],
            close_at=row[6],
        )

    def available_from(
        self, *, exchange: str, session_id: TradingSessionId, limit: int,
    ) -> tuple[ArchiveTradingSession, ...]:
        """Bounded known calendar including the exact anchor; never infer dates."""
        if isinstance(limit, bool) or limit < 1:
            raise ValueError("calendar limit must be positive")
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT session_id, exchange, session_date, open_at,
                       break_start_at, break_end_at, close_at
                FROM mra.trading_session
                WHERE exchange = %s AND session_date >= (
                    SELECT session_date FROM mra.trading_session
                    WHERE session_id = %s AND exchange = %s
                )
                ORDER BY session_date, session_id LIMIT %s
                """, (exchange, session_id.value, exchange, limit),
            ).fetchall()
        if not rows or rows[0][0] != session_id.value:
            raise ValueError("exact Session is absent from exchange calendar")
        return tuple(ArchiveTradingSession(
            TradingSessionId(row[0]), str(row[1]), row[2], row[3], row[4], row[5], row[6],
        ) for row in rows)

    def following(
        self,
        *,
        exchange: str,
        after_session_id: TradingSessionId,
        count: int,
    ) -> tuple[ArchiveTradingSession, ...]:
        if isinstance(count, bool) or count < 1:
            raise ValueError("following Session count must be positive")
        with self._pool.connection(read_only=True) as connection:
            anchor = connection.execute(
                """
                SELECT session_date
                FROM mra.trading_session
                WHERE session_id = %s AND exchange = %s
                """,
                (after_session_id.value, exchange),
            ).fetchone()
            if anchor is None:
                raise ValueError("anchor Session is absent from exact exchange calendar")
            rows = connection.execute(
                """
                SELECT session_id, exchange, session_date, open_at,
                       break_start_at, break_end_at, close_at
                FROM mra.trading_session
                WHERE exchange = %s AND session_date > %s
                ORDER BY session_date, session_id
                LIMIT %s
                """,
                (exchange, anchor[0], count),
            ).fetchall()
        if len(rows) != count:
            raise ValueError("complete following TradingSession roster is unavailable")
        return tuple(
            ArchiveTradingSession(
                session_id=TradingSessionId(row[0]),
                exchange=str(row[1]),
                session_date=row[2],
                open_at=row[3],
                break_start_at=row[4],
                break_end_at=row[5],
                close_at=row[6],
            )
            for row in rows
        )


__all__ = ["PostgresArchiveTradingSessionReadPort"]
