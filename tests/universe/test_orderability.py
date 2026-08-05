from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.market_data import PriceLimitState
from market_regime_alpha.universe.operational import SuspensionStatus
from market_regime_alpha.universe.orderability import (
    OrderabilitySide,
    OrderabilityStatus,
    ResearchOrderabilityEvidence,
    default_research_orderability_policy,
)


UTC = timezone.utc
HASH = "sha256:" + "1" * 64


def _complete() -> ResearchOrderabilityEvidence:
    return ResearchOrderabilityEvidence(
        symbol="600000.SH",
        observed_at=datetime(2026, 8, 6, 6, 42, tzinfo=UTC),
        side=OrderabilitySide.BUY,
        suspension_status=SuspensionStatus.NOT_SUSPENDED,
        price_limit_state=PriceLimitState.NORMAL,
        last_price=Decimal("12.34"),
        board_rule_id="MAIN_BOARD_RULE_V1",
        lot_size=100,
        in_continuous_auction=True,
        liquidity_sufficient=True,
        listing_rule_id="STANDARD_LISTING_RULE_V1",
        source_manifest_id=ArtifactId("source-manifest-fixture"),
        source_manifest_hash=HASH,
    )


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"suspension_status": SuspensionStatus.UNKNOWN}, "SUSPENSION_STATUS_UNAVAILABLE"),
        ({"price_limit_state": PriceLimitState.UNKNOWN}, "PRICE_LIMIT_STATE_UNAVAILABLE"),
        ({"last_price": None}, "VALID_PRICE_UNAVAILABLE"),
        ({"board_rule_id": None}, "BOARD_RULE_UNAVAILABLE"),
        ({"lot_size": None}, "LOT_SIZE_UNAVAILABLE"),
        ({"in_continuous_auction": None}, "AUCTION_PHASE_UNAVAILABLE"),
        ({"liquidity_sufficient": None}, "LIQUIDITY_EVIDENCE_UNAVAILABLE"),
        ({"listing_rule_id": None}, "LISTING_RULE_UNAVAILABLE"),
    ),
)
def test_missing_evidence_is_orderability_unknown(
    changes: dict[str, object], reason: str
) -> None:
    assessment = default_research_orderability_policy().assess(
        replace(_complete(), **changes)
    )

    assert assessment.status is OrderabilityStatus.ORDERABILITY_UNKNOWN
    assert reason in assessment.reason_codes
    assert assessment.execution_authority_granted is False


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"suspension_status": SuspensionStatus.SUSPENDED}, "SUSPENDED"),
        ({"price_limit_state": PriceLimitState.LIMIT_UP}, "BUY_LIMIT_UP"),
        ({"in_continuous_auction": False}, "OUTSIDE_CONTINUOUS_AUCTION"),
        ({"liquidity_sufficient": False}, "LIQUIDITY_INSUFFICIENT"),
    ),
)
def test_explicit_blocker_is_not_orderable(
    changes: dict[str, object], reason: str
) -> None:
    assessment = default_research_orderability_policy().assess(
        replace(_complete(), **changes)
    )

    assert assessment.status is OrderabilityStatus.NOT_ORDERABLE
    assert reason in assessment.reason_codes


def test_complete_evidence_is_research_only_and_content_addressed() -> None:
    policy = default_research_orderability_policy()
    first = policy.assess(_complete())
    second = policy.assess(_complete())

    assert first == second
    assert first.status is OrderabilityStatus.ORDERABLE_FOR_RESEARCH
    assert first.execution_authority_granted is False
    assert first.content_hash.startswith("sha256:")
    assert "NO_ORDER_AUTHORITY" in first.limitations
