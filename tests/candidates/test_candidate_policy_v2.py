from __future__ import annotations

from datetime import date
from decimal import Decimal

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.candidates.policy import (
    CandidatePolicyDefinition,
    CandidatePolicyInput,
    CandidatePolicyRole,
    ContextAdjustmentDefinition,
    ValidatedFactorDefinition,
    compare_candidate_policies,
    evaluate_candidate_policy,
)
from market_regime_alpha.core.identity import ArtifactId


def _ref(kind: str, value: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(kind, ArtifactId(value), "sha256:" + value[-1] * 64)


def _challenger() -> CandidatePolicyDefinition:
    return CandidatePolicyDefinition.create(
        role=CandidatePolicyRole.CHALLENGER,
        policy_version="alpha-correctness-external-v1",
        validated_factors=(
            ValidatedFactorDefinition(
                "intraday_return_to_decision_time",
                "HIGHER_IS_BETTER",
                Decimal("1"),
                _ref("EXTERNAL_VALIDATION_EVIDENCE", "external-a"),
                True,
            ),
        ),
        context_adjustments=(
            ContextAdjustmentDefinition(
                "LIQUIDITY",
                Decimal("0.1"),
                "SCORE_ADJUSTMENT",
                _ref("CONTEXT_CONDITIONAL_EVIDENCE", "context-a"),
                "AMPLIFIER",
            ),
        ),
        top_k=1,
        minimum_liquidity=Decimal("100"),
    )


def _input(symbol: str, factor: Decimal | None, *, liquidity: Decimal = Decimal("1000")) -> CandidatePolicyInput:
    return CandidatePolicyInput(
        session=date(2026, 1, 2),
        symbol=symbol,
        universe_eligible=True,
        tradable=True,
        suspended=False,
        data_integrity=True,
        required_history=True,
        pit_correct=True,
        liquidity=liquidity,
        trading_restrictions_satisfied=True,
        factor_values={"intraday_return_to_decision_time": factor},
        context_values={"LIQUIDITY": Decimal("1")},
        incumbent_score=Decimal("0.5"),
        incumbent_selected=False,
        incumbent_factor_contributions={"legacy": Decimal("0.5")},
    )


def test_universal_integrity_is_separate_from_factor_specific_availability() -> None:
    evaluation = evaluate_candidate_policy(_challenger(), (_input("A", None),))
    record = evaluation.records[0]

    assert record.hard_integrity_eligible is True
    assert record.factor_available is False
    assert record.selection_status == "FACTOR_UNAVAILABLE"
    assert record.hard_gate_failure_reasons == ()
    assert "FACTOR_MISSING:intraday_return_to_decision_time" in record.reason_codes


def test_hard_integrity_rejects_illegal_sample_without_alpha_claim() -> None:
    evaluation = evaluate_candidate_policy(
        _challenger(),
        (_input("A", Decimal("1"), liquidity=Decimal("10")),),
    )
    record = evaluation.records[0]

    assert record.hard_integrity_eligible is False
    assert record.alpha_score is None
    assert record.hard_gate_failure_reasons == ("MINIMUM_LIQUIDITY_FAILED",)


def test_challenger_explains_factor_contribution_context_and_selection() -> None:
    evaluation = evaluate_candidate_policy(
        _challenger(),
        (_input("A", Decimal("2")), _input("B", Decimal("1"))),
    )
    selected = next(item for item in evaluation.records if item.symbol == "A")

    assert selected.factor_contributions == {
        "intraday_return_to_decision_time": Decimal("1")
    }
    assert selected.alpha_score == Decimal("1")
    assert selected.context_adjustments == {"LIQUIDITY": Decimal("0.1")}
    assert selected.final_score == Decimal("1.1")
    assert selected.rank == 1
    assert selected.selection_status == "SELECTED"


def test_incumbent_and_challenger_coexist_with_distinct_frozen_identity() -> None:
    incumbent = CandidatePolicyDefinition.create(
        role=CandidatePolicyRole.INCUMBENT,
        policy_version="incumbent-v1",
        validated_factors=(),
        context_adjustments=(),
        top_k=1,
        minimum_liquidity=Decimal("100"),
    )
    inputs = (_input("A", Decimal("2")), _input("B", Decimal("1")))
    incumbent_result = evaluate_candidate_policy(incumbent, inputs)
    challenger_result = evaluate_candidate_policy(_challenger(), inputs)
    comparison = compare_candidate_policies(
        incumbent_result,
        challenger_result,
        realized_returns={
            (date(2026, 1, 2), "A"): Decimal(".02"),
            (date(2026, 1, 2), "B"): Decimal(".01"),
        },
    )

    assert incumbent.policy_id != _challenger().policy_id
    assert incumbent_result.policy_reference != challenger_result.policy_reference
    assert comparison.incumbent_coverage == Decimal("1")
    assert comparison.challenger_selection_count == 1
