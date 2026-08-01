"""Account/symbol Thesis book used to preserve execution attribution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import (
    OpportunityId,
    PositionBookId,
    ThesisId,
)
from market_regime_alpha.evidence.canonical import canonical_hash


POSITION_BOOK_SCHEMA = "position-book-v1"


class PositionBookState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class PositionBook:
    schema_version: str
    position_book_id: PositionBookId
    account_id: str
    symbol: str
    opportunity_id: OpportunityId
    thesis_id: ThesisId
    thesis_version: int
    state: PositionBookState
    version: int
    opened_at: datetime
    closed_at: datetime | None
    actor: str
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != POSITION_BOOK_SCHEMA:
            raise ValueError("unsupported PositionBook schema")
        for label, value in (
            ("account_id", self.account_id),
            ("symbol", self.symbol),
            ("actor", self.actor),
            ("reason", self.reason),
        ):
            if not value or value != value.strip():
                raise ValueError(f"{label} must be a non-empty trimmed string")
        if self.thesis_version < 0 or self.version < 0:
            raise ValueError("PositionBook versions cannot be negative")
        if self.opened_at.tzinfo is None or self.opened_at.utcoffset() is None:
            raise ValueError("PositionBook opened_at must be timezone-aware")
        if self.state is PositionBookState.OPEN:
            if self.version != 0 or self.closed_at is not None:
                raise ValueError("OPEN PositionBook must be initial and unclosed")
        else:
            if self.version <= 0 or self.closed_at is None:
                raise ValueError("CLOSED PositionBook requires close transition")
            if self.closed_at < self.opened_at:
                raise ValueError("PositionBook close cannot precede open")
        if self.position_book_id != _book_id(
            self.account_id, self.symbol, self.thesis_id
        ):
            raise ValueError("PositionBook identity mismatch")

    @classmethod
    def open(
        cls,
        *,
        account_id: str,
        symbol: str,
        opportunity_id: OpportunityId,
        thesis_id: ThesisId,
        thesis_version: int,
        opened_at: datetime,
        actor: str,
        reason: str,
    ) -> PositionBook:
        return cls(
            schema_version=POSITION_BOOK_SCHEMA,
            position_book_id=_book_id(account_id, symbol, thesis_id),
            account_id=account_id,
            symbol=symbol,
            opportunity_id=opportunity_id,
            thesis_id=thesis_id,
            thesis_version=thesis_version,
            state=PositionBookState.OPEN,
            version=0,
            opened_at=opened_at,
            closed_at=None,
            actor=actor,
            reason=reason,
        )

    def close(
        self, *, closed_at: datetime, actor: str, reason: str
    ) -> PositionBook:
        if self.state is not PositionBookState.OPEN:
            raise ValueError("only OPEN PositionBook can close")
        return replace(
            self,
            state=PositionBookState.CLOSED,
            version=self.version + 1,
            closed_at=closed_at,
            actor=actor,
            reason=reason,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "position_book_id": str(self.position_book_id),
            "account_id": self.account_id,
            "symbol": self.symbol,
            "opportunity_id": str(self.opportunity_id),
            "thesis_id": str(self.thesis_id),
            "thesis_version": self.thesis_version,
            "state": self.state.value,
            "version": self.version,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "actor": self.actor,
            "reason": self.reason,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PositionBook:
        expected = {
            "schema_version",
            "position_book_id",
            "account_id",
            "symbol",
            "opportunity_id",
            "thesis_id",
            "thesis_version",
            "state",
            "version",
            "opened_at",
            "closed_at",
            "actor",
            "reason",
        }
        if set(payload) != expected:
            raise ValueError("PositionBook fields mismatch")
        closed = payload["closed_at"]
        return cls(
            schema_version=str(payload["schema_version"]),
            position_book_id=PositionBookId(str(payload["position_book_id"])),
            account_id=str(payload["account_id"]),
            symbol=str(payload["symbol"]),
            opportunity_id=OpportunityId(str(payload["opportunity_id"])),
            thesis_id=ThesisId(str(payload["thesis_id"])),
            thesis_version=int(payload["thesis_version"]),
            state=PositionBookState(str(payload["state"])),
            version=int(payload["version"]),
            opened_at=datetime.fromisoformat(str(payload["opened_at"])),
            closed_at=(
                datetime.fromisoformat(str(closed)) if closed is not None else None
            ),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
        )


def _book_id(
    account_id: str, symbol: str, thesis_id: ThesisId
) -> PositionBookId:
    digest = canonical_hash(
        {
            "account_id": account_id,
            "symbol": symbol,
            "thesis_id": str(thesis_id),
            "schema_version": POSITION_BOOK_SCHEMA,
        }
    ).split(":", 1)[1]
    return PositionBookId(f"position-book-{digest[:24]}")
