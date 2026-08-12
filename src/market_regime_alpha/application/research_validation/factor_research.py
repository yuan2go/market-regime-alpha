"""Versioned factor metadata and conservative redundancy diagnostics.

This module describes values already copied by canonical Factor Extraction.  It
does not create a second feature implementation or automatically delete a
factor.  Correlation is exploratory evidence only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from math import sqrt
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.application.canonical_lifecycle._immutable_io import (
    publish_immutable_text,
)
from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ResearchEvidenceAuthority,
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    FactorFamily,
    ResearchFactorExposure,
    ResearchPanelEnrichment,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)


class FactorScoringRole(str, Enum):
    MODEL_CONTRIBUTION_RECORDED = "MODEL_CONTRIBUTION_RECORDED"
    GATE_OR_DIAGNOSTIC = "GATE_OR_DIAGNOSTIC"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"


class AlphaFactorKind(str, Enum):
    PRICE_MOMENTUM = "PRICE_MOMENTUM"
    SHORT_TERM_REVERSAL = "SHORT_TERM_REVERSAL"
    CROSS_SECTIONAL_RELATIVE_STRENGTH = "CROSS_SECTIONAL_RELATIVE_STRENGTH"
    VOLUME_AMOUNT_EXPANSION = "VOLUME_AMOUNT_EXPANSION"
    VOLUME_PERSISTENCE = "VOLUME_PERSISTENCE"
    LIQUIDITY = "LIQUIDITY"
    VOLATILITY = "VOLATILITY"
    DRAWDOWN = "DRAWDOWN"
    TREND = "TREND"
    VWAP_DISTANCE = "VWAP_DISTANCE"
    MARKET_BREADTH_CONTEXT = "MARKET_BREADTH_CONTEXT"
    ETF_RELATIVE_STRENGTH = "ETF_RELATIVE_STRENGTH"
    THEME_STRENGTH = "THEME_STRENGTH"
    CAPITAL_PROXY = "CAPITAL_PROXY"


@dataclass(frozen=True, slots=True)
class AlphaFactorSpecification:
    kind: AlphaFactorKind
    allowed_families: tuple[FactorFamily, ...]
    factor_id_tokens: tuple[str, ...]
    normalization_policy: str
    missing_policy: str = "EXPLICIT_MISSING_NO_IMPUTATION"
    availability_policy: str = "AVAILABLE_AT_OR_BEFORE_DECISION_TIME"

    def __post_init__(self) -> None:
        if self.allowed_families != tuple(
            sorted(set(self.allowed_families), key=lambda item: item.value)
        ):
            raise ValueError("Alpha factor families must be unique and sorted")
        if self.factor_id_tokens != tuple(sorted(set(self.factor_id_tokens))):
            raise ValueError("Alpha factor identity tokens must be unique and sorted")

    def matches(self, exposure: ResearchFactorExposure) -> bool:
        identity = exposure.factor_id.lower()
        return exposure.family in self.allowed_families and any(
            token in identity for token in self.factor_id_tokens
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "allowed_families": [item.value for item in self.allowed_families],
            "factor_id_tokens": list(self.factor_id_tokens),
            "normalization_policy": self.normalization_policy,
            "missing_policy": self.missing_policy,
            "availability_policy": self.availability_policy,
        }


@dataclass(frozen=True, slots=True)
class AlphaFactorCoverage:
    kind: AlphaFactorKind
    matched_exposure_count: int
    available_value_count: int
    symbol_count: int
    matched_factor_ids: tuple[str, ...]

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "matched_exposure_count": self.matched_exposure_count,
            "available_value_count": self.available_value_count,
            "symbol_count": self.symbol_count,
            "matched_factor_ids": list(self.matched_factor_ids),
        }


@dataclass(frozen=True, slots=True)
class AlphaFactorBaselineAssessment:
    assessment_id: ArtifactId
    assessment_hash: str
    enrichment_reference: ValidationArtifactReference
    specifications: tuple[AlphaFactorSpecification, ...]
    coverage: tuple[AlphaFactorCoverage, ...]
    decision_time: datetime
    assessed_at: datetime
    authority: ResearchEvidenceAuthority
    limitations: tuple[str, ...]
    schema_version: str = "alpha-factor-baseline-assessment/v1"

    def __post_init__(self) -> None:
        require_sha256("assessment_hash", self.assessment_hash)
        if self.authority is not ResearchEvidenceAuthority.EXPLORATORY:
            raise ValueError("Alpha Factor Baseline is exploratory only")
        if canonical_hash(self.identity_payload()) != self.assessment_hash:
            raise ValueError("Alpha Factor Baseline Assessment hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "enrichment_reference": self.enrichment_reference.to_canonical_dict(),
            "specifications": [
                item.to_canonical_dict() for item in self.specifications
            ],
            "coverage": [item.to_canonical_dict() for item in self.coverage],
            "decision_time": timestamp(self.decision_time),
            "assessed_at": timestamp(self.assessed_at),
            "authority": self.authority.value,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class ResearchFactorDefinition:
    factor_key: str
    factor_id: str
    definition_version: str
    family: FactorFamily
    timeframe: str | None
    definition: str
    input_value_paths: tuple[str, ...]
    source_references: tuple[ValidationArtifactReference, ...]
    availability_policy: str
    missing_policy: str
    normalization_policy: str
    scoring_role: FactorScoringRole
    source_information_families: tuple[str, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("factor_key", self.factor_key),
            ("factor_id", self.factor_id),
            ("definition_version", self.definition_version),
            ("definition", self.definition),
            ("availability_policy", self.availability_policy),
            ("missing_policy", self.missing_policy),
            ("normalization_policy", self.normalization_policy),
        ):
            require_text(label, value)
        if self.input_value_paths != tuple(sorted(set(self.input_value_paths))):
            raise ValueError("Factor definition input paths must be unique and sorted")
        if self.source_references != tuple(
            sorted(
                set(self.source_references),
                key=lambda item: (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        ):
            raise ValueError("Factor definition lineage must be unique and sorted")
        if self.source_information_families != tuple(
            sorted(set(self.source_information_families))
        ):
            raise ValueError("Factor information families must be unique and sorted")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "factor_key": self.factor_key,
            "factor_id": self.factor_id,
            "definition_version": self.definition_version,
            "family": self.family.value,
            "timeframe": self.timeframe,
            "definition": self.definition,
            "input_value_paths": list(self.input_value_paths),
            "source_references": [
                item.to_canonical_dict() for item in self.source_references
            ],
            "availability_policy": self.availability_policy,
            "missing_policy": self.missing_policy,
            "normalization_policy": self.normalization_policy,
            "scoring_role": self.scoring_role.value,
            "source_information_families": list(
                self.source_information_families
            ),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> ResearchFactorDefinition:
        raw_paths = value["input_value_paths"]
        raw_sources = value["source_references"]
        raw_families = value["source_information_families"]
        if not isinstance(raw_paths, list) or not isinstance(raw_sources, list):
            raise ValueError("Factor Definition paths and sources must be arrays")
        if not isinstance(raw_families, list):
            raise ValueError("Factor Definition information families must be an array")
        return cls(
            factor_key=str(value["factor_key"]),
            factor_id=str(value["factor_id"]),
            definition_version=str(value["definition_version"]),
            family=FactorFamily(str(value["family"])),
            timeframe=None if value["timeframe"] is None else str(value["timeframe"]),
            definition=str(value["definition"]),
            input_value_paths=tuple(str(item) for item in raw_paths),
            source_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in raw_sources
            ),
            availability_policy=str(value["availability_policy"]),
            missing_policy=str(value["missing_policy"]),
            normalization_policy=str(value["normalization_policy"]),
            scoring_role=FactorScoringRole(str(value["scoring_role"])),
            source_information_families=tuple(str(item) for item in raw_families),
        )


@dataclass(frozen=True, slots=True)
class FactorResearchCatalog:
    catalog_id: ArtifactId
    catalog_hash: str
    enrichment_reference: ValidationArtifactReference
    definitions: tuple[ResearchFactorDefinition, ...]
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "factor-research-catalog/v1"

    def __post_init__(self) -> None:
        require_sha256("catalog_hash", self.catalog_hash)
        if not self.definitions or self.definitions != tuple(
            sorted(self.definitions, key=lambda item: item.factor_key)
        ):
            raise ValueError("Factor catalog definitions must be non-empty and sorted")
        if len({item.factor_key for item in self.definitions}) != len(
            self.definitions
        ):
            raise ValueError("Factor catalog definitions must be unique")
        if canonical_hash(self.identity_payload()) != self.catalog_hash:
            raise ValueError("Factor catalog hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "enrichment_reference": self.enrichment_reference.to_canonical_dict(),
            "definitions": [item.to_canonical_dict() for item in self.definitions],
            "created_at": timestamp(self.created_at),
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "catalog_id": str(self.catalog_id),
            "catalog_hash": self.catalog_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> FactorResearchCatalog:
        raw_definitions = value["definitions"]
        raw_limitations = value["limitations"]
        if not isinstance(raw_definitions, list) or not isinstance(raw_limitations, list):
            raise ValueError("Factor Catalog definitions and limitations must be arrays")
        return cls(
            catalog_id=ArtifactId(str(value["catalog_id"])),
            catalog_hash=str(value["catalog_hash"]),
            enrichment_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["enrichment_reference"])
            ),
            definitions=tuple(
                ResearchFactorDefinition.from_canonical_dict(_mapping(item))
                for item in raw_definitions
            ),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            limitations=tuple(str(item) for item in raw_limitations),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class FactorCorrelationPair:
    left_factor_key: str
    right_factor_key: str
    common_symbol_count: int
    correlation: Decimal
    duplicate_candidate: bool

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "left_factor_key": self.left_factor_key,
            "right_factor_key": self.right_factor_key,
            "common_symbol_count": self.common_symbol_count,
            "correlation": str(self.correlation),
            "duplicate_candidate": self.duplicate_candidate,
        }


@dataclass(frozen=True, slots=True)
class FactorDeduplicationReport:
    report_id: ArtifactId
    report_hash: str
    catalog_reference: ValidationArtifactReference
    enrichment_reference: ValidationArtifactReference
    correlation_threshold: Decimal
    minimum_common_symbols: int
    evaluated_pair_count: int
    estimable_pair_count: int
    high_correlation_pairs: tuple[FactorCorrelationPair, ...]
    analyzed_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "factor-deduplication-report/v1"

    def __post_init__(self) -> None:
        require_sha256("report_hash", self.report_hash)
        if not Decimal("0") < self.correlation_threshold <= Decimal("1"):
            raise ValueError("Factor correlation threshold must be within (0, 1]")
        if self.minimum_common_symbols < 3:
            raise ValueError("Factor de-dup requires at least three common symbols")
        if self.estimable_pair_count > self.evaluated_pair_count:
            raise ValueError("Factor pair counts are invalid")
        if canonical_hash(self.identity_payload()) != self.report_hash:
            raise ValueError("Factor de-dup report hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "catalog_reference": self.catalog_reference.to_canonical_dict(),
            "enrichment_reference": self.enrichment_reference.to_canonical_dict(),
            "correlation_threshold": str(self.correlation_threshold),
            "minimum_common_symbols": self.minimum_common_symbols,
            "evaluated_pair_count": self.evaluated_pair_count,
            "estimable_pair_count": self.estimable_pair_count,
            "high_correlation_pairs": [
                item.to_canonical_dict() for item in self.high_correlation_pairs
            ],
            "analyzed_at": timestamp(self.analyzed_at),
            "limitations": list(self.limitations),
        }


def alpha_factor_baseline_specifications() -> tuple[AlphaFactorSpecification, ...]:
    """Return the small, interpretable factor taxonomy used by Alpha research.

    Specifications select existing canonical exposures.  They deliberately do
    not recompute data or turn missing factor families into synthetic values.
    """

    cross_sectional = "WINSORIZE_1_99_THEN_CROSS_SECTIONAL_ZSCORE_PER_DECISION_TIME"
    temporal = "OWNER_VALUE_OR_FROZEN_ROLLING_NORMALIZATION"
    specs = (
        _alpha_spec(
            AlphaFactorKind.PRICE_MOMENTUM,
            (FactorFamily.MOMENTUM_TREND, FactorFamily.PRICE_ACTION),
            ("momentum", "return_10", "return_3", "return_5"),
            cross_sectional,
        ),
        _alpha_spec(
            AlphaFactorKind.SHORT_TERM_REVERSAL,
            (FactorFamily.PRICE_ACTION,),
            ("return_1", "short_return"),
            cross_sectional,
        ),
        _alpha_spec(
            AlphaFactorKind.CROSS_SECTIONAL_RELATIVE_STRENGTH,
            (FactorFamily.CANDIDATE, FactorFamily.MOMENTUM_TREND),
            ("relative_strength", "rank", "strength"),
            cross_sectional,
        ),
        _alpha_spec(
            AlphaFactorKind.VOLUME_AMOUNT_EXPANSION,
            (FactorFamily.AMOUNT, FactorFamily.VOLUME),
            ("amount_expansion", "amount_ratio", "volume_expansion", "volume_ratio"),
            cross_sectional,
        ),
        _alpha_spec(
            AlphaFactorKind.VOLUME_PERSISTENCE,
            (FactorFamily.AMOUNT, FactorFamily.VOLUME),
            ("amount_persistence", "turnover_persistence", "volume_persistence"),
            cross_sectional,
        ),
        _alpha_spec(
            AlphaFactorKind.LIQUIDITY,
            (FactorFamily.AMOUNT, FactorFamily.LIQUIDITY),
            ("amount_percentile", "median_amount", "turnover_rate"),
            cross_sectional,
        ),
        _alpha_spec(
            AlphaFactorKind.VOLATILITY,
            (FactorFamily.PRICE_ACTION, FactorFamily.VOLATILITY),
            ("high_low_range", "realized_volatility", "volatility"),
            temporal,
        ),
        _alpha_spec(
            AlphaFactorKind.DRAWDOWN,
            (FactorFamily.PRICE_ACTION, FactorFamily.VOLATILITY),
            ("drawdown",),
            temporal,
        ),
        _alpha_spec(
            AlphaFactorKind.TREND,
            (FactorFamily.MA_EMA, FactorFamily.MACD, FactorFamily.MOMENTUM_TREND),
            ("ma_slope", "macd", "price_vs_ema", "price_vs_sma", "trend"),
            cross_sectional,
        ),
        _alpha_spec(
            AlphaFactorKind.VWAP_DISTANCE,
            (FactorFamily.VWAP,),
            ("distance_from_vwap", "price_vs_vwap"),
            cross_sectional,
        ),
        _alpha_spec(
            AlphaFactorKind.MARKET_BREADTH_CONTEXT,
            (FactorFamily.MARKET_REGIME,),
            ("breadth", "market_regime"),
            "OWNER_RECORDED_MARKET_CONTEXT_NO_CROSS_SECTIONAL_NORMALIZATION",
        ),
        _alpha_spec(
            AlphaFactorKind.ETF_RELATIVE_STRENGTH,
            (FactorFamily.ETF,),
            ("relative_strength", "strength"),
            cross_sectional,
        ),
        _alpha_spec(
            AlphaFactorKind.THEME_STRENGTH,
            (FactorFamily.THEME,),
            ("strength", "theme"),
            cross_sectional,
        ),
        _alpha_spec(
            AlphaFactorKind.CAPITAL_PROXY,
            (FactorFamily.CAPITAL,),
            ("capital", "proxy", "strength"),
            cross_sectional,
        ),
    )
    return tuple(sorted(specs, key=lambda item: item.kind.value))


def assess_alpha_factor_baseline(
    *,
    enrichment: ResearchPanelEnrichment,
    decision_time: datetime,
    assessed_at: datetime,
) -> AlphaFactorBaselineAssessment:
    if assessed_at < decision_time:
        raise ValueError("Alpha factor assessment cannot predate DecisionTime")
    future = tuple(
        item
        for item in enrichment.exposures
        if item.available_at is not None and item.available_at > decision_time
    )
    if future:
        raise ValueError("Alpha factor exposure is available after DecisionTime")
    specs = alpha_factor_baseline_specifications()
    coverage: list[AlphaFactorCoverage] = []
    for specification in specs:
        matched = tuple(
            item for item in enrichment.exposures if specification.matches(item)
        )
        available = tuple(
            item
            for item in matched
            if item.raw_numeric is not None and not item.missingness
        )
        coverage.append(
            AlphaFactorCoverage(
                specification.kind,
                len(matched),
                len(available),
                len({item.symbol for item in available}),
                tuple(sorted({item.factor_id for item in matched})),
            )
        )
    enrichment_reference = ValidationArtifactReference(
        "PANEL_ENRICHMENT", enrichment.enrichment_id, enrichment.enrichment_hash
    )
    limitations = tuple(
        sorted(
            {
                *ENGINEERING_LIMITATIONS,
                "EXPLORATORY_NOT_FORMAL_ALPHA_EVIDENCE",
                "MISSING_FACTORS_REMAIN_MISSING",
                "NORMALIZATION_POLICY_REQUIRES_EXPERIMENT_BINDING",
            }
        )
    )
    values = {
        "schema_version": "alpha-factor-baseline-assessment/v1",
        "enrichment_reference": enrichment_reference.to_canonical_dict(),
        "specifications": [item.to_canonical_dict() for item in specs],
        "coverage": [item.to_canonical_dict() for item in coverage],
        "decision_time": timestamp(decision_time),
        "assessed_at": timestamp(assessed_at),
        "authority": ResearchEvidenceAuthority.EXPLORATORY.value,
        "limitations": list(limitations),
    }
    assessment_id, digest = content_identity("alpha-factor-baseline", values)
    return AlphaFactorBaselineAssessment(
        assessment_id,
        digest,
        enrichment_reference,
        specs,
        tuple(coverage),
        decision_time,
        assessed_at,
        ResearchEvidenceAuthority.EXPLORATORY,
        limitations,
    )


def robust_cross_sectional_normalize(
    values: Mapping[str, Decimal],
    *,
    lower_quantile: Decimal = Decimal("0.01"),
    upper_quantile: Decimal = Decimal("0.99"),
) -> dict[str, Decimal]:
    """Winsorize one decision-time cross-section and population z-score it."""

    if not values:
        return {}
    if not Decimal("0") <= lower_quantile < upper_quantile <= Decimal("1"):
        raise ValueError("winsor quantiles must satisfy 0 <= lower < upper <= 1")
    ordered = sorted(values.values())
    if any(not item.is_finite() for item in ordered):
        raise ValueError("cross-sectional values must be finite")
    lower = _decimal_quantile(ordered, lower_quantile)
    upper = _decimal_quantile(ordered, upper_quantile)
    winsorized = {
        symbol: min(max(value, lower), upper)
        for symbol, value in sorted(values.items())
    }
    mean = sum(winsorized.values(), Decimal("0")) / Decimal(len(winsorized))
    variance = sum(
        ((value - mean) ** 2 for value in winsorized.values()), Decimal("0")
    ) / Decimal(len(winsorized))
    if variance == 0:
        return {symbol: Decimal("0") for symbol in winsorized}
    standard_deviation = Decimal(str(sqrt(float(variance))))
    return {
        symbol: (value - mean) / standard_deviation
        for symbol, value in winsorized.items()
    }


def _alpha_spec(
    kind: AlphaFactorKind,
    families: tuple[FactorFamily, ...],
    tokens: tuple[str, ...],
    normalization: str,
) -> AlphaFactorSpecification:
    return AlphaFactorSpecification(
        kind,
        tuple(sorted(set(families), key=lambda item: item.value)),
        tuple(sorted(set(tokens))),
        normalization,
    )


def _decimal_quantile(
    ordered: list[Decimal], probability: Decimal
) -> Decimal:
    if len(ordered) == 1:
        return ordered[0]
    position = probability * Decimal(len(ordered) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    weight = position - Decimal(lower_index)
    return ordered[lower_index] * (Decimal("1") - weight) + ordered[
        upper_index
    ] * weight


def build_factor_research_catalog(
    *, enrichment: ResearchPanelEnrichment, created_at: datetime
) -> FactorResearchCatalog:
    grouped: dict[tuple[FactorFamily, str, str | None], list[ResearchFactorExposure]] = {}
    for exposure in enrichment.exposures:
        grouped.setdefault(
            (exposure.family, exposure.factor_id, exposure.timeframe), []
        ).append(exposure)
    definitions = []
    for (family, factor_id, timeframe), exposures in sorted(
        grouped.items(), key=lambda item: (item[0][0].value, item[0][1], item[0][2] or "")
    ):
        references = tuple(
            sorted(
                {item.source_reference for item in exposures},
                key=lambda item: (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        )
        role = (
            FactorScoringRole.MODEL_CONTRIBUTION_RECORDED
            if any(item.model_contribution is not None for item in exposures)
            else FactorScoringRole.GATE_OR_DIAGNOSTIC
            if any(item.gate_result is not None for item in exposures)
            else FactorScoringRole.DIAGNOSTIC_ONLY
        )
        factor_key = f"{family.value}:{factor_id}:{timeframe or 'NONE'}"
        paths = tuple(sorted({item.source_value_path for item in exposures}))
        definitions.append(
            ResearchFactorDefinition(
                factor_key=factor_key,
                factor_id=factor_id,
                definition_version="canonical-copy-v1",
                family=family,
                timeframe=timeframe,
                definition="COPY_EXISTING_CANONICAL_OWNER_VALUE_NO_RECOMPUTATION",
                input_value_paths=paths,
                source_references=references,
                availability_policy="AVAILABLE_AT_OR_BEFORE_DECISION_TIME",
                missing_policy="EXPLICIT_MISSING_NO_IMPUTATION",
                normalization_policy=(
                    "OWNER_RECORDED"
                    if any(item.normalized_exposure is not None for item in exposures)
                    else "NOT_APPLIED"
                ),
                scoring_role=role,
                source_information_families=tuple(
                    sorted(
                        {
                            f"{item.source_reference.artifact_kind}:"
                            f"{item.source_value_path.split('.', 1)[0]}"
                            for item in exposures
                        }
                    )
                ),
            )
        )
    enrichment_ref = ValidationArtifactReference(
        "PANEL_ENRICHMENT", enrichment.enrichment_id, enrichment.enrichment_hash
    )
    limitations = tuple(
        sorted(
            {
                *ENGINEERING_LIMITATIONS,
                "ENGINEERING_DEFAULT_NOT_ECONOMIC_TRUTH",
                "FACTOR_METADATA_DOES_NOT_ESTABLISH_ALPHA",
            }
        )
    )
    payload = {
        "schema_version": "factor-research-catalog/v1",
        "enrichment_reference": enrichment_ref.to_canonical_dict(),
        "definitions": [item.to_canonical_dict() for item in definitions],
        "created_at": timestamp(created_at),
        "limitations": list(limitations),
    }
    artifact_id, digest = content_identity("factor-research-catalog", payload)
    return FactorResearchCatalog(
        artifact_id,
        digest,
        enrichment_ref,
        tuple(definitions),
        created_at,
        limitations,
    )


def analyze_factor_deduplication(
    *,
    enrichment: ResearchPanelEnrichment,
    catalog: FactorResearchCatalog,
    analyzed_at: datetime,
    correlation_threshold: Decimal = Decimal("0.90"),
    minimum_common_symbols: int = 3,
) -> FactorDeduplicationReport:
    if catalog.enrichment_reference.artifact_id != enrichment.enrichment_id:
        raise ValueError("Factor catalog does not bind supplied enrichment")
    values: dict[str, dict[str, Decimal]] = {}
    for exposure in enrichment.exposures:
        if exposure.raw_numeric is None:
            continue
        key = f"{exposure.family.value}:{exposure.factor_id}:{exposure.timeframe or 'NONE'}"
        values.setdefault(key, {})[exposure.symbol] = exposure.raw_numeric
    keys = tuple(sorted(values))
    evaluated = estimable = 0
    high: list[FactorCorrelationPair] = []
    for left_index, left in enumerate(keys):
        for right in keys[left_index + 1 :]:
            evaluated += 1
            symbols = tuple(sorted(set(values[left]) & set(values[right])))
            if len(symbols) < minimum_common_symbols:
                continue
            correlation = _correlation(
                tuple(values[left][symbol] for symbol in symbols),
                tuple(values[right][symbol] for symbol in symbols),
            )
            if correlation is None:
                continue
            estimable += 1
            if abs(correlation) >= correlation_threshold:
                high.append(
                    FactorCorrelationPair(
                        left,
                        right,
                        len(symbols),
                        correlation,
                        True,
                    )
                )
    pairs = tuple(
        sorted(high, key=lambda item: (item.left_factor_key, item.right_factor_key))
    )
    catalog_ref = ValidationArtifactReference(
        "FACTOR_RESEARCH_CATALOG", catalog.catalog_id, catalog.catalog_hash
    )
    limitations = tuple(
        sorted(
            {
                *ENGINEERING_LIMITATIONS,
                "CORRELATION_IS_NOT_AUTOMATIC_FACTOR_DELETION",
                "EXPLORATORY_CROSS_SECTION_ONLY",
            }
        )
    )
    payload = {
        "schema_version": "factor-deduplication-report/v1",
        "catalog_reference": catalog_ref.to_canonical_dict(),
        "enrichment_reference": catalog.enrichment_reference.to_canonical_dict(),
        "correlation_threshold": str(correlation_threshold),
        "minimum_common_symbols": minimum_common_symbols,
        "evaluated_pair_count": evaluated,
        "estimable_pair_count": estimable,
        "high_correlation_pairs": [item.to_canonical_dict() for item in pairs],
        "analyzed_at": timestamp(analyzed_at),
        "limitations": list(limitations),
    }
    artifact_id, digest = content_identity("factor-deduplication-report", payload)
    return FactorDeduplicationReport(
        artifact_id,
        digest,
        catalog_ref,
        catalog.enrichment_reference,
        correlation_threshold,
        minimum_common_symbols,
        evaluated,
        estimable,
        pairs,
        analyzed_at,
        limitations,
    )


def publish_factor_research_artifact(
    *, root: Path, artifact: FactorResearchCatalog | FactorDeduplicationReport
) -> Path:
    artifact_id = (
        artifact.catalog_id
        if isinstance(artifact, FactorResearchCatalog)
        else artifact.report_id
    )
    path = root / f"{artifact_id}.json"
    publish_immutable_text(
        path=path,
        payload=canonical_json(
            {
                "artifact_id": str(artifact_id),
                "artifact_hash": (
                    artifact.catalog_hash
                    if isinstance(artifact, FactorResearchCatalog)
                    else artifact.report_hash
                ),
                **artifact.identity_payload(),
            }
        )
        + "\n",
        collision_message="Factor research Artifact identity conflict",
    )
    return path


def _correlation(
    left: tuple[Decimal, ...], right: tuple[Decimal, ...]
) -> Decimal | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean = sum(left, Decimal("0")) / Decimal(len(left))
    right_mean = sum(right, Decimal("0")) / Decimal(len(right))
    numerator = sum(
        ((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True)),
        Decimal("0"),
    )
    left_sum = sum(((x - left_mean) ** 2 for x in left), Decimal("0"))
    right_sum = sum(((y - right_mean) ** 2 for y in right), Decimal("0"))
    if left_sum == 0 or right_sum == 0:
        return None
    return numerator / Decimal(str(sqrt(float(left_sum * right_sum))))


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object payload")
    return value


__all__ = [
    "AlphaFactorBaselineAssessment",
    "AlphaFactorCoverage",
    "AlphaFactorKind",
    "AlphaFactorSpecification",
    "FactorDeduplicationReport",
    "FactorResearchCatalog",
    "FactorScoringRole",
    "ResearchFactorDefinition",
    "analyze_factor_deduplication",
    "alpha_factor_baseline_specifications",
    "assess_alpha_factor_baseline",
    "build_factor_research_catalog",
    "publish_factor_research_artifact",
    "robust_cross_sectional_normalize",
]
