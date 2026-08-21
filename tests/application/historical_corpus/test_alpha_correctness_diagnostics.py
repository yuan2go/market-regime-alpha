from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from market_regime_alpha.application.historical_corpus.alpha_diagnostics import (
    AlphaObservation,
    ExecutionPriceInputs,
    ExecutionPriceProxy,
    FactorObservation,
    FrozenPlaceboProtocol,
    MovingBlockInferenceProtocol,
    PlaceboKind,
    SessionEstimate,
    apply_placebo,
    diagnose_execution_price,
    evaluate_factor_redundancy,
    evaluate_robust_inference,
)


def _alpha_observations() -> tuple[AlphaObservation, ...]:
    return tuple(
        AlphaObservation(
            session=date(2026, 1, day),
            symbol=symbol,
            factor_value=Decimal(str(day * 10 + index)),
            target_return=Decimal(str(index - 1)),
        )
        for day in (2, 3, 4)
        for index, symbol in enumerate(("000001.SZ", "000002.SZ", "600000.SH"))
    )


@pytest.mark.parametrize("kind", tuple(PlaceboKind))
def test_frozen_placebos_are_deterministic_and_content_addressed(kind: PlaceboKind) -> None:
    protocol = FrozenPlaceboProtocol.create(
        factor_id="intraday_return_to_decision_time",
        target_id="T_PLUS_1_1030_RETURN",
        seed=20260819,
        kinds=tuple(PlaceboKind),
    )

    first = apply_placebo(protocol, kind=kind, observations=_alpha_observations())
    second = apply_placebo(protocol, kind=kind, observations=_alpha_observations())

    assert first == second
    assert protocol.protocol_hash.startswith("sha256:")
    assert first.protocol_reference.content_hash == protocol.protocol_hash


def test_execution_reference_is_not_silently_treated_as_executable() -> None:
    inputs = ExecutionPriceInputs(
        decision_reference=Decimal("10"),
        next_observable_price=Decimal("10.1"),
        next_bar_open=Decimal("10.2"),
        session_close=Decimal("10.3"),
        target_price=Decimal("11"),
    )

    research = diagnose_execution_price(inputs, ExecutionPriceProxy.DECISION_REFERENCE_ONLY)
    executable = diagnose_execution_price(inputs, ExecutionPriceProxy.NEXT_BAR_OPEN)

    assert research.executable is False
    assert research.gross_return == Decimal("0.1")
    assert executable.executable is True
    assert executable.gross_return == Decimal("11") / Decimal("10.2") - 1


def test_missing_execution_proxy_fails_closed() -> None:
    with pytest.raises(ValueError, match="unavailable"):
        diagnose_execution_price(
            ExecutionPriceInputs(
                decision_reference=Decimal("10"),
                next_observable_price=None,
                next_bar_open=None,
                session_close=Decimal("10.3"),
                target_price=Decimal("11"),
            ),
            ExecutionPriceProxy.NEXT_BAR_OPEN,
        )


def test_factor_redundancy_reports_pairwise_rank_and_incremental_information() -> None:
    observations = tuple(
        FactorObservation(
            session=date(2026, 1, day),
            symbol=f"S{index}",
            factors={
                "intraday_return_to_decision_time": Decimal(index),
                "price_vs_vwap_return": Decimal(index) * Decimal("2"),
                "vwap_slope": Decimal((index + day) % 5),
            },
            target_return=Decimal(index),
        )
        for day in range(2, 7)
        for index in range(5)
    )

    result = evaluate_factor_redundancy(observations)

    exact_pair = next(
        item
        for item in result.pairs
        if item.left == "intraday_return_to_decision_time"
        and item.right == "price_vs_vwap_return"
    )
    assert exact_pair.correlation == Decimal("1")
    assert exact_pair.rank_correlation == Decimal("1")
    assert result.status == "PARTIALLY_REDUNDANT"
    assert {item.factor_id for item in result.incremental} == {
        "intraday_return_to_decision_time",
        "price_vs_vwap_return",
        "vwap_slope",
    }


def test_moving_block_inference_is_deterministic_and_block_sensitive() -> None:
    observations = tuple(
        SessionEstimate(date(2026, 1, day), Decimal(day - 10) / Decimal("100"))
        for day in range(2, 22)
    )
    protocol = MovingBlockInferenceProtocol.create(
        iterations=200,
        block_lengths=(1, 3, 5),
        confidence_level=Decimal("0.9"),
        seed=20260819,
    )

    first = evaluate_robust_inference(protocol, observations)
    second = evaluate_robust_inference(protocol, observations)

    assert first == second
    assert tuple(item.block_length for item in first.sensitivity) == (1, 3, 5)
    assert all(item.lower <= item.estimate <= item.upper for item in first.sensitivity)
    assert first.temporal_stability in {"STABLE", "UNSTABLE"}
