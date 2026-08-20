from __future__ import annotations

from dataclasses import replace

import pytest

from market_regime_alpha.candidates.contracts import CandidatePrediction
from market_regime_alpha.core.identity import (
    ExperimentId,
    FeatureMaterializationId,
    TargetId,
)
from market_regime_alpha.platform.candidate_prediction_adapter import (
    B0_MOMENTUM_MODEL_ID,
    B1_BALANCED_MODEL_ID,
)
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    EvaluationProtocolId,
)
from market_regime_alpha.platform.prediction_run import PredictionRun
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateSelectionStatus,
)
from market_regime_alpha.research.candidate_discovery.legacy_adapter import (
    adapt_b0_b1_candidate_factors,
)
from market_regime_alpha.research.candidate_discovery.model import (
    discover_candidates_v2,
)
from market_regime_alpha.research.capital_evolution.model import (
    evaluate_capital_evolution_v0,
)
from market_regime_alpha.research.market_regime.model import (
    evaluate_market_regime_v0,
)
from market_regime_alpha.research.mr1_morning_pop import MR1TargetId
from market_regime_alpha.research.platform_v2.configs import (
    CapitalEvolutionModelConfig,
    CandidateDiscoveryModelConfig,
    MarketRegimeModelConfig,
    ThemeRotationModelConfig,
)
from market_regime_alpha.research.platform_v2.inputs import (
    ResearchInputBundle,
    ThemeMembership,
)
from market_regime_alpha.research.theme_rotation.model import (
    evaluate_theme_rotation_v0,
)
from market_regime_alpha.universe.contracts import TradingEligibilityStatus

from .test_capital_evolution import _symbol
from .test_theme_rotation import _theme


TARGET = TargetId(MR1TargetId.NEXT_SESSION_1030_RETURN.value)


def _prediction_runs(
    inputs: ResearchInputBundle,
    *,
    tied: bool = False,
) -> tuple[PredictionRun, PredictionRun]:
    symbols = inputs.universe_snapshot.member_symbols
    feature_ids = tuple(
        dict.fromkeys(
            feature_id
            for item in inputs.symbol_observations
            for feature_id in item.source_feature_ids
        )
    )
    if not feature_ids:
        feature_ids = (_symbol(symbols[0], 0.8).source_feature_ids[0],)
    materializations = tuple(
        FeatureMaterializationId(f"candidate-v2-materialization-{index}")
        for index in range(len(feature_ids))
    )
    output = []
    for model_id, experiment in (
        (B0_MOMENTUM_MODEL_ID, "candidate-v2-b0-experiment"),
        (B1_BALANCED_MODEL_ID, "candidate-v2-b1-experiment"),
    ):
        predictions = tuple(
            CandidatePrediction(
                symbol=symbol,
                universe_id=inputs.universe_snapshot.universe_id,
                model_id=model_id,
                target_id=TARGET,
                decision_time=inputs.source_manifest.decision_time,
                experiment_id=ExperimentId(experiment),
                population_size=len(symbols),
                model_score=(1.0 if tied else float(len(symbols) - rank)),
                rank=(1 if tied else rank),
                percentile=(
                    0.50
                    if tied
                    else 1.0 - (rank - 1) / (len(symbols) - 1)
                ),
            )
            for rank, symbol in enumerate(symbols, start=1)
        )
        output.append(
            PredictionRun(
                model_id=model_id,
                model_definition_hash="a" * 64,
                target_id=TARGET,
                evaluation_protocol_id=EvaluationProtocolId(
                    "candidate-v2-evaluation"
                ),
                experiment_protocol_id=ExperimentId(experiment),
                dataset_id=next(iter(inputs.prediction_runs)).dataset_id
                if inputs.prediction_runs
                else inputs.universe_snapshot.source_dataset_id,
                universe_id=inputs.universe_snapshot.universe_id,
                decision_time=inputs.source_manifest.decision_time,
                feature_definition_ids=feature_ids,
                feature_materialization_ids=materializations,
                code_revision="legacy-code",
                configuration_hash="b" * 64,
                predictions=predictions,
                rejections=(),
                population_size=len(symbols),
                ranking_coverage=1.0,
                data_eligibility=inputs.data_eligibility,
                evidence_level=EvidenceLevel.EXPLORATORY,
            )
        )
    return output[0], output[1]


def _qualified(
    base: ResearchInputBundle,
    *,
    tied: bool = False,
) -> ResearchInputBundle:
    symbols = base.universe_snapshot.member_symbols
    inputs = replace(
        base,
        theme_observations=(_theme("theme-a", 0.8),),
        symbol_observations=tuple(_symbol(symbol, 0.8) for symbol in symbols),
        theme_memberships=tuple(
            ThemeMembership(
                symbol,
                "theme-a",
                ("theme-support",) if symbol == symbols[0] else (),
            )
            for symbol in symbols
        ),
    )
    return replace(inputs, prediction_runs=_prediction_runs(inputs, tied=tied))


def _run(inputs: ResearchInputBundle):
    market = evaluate_market_regime_v0(
        inputs, MarketRegimeModelConfig(), code_revision="test-revision"
    )
    themes = evaluate_theme_rotation_v0(
        inputs, ThemeRotationModelConfig(), code_revision="test-revision"
    )
    capital = evaluate_capital_evolution_v0(
        inputs,
        themes,
        CapitalEvolutionModelConfig(),
        code_revision="test-revision",
    )
    candidates = discover_candidates_v2(
        inputs,
        market,
        themes,
        capital,
        CandidateDiscoveryModelConfig(),
        code_revision="test-revision",
    )
    return market, themes, capital, candidates


def test_legacy_adapter_projects_scores_without_probability_semantics(
    research_input_bundle: ResearchInputBundle,
) -> None:
    inputs = _qualified(research_input_bundle)
    factors = adapt_b0_b1_candidate_factors(inputs.prediction_runs)
    first = factors[inputs.universe_snapshot.member_symbols[0]]

    assert first.b0_momentum_percentile == 1.0
    assert first.b1_balanced_percentile == 1.0
    assert not hasattr(first, "probability")


def test_candidate_discovery_ranks_top_n_and_preserves_every_symbol(
    research_input_bundle: ResearchInputBundle,
) -> None:
    inputs = _qualified(research_input_bundle)
    _, _, _, candidates = _run(inputs)

    assert len(candidates.records) == 6
    assert len(candidates.selected) == 5
    assert tuple(item.symbol for item in candidates.selected) == (
        "600001.SH",
        "600002.SH",
        "600003.SH",
        "600004.SH",
        "600005.SH",
    )
    first = candidates.records[0]
    assert first.primary_theme_id == "theme-a"
    assert first.supporting_theme_ids == ("theme-support",)
    assert "B0_B1_ARE_BASELINE_FACTORS_NOT_PROBABILITIES" in first.reason_codes
    candidates.envelope.verify_payload(candidates.artifact_payload())


def test_candidate_boundary_tie_is_not_split_by_symbol(
    research_input_bundle: ResearchInputBundle,
) -> None:
    inputs = _qualified(research_input_bundle, tied=True)
    _, _, _, candidates = _run(inputs)
    ranked = tuple(item for item in candidates.records if item.rank is not None)
    assert {item.rank for item in ranked} == {1}
    assert {item.symbol for item in candidates.selected} == set(
        inputs.universe_snapshot.member_symbols
    )
    assert "CANDIDATE_BOUNDARY_TIE_EXPANDED" in candidates.reason_codes


def test_market_prohibit_rejects_complete_population(
    research_input_bundle: ResearchInputBundle,
) -> None:
    inputs = _qualified(research_input_bundle)
    observation = replace(
        inputs.market_observation,
        market_direction_return=-0.03,
        candidate_breadth_at_cutoff=0.05,
        market_amount_change_same_cutoff=-0.60,
        market_intraday_range_to_cutoff=0.05,
        limit_structure_score=-1.0,
    )
    _, _, _, candidates = _run(
        replace(inputs, market_observation=observation)
    )
    assert not candidates.selected
    assert all(
        item.selection_status is CandidateSelectionStatus.REJECTED
        and item.reason_codes == ("MARKET_REGIME_PROHIBITS_RISK",)
        for item in candidates.records
    )


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("liquidity_eligible", "INSUFFICIENT_LIQUIDITY"),
        ("history_complete", "INSUFFICIENT_HISTORY"),
        ("status_known", "TRADING_STATUS_UNKNOWN"),
    ),
)
def test_per_symbol_non_model_gates_are_explicit(
    research_input_bundle: ResearchInputBundle,
    field: str,
    reason: str,
) -> None:
    inputs = _qualified(research_input_bundle)
    first = inputs.symbol_observations[0]
    changed = replace(first, **{field: False})
    _, _, _, candidates = _run(
        replace(
            inputs,
            symbol_observations=(changed, *inputs.symbol_observations[1:]),
        )
    )
    record = next(item for item in candidates.records if item.symbol == first.symbol)
    assert record.selection_status is CandidateSelectionStatus.REJECTED
    assert reason in record.reason_codes
    assert len(candidates.selected) == 5


def test_candidate_population_below_minimum_selects_nothing(
    research_input_bundle: ResearchInputBundle,
) -> None:
    inputs = _qualified(research_input_bundle)
    observations = tuple(
        replace(item, liquidity_eligible=index < 4)
        for index, item in enumerate(inputs.symbol_observations)
    )
    _, _, _, candidates = _run(
        replace(inputs, symbol_observations=observations)
    )
    assert not candidates.selected
    assert "CANDIDATE_POPULATION_INSUFFICIENT" in candidates.reason_codes


def test_unqualified_theme_cannot_be_bypassed_by_b0_b1(
    research_input_bundle: ResearchInputBundle,
) -> None:
    inputs = _qualified(research_input_bundle)
    inputs = replace(
        inputs,
        theme_observations=(_theme("theme-a", -0.10),),
    )

    _, _, _, candidates = _run(inputs)

    assert not candidates.selected
    assert all(
        "THEME_ROTATION_NOT_QUALIFIED" in item.reason_codes
        for item in candidates.records
    )


def test_missing_theme_membership_has_explicit_reconciliation(
    research_input_bundle: ResearchInputBundle,
) -> None:
    inputs = _qualified(research_input_bundle)
    missing_symbol = inputs.universe_snapshot.member_symbols[0]
    inputs = replace(
        inputs,
        theme_memberships=tuple(
            item
            for item in inputs.theme_memberships
            if item.symbol != missing_symbol
        ),
    )

    _, _, _, candidates = _run(inputs)

    record = next(
        item for item in candidates.records if item.symbol == missing_symbol
    )
    assert (
        record.selection_status
        is CandidateSelectionStatus.DATA_INSUFFICIENT
    )
    assert record.reason_codes == ("THEME_MEMBERSHIP_MISSING",)
    assert len(candidates.records) == len(
        inputs.universe_snapshot.member_symbols
    )


def test_ineligible_symbol_is_rejected_without_silent_drop(
    research_input_bundle: ResearchInputBundle,
) -> None:
    inputs = _qualified(research_input_bundle)
    first = inputs.eligibility_snapshot.records[0]
    eligibility = replace(
        inputs.eligibility_snapshot,
        records=(
            replace(
                first,
                status=TradingEligibilityStatus.INELIGIBLE,
                reasons=("POLICY_INELIGIBLE",),
            ),
            *inputs.eligibility_snapshot.records[1:],
        ),
    )

    _, _, _, candidates = _run(
        replace(inputs, eligibility_snapshot=eligibility)
    )

    record = next(
        item for item in candidates.records if item.symbol == first.symbol
    )
    assert record.selection_status is CandidateSelectionStatus.REJECTED
    assert record.reason_codes == ("ELIGIBILITY_INELIGIBLE",)
    assert len(candidates.records) == len(
        inputs.universe_snapshot.member_symbols
    )
