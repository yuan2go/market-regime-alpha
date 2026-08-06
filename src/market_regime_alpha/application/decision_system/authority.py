"""PostgreSQL readers for Fill-derived account authority used by Decision System."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping
import unicodedata

from market_regime_alpha.application.decision_system.contracts import (
    FillDerivedPositionReference,
)
from market_regime_alpha.core.identity import ArtifactId, PositionBookId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    normalize_canonical_datetime,
    require_sha256,
)
from market_regime_alpha.execution.postgres_traceability import (
    PostgresTraceableManualExecutionRepository,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.position.authority import (
    PositionProjector,
    SymbolTradingSessionStatus,
)


POSITION_SETTLEMENT_EVIDENCE_SCHEMA = "position_settlement_evidence/v1"
FILL_DERIVED_ACCOUNT_AUTHORITY_SCHEMA = "fill_derived_account_authority/v2"


@dataclass(frozen=True, slots=True)
class PositionSettlementEvidence:
    """Explicit calendar/session evidence for an A-share T+1 projection."""

    evidence_id: ArtifactId
    content_hash: str
    account_id: str
    as_of_time: datetime
    trading_calendar: TradingCalendarArtifact
    symbol_session_statuses: tuple[SymbolTradingSessionStatus, ...]

    def __post_init__(self) -> None:
        require_sha256("Position settlement content_hash", self.content_hash)
        _required_text(self.account_id)
        if normalize_canonical_datetime(self.as_of_time) != self.as_of_time:
            raise ValueError("Position settlement AsOfTime must use whole seconds")
        if self.trading_calendar.market != "CN_A_SHARE":
            raise ValueError("Position settlement requires CN_A_SHARE calendar")
        ordered = tuple(
            sorted(
                self.symbol_session_statuses,
                key=lambda item: (item.symbol, item.session_date, str(item.status_id)),
            )
        )
        if self.symbol_session_statuses != ordered:
            raise ValueError("Position settlement statuses must be canonically ordered")
        scopes = tuple((item.symbol, item.session_date) for item in ordered)
        if len(scopes) != len(set(scopes)):
            raise ValueError("Position settlement status scopes must be unique")
        if any(
            item.availability_time > self.as_of_time
            or normalize_canonical_datetime(item.availability_time)
            != item.availability_time
            for item in ordered
        ):
            raise ValueError("Position settlement statuses must be available by AsOfTime")
        expected = canonical_hash(self.semantic_payload())
        if expected != self.content_hash:
            raise ValueError("Position settlement content hash mismatch")
        if self.evidence_id != ArtifactId(
            f"position-settlement-evidence-{expected[7:31]}"
        ):
            raise ValueError("Position settlement identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        account_id: str,
        as_of_time: datetime,
        trading_calendar: TradingCalendarArtifact,
        symbol_session_statuses: tuple[SymbolTradingSessionStatus, ...],
    ) -> PositionSettlementEvidence:
        ordered = tuple(
            sorted(
                symbol_session_statuses,
                key=lambda item: (item.symbol, item.session_date, str(item.status_id)),
            )
        )
        prototype = cls._payload(
            account_id=account_id,
            as_of_time=as_of_time,
            trading_calendar=trading_calendar,
            symbol_session_statuses=ordered,
        )
        digest = canonical_hash(prototype)
        return cls(
            evidence_id=ArtifactId(f"position-settlement-evidence-{digest[7:31]}"),
            content_hash=digest,
            account_id=account_id,
            as_of_time=as_of_time,
            trading_calendar=trading_calendar,
            symbol_session_statuses=ordered,
        )

    def statuses_for(self, symbol: str) -> tuple[SymbolTradingSessionStatus, ...]:
        return tuple(item for item in self.symbol_session_statuses if item.symbol == symbol)

    def semantic_payload(self) -> dict[str, Any]:
        return self._payload(
            account_id=self.account_id,
            as_of_time=self.as_of_time,
            trading_calendar=self.trading_calendar,
            symbol_session_statuses=self.symbol_session_statuses,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": str(self.evidence_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> PositionSettlementEvidence:
        expected = {
            "schema_version", "evidence_id", "content_hash", "account_id",
            "as_of_time", "trading_calendar", "symbol_session_statuses",
        }
        if set(payload) != expected:
            raise ValueError("Position settlement fields mismatch")
        if payload["schema_version"] != POSITION_SETTLEMENT_EVIDENCE_SCHEMA:
            raise ValueError("unsupported Position settlement schema")
        raw_as_of = _required_text(payload["as_of_time"])
        as_of = datetime.fromisoformat(raw_as_of)
        if canonical_datetime(as_of) != raw_as_of:
            raise ValueError("Position settlement AsOfTime is not canonical")
        raw_statuses = payload["symbol_session_statuses"]
        if not isinstance(raw_statuses, list):
            raise TypeError("Position settlement statuses must be an array")
        return cls(
            evidence_id=ArtifactId(_required_text(payload["evidence_id"])),
            content_hash=_required_text(payload["content_hash"]),
            account_id=_required_text(payload["account_id"]),
            as_of_time=as_of,
            trading_calendar=TradingCalendarArtifact.from_canonical_dict(
                _required_object(payload["trading_calendar"])
            ),
            symbol_session_statuses=tuple(
                SymbolTradingSessionStatus.from_canonical_dict(
                    _required_object(item)
                )
                for item in raw_statuses
            ),
        )

    @staticmethod
    def _payload(
        *,
        account_id: str,
        as_of_time: datetime,
        trading_calendar: TradingCalendarArtifact,
        symbol_session_statuses: tuple[SymbolTradingSessionStatus, ...],
    ) -> dict[str, Any]:
        return {
            "schema_version": POSITION_SETTLEMENT_EVIDENCE_SCHEMA,
            "account_id": account_id,
            "as_of_time": canonical_datetime(as_of_time),
            "trading_calendar": trading_calendar.to_canonical_dict(),
            "symbol_session_statuses": [
                item.to_canonical_dict() for item in symbol_session_statuses
            ],
        }


@dataclass(frozen=True, slots=True)
class FillDerivedAccountAuthority:
    authority_id: ArtifactId
    content_hash: str
    account_id: str
    as_of_time: datetime
    positions: tuple[FillDerivedPositionReference, ...]
    fill_ledger_head: str
    fill_ledger_complete: bool
    settlement_evidence_id: ArtifactId | None
    settlement_evidence_hash: str | None

    def __post_init__(self) -> None:
        require_sha256("Fill authority content_hash", self.content_hash)
        require_sha256("Fill authority ledger head", self.fill_ledger_head)
        if self.as_of_time.tzinfo is None or self.as_of_time.utcoffset() is None:
            raise ValueError("Fill authority AsOfTime must be aware")
        if normalize_canonical_datetime(self.as_of_time) != self.as_of_time:
            raise ValueError("Fill authority AsOfTime must use whole seconds")
        _required_text(self.account_id)
        symbols = tuple(item.symbol for item in self.positions)
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("Fill authority positions must be symbol sorted and unique")
        if any(
            item.account_id != self.account_id
            or item.as_of_time != self.as_of_time
            for item in self.positions
        ):
            raise ValueError("Fill authority position scope mismatch")
        if (self.settlement_evidence_id is None) != (
            self.settlement_evidence_hash is None
        ):
            raise ValueError("Fill authority settlement evidence must be paired")
        if self.settlement_evidence_hash is not None:
            require_sha256(
                "Fill authority settlement evidence hash",
                self.settlement_evidence_hash,
            )
        expected = canonical_hash(self.semantic_payload())
        if expected != self.content_hash:
            raise ValueError("Fill authority content hash mismatch")
        if self.authority_id != ArtifactId(
            f"fill-derived-account-authority-{expected[7:31]}"
        ):
            raise ValueError("Fill authority identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        account_id: str,
        as_of_time: datetime,
        positions: tuple[FillDerivedPositionReference, ...],
        fill_ledger_head: str,
        fill_ledger_complete: bool,
        settlement_evidence_id: ArtifactId | None = None,
        settlement_evidence_hash: str | None = None,
    ) -> FillDerivedAccountAuthority:
        ordered = tuple(sorted(positions, key=lambda item: item.symbol))
        prototype = cls._payload(
            account_id=account_id,
            as_of_time=as_of_time,
            positions=ordered,
            fill_ledger_head=fill_ledger_head,
            fill_ledger_complete=fill_ledger_complete,
            settlement_evidence_id=settlement_evidence_id,
            settlement_evidence_hash=settlement_evidence_hash,
        )
        digest = canonical_hash(prototype)
        return cls(
            authority_id=ArtifactId(
                f"fill-derived-account-authority-{digest[7:31]}"
            ),
            content_hash=digest,
            account_id=account_id,
            as_of_time=as_of_time,
            positions=ordered,
            fill_ledger_head=fill_ledger_head,
            fill_ledger_complete=fill_ledger_complete,
            settlement_evidence_id=settlement_evidence_id,
            settlement_evidence_hash=settlement_evidence_hash,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return self._payload(
            account_id=self.account_id,
            as_of_time=self.as_of_time,
            positions=self.positions,
            fill_ledger_head=self.fill_ledger_head,
            fill_ledger_complete=self.fill_ledger_complete,
            settlement_evidence_id=self.settlement_evidence_id,
            settlement_evidence_hash=self.settlement_evidence_hash,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "authority_id": str(self.authority_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: dict[str, Any],
    ) -> FillDerivedAccountAuthority:
        expected = {
            "authority_id", "content_hash", "schema_version", "account_id",
            "as_of_time", "positions", "fill_ledger_head",
            "fill_ledger_complete",
            "settlement_evidence_id", "settlement_evidence_hash",
        }
        if set(payload) != expected:
            raise ValueError("Fill authority fields mismatch")
        if payload["schema_version"] != FILL_DERIVED_ACCOUNT_AUTHORITY_SCHEMA:
            raise ValueError("unsupported Fill authority schema")
        raw_as_of = payload["as_of_time"]
        if not isinstance(raw_as_of, str):
            raise TypeError("Fill authority AsOfTime must be canonical text")
        parsed_as_of = datetime.fromisoformat(raw_as_of)
        if canonical_datetime(parsed_as_of) != raw_as_of:
            raise ValueError("Fill authority AsOfTime is not canonical")
        raw_positions = payload["positions"]
        if not isinstance(raw_positions, list):
            raise TypeError("Fill authority positions must be an array")
        complete = payload["fill_ledger_complete"]
        if not isinstance(complete, bool):
            raise TypeError("Fill authority completeness must be boolean")
        return cls(
            authority_id=ArtifactId(_required_text(payload["authority_id"])),
            content_hash=_required_text(payload["content_hash"]),
            account_id=_required_text(payload["account_id"]),
            as_of_time=parsed_as_of,
            positions=tuple(
                FillDerivedPositionReference.from_canonical_dict(
                    _required_object(item)
                )
                for item in raw_positions
            ),
            fill_ledger_head=_required_text(payload["fill_ledger_head"]),
            fill_ledger_complete=complete,
            settlement_evidence_id=(
                None
                if payload["settlement_evidence_id"] is None
                else ArtifactId(_required_text(payload["settlement_evidence_id"]))
            ),
            settlement_evidence_hash=(
                None
                if payload["settlement_evidence_hash"] is None
                else _required_text(payload["settlement_evidence_hash"])
            ),
        )

    @staticmethod
    def _payload(
        *,
        account_id: str,
        as_of_time: datetime,
        positions: tuple[FillDerivedPositionReference, ...],
        fill_ledger_head: str,
        fill_ledger_complete: bool,
        settlement_evidence_id: ArtifactId | None,
        settlement_evidence_hash: str | None,
    ) -> dict[str, Any]:
        return {
            "schema_version": FILL_DERIVED_ACCOUNT_AUTHORITY_SCHEMA,
            "account_id": account_id,
            "as_of_time": canonical_datetime(as_of_time),
            "positions": [item.to_canonical_dict() for item in positions],
            "fill_ledger_head": fill_ledger_head,
            "fill_ledger_complete": fill_ledger_complete,
            "settlement_evidence_id": (
                None if settlement_evidence_id is None else str(settlement_evidence_id)
            ),
            "settlement_evidence_hash": settlement_evidence_hash,
        }


@dataclass(frozen=True, slots=True)
class DecisionStateAuthorityContext:
    market_state: str
    etf_states: tuple[tuple[str, str], ...]
    theme_states: tuple[tuple[str, str], ...]
    capital_state: str
    oldest_available_at: datetime

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str)
            and value
            and value == unicodedata.normalize("NFC", value)
            for value in (self.market_state, self.capital_state)
        ):
            raise ValueError("Decision State context values must be text")
        if self.etf_states != tuple(sorted(set(self.etf_states))):
            raise ValueError("ETF State context must be sorted and unique")
        if self.theme_states != tuple(sorted(set(self.theme_states))):
            raise ValueError("Theme State context must be sorted and unique")
        for scope, state in self.etf_states + self.theme_states:
            _required_text(scope)
            _required_text(state)
        if self.oldest_available_at.tzinfo is None:
            raise ValueError("Decision State availability must be aware")
        if (
            normalize_canonical_datetime(self.oldest_available_at)
            != self.oldest_available_at
        ):
            raise ValueError("Decision State availability must use whole seconds")


class PostgresFillDerivedAccountAuthorityReader:
    """Rebuild current positions from append-only PostgreSQL Fill authority."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory
        self._execution = PostgresTraceableManualExecutionRepository(factory)

    def load(
        self,
        *,
        account_id: str,
        as_of_time: datetime,
        settlement_evidence: PositionSettlementEvidence | None = None,
    ) -> FillDerivedAccountAuthority:
        canonical_as_of = normalize_canonical_datetime(as_of_time)
        if settlement_evidence is not None and (
            settlement_evidence.account_id != account_id
            or settlement_evidence.as_of_time != canonical_as_of
        ):
            raise ValueError("Position settlement evidence scope mismatch")
        with self._factory.connection(read_only=True) as connection:
            book_rows = connection.execute(
                """
                SELECT position_book_id
                FROM position_books
                WHERE account_id = %s
                  AND opened_at <= %s
                  AND (closed_at IS NULL OR closed_at > %s)
                ORDER BY symbol, position_book_id
                """,
                (account_id, canonical_as_of, canonical_as_of),
            ).fetchall()
        books = tuple(
            self._execution.get_position_book(
                PositionBookId(str(row[0]))
            )
            for row in book_rows
        )
        references: list[FillDerivedPositionReference] = []
        for book in books:
            trades = tuple(
                item
                for item in self._execution.trades_for_book(book.position_book_id)
                if item.created_at <= canonical_as_of
            )
            fills = tuple(
                item
                for item in self._execution.fills_for_book(book.position_book_id)
                if item.recorded_at <= canonical_as_of
            )
            if not fills:
                continue
            if settlement_evidence is None:
                snapshot = PositionProjector().project_book(
                    book=book,
                    trades=trades,
                    fills=fills,
                    as_of=canonical_as_of,
                )
            else:
                snapshot = PositionProjector().project_book_t_plus_one(
                    book=book,
                    trades=trades,
                    fills=fills,
                    calendar=settlement_evidence.trading_calendar,
                    symbol_session_statuses=settlement_evidence.statuses_for(
                        book.symbol
                    ),
                    as_of=canonical_as_of,
                )
            references.append(
                FillDerivedPositionReference(
                    snapshot_id=ArtifactId(str(snapshot.snapshot_id)),
                    snapshot_hash=canonical_hash(snapshot.to_canonical_dict()),
                    account_id=snapshot.account_id,
                    symbol=snapshot.symbol,
                    as_of_time=canonical_as_of,
                    total_quantity=snapshot.total_quantity,
                    available_quantity=snapshot.available_quantity,
                    frozen_quantity=snapshot.frozen_quantity,
                    average_cost=(
                        None
                        if snapshot.average_cost is None
                        else Decimal(str(snapshot.average_cost))
                    ),
                    source_fill_ids=tuple(str(item) for item in snapshot.source_fill_ids),
                    complete=(
                        snapshot.available_quantity is not None
                        and snapshot.frozen_quantity is not None
                    ),
                )
            )

        with self._factory.connection(read_only=True) as connection:
            ledger_rows = connection.execute(
                """
                SELECT fill_id, fill_json
                FROM manual_fills
                WHERE account_id = %s AND recorded_at <= %s
                ORDER BY recorded_at, fill_id
                """,
                (account_id, canonical_as_of),
            ).fetchall()
            bound_fill_rows = connection.execute(
                """
                WITH bindings AS (
                    SELECT manual_trade_id, position_book_id
                    FROM traceable_manual_trade_bindings
                    UNION ALL
                    SELECT manual_trade_id, position_book_id
                    FROM risk_reducing_manual_trade_bindings
                )
                SELECT fill.fill_id
                FROM bindings AS binding
                JOIN position_books AS book
                  ON book.position_book_id = binding.position_book_id
                JOIN manual_fills AS fill
                  ON fill.manual_trade_id = binding.manual_trade_id
                WHERE book.account_id = %s AND fill.recorded_at <= %s
                ORDER BY fill.recorded_at, fill.fill_id
                """,
                (account_id, canonical_as_of),
            ).fetchall()
        ledger_fill_ids = {str(row[0]) for row in ledger_rows}
        bound_fill_ids = {str(row[0]) for row in bound_fill_rows}
        fill_ledger_head = canonical_hash(
            {
                "schema_version": "fill_ledger_head/v1",
                "account_id": account_id,
                "as_of_time": canonical_datetime(canonical_as_of),
                "fills": [row[1] for row in ledger_rows],
            }
        )
        return FillDerivedAccountAuthority.create(
            account_id=account_id,
            as_of_time=canonical_as_of,
            positions=tuple(references),
            fill_ledger_head=fill_ledger_head,
            fill_ledger_complete=ledger_fill_ids == bound_fill_ids,
            settlement_evidence_id=(
                None if settlement_evidence is None else settlement_evidence.evidence_id
            ),
            settlement_evidence_hash=(
                None if settlement_evidence is None else settlement_evidence.content_hash
            ),
        )


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError("Fill authority value must be non-empty text")
    if value != unicodedata.normalize("NFC", value):
        raise ValueError("Fill authority value is not Unicode NFC")
    return value


def _required_object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Fill authority value must be an object")
    return value


__all__ = [
    "FILL_DERIVED_ACCOUNT_AUTHORITY_SCHEMA",
    "POSITION_SETTLEMENT_EVIDENCE_SCHEMA",
    "DecisionStateAuthorityContext",
    "FillDerivedAccountAuthority",
    "PostgresFillDerivedAccountAuthorityReader",
    "PositionSettlementEvidence",
]
