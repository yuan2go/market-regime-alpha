from __future__ import annotations

from dataclasses import replace

import pytest

from market_regime_alpha.core.identity import ArtifactId, FeatureDefinitionId
from market_regime_alpha.core.time import AvailabilityTime
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionState,
)
from market_regime_alpha.research.capital_evolution.model import (
    evaluate_capital_evolution_v0,
)
from market_regime_alpha.research.platform_v2.configs import (
    CapitalEvolutionModelConfig,
    ThemeRotationModelConfig,
)
from market_regime_alpha.research.platform_v2.inputs import (
    ResearchInputBundle,
    SymbolResearchObservation,
    ThemeMembership,
)
from market_regime_alpha.research.theme_rotation.model import (
    evaluate_theme_rotation_v0,
)

from .conftest import DECISION_AT
from .test_theme_rotation import _theme


def _symbol(symbol: str, strength: float) -> SymbolResearchObservation:
    ratio = (strength + 1.0) / 2.0
    return SymbolResearchObservation(
        symbol=symbol,
        available_at=AvailabilityTime(DECISION_AT),
        source_artifact_id=ArtifactId(f"symbol-source-{symbol}"),
        symbol_relative_strength=strength * 0.05,
        symbol_amount_expansion=strength * 0.50,
        theme_participation_contribution=strength * 0.20,
        leader_correlation=strength,
        leader_lag=-strength * 5.0,
        rank_persistence=ratio,
        amount_persistence=ratio,
        liquidity_eligible=True,
        history_complete=True,
        status_known=True,
        source_feature_ids=(
            FeatureDefinitionId("feature-r5-momentum-5s-v1"),
        ),
    )


@pytest.mark.parametrize(
    ("strength", "expected"),
    (
        (0.20, CapitalEvolutionState.ACCUMULATION),
        (0.40, CapitalEvolutionState.IGNITION),
        (0.60, CapitalEvolutionState.DIFFUSION),
        (0.85, CapitalEvolutionState.ACCELERATION),
        (-0.40, CapitalEvolutionState.EXHAUSTION),
        (-0.80, CapitalEvolutionState.COLLAPSE),
    ),
)
def test_capital_evolution_states_use_only_decision_time_observations(
    research_input_bundle: ResearchInputBundle,
    strength: float,
    expected: CapitalEvolutionState,
) -> None:
    theme = _theme("theme-a", strength)
    inputs = replace(
        research_input_bundle,
        theme_observations=(theme,),
        symbol_observations=(_symbol("600001.SH", strength),),
        theme_memberships=(
            ThemeMembership("600001.SH", "theme-a"),
        ),
    )
    rotation = evaluate_theme_rotation_v0(
        inputs, ThemeRotationModelConfig(), code_revision="test-revision"
    )
    snapshot = evaluate_capital_evolution_v0(
        inputs,
        rotation,
        CapitalEvolutionModelConfig(),
        code_revision="test-revision",
    )
    assert snapshot.themes[0].capital_evolution_state is expected
    assert snapshot.symbols[0].capital_evolution_state is expected


def test_capital_evolution_divergence_is_explicit(
    research_input_bundle: ResearchInputBundle,
) -> None:
    theme = replace(
        _theme("theme-a", 0.80),
        capital_concentration=0.90,
        participation_change=-0.10,
    )
    inputs = replace(
        research_input_bundle,
        theme_observations=(theme,),
        symbol_observations=(_symbol("600001.SH", 0.80),),
        theme_memberships=(ThemeMembership("600001.SH", "theme-a"),),
    )
    rotation = evaluate_theme_rotation_v0(
        inputs, ThemeRotationModelConfig(), code_revision="test-revision"
    )
    snapshot = evaluate_capital_evolution_v0(
        inputs,
        rotation,
        CapitalEvolutionModelConfig(),
        code_revision="test-revision",
    )
    assert (
        snapshot.themes[0].capital_evolution_state
        is CapitalEvolutionState.DIVERGENCE
    )
    assert "CAPITAL_DIVERGENCE_GATE" in snapshot.themes[0].reason_codes

