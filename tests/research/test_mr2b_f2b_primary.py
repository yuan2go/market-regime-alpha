from market_regime_alpha.research.mr2b_f2b_primary import (
    PrimaryAssessment,
    evaluate_primary_gate,
)


def _evidence(effect: float = 0.002) -> dict[str, object]:
    return {
        "up_count": 20,
        "down_count": 20,
        "context_complete": True,
        "observed_effect": effect,
        "bootstrap_valid_draws": 10_000,
        "bootstrap_ci_lower": 0.001,
        "circular_shift_p_value": 0.01,
        "first_half_effect": 0.002,
        "second_half_effect": 0.002,
        "half_coverage_complete": True,
        "largest_absolute_contribution_share": 0.1,
        "top_3_absolute_contribution_share": 0.3,
        "panel_effects": (0.002, 0.002, 0.002, 0.002),
        "artifact_semantics_verified": True,
    }


def test_negative_effect_never_promotes_by_absolute_magnitude() -> None:
    result = evaluate_primary_gate(_evidence(-0.002))
    assert result.assessment is PrimaryAssessment.PRIMARY_HYPOTHESIS_NOT_SUPPORTED
    assert "OPPOSITE_DIRECTION" in result.failure_reasons


def test_positive_but_subfloor_effect_is_not_supported() -> None:
    result = evaluate_primary_gate(_evidence(0.0005))
    assert result.assessment is PrimaryAssessment.PRIMARY_HYPOTHESIS_NOT_SUPPORTED
    assert "BELOW_ECONOMIC_EFFECT_FLOOR" in result.failure_reasons


def test_slice_shortage_is_insufficient_evidence() -> None:
    evidence = _evidence()
    evidence["up_count"] = 14
    result = evaluate_primary_gate(evidence)
    assert result.assessment is PrimaryAssessment.INSUFFICIENT_EVIDENCE


def test_temporal_concentration_and_panel_failures_are_explicit() -> None:
    evidence = _evidence()
    evidence.update(
        second_half_effect=-0.001,
        largest_absolute_contribution_share=0.6,
        panel_effects=(0.002, 0.002, 0.0, 0.002),
    )
    result = evaluate_primary_gate(evidence)
    assert result.assessment is PrimaryAssessment.PRIMARY_HYPOTHESIS_NOT_SUPPORTED
    assert set(result.failure_reasons) >= {
        "TEMPORAL_DIRECTION_INCONSISTENT",
        "CONCENTRATED_EFFECT",
        "COMPARATOR_PANEL_UNSTABLE",
    }
