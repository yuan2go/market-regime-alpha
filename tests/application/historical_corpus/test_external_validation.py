from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from market_regime_alpha.application.historical_corpus.alpha_correctness import (
    AlphaCorrectnessStatus,
)
from market_regime_alpha.application.historical_corpus.external_validation import (
    ExternalValidationObservation,
    FrozenAlphaHypothesis,
    FrozenExternalValidationExperiment,
    ValidationDimension,
    ValidationScope,
    evaluate_external_validation,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId


def _ref(kind: str, value: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(value),
        "sha256:" + value[-1] * 64,
    )


def _hypothesis() -> FrozenAlphaHypothesis:
    return FrozenAlphaHypothesis.create(
        factor_directions=(
            ("intraday_return_to_decision_time", "HIGHER_IS_BETTER"),
            ("price_vs_vwap_return", "HIGHER_IS_BETTER"),
            ("vwap_slope", "HIGHER_IS_BETTER"),
        ),
        candidate_scoring="EQUAL_WEIGHT_RANK_PERCENTILE",
        decision_time_policy="14:55_ASIA_SHANGHAI",
        target_reference=_ref("OUTCOME_TARGET", "target-a"),
        top_k=3,
        cost_assumption=Decimal("0.001"),
        minimum_effect_retention=Decimal("0.5"),
        minimum_coverage=Decimal("0.8"),
    )


def _scope(period: str, universe: str, provider: str) -> ValidationScope:
    return ValidationScope(
        temporal_partition=period,
        universe_reference=_ref("UNIVERSE", universe),
        provider_reference=_ref("PROVIDER", provider),
    )


def test_external_experiment_freezes_hypothesis_and_one_dimension() -> None:
    experiment = FrozenExternalValidationExperiment.create(
        hypothesis=_hypothesis(),
        correctness_evidence_reference=_ref("ALPHA_CORRECTNESS", "proof-a"),
        correctness_status=AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED,
        discovery_scope=_scope("2025-H1", "universe-a", "provider-a"),
        validation_scope=_scope("2025-H2", "universe-a", "provider-a"),
        dimension=ValidationDimension.TEMPORAL_VALIDATION,
        random_seed=20260819,
    )

    assert experiment.experiment_hash.startswith("sha256:")
    assert experiment.hypothesis.minimum_effect_retention == Decimal("0.5")


def test_external_experiment_rejects_dimension_confounding() -> None:
    with pytest.raises(ValueError, match="exactly the declared validation dimension"):
        FrozenExternalValidationExperiment.create(
            hypothesis=_hypothesis(),
            correctness_evidence_reference=_ref("ALPHA_CORRECTNESS", "proof-a"),
            correctness_status=AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED,
            discovery_scope=_scope("2025-H1", "universe-a", "provider-a"),
            validation_scope=_scope("2025-H2", "universe-b", "provider-a"),
            dimension=ValidationDimension.TEMPORAL_VALIDATION,
            random_seed=20260819,
        )


def test_external_experiment_rejects_uncorrected_hypothesis() -> None:
    with pytest.raises(ValueError, match="correctness-supported"):
        FrozenExternalValidationExperiment.create(
            hypothesis=_hypothesis(),
            correctness_evidence_reference=_ref("ALPHA_CORRECTNESS", "proof-a"),
            correctness_status=AlphaCorrectnessStatus.PARTIALLY_REPRODUCED,
            discovery_scope=_scope("2025-H1", "universe-a", "provider-a"),
            validation_scope=_scope("2025-H2", "universe-a", "provider-a"),
            dimension=ValidationDimension.TEMPORAL_VALIDATION,
            random_seed=20260819,
        )


def test_external_evaluation_preserves_pit_oos_ceiling_and_frozen_thresholds() -> None:
    experiment = FrozenExternalValidationExperiment.create(
        hypothesis=_hypothesis(),
        correctness_evidence_reference=_ref("ALPHA_CORRECTNESS", "proof-a"),
        correctness_status=AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED,
        discovery_scope=_scope("2025-H1", "universe-a", "provider-a"),
        validation_scope=_scope("2025-H2", "universe-a", "provider-a"),
        dimension=ValidationDimension.TEMPORAL_VALIDATION,
        random_seed=20260819,
    )
    observations = tuple(
        ExternalValidationObservation(
            session=date(2026, 1, day),
            symbol=f"S{index}",
            score=Decimal(index),
            target_return=Decimal(index - 2) / Decimal("100"),
            gross_return=Decimal(index - 2) / Decimal("100"),
            cost_return=Decimal("0.001"),
            capacity=Decimal("1000000"),
        )
        for day in range(2, 10)
        for index in range(5)
    )

    result = evaluate_external_validation(
        experiment,
        observations=observations,
        expected_population=40,
        discovery_rank_ic=Decimal("1"),
        pit_complete=False,
        free_data=True,
    )

    assert result.coverage == Decimal("1")
    assert result.rank_ic == Decimal("1")
    assert result.effect_retention == Decimal("1")
    assert result.external_validation_classification == "EXTERNAL_VALIDATION"
    assert result.formal_oos is False
    assert "PIT_INCOMPLETE" in result.limitations
    assert result.thresholds_reference == experiment.hypothesis.reference
