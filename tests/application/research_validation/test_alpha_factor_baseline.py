from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    FactorFamily,
    ResearchFactorExposure,
    ResearchPanelEnrichment,
)
from market_regime_alpha.application.research_validation.factor_research import (
    AlphaFactorKind,
    assess_alpha_factor_baseline,
    alpha_factor_baseline_specifications,
    robust_cross_sectional_normalize,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


NOW = datetime(2026, 8, 12, 6, 30, tzinfo=UTC)


def _reference(name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        "FEATURE_ARTIFACT_V2",
        ArtifactId(name),
        canonical_hash({"name": name}),
    )


def _exposure(
    symbol: str,
    family: FactorFamily,
    factor_id: str,
    value: Decimal,
    *,
    available_at: datetime = NOW,
) -> ResearchFactorExposure:
    return ResearchFactorExposure(
        symbol=symbol,
        family=family,
        factor_id=factor_id,
        timeframe="DAILY",
        raw_numeric=value,
        raw_text=None,
        normalized_exposure=None,
        model_contribution=None,
        gate_result="AVAILABLE",
        missingness=(),
        available_at=available_at,
        source_reference=_reference(f"{symbol}-{factor_id}"),
        source_value_path=f"values.{factor_id}",
    )


def test_alpha_factor_baseline_reports_actual_coverage_without_inventing_values() -> None:
    panel = ResearchPanelEnrichment.create(
        panel_reference=ValidationArtifactReference(
            "RESEARCH_PANEL_V2",
            ArtifactId("alpha-factor-panel"),
            canonical_hash({"panel": 1}),
        ),
        exposures=tuple(
            sorted(
                (
                    _exposure(
                        "000001.SZ",
                        FactorFamily.PRICE_ACTION,
                        "technical.price_action.v1.return_5",
                        Decimal("0.05"),
                    ),
                    _exposure(
                        "000002.SZ",
                        FactorFamily.VOLUME,
                        "technical.volume_amount_structure.v1.volume_expansion",
                        Decimal("1.4"),
                    ),
                    _exposure(
                        "000003.SZ",
                        FactorFamily.THEME,
                        "state.theme.strength",
                        Decimal("0.7"),
                    ),
                ),
                key=lambda item: (
                    item.symbol,
                    item.family.value,
                    item.factor_id,
                    item.timeframe or "",
                    item.source_value_path,
                ),
            )
        ),
        extracted_at=NOW,
    )

    result = assess_alpha_factor_baseline(
        enrichment=panel,
        decision_time=NOW,
        assessed_at=NOW,
    )

    coverage = {item.kind: item for item in result.coverage}
    assert coverage[AlphaFactorKind.PRICE_MOMENTUM].available_value_count == 1
    assert coverage[AlphaFactorKind.VOLUME_AMOUNT_EXPANSION].available_value_count == 1
    assert coverage[AlphaFactorKind.THEME_STRENGTH].available_value_count == 1
    assert coverage[AlphaFactorKind.DRAWDOWN].available_value_count == 0
    assert "EXPLORATORY_NOT_FORMAL_ALPHA_EVIDENCE" in result.limitations
    assert len(alpha_factor_baseline_specifications()) == len(AlphaFactorKind)


def test_alpha_factor_baseline_rejects_future_available_feature() -> None:
    future = _exposure(
        "000001.SZ",
        FactorFamily.PRICE_ACTION,
        "technical.price_action.v1.return_5",
        Decimal("0.05"),
        available_at=NOW + timedelta(seconds=1),
    )
    panel = ResearchPanelEnrichment.create(
        panel_reference=ValidationArtifactReference(
            "RESEARCH_PANEL_V2",
            ArtifactId("future-factor-panel"),
            canonical_hash({"panel": 2}),
        ),
        exposures=(future,),
        extracted_at=NOW + timedelta(seconds=1),
    )

    with pytest.raises(ValueError, match="after DecisionTime"):
        assess_alpha_factor_baseline(
            enrichment=panel,
            decision_time=NOW,
            assessed_at=NOW + timedelta(seconds=2),
        )


def test_robust_cross_sectional_normalization_is_deterministic_and_bounded() -> None:
    values = {
        "A": Decimal("1"),
        "B": Decimal("2"),
        "C": Decimal("3"),
        "D": Decimal("1000"),
    }

    first = robust_cross_sectional_normalize(values)
    second = robust_cross_sectional_normalize(dict(reversed(tuple(values.items()))))

    assert first == second
    assert tuple(first) == ("A", "B", "C", "D")
    assert all(value.is_finite() for value in first.values())
