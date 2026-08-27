from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
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
    TimedPriceObservation,
    apply_placebo,
    diagnose_execution_price,
    evaluate_factor_redundancy,
    evaluate_placebo_rank_ic,
    evaluate_robust_inference,
    evaluate_robust_inference_family,
)
from market_regime_alpha.application.research_validation.common import ValidationArtifactReference
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


DECISION = datetime(2026, 1, 2, 6, 55, tzinfo=UTC)


def _price(value: str, minutes: int, kind: str) -> TimedPriceObservation:
    observed = DECISION + timedelta(minutes=minutes)
    return TimedPriceObservation(
        Decimal(value),
        observed,
        observed,
        ValidationArtifactReference(
            kind,
            ArtifactId(f"price-{kind.lower()}-{minutes}"),
            canonical_hash({"kind": kind, "minutes": minutes, "value": value}),
        ),
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
    diagnostic = evaluate_placebo_rank_ic(first)
    assert diagnostic.observation_count == len(first.observations)
    assert diagnostic.session_count > 0
    assert Decimal("0") <= diagnostic.positive_ic_ratio <= Decimal("1")
    assert first.to_canonical_dict()["rank_ic_diagnostic"] == (
        diagnostic.to_canonical_dict()
    )


def test_execution_reference_is_not_silently_treated_as_executable() -> None:
    inputs = ExecutionPriceInputs(
        information_cutoff=DECISION,
        decision_reference=_price("10", 0, "DECISION_REFERENCE"),
        next_observable_price=_price("10.1", 1, "NEXT_OBSERVABLE_PRICE"),
        next_bar_open=_price("10.2", 5, "NEXT_BAR_OPEN"),
        session_close=_price("10.3", 65, "SESSION_CLOSE"),
        target_reference=_price("11", 24 * 60, "TARGET_REFERENCE"),
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
                information_cutoff=DECISION,
                decision_reference=_price("10", 0, "DECISION_REFERENCE"),
                next_observable_price=None,
                next_bar_open=None,
                session_close=_price("10.3", 65, "SESSION_CLOSE"),
                target_reference=_price("11", 24 * 60, "TARGET_REFERENCE"),
            ),
            ExecutionPriceProxy.NEXT_BAR_OPEN,
        )


def test_executable_proxy_must_be_observed_before_target_event() -> None:
    delayed_target = TimedPriceObservation(
        Decimal("11"),
        DECISION + timedelta(minutes=10),
        DECISION + timedelta(minutes=30),
        _price("11", 10, "TARGET_REFERENCE").source_reference,
    )
    with pytest.raises(ValueError, match="observable window"):
        ExecutionPriceInputs(
            information_cutoff=DECISION,
            decision_reference=_price("10", 0, "DECISION_REFERENCE"),
            next_observable_price=_price("10.1", 20, "NEXT_OBSERVABLE_PRICE"),
            next_bar_open=None,
            session_close=None,
            target_reference=delayed_target,
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
    assert first.raw_p_value == max(item.null_p_value for item in first.sensitivity)
    assert first.temporal_stability in {"STABLE", "UNSTABLE"}
    assert protocol.to_canonical_dict()["schema_version"] == "alpha-moving-block-inference/v2"
    assert protocol.to_canonical_dict()["test_method"] == "NULL_CENTERED_MOVING_BLOCK"


def test_moving_block_inference_tests_the_zero_mean_null() -> None:
    observations = tuple(
        SessionEstimate(date(2026, 1, day), Decimal("0.1"))
        for day in range(2, 22)
    )
    protocol = MovingBlockInferenceProtocol.create(
        iterations=199,
        block_lengths=(1, 3, 5),
        confidence_level=Decimal("0.9"),
        seed=20260819,
    )

    result = evaluate_robust_inference(protocol, observations)

    assert result.raw_p_value == Decimal("0.005")
    assert result.adjusted_p_value == result.raw_p_value
    assert all(item.null_p_value == Decimal("0.005") for item in result.sensitivity)


def test_robust_inference_adjusts_one_frozen_multiple_testing_family() -> None:
    protocol = MovingBlockInferenceProtocol.create(
        iterations=100,
        block_lengths=(1, 3),
        confidence_level=Decimal("0.9"),
        seed=20260819,
    )
    family = evaluate_robust_inference_family(
        protocol,
        {
            "factor-a": tuple(
                SessionEstimate(date(2026, 2, day), Decimal(day) / Decimal("100"))
                for day in range(1, 11)
            ),
            "factor-b": tuple(
                SessionEstimate(date(2026, 2, day), Decimal(day - 6) / Decimal("100"))
                for day in range(1, 11)
            ),
        },
    )

    assert tuple(family) == ("factor-a", "factor-b")
    assert all(
        item.adjusted_p_value >= item.raw_p_value for item in family.values()
    )
