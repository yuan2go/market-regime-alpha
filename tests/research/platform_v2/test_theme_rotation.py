from __future__ import annotations

from dataclasses import replace

import pytest

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import AvailabilityTime
from market_regime_alpha.research.platform_v2.configs import (
    ThemeRotationModelConfig,
)
from market_regime_alpha.research.platform_v2.inputs import (
    ResearchInputBundle,
    ThemeResearchObservation,
)
from market_regime_alpha.research.theme_rotation.contracts import RotationState
from market_regime_alpha.research.theme_rotation.model import (
    evaluate_theme_rotation_v0,
)

from .conftest import DECISION_AT


def _theme(
    theme_id: str,
    strength: float,
    *,
    participation: float | None = None,
    missing: bool = False,
) -> ThemeResearchObservation:
    scaled_return = strength * 0.05
    ratio = max(0.0, min(1.0, (strength + 1.0) / 2.0))
    return ThemeResearchObservation(
        theme_id=theme_id,
        theme_name=f"Theme {theme_id}",
        benchmark_id=f"benchmark-{theme_id}",
        proxy_etf_ids=(f"etf-{theme_id}",),
        available_at=AvailabilityTime(DECISION_AT),
        source_artifact_id=ArtifactId(f"theme-source-{theme_id}"),
        relative_strength_1d=None if missing else scaled_return,
        relative_strength_3d=scaled_return,
        relative_strength_5d=scaled_return,
        relative_strength_10d=scaled_return,
        amount_expansion=strength * 0.50,
        etf_amount_expansion=strength * 0.50,
        breadth=ratio,
        new_high_breadth=ratio,
        leader_strength=scaled_return,
        participation_change=(
            participation if participation is not None else strength * 0.20
        ),
        rank_persistence=ratio,
        amount_persistence=ratio,
        capital_concentration=1.0 - ratio,
        diffusion_score=ratio,
        confidence=1.0,
    )


@pytest.mark.parametrize(
    ("observation", "expected"),
    (
        (_theme("starting", 0.10), RotationState.STARTING),
        (_theme("strengthening", 0.40), RotationState.STRENGTHENING),
        (_theme("leading", 0.80), RotationState.LEADING),
        (
            _theme("diverging", 0.80, participation=-0.10),
            RotationState.DIVERGING,
        ),
        (_theme("weakening", -0.10), RotationState.WEAKENING),
        (_theme("missing", 0.50, missing=True), RotationState.DATA_INSUFFICIENT),
    ),
)
def test_theme_rotation_states(
    research_input_bundle: ResearchInputBundle,
    observation: ThemeResearchObservation,
    expected: RotationState,
) -> None:
    snapshot = evaluate_theme_rotation_v0(
        replace(research_input_bundle, theme_observations=(observation,)),
        ThemeRotationModelConfig(),
        code_revision="test-revision",
    )
    assert snapshot.themes[0].rotation_state is expected
    snapshot.envelope.verify_payload(snapshot.artifact_payload())


def test_theme_rotation_rank_tie_break_is_theme_id(
    research_input_bundle: ResearchInputBundle,
) -> None:
    snapshot = evaluate_theme_rotation_v0(
        replace(
            research_input_bundle,
            theme_observations=(_theme("beta", 0.80), _theme("alpha", 0.80)),
        ),
        ThemeRotationModelConfig(),
        code_revision="test-revision",
    )
    assert tuple(item.theme_id for item in snapshot.themes) == ("alpha", "beta")
    assert tuple(item.rank for item in snapshot.themes) == (1, 2)

