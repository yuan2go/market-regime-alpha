"""Research-only, fail-closed orderability assessment contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data import PriceLimitState
from market_regime_alpha.market_data.contracts import require_decimal, require_utc_second
from market_regime_alpha.universe.operational import SuspensionStatus


RESEARCH_ORDERABILITY_POLICY_SCHEMA = "research-orderability-policy-v1"
RESEARCH_ORDERABILITY_ASSESSMENT_SCHEMA = "research-orderability-assessment-v1"


class OrderabilitySide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderabilityStatus(str, Enum):
    ORDERABLE_FOR_RESEARCH = "ORDERABLE_FOR_RESEARCH"
    NOT_ORDERABLE = "NOT_ORDERABLE"
    ORDERABILITY_UNKNOWN = "ORDERABILITY_UNKNOWN"


@dataclass(frozen=True, slots=True)
class ResearchOrderabilityEvidence:
    symbol: str
    observed_at: datetime
    side: OrderabilitySide
    suspension_status: SuspensionStatus
    price_limit_state: PriceLimitState
    last_price: Decimal | None
    board_rule_id: str | None
    lot_size: int | None
    in_continuous_auction: bool | None
    liquidity_sufficient: bool | None
    listing_rule_id: str | None
    source_manifest_id: ArtifactId
    source_manifest_hash: str

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_utc_second("observed_at", self.observed_at)
        if self.last_price is not None:
            require_decimal("last_price", self.last_price, positive=True)
        for label, text_value in (
            ("board_rule_id", self.board_rule_id),
            ("listing_rule_id", self.listing_rule_id),
        ):
            if text_value is not None:
                require_text(label, text_value)
        if self.lot_size is not None and (
            isinstance(self.lot_size, bool)
            or not isinstance(self.lot_size, int)
            or self.lot_size <= 0
        ):
            raise ValueError("lot_size must be a positive integer or None")
        for label, boolean_value in (
            ("in_continuous_auction", self.in_continuous_auction),
            ("liquidity_sufficient", self.liquidity_sufficient),
        ):
            if boolean_value is not None and not isinstance(boolean_value, bool):
                raise TypeError(f"{label} must be a bool or None")
        require_sha256("source_manifest_hash", self.source_manifest_hash)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "observed_at": canonical_datetime(self.observed_at),
            "side": self.side.value,
            "suspension_status": self.suspension_status.value,
            "price_limit_state": self.price_limit_state.value,
            "last_price": None if self.last_price is None else str(self.last_price),
            "board_rule_id": self.board_rule_id,
            "lot_size": self.lot_size,
            "in_continuous_auction": self.in_continuous_auction,
            "liquidity_sufficient": self.liquidity_sufficient,
            "listing_rule_id": self.listing_rule_id,
            "source_manifest_id": str(self.source_manifest_id),
            "source_manifest_hash": self.source_manifest_hash,
        }


@dataclass(frozen=True, slots=True)
class ResearchOrderabilityAssessment:
    schema_version: str
    assessment_id: ArtifactId
    content_hash: str
    policy_id: ArtifactId
    policy_hash: str
    symbol: str
    observed_at: datetime
    status: OrderabilityStatus
    reason_codes: tuple[str, ...]
    evidence_hash: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_ORDERABILITY_ASSESSMENT_SCHEMA:
            raise ValueError("unsupported Research Orderability assessment schema")
        require_text("symbol", self.symbol)
        require_utc_second("observed_at", self.observed_at)
        for label, value in (
            ("content_hash", self.content_hash),
            ("policy_hash", self.policy_hash),
            ("evidence_hash", self.evidence_hash),
        ):
            require_sha256(label, value)
        if not self.reason_codes or self.reason_codes != tuple(
            sorted(set(self.reason_codes))
        ):
            raise ValueError("Orderability reasons must be non-empty and sorted")
        if self.limitations != (
            "NO_ORDER_AUTHORITY",
            "RESEARCH_ONLY_ORDERABILITY",
        ):
            raise ValueError("Orderability authority ceiling is incomplete")
        self.verify_identity()

    @property
    def execution_authority_granted(self) -> bool:
        return False

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": RESEARCH_ORDERABILITY_ASSESSMENT_SCHEMA,
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            "symbol": self.symbol,
            "observed_at": canonical_datetime(self.observed_at),
            "status": self.status.value,
            "reason_codes": list(self.reason_codes),
            "evidence_hash": self.evidence_hash,
            "limitations": list(self.limitations),
        }

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Research Orderability assessment hash mismatch")
        expected = f"research-orderability-{digest.split(':', 1)[1][:24]}"
        if str(self.assessment_id) != expected:
            raise ValueError("Research Orderability assessment identity mismatch")


@dataclass(frozen=True, slots=True)
class ResearchOrderabilityPolicy:
    schema_version: str
    policy_id: ArtifactId
    content_hash: str
    policy_version: str

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_ORDERABILITY_POLICY_SCHEMA:
            raise ValueError("unsupported Research Orderability policy schema")
        require_text("policy_version", self.policy_version)
        require_sha256("content_hash", self.content_hash)
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Research Orderability policy hash mismatch")
        expected = f"research-orderability-policy-{digest.split(':', 1)[1][:24]}"
        if str(self.policy_id) != expected:
            raise ValueError("Research Orderability policy identity mismatch")

    @classmethod
    def create(cls, *, policy_version: str) -> ResearchOrderabilityPolicy:
        payload = {
            "schema_version": RESEARCH_ORDERABILITY_POLICY_SCHEMA,
            "policy_version": policy_version,
            "required_evidence": [
                "AUCTION_PHASE",
                "BOARD_RULE",
                "LIQUIDITY",
                "LISTING_RULE",
                "LOT_SIZE",
                "PRICE_LIMIT_STATE",
                "SUSPENSION_STATUS",
                "VALID_PRICE",
            ],
            "authority": "RESEARCH_ONLY",
        }
        digest = canonical_hash(payload)
        return cls(
            schema_version=RESEARCH_ORDERABILITY_POLICY_SCHEMA,
            policy_id=ArtifactId(
                f"research-orderability-policy-{digest.split(':', 1)[1][:24]}"
            ),
            content_hash=digest,
            policy_version=policy_version,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": RESEARCH_ORDERABILITY_POLICY_SCHEMA,
            "policy_version": self.policy_version,
            "required_evidence": [
                "AUCTION_PHASE",
                "BOARD_RULE",
                "LIQUIDITY",
                "LISTING_RULE",
                "LOT_SIZE",
                "PRICE_LIMIT_STATE",
                "SUSPENSION_STATUS",
                "VALID_PRICE",
            ],
            "authority": "RESEARCH_ONLY",
        }

    def assess(
        self, evidence: ResearchOrderabilityEvidence
    ) -> ResearchOrderabilityAssessment:
        blockers: list[str] = []
        if evidence.suspension_status is SuspensionStatus.SUSPENDED:
            blockers.append("SUSPENDED")
        if (
            evidence.side is OrderabilitySide.BUY
            and evidence.price_limit_state is PriceLimitState.LIMIT_UP
        ):
            blockers.append("BUY_LIMIT_UP")
        if (
            evidence.side is OrderabilitySide.SELL
            and evidence.price_limit_state is PriceLimitState.LIMIT_DOWN
        ):
            blockers.append("SELL_LIMIT_DOWN")
        if evidence.in_continuous_auction is False:
            blockers.append("OUTSIDE_CONTINUOUS_AUCTION")
        if evidence.liquidity_sufficient is False:
            blockers.append("LIQUIDITY_INSUFFICIENT")

        missing: list[str] = []
        if evidence.suspension_status is SuspensionStatus.UNKNOWN:
            missing.append("SUSPENSION_STATUS_UNAVAILABLE")
        if evidence.price_limit_state is PriceLimitState.UNKNOWN:
            missing.append("PRICE_LIMIT_STATE_UNAVAILABLE")
        if evidence.last_price is None:
            missing.append("VALID_PRICE_UNAVAILABLE")
        if evidence.board_rule_id is None:
            missing.append("BOARD_RULE_UNAVAILABLE")
        if evidence.lot_size is None:
            missing.append("LOT_SIZE_UNAVAILABLE")
        if evidence.in_continuous_auction is None:
            missing.append("AUCTION_PHASE_UNAVAILABLE")
        if evidence.liquidity_sufficient is None:
            missing.append("LIQUIDITY_EVIDENCE_UNAVAILABLE")
        if evidence.listing_rule_id is None:
            missing.append("LISTING_RULE_UNAVAILABLE")

        if blockers:
            status = OrderabilityStatus.NOT_ORDERABLE
            reasons = tuple(sorted(blockers))
        elif missing:
            status = OrderabilityStatus.ORDERABILITY_UNKNOWN
            reasons = tuple(sorted(missing))
        else:
            status = OrderabilityStatus.ORDERABLE_FOR_RESEARCH
            reasons = ("ALL_RESEARCH_ORDERABILITY_EVIDENCE_PRESENT",)
        evidence_hash = canonical_hash(evidence.to_canonical_dict())
        values: dict[str, Any] = {
            "schema_version": RESEARCH_ORDERABILITY_ASSESSMENT_SCHEMA,
            "policy_id": str(self.policy_id),
            "policy_hash": self.content_hash,
            "symbol": evidence.symbol,
            "observed_at": canonical_datetime(evidence.observed_at),
            "status": status.value,
            "reason_codes": list(reasons),
            "evidence_hash": evidence_hash,
            "limitations": [
                "NO_ORDER_AUTHORITY",
                "RESEARCH_ONLY_ORDERABILITY",
            ],
        }
        digest = canonical_hash(values)
        return ResearchOrderabilityAssessment(
            schema_version=RESEARCH_ORDERABILITY_ASSESSMENT_SCHEMA,
            assessment_id=ArtifactId(
                f"research-orderability-{digest.split(':', 1)[1][:24]}"
            ),
            content_hash=digest,
            policy_id=self.policy_id,
            policy_hash=self.content_hash,
            symbol=evidence.symbol,
            observed_at=evidence.observed_at,
            status=status,
            reason_codes=reasons,
            evidence_hash=evidence_hash,
            limitations=(
                "NO_ORDER_AUTHORITY",
                "RESEARCH_ONLY_ORDERABILITY",
            ),
        )


def default_research_orderability_policy() -> ResearchOrderabilityPolicy:
    return ResearchOrderabilityPolicy.create(
        policy_version="a-share-research-orderability-v1"
    )


__all__ = [
    "OrderabilitySide",
    "OrderabilityStatus",
    "ResearchOrderabilityAssessment",
    "ResearchOrderabilityEvidence",
    "ResearchOrderabilityPolicy",
    "default_research_orderability_policy",
]
