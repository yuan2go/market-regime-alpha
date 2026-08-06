from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.application.decision_system.contracts import (
    DecisionModelQualification,
    ManualAccountObservation,
    ManualPositionObservation,
)
from market_regime_alpha.application.decision_system.window import (
    DailyDecisionWindowPolicy,
    DecisionWindowBlocked,
)
from market_regime_alpha.core.identity import ArtifactId
from tests.application.decision_system.support import (
    TRADING_DATE,
    candidate,
    observation,
    summary,
)


UTC = timezone.utc


@pytest.mark.parametrize(
    ("hour", "minute", "allowed"),
    ((6, 29, False), (6, 30, True), (6, 45, True), (6, 55, True), (6, 56, False)),
)
def test_daily_decision_is_a_window_not_a_single_point(hour: int, minute: int, allowed: bool) -> None:
    policy = DailyDecisionWindowPolicy()
    as_of = datetime(2026, 8, 6, hour, minute, tzinfo=UTC)

    if allowed:
        policy.require_preview(trading_date=TRADING_DATE, as_of_time=as_of)
        policy.require_finalize(
            trading_date=TRADING_DATE,
            as_of_time=as_of,
            latest_available_at=as_of,
        )
    else:
        with pytest.raises(DecisionWindowBlocked):
            policy.require_preview(trading_date=TRADING_DATE, as_of_time=as_of)
        with pytest.raises(DecisionWindowBlocked):
            policy.require_finalize(
                trading_date=TRADING_DATE,
                as_of_time=as_of,
                latest_available_at=as_of,
            )


def test_finalize_rejects_late_evidence_and_complete_close_bar() -> None:
    policy = DailyDecisionWindowPolicy()
    as_of = datetime(2026, 8, 6, 6, 45, tzinfo=UTC)

    with pytest.raises(DecisionWindowBlocked, match="AVAILABLE_AT_EXCEEDS_AS_OF"):
        policy.require_finalize(
            trading_date=TRADING_DATE,
            as_of_time=as_of,
            latest_available_at=datetime(2026, 8, 6, 6, 46, tzinfo=UTC),
        )
    with pytest.raises(DecisionWindowBlocked, match="COMPLETE_CLOSE_BAR_PROHIBITED"):
        policy.require_finalize(
            trading_date=TRADING_DATE,
            as_of_time=as_of,
            latest_available_at=as_of,
            uses_complete_close_bar=True,
        )


def test_manual_account_is_decimal_append_only_observation_contract() -> None:
    account = observation()

    assert account.total_equity == Decimal("100000.120000")
    assert account.positions[0].average_cost == Decimal("10.123456")
    assert not hasattr(account, "fills")
    assert not hasattr(account, "position_mutations")
    with pytest.raises(TypeError, match="Decimal"):
        observation(total_equity=100000.12)  # type: ignore[arg-type]


def test_account_identity_canonicalizes_decimal_and_timezone_equivalence() -> None:
    canonical = observation(
        total_equity=Decimal("100000.120000"),
        available_cash=Decimal("80000.120000"),
    )
    china = timezone(timedelta(hours=8))
    equivalent = ManualAccountObservation.create(
        account_id=canonical.account_id,
        trading_date=canonical.trading_date,
        as_of_time=canonical.as_of_time.astimezone(china),
        total_equity=Decimal("100000.12"),
        available_cash=Decimal("80000.12"),
        frozen_cash=Decimal("0.000"),
        source=canonical.source,
        actor=canonical.actor,
        reason=canonical.reason,
        notes=canonical.notes,
        idempotency_key=canonical.idempotency_key,
        revision=canonical.revision,
        previous_observation_id=None,
        positions=canonical.positions,
        created_at=canonical.created_at.astimezone(china),
    )

    assert equivalent.observation_id == canonical.observation_id
    assert equivalent.content_hash == canonical.content_hash
    assert equivalent.to_canonical_dict() == canonical.to_canonical_dict()


def test_account_contract_rejects_noncanonical_time_and_unicode() -> None:
    with pytest.raises(ValueError, match="whole-second"):
        replace(
            observation(),
            as_of_time=observation().as_of_time.replace(microsecond=1),
        )
    with pytest.raises(ValueError, match="Unicode NFC"):
        observation(notes="Cafe\u0301")


def test_summary_rejects_candidate_or_signal_content_not_bound_to_state_bundles() -> None:
    claim = type("Claim", (), {"run_id": "run-a", "tick_id": "tick-a"})()
    valid = summary(
        claim=claim,
        observation_id=observation().observation_id,
        reconciliation_id=ArtifactId("reconciliation-a"),
    )

    with pytest.raises(ValueError, match="bundle content lineage"):
        replace(
            valid,
            candidates=(
                replace(
                    valid.candidates[0],
                    model_qualification=DecisionModelQualification.UNQUALIFIED,
                ),
            ),
        )
    with pytest.raises(ValueError, match="content hash mismatch"):
        replace(
            valid,
            candidates=(
                replace(
                    candidate(),
                    factor_coverage=Decimal("0.10"),
                ),
            ),
        )


@pytest.mark.parametrize(
    ("total", "available", "frozen"),
    ((-1, 0, -1), (100, 101, -1), (100, 80, 10)),
)
def test_manual_position_rejects_invalid_quantity_partition(total: int, available: int, frozen: int) -> None:
    with pytest.raises(ValueError):
        ManualPositionObservation(
            symbol="600000.SH",
            total_quantity=total,
            available_quantity=available,
            frozen_quantity=frozen,
            average_cost=Decimal("10") if total else None,
            observed_market_value=Decimal("100"),
        )
