from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from market_regime_alpha.application.historical_corpus.context_conditional import (
    ContextDefinition,
    ContextKind,
    ContextObservation,
    ContextResearchRole,
    evaluate_context_conditioning,
)


def test_session_level_context_cannot_be_packaged_as_within_session_interaction() -> None:
    definition = ContextDefinition.create(
        context_id="MARKET_REGIME",
        kind=ContextKind.SESSION_LEVEL_CONTEXT,
        role=ContextResearchRole.CONDITIONAL_PERFORMANCE,
        public_observable_proxy=True,
    )
    observations = (
        ContextObservation(date(2026, 1, 2), "A", Decimal("1"), Decimal(".01"), "BULL", Decimal("1")),
        ContextObservation(date(2026, 1, 2), "B", Decimal("2"), Decimal(".02"), "BEAR", Decimal("0")),
    )

    with pytest.raises(ValueError, match="constant within each session"):
        evaluate_context_conditioning(definition, observations=observations, top_k=1)


def test_session_context_evaluates_performance_across_sessions_only() -> None:
    definition = ContextDefinition.create(
        context_id="MARKET_REGIME",
        kind=ContextKind.SESSION_LEVEL_CONTEXT,
        role=ContextResearchRole.CONDITIONAL_PERFORMANCE,
        public_observable_proxy=True,
    )
    observations = tuple(
        ContextObservation(
            date(2026, 1, day),
            f"S{index}",
            Decimal(index),
            Decimal(index if label == "BULL" else -index),
            label,
            Decimal("1") if label == "BULL" else Decimal("-1"),
        )
        for day, label in ((2, "BULL"), (3, "BEAR"), (4, "BULL"), (5, "BEAR"))
        for index in range(4)
    )

    result = evaluate_context_conditioning(definition, observations=observations, top_k=2)

    assert result.interaction_effect is None
    assert result.incremental_information is None
    assert result.status in {"AMPLIFIER", "SUPPRESSOR", "UNSTABLE"}
    assert {item.context_value for item in result.slices} == {"BEAR", "BULL"}


def test_cross_sectional_context_supports_interaction_and_incremental_information() -> None:
    definition = ContextDefinition.create(
        context_id="LIQUIDITY",
        kind=ContextKind.CROSS_SECTIONAL_CONTEXT,
        role=ContextResearchRole.INTERACTION,
        public_observable_proxy=True,
    )
    observations = tuple(
        ContextObservation(
            date(2026, 1, day),
            f"S{index}",
            Decimal(index),
            Decimal(index * (index + 1)),
            "HIGH" if index >= 2 else "LOW",
            Decimal(index),
        )
        for day in range(2, 7)
        for index in range(4)
    )

    result = evaluate_context_conditioning(definition, observations=observations, top_k=2)

    assert result.interaction_effect is not None
    assert result.incremental_information is not None
    assert result.status != "NOT_ESTIMABLE"


def test_cross_sectional_context_without_within_session_variation_is_not_estimable() -> None:
    definition = ContextDefinition.create(
        context_id="CAPITAL_PUBLIC_PROXY",
        kind=ContextKind.CROSS_SECTIONAL_CONTEXT,
        role=ContextResearchRole.INTERACTION,
        public_observable_proxy=True,
    )
    observations = tuple(
        ContextObservation(date(2026, 1, day), f"S{index}", Decimal(index), Decimal(index), "SAME", Decimal("1"))
        for day in range(2, 6)
        for index in range(4)
    )

    result = evaluate_context_conditioning(definition, observations=observations, top_k=2)

    assert result.status == "NOT_ESTIMABLE"
    assert result.interaction_effect is None
    assert "WITHIN_SESSION_CONTEXT_VARIATION_REQUIRED" in result.limitations
