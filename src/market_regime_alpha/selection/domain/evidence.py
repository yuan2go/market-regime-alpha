"""Selection-owned DTOs for narrow Market/PIT observations and exact lineage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.market.domain import MembershipStatus
from market_regime_alpha.selection.domain.vocabulary import MarketEvidenceStatus
from market_regime_alpha.shared.financial import bounded_decimal
from market_regime_alpha.shared.hashing import canonical_json_sha256


def _ordered(values: tuple[UUID, ...]) -> tuple[UUID, ...]:
    return tuple(sorted(set(values), key=str))


@dataclass(frozen=True, slots=True)
class MarketLineage:
    fact_revision_ids: tuple[UUID, ...] = ()
    bar_revision_ids: tuple[UUID, ...] = ()
    gap_ids: tuple[UUID, ...] = ()
    session_ids: tuple[UUID, ...] = ()
    capture_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "fact_revision_ids",
            "bar_revision_ids",
            "gap_ids",
            "session_ids",
            "capture_ids",
        ):
            values = getattr(self, field_name)
            ordered = _ordered(values)
            if values != ordered:
                raise ValueError(f"{field_name} must be unique and sorted")

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self)


@dataclass(frozen=True, slots=True)
class MembershipEvidence:
    status: MarketEvidenceStatus
    membership_status: MembershipStatus | None
    classification_id: UUID | None
    membership_revision_id: UUID | None
    gap_id: UUID | None
    capture_id: UUID | None
    decision_visible_at: datetime | None
    lineage: MarketLineage

    def __post_init__(self) -> None:
        if self.status is MarketEvidenceStatus.AVAILABLE:
            if (
                self.membership_status is None
                or self.classification_id is None
                or self.membership_revision_id is None
                or self.capture_id is None
                or self.decision_visible_at is None
            ):
                raise ValueError("available membership evidence requires exact lineage")
        elif self.membership_status is not None and self.status is MarketEvidenceStatus.MISSING:
            raise ValueError("missing membership evidence cannot assert a status")


@dataclass(frozen=True, slots=True)
class CriterionEvidence:
    status: MarketEvidenceStatus
    lineage: MarketLineage
    observed_decimal: Decimal | None = None
    observed_status: str | None = None
    observed_count: int | None = None
    effective_from: datetime | None = None

    def __post_init__(self) -> None:
        present = sum(
            item is not None
            for item in (
                self.observed_decimal,
                self.observed_status,
                self.observed_count,
            )
        )
        if self.status is MarketEvidenceStatus.AVAILABLE and present != 1:
            raise ValueError("available criterion evidence requires one typed value")
        if present > 1:
            raise ValueError("criterion evidence cannot mix typed values")
        if self.observed_decimal is not None:
            object.__setattr__(
                self,
                "observed_decimal",
                bounded_decimal(
                    self.observed_decimal,
                    field="observed criterion value",
                    precision=30,
                    scale=10,
                ),
            )
        if self.observed_count is not None and self.observed_count < 0:
            raise ValueError("observed_count must be non-negative")


__all__ = ["CriterionEvidence", "MarketLineage", "MembershipEvidence"]
