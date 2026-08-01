"""Adapter from Fill/calendar Position Authority to complete-account Risk input."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.execution.position_book import PositionBook, PositionBookState
from market_regime_alpha.portfolio.account_authority import (
    AccountPortfolioCompleteness,
    AccountPosition,
    AccountReconciliationState,
    AuthoritativeAccountPortfolioSnapshot,
)
from market_regime_alpha.position.authority import (
    T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA,
    PositionSnapshot,
    PositionState,
)


@dataclass(frozen=True, slots=True)
class PositionRiskValuationInput:
    symbol: str
    theme_id: str
    market_price: float
    loss_per_share: float
    source_artifact_id: ArtifactId
    source_artifact_hash: str

    def __post_init__(self) -> None:
        for label, value in (("symbol", self.symbol), ("theme_id", self.theme_id)):
            if not value or value != value.strip():
                raise ValueError(f"{label} must be a non-empty trimmed string")
        if (
            not isfinite(self.market_price)
            or self.market_price <= 0.0
            or not isfinite(self.loss_per_share)
            or self.loss_per_share <= 0.0
        ):
            raise ValueError("Position Risk valuation values must be positive")
        require_sha256("source_artifact_hash", self.source_artifact_hash)


class PositionAuthorityAccountSnapshotBuilder:
    """Build Risk input only from every OPEN PositionBook projection."""

    def build(
        self,
        *,
        account_id: str,
        as_of: datetime,
        source_reference: str,
        net_asset_value: float,
        available_cash: float,
        open_books: tuple[PositionBook, ...],
        position_snapshots: tuple[PositionSnapshot, ...],
        valuations: tuple[PositionRiskValuationInput, ...],
        reconciliation_state: AccountReconciliationState,
        version: int,
    ) -> AuthoritativeAccountPortfolioSnapshot:
        books = {item.position_book_id: item for item in open_books}
        positions = {
            item.position_book_id: item
            for item in position_snapshots
            if item.position_book_id is not None
        }
        valuation_by_symbol = {item.symbol: item for item in valuations}
        if len(books) != len(open_books) or len(positions) != len(position_snapshots):
            raise ValueError("Position Authority inputs require unique identities")
        if set(books) != set(positions):
            raise ValueError("every OPEN PositionBook requires one PositionSnapshot")
        symbols = {item.symbol for item in open_books}
        if set(valuation_by_symbol) != symbols or len(valuation_by_symbol) != len(
            valuations
        ):
            raise ValueError("every OPEN Position symbol requires one valuation input")
        account_positions: list[AccountPosition] = []
        for book_id, book in books.items():
            position = positions[book_id]
            valuation = valuation_by_symbol[book.symbol]
            if (
                book.state is not PositionBookState.OPEN
                or book.account_id != account_id
                or position.schema_version != T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA
                or position.account_id != account_id
                or position.symbol != book.symbol
                or position.thesis_id != book.thesis_id
                or position.as_of != as_of
                or position.state is PositionState.RECONCILIATION_REQUIRED
                or position.state is PositionState.CLOSED
                or position.available_quantity is None
            ):
                raise ValueError("Position Authority snapshot is invalid for account Risk")
            if valuation.symbol != position.symbol:
                raise ValueError("Position valuation scope mismatch")
            account_positions.append(
                AccountPosition(
                    symbol=position.symbol,
                    theme_id=valuation.theme_id,
                    total_quantity=position.total_quantity,
                    available_quantity=position.available_quantity,
                    market_price=valuation.market_price,
                    loss_per_share=valuation.loss_per_share,
                    source_position_snapshot_id=ArtifactId(str(position.snapshot_id)),
                    source_position_snapshot_hash=canonical_hash(
                        position.to_canonical_dict()
                    ),
                )
            )
        return AuthoritativeAccountPortfolioSnapshot.create(
            account_id=account_id,
            as_of=as_of,
            source_reference=source_reference,
            net_asset_value=net_asset_value,
            available_cash=available_cash,
            all_positions=tuple(account_positions),
            completeness=AccountPortfolioCompleteness.COMPLETE_ACCOUNT,
            reconciliation_state=reconciliation_state,
            version=version,
        )
