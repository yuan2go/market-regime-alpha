"""Bounded canonical financial values shared by target contexts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import StrEnum
import re


_CURRENCY = re.compile(r"^[A-Z]{3}$")


class QuantityUnit(StrEnum):
    """Closed units currently admitted at canonical context boundaries."""

    SHARES = "SHARES"


def bounded_decimal(
    value: Decimal,
    *,
    field: str,
    precision: int,
    scale: int,
) -> Decimal:
    """Return a fixed-scale value or reject input PostgreSQL would round/overflow."""

    if not isinstance(value, Decimal):
        raise TypeError(f"{field} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    quantum = Decimal(1).scaleb(-scale)
    try:
        with localcontext() as context:
            context.prec = precision + scale + 2
            canonical = value.quantize(quantum)
    except InvalidOperation as exc:
        raise ValueError(f"{field} exceeds numeric({precision}, {scale})") from exc
    if canonical != value:
        raise ValueError(f"{field} exceeds numeric({precision}, {scale}) scale")
    if abs(canonical) >= Decimal(10) ** (precision - scale):
        raise ValueError(f"{field} exceeds numeric({precision}, {scale}) precision")
    if canonical == 0:
        canonical = abs(canonical)
    return canonical


@dataclass(frozen=True, slots=True)
class Money:
    """A currency-qualified canonical amount stored as numeric(30, 10)."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "amount",
            bounded_decimal(
                self.amount,
                field="money.amount",
                precision=30,
                scale=10,
            ),
        )
        if not _CURRENCY.fullmatch(self.currency):
            raise ValueError("money.currency must be a three-letter uppercase code")


@dataclass(frozen=True, slots=True)
class Quantity:
    """A unit-qualified canonical quantity stored as numeric(38, 10)."""

    amount: Decimal
    unit: QuantityUnit

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "amount",
            bounded_decimal(
                self.amount,
                field="quantity.amount",
                precision=38,
                scale=10,
            ),
        )
        if not isinstance(self.unit, QuantityUnit):
            raise TypeError("quantity.unit must be QuantityUnit")


__all__ = ["Money", "Quantity", "QuantityUnit", "bounded_decimal"]
