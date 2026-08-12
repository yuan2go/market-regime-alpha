from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.strategy_shadow.decision_attribution import (
    AttributionDimension,
    AttributionObservation,
    AttributionValueStatus,
    DiagnosisOutcome,
    build_decision_chain_attribution,
    diagnose_research_outcome,
    freeze_diagnosis_with_experiment,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from tests.application.research_validation.test_formal_protocol import (
    _formal_protocol,
)


NOW = datetime(2026, 8, 12, tzinfo=UTC)


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind, ArtifactId(name), canonical_hash({"name": name})
    )


def _observations() -> tuple[AttributionObservation, ...]:
    return tuple(
        AttributionObservation(
            dimension=dimension,
            key=f"{dimension.value.lower()}-slice",
            status=AttributionValueStatus.AVAILABLE,
            diagnostic_value=Decimal(index) / Decimal("100"),
            source_references=(
                _reference("DIAGNOSTIC_SOURCE", f"source-{index}"),
            ),
            reason_codes=("DESCRIPTIVE_DIAGNOSTIC_ONLY",),
        )
        for index, dimension in enumerate(AttributionDimension, start=1)
    )


def test_decision_chain_requires_every_layer_and_never_claims_causality() -> None:
    attribution = build_decision_chain_attribution(
        outcome_reference=_reference("STRATEGY_ECONOMICS_RESULT", "outcome"),
        observations=_observations(),
        created_at=NOW,
    )

    assert {item.dimension for item in attribution.observations} == set(
        AttributionDimension
    )
    assert attribution.causal_claim is False
    assert "STRUCTURED_DIAGNOSTIC_NOT_CAUSAL" in attribution.limitations

    with pytest.raises(ValueError, match="every decision-chain dimension"):
        build_decision_chain_attribution(
            outcome_reference=_reference(
                "STRATEGY_ECONOMICS_RESULT", "outcome-incomplete"
            ),
            observations=_observations()[:-1],
            created_at=NOW,
        )


def test_feedback_requires_a_new_frozen_experiment_before_execution() -> None:
    attribution = build_decision_chain_attribution(
        outcome_reference=_reference("STRATEGY_ECONOMICS_RESULT", "outcome-2"),
        observations=_observations(),
        created_at=NOW,
    )
    experiment = _formal_protocol().experiment_definition
    assert experiment is not None
    diagnosis = diagnose_research_outcome(
        attribution=attribution,
        outcome=DiagnosisOutcome.INCONCLUSIVE,
        selected_slices=(("MARKET_REGIME", "market_regime-slice"),),
        diagnosis="Regime slice did not add stable incremental lift.",
        proposed_research_question=experiment.research_question,
        proposed_hypothesis=experiment.hypothesis,
        primary_research_change="Replace regime interaction with a frozen null comparison.",
        diagnosed_at=NOW,
    )

    assert diagnosis.ready_for_experiment is False
    assert diagnosis.next_experiment_reference is None

    frozen = freeze_diagnosis_with_experiment(
        diagnosis=diagnosis,
        experiment_definition=experiment,
        frozen_at=NOW,
    )

    assert frozen.ready_for_experiment is True
    assert frozen.next_experiment_reference is not None
    assert frozen.diagnosis_id != diagnosis.diagnosis_id


def test_feedback_rejects_after_the_fact_hypothesis_drift() -> None:
    attribution = build_decision_chain_attribution(
        outcome_reference=_reference("STRATEGY_ECONOMICS_RESULT", "outcome-3"),
        observations=_observations(),
        created_at=NOW,
    )
    experiment = _formal_protocol().experiment_definition
    assert experiment is not None
    diagnosis = diagnose_research_outcome(
        attribution=attribution,
        outcome=DiagnosisOutcome.FAILURE,
        selected_slices=(("SIGNAL", "signal-slice"),),
        diagnosis="Signal layer had no incremental lift.",
        proposed_research_question="A different question",
        proposed_hypothesis="A different hypothesis",
        primary_research_change="Remove one duplicated Signal threshold.",
        diagnosed_at=NOW,
    )

    with pytest.raises(ValueError, match="question/hypothesis"):
        freeze_diagnosis_with_experiment(
            diagnosis=diagnosis,
            experiment_definition=experiment,
            frozen_at=NOW,
        )
