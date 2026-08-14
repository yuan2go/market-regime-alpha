"""Strategy-authorized sizing embedded in the existing ManualTrade intent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)


STRATEGY_EXECUTION_AUTHORIZATION_SCHEMA = "strategy-execution-authorization/v1"
_BUY_ACTIONS = frozenset({"ENTER", "ADD"})
_SELL_ACTIONS = frozenset({"REDUCE", "EXIT"})


@dataclass(frozen=True, slots=True)
class StrategyExecutionAuthorization:
    """Frozen Portfolio/Proposal lineage plus executable A-share quantity."""

    authorization_id: ArtifactId
    authorization_hash: str
    portfolio_decision_reference: RuntimeArtifactReference
    strategy_version_reference: RuntimeArtifactReference
    proposal_reference: RuntimeArtifactReference
    account_observation_reference: RuntimeArtifactReference
    trading_calendar_reference: RuntimeArtifactReference
    price_reference: RuntimeArtifactReference
    account_id: str
    symbol: str
    action: str
    accepted_weight: Decimal
    account_nav: Decimal
    available_cash: Decimal
    reference_price: Decimal
    current_quantity: int
    available_quantity: int
    lot_size: int
    authorized_notional: Decimal
    recommended_quantity: int
    intended_quantity: int
    residual_cash: Decimal
    override_reason: str | None
    decision_time: datetime
    created_at: datetime
    schema_version: str = STRATEGY_EXECUTION_AUTHORIZATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != STRATEGY_EXECUTION_AUTHORIZATION_SCHEMA:
            raise ValueError("unsupported Strategy Execution Authorization schema")
        require_sha256("authorization_hash", self.authorization_hash)
        require_text("account_id", self.account_id)
        require_text("symbol", self.symbol)
        if self.action not in _BUY_ACTIONS | _SELL_ACTIONS:
            raise ValueError("Strategy action is not executable")
        if self.accepted_weight == 0 or abs(self.accepted_weight) > 1:
            raise ValueError("accepted Strategy weight must be within [-1, 1] and non-zero")
        if (self.action in _BUY_ACTIONS) != (self.accepted_weight > 0):
            raise ValueError("accepted Strategy weight disagrees with action")
        if self.account_nav <= 0 or self.available_cash < 0 or self.reference_price <= 0:
            raise ValueError("account NAV and reference price must be positive")
        if min(self.current_quantity, self.available_quantity) < 0:
            raise ValueError("position quantities cannot be negative")
        if self.available_quantity > self.current_quantity:
            raise ValueError("available quantity cannot exceed current quantity")
        if self.lot_size <= 0:
            raise ValueError("lot size must be positive")
        if min(self.recommended_quantity, self.intended_quantity) <= 0:
            raise ValueError("NOT_EXECUTABLE_QUANTITY")
        if self.intended_quantity > self.recommended_quantity:
            raise ValueError("operator quantity cannot exceed Strategy authorization")
        if self.action in _BUY_ACTIONS | {"REDUCE"} and (
            self.intended_quantity % self.lot_size
        ):
            raise ValueError("executable quantity must use the declared lot size")
        if self.action == "EXIT" and self.intended_quantity != self.recommended_quantity:
            raise ValueError("EXIT quantity must close all currently available shares")
        override = self.intended_quantity != self.recommended_quantity
        if override != (self.override_reason is not None):
            raise ValueError("operator override quantity and reason must be paired")
        if self.override_reason is not None:
            require_text("override_reason", self.override_reason)
        canonical_datetime(self.decision_time)
        canonical_datetime(self.created_at)
        if self.created_at < self.decision_time:
            raise ValueError("Execution Authorization cannot predate Strategy decision")
        expected_notional = abs(self.accepted_weight) * self.account_nav
        if self.authorized_notional != expected_notional:
            raise ValueError("authorized notional does not match accepted weight and NAV")
        expected_price_reference = _price_reference(
            proposal_reference=self.proposal_reference,
            account_observation_reference=self.account_observation_reference,
            reference_price=self.reference_price,
            decision_time=self.decision_time,
        )
        if self.price_reference != expected_price_reference:
            raise ValueError("Strategy reference price identity mismatch")
        executable_notional = (
            min(expected_notional, self.available_cash)
            if self.action in _BUY_ACTIONS
            else expected_notional
        )
        expected_residual = max(
            Decimal("0"),
            executable_notional
            - Decimal(self.intended_quantity) * self.reference_price,
        )
        if self.residual_cash != expected_residual:
            raise ValueError("residual cash does not reconcile")
        digest = canonical_hash(self.identity_payload())
        if (
            digest != self.authorization_hash
            or str(self.authorization_id)
            != f"strategy-execution-authorization:{digest[7:]}"
        ):
            raise ValueError("Strategy Execution Authorization identity mismatch")

    @property
    def operator_override(self) -> bool:
        return self.intended_quantity != self.recommended_quantity

    @classmethod
    def create(
        cls,
        *,
        portfolio_decision_reference: RuntimeArtifactReference,
        strategy_version_reference: RuntimeArtifactReference,
        proposal_reference: RuntimeArtifactReference,
        account_observation_reference: RuntimeArtifactReference,
        trading_calendar_reference: RuntimeArtifactReference,
        account_id: str,
        symbol: str,
        action: str,
        accepted_weight: Decimal,
        account_nav: Decimal,
        available_cash: Decimal,
        reference_price: Decimal,
        current_quantity: int,
        available_quantity: int,
        lot_size: int,
        operator_quantity: int | None,
        override_reason: str | None,
        decision_time: datetime,
        created_at: datetime,
    ) -> StrategyExecutionAuthorization:
        authorized_notional = abs(accepted_weight) * account_nav
        executable_notional = (
            min(authorized_notional, available_cash)
            if action in _BUY_ACTIONS
            else authorized_notional
        )
        by_weight = int(
            (executable_notional / reference_price / Decimal(lot_size)).to_integral_value(
                rounding=ROUND_FLOOR
            )
        ) * lot_size
        if action in _BUY_ACTIONS:
            recommended = by_weight
        elif action == "REDUCE":
            available_lots = available_quantity // lot_size * lot_size
            recommended = min(by_weight, available_lots)
        elif action == "EXIT":
            recommended = available_quantity
        else:
            raise ValueError("Strategy action is not executable")
        intended = recommended if operator_quantity is None else operator_quantity
        residual_cash = max(
            Decimal("0"),
            executable_notional - Decimal(intended) * reference_price,
        )
        price_reference = _price_reference(
            proposal_reference=proposal_reference,
            account_observation_reference=account_observation_reference,
            reference_price=reference_price,
            decision_time=decision_time,
        )
        values: dict[str, Any] = {
            "portfolio_decision_reference": portfolio_decision_reference,
            "strategy_version_reference": strategy_version_reference,
            "proposal_reference": proposal_reference,
            "account_observation_reference": account_observation_reference,
            "trading_calendar_reference": trading_calendar_reference,
            "price_reference": price_reference,
            "account_id": account_id,
            "symbol": symbol,
            "action": action,
            "accepted_weight": accepted_weight,
            "account_nav": account_nav,
            "available_cash": available_cash,
            "reference_price": reference_price,
            "current_quantity": current_quantity,
            "available_quantity": available_quantity,
            "lot_size": lot_size,
            "authorized_notional": authorized_notional,
            "recommended_quantity": recommended,
            "intended_quantity": intended,
            "residual_cash": residual_cash,
            "override_reason": override_reason,
            "decision_time": decision_time,
            "created_at": created_at,
            "schema_version": STRATEGY_EXECUTION_AUTHORIZATION_SCHEMA,
        }
        digest = canonical_hash(_authorization_payload(**values))
        return cls(
            authorization_id=ArtifactId(
                f"strategy-execution-authorization:{digest[7:]}"
            ),
            authorization_hash=digest,
            **values,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _authorization_payload(
            portfolio_decision_reference=self.portfolio_decision_reference,
            strategy_version_reference=self.strategy_version_reference,
            proposal_reference=self.proposal_reference,
            account_observation_reference=self.account_observation_reference,
            trading_calendar_reference=self.trading_calendar_reference,
            price_reference=self.price_reference,
            account_id=self.account_id,
            symbol=self.symbol,
            action=self.action,
            accepted_weight=self.accepted_weight,
            account_nav=self.account_nav,
            available_cash=self.available_cash,
            reference_price=self.reference_price,
            current_quantity=self.current_quantity,
            available_quantity=self.available_quantity,
            lot_size=self.lot_size,
            authorized_notional=self.authorized_notional,
            recommended_quantity=self.recommended_quantity,
            intended_quantity=self.intended_quantity,
            residual_cash=self.residual_cash,
            override_reason=self.override_reason,
            decision_time=self.decision_time,
            created_at=self.created_at,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "authorization_id": str(self.authorization_id),
            "authorization_hash": self.authorization_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> StrategyExecutionAuthorization:
        return cls(
            authorization_id=ArtifactId(str(payload["authorization_id"])),
            authorization_hash=str(payload["authorization_hash"]),
            portfolio_decision_reference=_reference(
                payload["portfolio_decision_reference"]
            ),
            strategy_version_reference=_reference(
                payload["strategy_version_reference"]
            ),
            proposal_reference=_reference(payload["proposal_reference"]),
            account_observation_reference=_reference(
                payload["account_observation_reference"]
            ),
            trading_calendar_reference=_reference(
                payload["trading_calendar_reference"]
            ),
            price_reference=_reference(payload["price_reference"]),
            account_id=str(payload["account_id"]),
            symbol=str(payload["symbol"]),
            action=str(payload["action"]),
            accepted_weight=Decimal(str(payload["accepted_weight"])),
            account_nav=Decimal(str(payload["account_nav"])),
            available_cash=Decimal(str(payload["available_cash"])),
            reference_price=Decimal(str(payload["reference_price"])),
            current_quantity=int(payload["current_quantity"]),
            available_quantity=int(payload["available_quantity"]),
            lot_size=int(payload["lot_size"]),
            authorized_notional=Decimal(str(payload["authorized_notional"])),
            recommended_quantity=int(payload["recommended_quantity"]),
            intended_quantity=int(payload["intended_quantity"]),
            residual_cash=Decimal(str(payload["residual_cash"])),
            override_reason=(
                None
                if payload["override_reason"] is None
                else str(payload["override_reason"])
            ),
            decision_time=datetime.fromisoformat(str(payload["decision_time"])),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            schema_version=str(payload["schema_version"]),
        )


def _authorization_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": values["schema_version"],
        "portfolio_decision_reference": values[
            "portfolio_decision_reference"
        ].to_canonical_dict(),
        "strategy_version_reference": values[
            "strategy_version_reference"
        ].to_canonical_dict(),
        "proposal_reference": values["proposal_reference"].to_canonical_dict(),
        "account_observation_reference": values[
            "account_observation_reference"
        ].to_canonical_dict(),
        "trading_calendar_reference": values[
            "trading_calendar_reference"
        ].to_canonical_dict(),
        "price_reference": values["price_reference"].to_canonical_dict(),
        "account_id": values["account_id"],
        "symbol": values["symbol"],
        "action": values["action"],
        "accepted_weight": str(values["accepted_weight"]),
        "account_nav": str(values["account_nav"]),
        "available_cash": str(values["available_cash"]),
        "reference_price": str(values["reference_price"]),
        "current_quantity": values["current_quantity"],
        "available_quantity": values["available_quantity"],
        "lot_size": values["lot_size"],
        "authorized_notional": str(values["authorized_notional"]),
        "recommended_quantity": values["recommended_quantity"],
        "intended_quantity": values["intended_quantity"],
        "residual_cash": str(values["residual_cash"]),
        "override_reason": values["override_reason"],
        "decision_time": canonical_datetime(values["decision_time"]),
        "created_at": canonical_datetime(values["created_at"]),
    }


def _price_reference(
    *,
    proposal_reference: RuntimeArtifactReference,
    account_observation_reference: RuntimeArtifactReference,
    reference_price: Decimal,
    decision_time: datetime,
) -> RuntimeArtifactReference:
    payload = {
        "schema_version": "strategy-reference-price/v1",
        "proposal_id": str(proposal_reference.artifact_id),
        "account_observation_id": str(account_observation_reference.artifact_id),
        "reference_price": str(reference_price),
        "decision_time": canonical_datetime(decision_time),
    }
    digest = canonical_hash(payload)
    return RuntimeArtifactReference(
        "STRATEGY_REFERENCE_PRICE",
        ArtifactId(f"strategy-reference-price:{digest[7:]}"),
        digest,
    )


def _reference(value: object) -> RuntimeArtifactReference:
    if not isinstance(value, Mapping):
        raise ValueError("expected Artifact reference")
    return RuntimeArtifactReference.from_canonical_dict(value)


__all__ = [
    "STRATEGY_EXECUTION_AUTHORIZATION_SCHEMA",
    "StrategyExecutionAuthorization",
]
