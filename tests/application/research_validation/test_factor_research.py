from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    FactorFamily,
    ResearchFactorExposure,
    ResearchPanelEnrichment,
)
from market_regime_alpha.application.research_validation.factor_research import (
    FactorScoringRole,
    analyze_factor_deduplication,
    build_factor_research_catalog,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


NOW = datetime(2026, 8, 10, tzinfo=UTC)


def _reference(name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        "FEATURE_ARTIFACT_V2",
        ArtifactId(name),
        canonical_hash({"name": name}),
    )


def _exposure(
    symbol: str, factor_id: str, value: str, reference: ValidationArtifactReference
) -> ResearchFactorExposure:
    return ResearchFactorExposure(
        symbol=symbol,
        family=FactorFamily.PRICE_ACTION,
        factor_id=factor_id,
        timeframe="DAILY",
        raw_numeric=Decimal(value),
        raw_text=None,
        normalized_exposure=None,
        model_contribution=None,
        gate_result=None,
        missingness=(),
        available_at=NOW,
        source_reference=reference,
        source_value_path=f"values.{factor_id}",
    )


def test_factor_catalog_and_dedup_preserve_lineage_without_alpha_claim() -> None:
    left = _reference("feature-left")
    right = _reference("feature-right")
    exposures = tuple(
        sorted(
            (
                *(
                    _exposure(symbol, "left", str(index), left)
                    for index, symbol in enumerate(
                        ("000001.SZ", "000002.SZ", "000003.SZ"), start=1
                    )
                ),
                *(
                    _exposure(symbol, "right", str(index * 2), right)
                    for index, symbol in enumerate(
                        ("000001.SZ", "000002.SZ", "000003.SZ"), start=1
                    )
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
    )
    panel_reference = ValidationArtifactReference(
        "RESEARCH_PANEL_V2",
        ArtifactId("factor-panel"),
        canonical_hash({"panel": 1}),
    )
    enrichment = ResearchPanelEnrichment.create(
        panel_reference=panel_reference,
        exposures=exposures,
        extracted_at=NOW,
    )

    catalog = build_factor_research_catalog(
        enrichment=enrichment, created_at=NOW
    )
    report = analyze_factor_deduplication(
        enrichment=enrichment,
        catalog=catalog,
        analyzed_at=NOW,
    )

    assert {item.factor_id for item in catalog.definitions} == {"left", "right"}
    assert all(
        item.missing_policy == "EXPLICIT_MISSING_NO_IMPUTATION"
        and item.normalization_policy == "NOT_APPLIED"
        and item.scoring_role is FactorScoringRole.DIAGNOSTIC_ONLY
        for item in catalog.definitions
    )
    assert "ENGINEERING_DEFAULT_NOT_ECONOMIC_TRUTH" in catalog.limitations
    assert report.evaluated_pair_count == 1
    assert report.estimable_pair_count == 1
    assert len(report.high_correlation_pairs) == 1
    assert report.high_correlation_pairs[0].correlation == Decimal("1")
    assert "CORRELATION_IS_NOT_AUTOMATIC_FACTOR_DELETION" in report.limitations
