from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalResearchEvidence,
    ResearchFinding,
    ResearchStatement,
    ResearchStatementKind,
)
from market_regime_alpha.candidates.policy import (
    CandidateComparisonProtocol,
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


DATASET = _ref("RESEARCH_PANEL_DATASET", "dataset-a")


def _evidence(
    kind: HistoricalEvidenceKind, payload: dict[str, object]
) -> HistoricalResearchEvidence:
    return HistoricalResearchEvidence.create(
        run_id=ArtifactId(f"{kind.value.lower()}-run"),
        command_hash="sha256:" + "d" * 64,
        experiment_reference=_ref("RESEARCH_EXPERIMENT_DEFINITION", f"{kind.value.lower()}-exp-a"),
        evidence_kind=kind,
        research_question="Synthetic owner admission test.",
        classification=ResearchFinding.POSITIVE,
        rationale="Supported for an engineering unit test.",
        source_references=(DATASET,),
        metrics=(),
        payload=payload,
        created_at=datetime(2026, 8, 21, tzinfo=UTC),
        statements=(ResearchStatement(ResearchStatementKind.FACT, "Owner test."),),
    )


def _challenger() -> CandidatePolicyDefinition:
    return CandidatePolicyDefinition.create(
        role=CandidatePolicyRole.CHALLENGER,
        policy_version="alpha-correctness-external-v1",
        validated_factors=(
            ValidatedFactorDefinition(
                "intraday_return_to_decision_time",
                "HIGHER_IS_BETTER",
                Decimal("1"),
                _evidence(
                    HistoricalEvidenceKind.EXTERNAL_VALIDATION,
                    {
                        "qualification_status": "SUPPORTED",
                        "validated_factors": [
                            [
                                "intraday_return_to_decision_time",
                                "HIGHER_IS_BETTER",
                            ]
                        ],
                    },
                ),
            ),
        ),
        context_adjustments=(
            ContextAdjustmentDefinition(
                "LIQUIDITY",
                Decimal("0.1"),
                "SCORE_ADJUSTMENT",
                _evidence(
                    HistoricalEvidenceKind.CONTEXT_CONDITIONAL,
                    {"status": "AMPLIFIER"},
                ),
            ),
        ),
        top_k=1,
        minimum_liquidity=Decimal("100"),
        dataset_reference=DATASET,
    )


def test_challenger_factor_must_be_named_by_external_validation_evidence() -> None:
    evidence = _evidence(
        HistoricalEvidenceKind.EXTERNAL_VALIDATION,
        {
            "qualification_status": "SUPPORTED",
            "validated_factors": [["vwap_slope", "HIGHER_IS_BETTER"]],
        },
    )

    with pytest.raises(ValueError, match="outside External Validation"):
        ValidatedFactorDefinition(
            "intraday_return_to_decision_time",
            "HIGHER_IS_BETTER",
            Decimal("1"),
            evidence,
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
        incumbent_hard_integrity_eligible=True,
        incumbent_hard_gate_failure_reasons=(),
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
        dataset_reference=DATASET,
    )
    inputs = (_input("A", Decimal("2")), _input("B", Decimal("1")))
    incumbent_result = evaluate_candidate_policy(incumbent, inputs)
    challenger_result = evaluate_candidate_policy(_challenger(), inputs)
    comparison = compare_candidate_policies(
        incumbent_result,
        challenger_result,
        protocol=CandidateComparisonProtocol.create(
            dataset_reference=DATASET,
            target_reference=_ref("OUTCOME_TARGET", "target-a"),
            cost_assumption=Decimal("0.001"),
        ),
        realized_returns={
            (date(2026, 1, 2), "A"): Decimal(".02"),
            (date(2026, 1, 2), "B"): Decimal(".01"),
        },
    )

    assert incumbent.policy_id != _challenger().policy_id
    assert incumbent_result.policy_reference != challenger_result.policy_reference
    assert comparison.incumbent_coverage == Decimal("1")
    assert comparison.challenger_selection_count == 1


def test_challenger_top_k_boundary_is_identity_neutral() -> None:
    evaluation = evaluate_candidate_policy(
        _challenger(),
        (_input("A", Decimal("1")), _input("B", Decimal("1"))),
    )

    assert {item.rank for item in evaluation.records} == {1}
    assert {item.selection_weight for item in evaluation.records} == {
        Decimal("0.5")
    }
    assert all(item.selection_status == "SELECTED" for item in evaluation.records)


def test_incumbent_projection_does_not_reapply_challenger_liquidity_threshold() -> None:
    incumbent = CandidatePolicyDefinition.create(
        role=CandidatePolicyRole.INCUMBENT,
        policy_version="incumbent-v1",
        validated_factors=(),
        context_adjustments=(),
        top_k=1,
        minimum_liquidity=Decimal("100"),
        dataset_reference=DATASET,
    )
    result = evaluate_candidate_policy(
        incumbent,
        (_input("A", Decimal("1"), liquidity=Decimal("1")),),
    )

    assert result.records[0].hard_integrity_eligible is True
    assert "MINIMUM_LIQUIDITY_FAILED" not in result.records[0].reason_codes
