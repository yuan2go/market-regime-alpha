from market_regime_alpha.research.mr2b_f2b_v2_primary import evaluate_primary_gate_v2
from market_regime_alpha.research.mr2b_f2b_v2_protocol import frozen_f2b_v2_protocol
from market_regime_alpha.research.mr2b_f2b_v2_statistics import PrimaryCoverageAssessment


def test_insufficient_coverage_produces_assessment_without_statistics() -> None:
    coverage = PrimaryCoverageAssessment(44, 14, 30, 0, 0, True, False, ("INSUFFICIENT_UP_SLICE",))
    result = evaluate_primary_gate_v2(coverage=coverage, evidence=None, protocol=frozen_f2b_v2_protocol())
    assert result.assessment.value == "INSUFFICIENT_EVIDENCE"
    assert result.failure_reasons == ("INSUFFICIENT_UP_SLICE",)


def test_gate_thresholds_come_from_protocol() -> None:
    protocol = frozen_f2b_v2_protocol()
    coverage = PrimaryCoverageAssessment(30, 15, 15, 0, 0, True, True, ())
    evidence = {
        "observed_effect": protocol.economic_effect_floor / 2,
        "bootstrap_valid_draws": protocol.bootstrap_draws,
        "bootstrap_ci_lower": 0.0001,
        "circular_shift_p_value": protocol.circular_shift_alpha,
        "first_half_effect": 0.001,
        "second_half_effect": 0.001,
        "half_coverage_complete": True,
        "largest_absolute_contribution_share": protocol.largest_contribution_limit,
        "top_3_absolute_contribution_share": protocol.top_3_contribution_limit,
        "panel_effects": (0.001,) * protocol.seed_panel_count,
    }
    result = evaluate_primary_gate_v2(coverage=coverage, evidence=evidence, protocol=protocol)
    assert result.assessment.value == "PRIMARY_HYPOTHESIS_NOT_SUPPORTED"
    assert "BELOW_ECONOMIC_EFFECT_FLOOR" in result.failure_reasons
    assert "ARTIFACT_SEMANTICS_UNVERIFIED" not in result.failure_reasons
