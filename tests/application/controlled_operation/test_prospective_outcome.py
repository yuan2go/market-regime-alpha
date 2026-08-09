from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    OutcomeMarketCondition,
    ShadowOutcomeObservation,
)


AVAILABLE = datetime(2026, 8, 11, 2, 31, tzinfo=UTC)


def test_checkpoint_outcome_derives_returns_and_round_trips() -> None:
    observation = ShadowOutcomeObservation.create(
        symbol="600000.SH",
        decision_reference_price=Decimal("10"),
        next_open=Decimal("10.1"),
        price_0930=Decimal("10.1"),
        price_1000=Decimal("10.2"),
        price_1030=Decimal("10.3"),
        mfe=Decimal("0.04"),
        mae=Decimal("-0.01"),
        first_passage_plus_1=AVAILABLE,
        first_passage_plus_2=AVAILABLE,
        first_passage_minus_1=None,
        market_conditions=(OutcomeMarketCondition.TRADING,),
        availability_status=OutcomeAvailabilityStatus.COMPLETE,
        outcome_available_at=AVAILABLE,
        reason_codes=("OUTCOME_COMPLETE",),
    )

    assert observation.open_return == Decimal("0.01")
    assert observation.return_1000 == Decimal("0.02")
    assert observation.return_1030 == Decimal("0.03")
    assert ShadowOutcomeObservation.from_canonical_dict(
        observation.to_canonical_dict()
    ) == observation


def test_checkpoint_outcome_rejects_caller_forged_return() -> None:
    canonical = ShadowOutcomeObservation.create(
        symbol="600000.SH",
        decision_reference_price=Decimal("10"),
        next_open=Decimal("10.1"),
        price_0930=Decimal("10.1"),
        price_1000=None,
        price_1030=None,
        mfe=None,
        mae=None,
        first_passage_plus_1=None,
        first_passage_plus_2=None,
        first_passage_minus_1=None,
        market_conditions=(OutcomeMarketCondition.MISSING_QUOTE,),
        availability_status=OutcomeAvailabilityStatus.PARTIAL,
        outcome_available_at=AVAILABLE,
        reason_codes=("CHECKPOINT_QUOTE_MISSING",),
    )
    payload = canonical.to_canonical_dict()
    payload["return_1000"] = "0.5"

    with pytest.raises(ValueError, match="returns do not match"):
        ShadowOutcomeObservation.from_canonical_dict(payload)
