from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D, localcontext

import pytest

from market_regime_alpha.interfaces.cli.main import _parser
from market_regime_alpha.research_qualification.domain.historical_comparison import historical_comparison_statistics
from market_regime_alpha.shared.hashing import canonical_json_sha256
from tests.contracts.research_qualification.test_historical_comparison import source


def projection():
    points, arguments = source()
    statistics = historical_comparison_statistics(points, **arguments)
    payload = {"schema": "mra-historical-comparison-v2", "statistics": statistics, "robustness": {"comparisons": ()}}
    return payload | {"projection_sha256": canonical_json_sha256(payload)}


def test_independent_common_ranking_does_not_require_a_constant_reference_rank():
    from market_regime_alpha.research_qualification.domain.historical_ordering import with_independent_ordering

    original = projection()
    frozen = deepcopy(original)
    # The retained field is explicitly paired: the zero reference has no rank.
    model = original["statistics"]["arms"][1]
    assert model["common_population"]["daily_rank_ic"]["model"]["mean"]["value"] is None
    result = with_independent_ordering(original)
    zero, model = result["independent_ordering"]["arms"]
    assert result["schema"] == "mra-historical-comparison-v3"
    assert result["prior_projection_sha256"] == original["projection_sha256"]
    assert original == frozen
    assert result["statistics"] == original["statistics"]
    assert zero["all_arm_common_population"]["state"] == "NOT_ESTIMABLE"
    assert zero["all_arm_common_population"]["mean"] is None
    # Predictions (-.5,0,.5) and labels (-1,0,1) have identical ranks each day.
    assert model["all_arm_common_population"]["mean"] == D(1)
    assert model["all_arm_common_population"]["estimable_sessions"] == 2
    assert model["all_arm_common_population"]["expected_sessions"] == 2
    assert model["per_fold"][0]["statistics"]["mean"] == D(1)
    assert model["per_month"][0]["statistics"]["mean"] == D(1)
    assert model["per_year"][0]["statistics"]["mean"] == D(1)
    with localcontext() as context:
        context.prec = 6
        assert with_independent_ordering(original) == result
    assert canonical_json_sha256({k: v for k, v in result.items() if k != "projection_sha256"}) == result["projection_sha256"]


def test_invalid_original_projection_cannot_be_relabelled_as_current_diagnostics():
    from market_regime_alpha.research_qualification.domain.historical_ordering import with_independent_ordering

    original = projection()
    for changed in (original | {"schema": "mra-historical-comparison-v1"}, original | {"projection_sha256": "0" * 64}):
        with pytest.raises(ValueError):
            with_independent_ordering(changed)


def test_missing_date_is_retained_in_independent_common_ranking():
    from market_regime_alpha.research_qualification.domain.historical_ordering import with_independent_ordering

    points, arguments = source()
    points = tuple(replace(point, prediction=None, forecast_status="NOT_ESTIMABLE", input_state="NOT_ESTIMABLE")
        if point.arm_id.int == 2 and point.session_id.int == 5 else point for point in points)
    original = {"schema": "mra-historical-comparison-v2",
        "statistics": historical_comparison_statistics(points, **arguments), "robustness": {"comparisons": ()}}
    original["projection_sha256"] = canonical_json_sha256(original)
    model = with_independent_ordering(original)["independent_ordering"]["arms"][1]["all_arm_common_population"]
    assert model["mean"] == 1
    assert model["expected_sessions"] == 2 and model["estimable_sessions"] == 1
    assert model["not_estimable_sessions"] == 1
    assert model["per_day"][1]["state"] == "NOT_ESTIMABLE" and model["per_day"][1]["observation_count"] == 0


def test_independent_model_rank_does_not_invent_a_paired_constant_rank_delta():
    from market_regime_alpha.research_qualification.domain.historical_ordering import with_independent_ordering
    from market_regime_alpha.research_qualification.domain.robustness_statistics import robustness_statistics
    from tests.contracts.research_qualification.test_robustness_statistics import inputs

    points, arguments = inputs()
    original = {"schema": "mra-historical-comparison-v2",
        "statistics": historical_comparison_statistics(points, **arguments, baseline_arm_id=arguments["arms"][0][0]),
        "robustness": robustness_statistics(points, **arguments)}
    original["projection_sha256"] = canonical_json_sha256(original)
    pairs = with_independent_ordering(original)["independent_ordering"]["comparisons"]
    assert len(pairs) == 7
    for pair in pairs:
        assert pair["model_on_pair_population"]["mean"] == 1
        if pair["reference"] in ("zero", "training_mean", "training_median"):
            assert pair["reference_on_pair_population"]["mean"] is None
            assert pair["mean_paired_daily_rank_ic_delta"] is None
            assert pair["paired_daily_ic_uncertainty"]["state"] == "NOT_ESTIMABLE"
        else:
            assert pair["reference_on_pair_population"]["mean"] == 1
            assert pair["mean_paired_daily_rank_ic_delta"] == 0


def test_new_projection_is_explicit_and_old_cli_default_is_retained():
    arguments = ["research", "history-compare", "--run-id", "00000000-0000-0000-0000-000000000001",
        "--expected-database-name", "isolated", "--expected-database-oid", "42"]
    assert _parser().parse_args(arguments).projection_version is None
    assert _parser().parse_args([*arguments, "--projection-version", "3"]).projection_version == 3
    with pytest.raises(SystemExit):
        _parser().parse_args([*arguments, "--projection-version", "2"])
