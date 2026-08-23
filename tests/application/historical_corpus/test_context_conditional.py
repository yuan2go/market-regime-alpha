from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.historical_corpus.context_conditional import (
    ContextConditionalEvaluation,
    ContextDefinition,
    ContextKind,
    ContextObservation,
    ContextResearchRole,
    evaluate_context_conditioning,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalResearchEvidence,
    ResearchFinding,
    ResearchStatement,
    ResearchStatementKind,
)
from market_regime_alpha.application.research_validation.common import ValidationArtifactReference
from market_regime_alpha.core.identity import ArtifactId


def _ref(kind: str, value: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(kind, ArtifactId(value), "sha256:" + "a" * 64)


TARGET = _ref("OUTCOME_TARGET", "context-target")


def _external_evidence() -> HistoricalResearchEvidence:
    return HistoricalResearchEvidence.create(
        run_id=ArtifactId("external-run"),
        command_hash="sha256:" + "b" * 64,
        experiment_reference=_ref("RESEARCH_EXPERIMENT_DEFINITION", "external-exp"),
        evidence_kind=HistoricalEvidenceKind.EXTERNAL_VALIDATION,
        research_question="Does the Alpha retain effect?",
        classification=ResearchFinding.POSITIVE,
        rationale="Synthetic supported owner evidence.",
        source_references=(_ref("RESEARCH_PANEL", "panel"),),
        metrics=(),
        payload={
            "qualification_status": "SUPPORTED",
            "validated_factors": [["alpha_factor", "HIGHER_IS_BETTER"]],
            "experiment": {
                "hypothesis": {"target_reference": TARGET.to_canonical_dict()}
            },
        },
        created_at=datetime(2026, 8, 21, tzinfo=UTC),
        statements=(ResearchStatement(ResearchStatementKind.FACT, "Owner test."),),
    )


PANEL = _ref("RESEARCH_PANEL", "context-panel")


def _definition(
    *,
    context_id: str,
    kind: ContextKind,
    role: ContextResearchRole,
    expected_population: int,
) -> ContextDefinition:
    return ContextDefinition.create(
        context_id=context_id,
        kind=kind,
        role=role,
        public_observable_proxy=True,
        research_panel_references=(PANEL,),
        top_k=2,
        expected_population=expected_population,
        effect_threshold=Decimal("0.02"),
        alpha_evidence=_external_evidence(),
    )


def test_session_level_context_cannot_be_packaged_as_within_session_interaction() -> None:
    definition = _definition(
        context_id="MARKET_REGIME",
        kind=ContextKind.SESSION_LEVEL_CONTEXT,
        role=ContextResearchRole.CONDITIONAL_PERFORMANCE,
        expected_population=2,
    )
    observations = (
        ContextObservation(date(2026, 1, 2), "A", Decimal("1"), Decimal(".01"), "BULL", Decimal("1"), PANEL, TARGET),
        ContextObservation(date(2026, 1, 2), "B", Decimal("2"), Decimal(".02"), "BEAR", Decimal("0"), PANEL, TARGET),
    )

    with pytest.raises(ValueError, match="constant within each session"):
        evaluate_context_conditioning(definition, observations=observations)


def test_session_context_evaluates_performance_across_sessions_only() -> None:
    definition = _definition(
        context_id="MARKET_REGIME",
        kind=ContextKind.SESSION_LEVEL_CONTEXT,
        role=ContextResearchRole.CONDITIONAL_PERFORMANCE,
        expected_population=16,
    )
    observations = tuple(
        ContextObservation(
            date(2026, 1, day),
            f"S{index}",
            Decimal(index),
            Decimal(index if label == "BULL" else -index),
            label,
            Decimal("1") if label == "BULL" else Decimal("-1"),
            PANEL,
            TARGET,
        )
        for day, label in ((2, "BULL"), (3, "BEAR"), (4, "BULL"), (5, "BEAR"))
        for index in range(4)
    )

    result = evaluate_context_conditioning(definition, observations=observations)

    assert result.interaction_effect is not None
    assert result.incremental_information is None
    assert result.status in {"AMPLIFIER", "SUPPRESSOR", "UNSTABLE"}
    assert {item.context_value for item in result.slices} == {"BEAR", "BULL"}
    assert ContextConditionalEvaluation.from_canonical_dict(
        result.to_canonical_dict()
    ) == result


def test_cross_sectional_context_supports_interaction_and_incremental_information() -> None:
    definition = _definition(
        context_id="LIQUIDITY",
        kind=ContextKind.CROSS_SECTIONAL_CONTEXT,
        role=ContextResearchRole.INTERACTION,
        expected_population=20,
    )
    observations = tuple(
        ContextObservation(
            date(2026, 1, day),
            f"S{index}",
            Decimal(index),
            Decimal(index * (index + 1)),
            "HIGH" if index >= 2 else "LOW",
            Decimal(index),
            PANEL,
            TARGET,
        )
        for day in range(2, 7)
        for index in range(4)
    )

    result = evaluate_context_conditioning(definition, observations=observations)

    assert result.interaction_effect is not None
    assert result.incremental_information is not None
    assert result.status != "NOT_ESTIMABLE"


def test_session_level_capital_proxy_cannot_be_declared_cross_sectional() -> None:
    with pytest.raises(ValueError, match="owner role is fixed"):
        _definition(
            context_id="CAPITAL_PUBLIC_PROXY",
            kind=ContextKind.CROSS_SECTIONAL_CONTEXT,
            role=ContextResearchRole.INTERACTION,
            expected_population=16,
        )


def test_cross_sectional_liquidity_without_variation_is_not_estimable() -> None:
    definition = _definition(
        context_id="LIQUIDITY",
        kind=ContextKind.CROSS_SECTIONAL_CONTEXT,
        role=ContextResearchRole.INTERACTION,
        expected_population=16,
    )
    observations = tuple(
        ContextObservation(
            date(2026, 1, day),
            f"S{index}",
            Decimal(index),
            Decimal(index),
            "SAME",
            Decimal("1"),
            PANEL,
            TARGET,
        )
        for day in range(2, 6)
        for index in range(4)
    )

    result = evaluate_context_conditioning(definition, observations=observations)

    assert result.status == "NOT_ESTIMABLE"
    assert "WITHIN_SESSION_CONTEXT_VARIATION_REQUIRED" in result.limitations


def test_session_context_with_identical_alpha_effect_is_neutral() -> None:
    definition = _definition(
        context_id="VOLATILITY_REGIME",
        kind=ContextKind.SESSION_LEVEL_CONTEXT,
        role=ContextResearchRole.CONDITIONAL_PERFORMANCE,
        expected_population=32,
    )
    observations = tuple(
        ContextObservation(
            date(2026, 2, day),
            f"S{index}",
            Decimal(index),
            Decimal(index),
            "HIGH" if day % 2 else "LOW",
            Decimal(day % 2),
            PANEL,
            TARGET,
        )
        for day in range(2, 10)
        for index in range(4)
    )

    result = evaluate_context_conditioning(definition, observations=observations)

    assert result.status == "NEUTRAL"
    assert result.interaction_effect == Decimal("0")
