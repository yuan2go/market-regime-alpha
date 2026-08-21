"""Pre-Strategy Risk composition and immutable Strategy Opportunity facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True, slots=True)
class PreStrategySymbolRiskDecision:
    symbol: str
    allows_action: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("pre-Strategy Risk reason codes must be unique and sorted")
        if self.allows_action == bool(self.reason_codes):
            raise ValueError("pre-Strategy Risk decision and reason codes disagree")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "allows_action": self.allows_action,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> PreStrategySymbolRiskDecision:
        return cls(
            symbol=str(payload["symbol"]),
            allows_action=bool(payload["allows_action"]),
            reason_codes=tuple(str(item) for item in payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class PreStrategyRiskState:
    risk_state_id: ArtifactId
    risk_state_hash: str
    account_scope: str
    candidate_reference: RuntimeArtifactReference
    decision_time: datetime
    available_at: datetime
    account_state_reference: RuntimeArtifactReference
    position_state_references: tuple[RuntimeArtifactReference, ...]
    liquidity_constraint_references: tuple[RuntimeArtifactReference, ...]
    position_constraint_references: tuple[RuntimeArtifactReference, ...]
    risk_limit_references: tuple[RuntimeArtifactReference, ...]
    trading_restriction_references: tuple[RuntimeArtifactReference, ...]
    symbol_decisions: tuple[PreStrategySymbolRiskDecision, ...]
    limitations: tuple[str, ...]
    schema_version: str = "pre-strategy-risk-state/v1"

    def __post_init__(self) -> None:
        require_text("account_scope", self.account_scope)
        require_sha256("risk_state_hash", self.risk_state_hash)
        canonical_datetime(self.decision_time)
        canonical_datetime(self.available_at)
        if self.available_at > self.decision_time:
            raise ValueError("pre-Strategy Risk state is unavailable at DecisionTime")
        if self.candidate_reference.reference_kind != "CANDIDATE_SET":
            raise ValueError("pre-Strategy Risk requires Candidate owner")
        if self.account_state_reference.reference_kind in {
            "COMPLETE_ACCOUNT_RISK_DECISION",
            "CROSS_STRATEGY_PORTFOLIO",
            "PORTFOLIO_DECISION",
        }:
            raise ValueError("post-Portfolio facts cannot own pre-Strategy Risk")
        for references in self.reference_groups:
            if references != _references(references):
                raise ValueError("pre-Strategy Risk owner references must be unique and sorted")
            if any(
                item.reference_kind == "COMPLETE_ACCOUNT_RISK_DECISION"
                for item in references
            ):
                raise ValueError("Complete Account Risk is post-Portfolio authority")
        symbols = tuple(item.symbol for item in self.symbol_decisions)
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("pre-Strategy Risk symbol decisions must be unique and sorted")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("pre-Strategy Risk limitations must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.risk_state_hash:
            raise ValueError("pre-Strategy Risk state hash mismatch")
        if self.risk_state_id != ArtifactId(
            f"pre-strategy-risk-state:{self.risk_state_hash[7:]}"
        ):
            raise ValueError("pre-Strategy Risk state identity mismatch")

    @property
    def reference_groups(self) -> tuple[tuple[RuntimeArtifactReference, ...], ...]:
        return (
            self.position_state_references,
            self.liquidity_constraint_references,
            self.position_constraint_references,
            self.risk_limit_references,
            self.trading_restriction_references,
        )

    @property
    def source_references(self) -> tuple[RuntimeArtifactReference, ...]:
        return _references(
            (
                self.candidate_reference,
                self.account_state_reference,
                *(item for group in self.reference_groups for item in group),
            )
        )

    @property
    def reference(self) -> RuntimeArtifactReference:
        return RuntimeArtifactReference(
            "PRE_STRATEGY_RISK_STATE",
            self.risk_state_id,
            self.risk_state_hash,
        )

    def decision_for(self, symbol: str) -> PreStrategySymbolRiskDecision:
        matches = tuple(item for item in self.symbol_decisions if item.symbol == symbol)
        if len(matches) != 1:
            raise KeyError(symbol)
        return matches[0]

    @classmethod
    def create(
        cls,
        *,
        account_scope: str,
        candidate_reference: RuntimeArtifactReference,
        decision_time: datetime,
        available_at: datetime,
        account_state_reference: RuntimeArtifactReference,
        position_state_references: tuple[RuntimeArtifactReference, ...],
        liquidity_constraint_references: tuple[RuntimeArtifactReference, ...],
        position_constraint_references: tuple[RuntimeArtifactReference, ...],
        risk_limit_references: tuple[RuntimeArtifactReference, ...],
        trading_restriction_references: tuple[RuntimeArtifactReference, ...],
        symbol_decisions: tuple[PreStrategySymbolRiskDecision, ...],
        limitations: tuple[str, ...] = (),
    ) -> PreStrategyRiskState:
        values = {
            "account_scope": account_scope,
            "candidate_reference": candidate_reference,
            "decision_time": decision_time,
            "available_at": available_at,
            "account_state_reference": account_state_reference,
            "position_state_references": _references(position_state_references),
            "liquidity_constraint_references": _references(
                liquidity_constraint_references
            ),
            "position_constraint_references": _references(
                position_constraint_references
            ),
            "risk_limit_references": _references(risk_limit_references),
            "trading_restriction_references": _references(
                trading_restriction_references
            ),
            "symbol_decisions": tuple(
                sorted(symbol_decisions, key=lambda item: item.symbol)
            ),
            "limitations": tuple(sorted(set(limitations))),
        }
        digest = canonical_hash(_risk_payload(**values))
        return cls(
            risk_state_id=ArtifactId(f"pre-strategy-risk-state:{digest[7:]}"),
            risk_state_hash=digest,
            account_scope=account_scope,
            candidate_reference=candidate_reference,
            decision_time=decision_time,
            available_at=available_at,
            account_state_reference=account_state_reference,
            position_state_references=_references(position_state_references),
            liquidity_constraint_references=_references(
                liquidity_constraint_references
            ),
            position_constraint_references=_references(
                position_constraint_references
            ),
            risk_limit_references=_references(risk_limit_references),
            trading_restriction_references=_references(
                trading_restriction_references
            ),
            symbol_decisions=tuple(
                sorted(symbol_decisions, key=lambda item: item.symbol)
            ),
            limitations=tuple(sorted(set(limitations))),
        )

    def identity_payload(self) -> dict[str, Any]:
        return _risk_payload(
            **{
                name: getattr(self, name)
                for name in (
                    "account_scope",
                    "candidate_reference",
                    "decision_time",
                    "available_at",
                    "account_state_reference",
                    "position_state_references",
                    "liquidity_constraint_references",
                    "position_constraint_references",
                    "risk_limit_references",
                    "trading_restriction_references",
                    "symbol_decisions",
                    "limitations",
                )
            }
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "risk_state_id": str(self.risk_state_id),
            "risk_state_hash": self.risk_state_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PreStrategyRiskState:
        def refs(name: str) -> tuple[RuntimeArtifactReference, ...]:
            return tuple(
                RuntimeArtifactReference.from_canonical_dict(item)
                for item in payload[name]
            )

        return cls(
            risk_state_id=ArtifactId(str(payload["risk_state_id"])),
            risk_state_hash=str(payload["risk_state_hash"]),
            account_scope=str(payload["account_scope"]),
            candidate_reference=RuntimeArtifactReference.from_canonical_dict(
                payload["candidate_reference"]
            ),
            decision_time=datetime.fromisoformat(str(payload["decision_time"])),
            available_at=datetime.fromisoformat(str(payload["available_at"])),
            account_state_reference=RuntimeArtifactReference.from_canonical_dict(
                payload["account_state_reference"]
            ),
            position_state_references=refs("position_state_references"),
            liquidity_constraint_references=refs(
                "liquidity_constraint_references"
            ),
            position_constraint_references=refs(
                "position_constraint_references"
            ),
            risk_limit_references=refs("risk_limit_references"),
            trading_restriction_references=refs(
                "trading_restriction_references"
            ),
            symbol_decisions=tuple(
                PreStrategySymbolRiskDecision.from_canonical_dict(item)
                for item in payload["symbol_decisions"]
            ),
            limitations=tuple(str(item) for item in payload["limitations"]),
            schema_version=str(payload["schema_version"]),
        )


def _risk_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "pre-strategy-risk-state/v1",
        "account_scope": values["account_scope"],
        "candidate_reference": values["candidate_reference"].to_canonical_dict(),
        "decision_time": canonical_datetime(values["decision_time"]),
        "available_at": canonical_datetime(values["available_at"]),
        "account_state_reference": values[
            "account_state_reference"
        ].to_canonical_dict(),
        **{
            name: [item.to_canonical_dict() for item in values[name]]
            for name in (
                "position_state_references",
                "liquidity_constraint_references",
                "position_constraint_references",
                "risk_limit_references",
                "trading_restriction_references",
            )
        },
        "symbol_decisions": [
            item.to_canonical_dict() for item in values["symbol_decisions"]
        ],
        "limitations": list(values["limitations"]),
    }


def _references(
    references: tuple[RuntimeArtifactReference, ...],
) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.reference_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


__all__ = ["PreStrategyRiskState", "PreStrategySymbolRiskDecision"]
