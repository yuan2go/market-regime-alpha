"""Versioned, deterministic exploratory factor-ablation runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from math import sqrt
from statistics import fmean
from typing import Any, Callable, Iterable, Mapping

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ResearchEvidenceAuthority,
    ValidationArtifactReference,
    content_identity,
    decimal_text,
    timestamp,
)
from market_regime_alpha.application.research_validation.factor_extraction import FactorFamily
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text
from market_regime_alpha.research.cross_sectional_ranking import (
    FactorCrossSection,
    composite_percentile_scores,
    fractional_boundary_weights,
    fractional_slot_weight_total,
    rank_percentiles,
)


class AblationVariantKind(str, Enum):
    FULL = "FULL"
    NO_MARKET = "NO_MARKET"
    NO_THEME = "NO_THEME"
    NO_CAPITAL = "NO_CAPITAL"
    NO_DYNAMIC_POOL = "NO_DYNAMIC_POOL"
    PRICE_ONLY = "PRICE_ONLY"
    VOLUME_ONLY = "VOLUME_ONLY"
    PRICE_VOLUME = "PRICE_VOLUME"
    PRICE_VOLUME_MARKET_REGIME = "PRICE_VOLUME_MARKET_REGIME"
    PRICE_VOLUME_MARKET_REGIME_ETF = "PRICE_VOLUME_MARKET_REGIME_ETF"
    PRICE_VOLUME_MARKET_REGIME_ETF_THEME = "PRICE_VOLUME_MARKET_REGIME_ETF_THEME"
    PRICE_VOLUME_MARKET_REGIME_ETF_THEME_CAPITAL = "PRICE_VOLUME_MARKET_REGIME_ETF_THEME_CAPITAL"
    THROUGH_DYNAMIC_POOL = "THROUGH_DYNAMIC_POOL"
    THROUGH_CANDIDATE_RANKING = "THROUGH_CANDIDATE_RANKING"
    THROUGH_SIGNAL = "THROUGH_SIGNAL"
    THROUGH_FORECAST = "THROUGH_FORECAST"
    STATIC_ONLY = "STATIC_ONLY"
    DYNAMIC_ONLY = "DYNAMIC_ONLY"
    CUSTOM_DELETE = "CUSTOM_DELETE"


@dataclass(frozen=True, slots=True)
class AblationVariant:
    variant_id: str
    kind: AblationVariantKind
    included_families: tuple[FactorFamily, ...]
    deleted_families: tuple[FactorFamily, ...]
    deleted_factor_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_text("variant_id", self.variant_id)
        if self.included_families != tuple(sorted(set(self.included_families), key=lambda item: item.value)):
            raise ValueError("included families must be unique and sorted")
        if self.deleted_families != tuple(sorted(set(self.deleted_families), key=lambda item: item.value)):
            raise ValueError("deleted families must be unique and sorted")
        if self.deleted_factor_ids != tuple(sorted(set(self.deleted_factor_ids))):
            raise ValueError("deleted factor ids must be unique and sorted")

    @classmethod
    def standard(cls, kind: AblationVariantKind) -> AblationVariant:
        all_families = tuple(sorted(FactorFamily, key=lambda item: item.value))
        deleted: dict[AblationVariantKind, set[FactorFamily]] = {
            AblationVariantKind.NO_MARKET: {FactorFamily.MARKET_REGIME, FactorFamily.ETF},
            AblationVariantKind.NO_THEME: {FactorFamily.THEME},
            AblationVariantKind.NO_CAPITAL: {FactorFamily.CAPITAL},
            AblationVariantKind.NO_DYNAMIC_POOL: {FactorFamily.DYNAMIC_POOL},
            AblationVariantKind.STATIC_ONLY: {FactorFamily.DYNAMIC_POOL, FactorFamily.INTRADAY},
        }
        included: dict[AblationVariantKind, set[FactorFamily]] = {
            AblationVariantKind.PRICE_ONLY: {
                FactorFamily.PRICE,
                FactorFamily.PRICE_ACTION,
                FactorFamily.MA_EMA,
                FactorFamily.MACD,
                FactorFamily.VWAP,
                FactorFamily.VOLATILITY,
                FactorFamily.MOMENTUM_TREND,
            },
            AblationVariantKind.VOLUME_ONLY: {
                FactorFamily.VOLUME,
                FactorFamily.AMOUNT,
                FactorFamily.LIQUIDITY,
            },
            AblationVariantKind.PRICE_VOLUME: {
                FactorFamily.PRICE,
                FactorFamily.PRICE_ACTION,
                FactorFamily.MA_EMA,
                FactorFamily.MACD,
                FactorFamily.VWAP,
                FactorFamily.VOLATILITY,
                FactorFamily.MOMENTUM_TREND,
                FactorFamily.VOLUME,
                FactorFamily.AMOUNT,
                FactorFamily.LIQUIDITY,
            },
            AblationVariantKind.DYNAMIC_ONLY: {
                FactorFamily.DYNAMIC_POOL,
                FactorFamily.CANDIDATE,
                FactorFamily.INTRADAY,
                FactorFamily.SIGNAL,
                FactorFamily.FORECAST,
            },
        }
        price_volume = included[AblationVariantKind.PRICE_VOLUME]
        cumulative: dict[AblationVariantKind, set[FactorFamily]] = {
            AblationVariantKind.PRICE_VOLUME_MARKET_REGIME: {
                *price_volume,
                FactorFamily.MARKET_REGIME,
            },
            AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF: {
                *price_volume,
                FactorFamily.MARKET_REGIME,
                FactorFamily.ETF,
            },
            AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF_THEME: {
                *price_volume,
                FactorFamily.MARKET_REGIME,
                FactorFamily.ETF,
                FactorFamily.THEME,
            },
            AblationVariantKind.PRICE_VOLUME_MARKET_REGIME_ETF_THEME_CAPITAL: {
                *price_volume,
                FactorFamily.MARKET_REGIME,
                FactorFamily.ETF,
                FactorFamily.THEME,
                FactorFamily.CAPITAL,
            },
            AblationVariantKind.THROUGH_DYNAMIC_POOL: {
                *price_volume,
                FactorFamily.MARKET_REGIME,
                FactorFamily.ETF,
                FactorFamily.THEME,
                FactorFamily.CAPITAL,
                FactorFamily.DYNAMIC_POOL,
            },
            AblationVariantKind.THROUGH_CANDIDATE_RANKING: {
                *price_volume,
                FactorFamily.MARKET_REGIME,
                FactorFamily.ETF,
                FactorFamily.THEME,
                FactorFamily.CAPITAL,
                FactorFamily.DYNAMIC_POOL,
                FactorFamily.CANDIDATE,
            },
            AblationVariantKind.THROUGH_SIGNAL: {
                *price_volume,
                FactorFamily.MARKET_REGIME,
                FactorFamily.ETF,
                FactorFamily.THEME,
                FactorFamily.CAPITAL,
                FactorFamily.DYNAMIC_POOL,
                FactorFamily.CANDIDATE,
                FactorFamily.SIGNAL,
            },
            AblationVariantKind.THROUGH_FORECAST: set(all_families),
        }
        included.update(cumulative)
        keep = included.get(kind, set(all_families))
        remove = deleted.get(kind, set())
        return cls(
            variant_id=kind.value.lower(),
            kind=kind,
            included_families=tuple(sorted(keep, key=lambda item: item.value)),
            deleted_families=tuple(sorted(remove, key=lambda item: item.value)),
        )

    def includes(self, family: FactorFamily, factor_id: str) -> bool:
        return family in self.included_families and family not in self.deleted_families and factor_id not in self.deleted_factor_ids


@dataclass(frozen=True, slots=True)
class AblationProtocol:
    protocol_id: ArtifactId
    protocol_hash: str
    protocol_version: str
    variants: tuple[AblationVariant, ...]
    comparison_sequence: tuple[str, ...]
    top_k: int
    scoring_contract: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        protocol_version: str,
        variants: tuple[AblationVariant, ...],
        comparison_sequence: tuple[str, ...] | None = None,
        top_k: int,
        scoring_contract: str,
        created_at: datetime,
    ) -> AblationProtocol:
        ordered = tuple(sorted(variants, key=lambda item: item.variant_id))
        if not ordered or len({item.variant_id for item in ordered}) != len(ordered) or top_k <= 0:
            raise ValueError("Ablation Protocol variants/top_k are invalid")
        frozen_sequence = tuple(item.variant_id for item in ordered) if comparison_sequence is None else comparison_sequence
        if (
            not frozen_sequence
            or len(set(frozen_sequence)) != len(frozen_sequence)
            or set(frozen_sequence) != {item.variant_id for item in ordered}
        ):
            raise ValueError("Ablation comparison sequence must cover frozen variants exactly once")
        require_text("scoring_contract", scoring_contract)
        payload = {
            "schema": "ablation-protocol/v2",
            "protocol_version": protocol_version,
            "variants": [_variant_payload(item) for item in ordered],
            "comparison_sequence": list(frozen_sequence),
            "top_k": top_k,
            "scoring_contract": scoring_contract,
            "created_at": timestamp(created_at),
        }
        artifact_id, digest = content_identity("ablation-protocol", payload)
        return cls(
            artifact_id,
            digest,
            protocol_version,
            ordered,
            frozen_sequence,
            top_k,
            scoring_contract,
            created_at,
        )


@dataclass(frozen=True, slots=True)
class AblationObservation:
    observation_id: str
    session_key: str
    symbol: str
    score: Decimal
    realized_return: Decimal
    mfe: Decimal | None
    mae: Decimal | None
    selected: bool
    previous_selected: bool
    factor_values: tuple[tuple[FactorFamily, str, Decimal], ...]
    cost_return: Decimal = Decimal("0")
    market_regime: str = "UNSPECIFIED"
    liquidity_bucket: str = "UNSPECIFIED"
    market_cap_bucket: str = "UNSPECIFIED"
    volatility_bucket: str = "UNSPECIFIED"
    theme: str = "UNSPECIFIED"
    industry: str = "UNSPECIFIED"
    trading_date: date | None = None

    def __post_init__(self) -> None:
        require_text("observation_id", self.observation_id)
        require_text("session_key", self.session_key)
        require_text("symbol", self.symbol)
        keys = tuple((family.value, factor_id) for family, factor_id, _value in self.factor_values)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("factor values must be unique and sorted")
        if not self.cost_return.is_finite() or self.cost_return < 0:
            raise ValueError("ablation cost_return must be finite and non-negative")
        for label, value in self.slice_values():
            require_text(f"ablation {label.lower()} slice", value)

    def slice_values(self) -> tuple[tuple[str, str], ...]:
        period_slices: tuple[tuple[str, str], ...] = ()
        if self.trading_date is not None:
            quarter = ((self.trading_date.month - 1) // 3) + 1
            period_slices = (
                ("MONTH", self.trading_date.strftime("%Y-%m")),
                ("QUARTER", f"{self.trading_date.year}-Q{quarter}"),
                ("YEAR", str(self.trading_date.year)),
            )
        return (
            ("INDUSTRY", self.industry),
            ("LIQUIDITY", self.liquidity_bucket),
            ("MARKET_CAP", self.market_cap_bucket),
            ("MARKET_REGIME", self.market_regime),
            *period_slices,
            ("THEME", self.theme),
            ("VOLATILITY", self.volatility_bucket),
        )


@dataclass(frozen=True, slots=True)
class PrecomputedAblationObservation:
    """One score and selection projection frozen by a canonical evaluator."""

    observation: AblationObservation
    score: Decimal
    top_weight: Decimal
    bottom_weight: Decimal

    def __post_init__(self) -> None:
        for label, value in (
            ("score", self.score),
            ("top_weight", self.top_weight),
            ("bottom_weight", self.bottom_weight),
        ):
            if not value.is_finite():
                raise ValueError(f"precomputed Ablation {label} must be finite")
        if not Decimal("0") <= self.top_weight <= Decimal("1"):
            raise ValueError("precomputed Ablation top weight must be within [0, 1]")
        if not Decimal("0") <= self.bottom_weight <= Decimal("1"):
            raise ValueError("precomputed Ablation bottom weight must be within [0, 1]")
        if self.top_weight > 0 and self.bottom_weight > 0:
            raise ValueError("precomputed Ablation top/bottom selections must be disjoint")


@dataclass(frozen=True, slots=True)
class AblationMetrics:
    sample_count: int
    session_count: int
    ic: Decimal | None
    rank_ic: Decimal | None
    icir: Decimal | None
    top_k_return: Decimal | None
    spread: Decimal | None
    hit_rate: Decimal | None
    mean_return: Decimal | None
    mean_mfe: Decimal | None
    mean_mae: Decimal | None
    turnover: Decimal | None
    max_drawdown: Decimal | None
    overlap: Decimal | None
    incremental_lift: Decimal | None
    gross_return: Decimal | None
    cost_return: Decimal | None
    net_return: Decimal | None

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "session_count": self.session_count,
            "ic": decimal_text(self.ic),
            "rank_ic": decimal_text(self.rank_ic),
            "icir": decimal_text(self.icir),
            "top_k_return": decimal_text(self.top_k_return),
            "spread": decimal_text(self.spread),
            "hit_rate": decimal_text(self.hit_rate),
            "mean_return": decimal_text(self.mean_return),
            "mean_mfe": decimal_text(self.mean_mfe),
            "mean_mae": decimal_text(self.mean_mae),
            "turnover": decimal_text(self.turnover),
            "max_drawdown": decimal_text(self.max_drawdown),
            "overlap": decimal_text(self.overlap),
            "incremental_lift": decimal_text(self.incremental_lift),
            "gross_return": decimal_text(self.gross_return),
            "cost_return": decimal_text(self.cost_return),
            "net_return": decimal_text(self.net_return),
        }


@dataclass(frozen=True, slots=True)
class FactorAblationResult:
    result_id: ArtifactId
    result_hash: str
    protocol_reference: ValidationArtifactReference
    panel_reference: ValidationArtifactReference
    variant: AblationVariant
    metrics: AblationMetrics
    baseline_result: ValidationArtifactReference | None
    created_at: datetime
    authority: ResearchEvidenceAuthority
    limitations: tuple[str, ...]
    schema_version: str = "factor-ablation-result/v1"

    def __post_init__(self) -> None:
        require_sha256("result_hash", self.result_hash)
        if self.authority is not ResearchEvidenceAuthority.EXPLORATORY:
            raise ValueError("Factor Ablation can only emit EXPLORATORY evidence")
        if canonical_hash(self.identity_payload()) != self.result_hash:
            raise ValueError("Factor Ablation result hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        protocol_reference: ValidationArtifactReference,
        panel_reference: ValidationArtifactReference,
        variant: AblationVariant,
        metrics: AblationMetrics,
        baseline_result: ValidationArtifactReference | None,
        created_at: datetime,
    ) -> FactorAblationResult:
        values = _result_payload(
            protocol_reference,
            panel_reference,
            variant,
            metrics,
            baseline_result,
            created_at,
        )
        artifact_id, digest = content_identity("factor-ablation-result", values)
        return cls(
            artifact_id,
            digest,
            protocol_reference,
            panel_reference,
            variant,
            metrics,
            baseline_result,
            created_at,
            ResearchEvidenceAuthority.EXPLORATORY,
            tuple(sorted({*ENGINEERING_LIMITATIONS, "NOT_GOVERNANCE_QUALIFICATION"})),
        )

    def identity_payload(self) -> dict[str, Any]:
        return _result_payload(
            self.protocol_reference,
            self.panel_reference,
            self.variant,
            self.metrics,
            self.baseline_result,
            self.created_at,
        )


@dataclass(frozen=True, slots=True)
class AblationSliceEvaluation:
    variant_id: str
    dimension: str
    value: str
    metrics: AblationMetrics

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "dimension": self.dimension,
            "value": self.value,
            "metrics": self.metrics.to_canonical_dict(),
        }


@dataclass(frozen=True, slots=True)
class AlphaAblationSuite:
    suite_id: ArtifactId
    suite_hash: str
    protocol_reference: ValidationArtifactReference
    panel_reference: ValidationArtifactReference
    comparison_sequence: tuple[str, ...]
    results: tuple[FactorAblationResult, ...]
    slice_evaluations: tuple[AblationSliceEvaluation, ...]
    created_at: datetime
    authority: ResearchEvidenceAuthority
    limitations: tuple[str, ...]
    schema_version: str = "alpha-ablation-suite/v1"

    def __post_init__(self) -> None:
        require_sha256("suite_hash", self.suite_hash)
        if self.authority is not ResearchEvidenceAuthority.EXPLORATORY:
            raise ValueError("Alpha Ablation Suite is exploratory evidence only")
        if tuple(item.variant.variant_id for item in self.results) != (self.comparison_sequence):
            raise ValueError("Alpha Ablation results must follow frozen sequence")
        if canonical_hash(self.identity_payload()) != self.suite_hash:
            raise ValueError("Alpha Ablation Suite hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_reference": self.protocol_reference.to_canonical_dict(),
            "panel_reference": self.panel_reference.to_canonical_dict(),
            "comparison_sequence": list(self.comparison_sequence),
            "result_references": [
                {
                    "artifact_kind": "FACTOR_ABLATION_RESULT",
                    "artifact_id": str(item.result_id),
                    "content_hash": item.result_hash,
                }
                for item in self.results
            ],
            "slice_evaluations": [item.to_canonical_dict() for item in self.slice_evaluations],
            "created_at": timestamp(self.created_at),
            "authority": self.authority.value,
            "limitations": list(self.limitations),
        }


ScoreFunction = Callable[[AblationObservation, AblationVariant], Decimal]


def run_factor_ablation(
    *,
    protocol: AblationProtocol,
    panel_reference: ValidationArtifactReference,
    observations: tuple[AblationObservation, ...],
    variant: AblationVariant,
    score_function: ScoreFunction | None,
    baseline_metrics: AblationMetrics | None,
    baseline_result: ValidationArtifactReference | None,
    created_at: datetime,
) -> FactorAblationResult:
    if not observations:
        raise ValueError("Ablation requires observations")
    if variant not in protocol.variants:
        raise ValueError("Ablation variant is not frozen in Protocol")
    if variant.kind is not AblationVariantKind.FULL and score_function is None:
        raise ValueError("Ablated variants require a protocol-bound scoring function; raw factors cannot be averaged")
    scorer = (lambda item, _variant: item.score) if score_function is None else score_function
    scored = tuple((item, scorer(item, variant)) for item in observations)
    metrics = _metrics(scored, top_k=protocol.top_k, baseline=baseline_metrics)
    protocol_reference = ValidationArtifactReference("ABLATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash)
    return FactorAblationResult.create(
        protocol_reference=protocol_reference,
        panel_reference=panel_reference,
        variant=variant,
        metrics=metrics,
        baseline_result=baseline_result,
        created_at=created_at,
    )


def run_alpha_ablation_suite(
    *,
    protocol: AblationProtocol,
    panel_reference: ValidationArtifactReference,
    observations: tuple[AblationObservation, ...],
    score_functions: Mapping[str, ScoreFunction],
    created_at: datetime,
) -> AlphaAblationSuite:
    """Evaluate the frozen cumulative research chain and diagnostic slices.

    Every step is compared with its immediate predecessor.  The output is
    descriptive EXPLORATORY evidence; it cannot satisfy Formal PIT/OOS gates.
    """

    if set(score_functions) != set(protocol.comparison_sequence):
        raise ValueError("Ablation score functions must exactly cover the frozen comparison sequence")
    variant_by_id = {item.variant_id: item for item in protocol.variants}
    results: list[FactorAblationResult] = []
    slices: list[AblationSliceEvaluation] = []
    baseline_metrics: AblationMetrics | None = None
    baseline_reference: ValidationArtifactReference | None = None
    baseline_slice_metrics: dict[tuple[str, str], AblationMetrics] = {}
    for variant_id in protocol.comparison_sequence:
        variant = variant_by_id[variant_id]
        result = run_factor_ablation(
            protocol=protocol,
            panel_reference=panel_reference,
            observations=observations,
            variant=variant,
            score_function=score_functions[variant_id],
            baseline_metrics=baseline_metrics,
            baseline_result=baseline_reference,
            created_at=created_at,
        )
        results.append(result)
        next_slice_metrics: dict[tuple[str, str], AblationMetrics] = {}
        for dimension, value in sorted({slice_value for item in observations for slice_value in item.slice_values()}):
            scoped = tuple(item for item in observations if (dimension, value) in item.slice_values())
            metrics = _metrics(
                tuple((item, score_functions[variant_id](item, variant)) for item in scoped),
                top_k=protocol.top_k,
                baseline=baseline_slice_metrics.get((dimension, value)),
            )
            next_slice_metrics[(dimension, value)] = metrics
            slices.append(AblationSliceEvaluation(variant_id, dimension, value, metrics))
        baseline_slice_metrics = next_slice_metrics
        baseline_metrics = result.metrics
        baseline_reference = ValidationArtifactReference("FACTOR_ABLATION_RESULT", result.result_id, result.result_hash)
    return _build_alpha_suite(
        protocol=protocol,
        panel_reference=panel_reference,
        results=tuple(results),
        slices=tuple(slices),
        created_at=created_at,
    )


def run_incremental_alpha_ablation_suite(
    *,
    protocol: AblationProtocol,
    panel_reference: ValidationArtifactReference,
    observation_sessions: Iterable[tuple[AblationObservation, ...]],
    created_at: datetime,
    maximum_slice_cells: int = 4096,
) -> AlphaAblationSuite:
    """Stream one cross-section at a time under the frozen percentile scorer."""

    if (
        protocol.scoring_contract
        != "WITHIN_SESSION_TIE_AWARE_EXACT_RATIONAL_FACTOR_PERCENTILE_MEAN_V2"
    ):
        raise ValueError("Incremental Ablation requires the frozen V2 percentile scorer")
    if maximum_slice_cells <= 0:
        raise ValueError("Incremental Ablation slice ceiling must be positive")
    variant_by_id = {item.variant_id: item for item in protocol.variants}
    accumulators = {variant_id: _MetricAccumulator(protocol.top_k) for variant_id in protocol.comparison_sequence}
    slice_accumulators: dict[tuple[str, str, str], _MetricAccumulator] = {}
    observed = False
    last_order: tuple[date, str] | None = None
    for session in observation_sessions:
        if not session:
            continue
        observed = True
        session_keys = {item.session_key for item in session}
        trading_dates = {item.trading_date for item in session}
        if len(session_keys) != 1 or len(trading_dates) != 1 or None in trading_dates:
            raise ValueError("Incremental Ablation batch must contain one canonical session")
        session_key = next(iter(session_keys))
        trading_date = next(iter(trading_dates))
        assert trading_date is not None
        order = trading_date, session_key
        if last_order is not None and order <= last_order:
            raise ValueError("Incremental Ablation sessions must be strictly ordered")
        last_order = order
        scores = _v2_within_session_scores(
            session,
            tuple(variant_by_id[item] for item in protocol.comparison_sequence),
        )
        slice_groups: dict[tuple[str, str], list[AblationObservation]] = {}
        for item in session:
            for dimension, value in item.slice_values():
                slice_groups.setdefault((dimension, value), []).append(item)
        for variant_id in protocol.comparison_sequence:
            scored = tuple((item, scores[(variant_id, item.observation_id)]) for item in session)
            accumulators[variant_id].add_session(scored)
            scored_by_id = {item.observation_id: score for item, score in scored}
            for (dimension, value), scoped in sorted(slice_groups.items()):
                key = variant_id, dimension, value
                accumulator = slice_accumulators.setdefault(key, _MetricAccumulator(protocol.top_k))
                if len(slice_accumulators) > maximum_slice_cells:
                    raise ValueError("Incremental Ablation exceeded declared slice ceiling")
                accumulator.add_session(tuple((item, scored_by_id[item.observation_id]) for item in scoped))
    if not observed:
        raise ValueError("Ablation requires observations")
    results: list[FactorAblationResult] = []
    slices: list[AblationSliceEvaluation] = []
    baseline_metrics: AblationMetrics | None = None
    baseline_reference: ValidationArtifactReference | None = None
    baseline_slice_metrics: dict[tuple[str, str], AblationMetrics] = {}
    for variant_id in protocol.comparison_sequence:
        variant = variant_by_id[variant_id]
        metrics = accumulators[variant_id].metrics(baseline_metrics)
        result = FactorAblationResult.create(
            protocol_reference=ValidationArtifactReference("ABLATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash),
            panel_reference=panel_reference,
            variant=variant,
            metrics=metrics,
            baseline_result=baseline_reference,
            created_at=created_at,
        )
        results.append(result)
        next_slice_metrics: dict[tuple[str, str], AblationMetrics] = {}
        slice_keys = sorted(
            (dimension, value) for candidate_variant, dimension, value in slice_accumulators if candidate_variant == variant_id
        )
        for dimension, value in slice_keys:
            slice_metrics = slice_accumulators[(variant_id, dimension, value)].metrics(baseline_slice_metrics.get((dimension, value)))
            next_slice_metrics[(dimension, value)] = slice_metrics
            slices.append(AblationSliceEvaluation(variant_id, dimension, value, slice_metrics))
        baseline_slice_metrics = next_slice_metrics
        baseline_metrics = metrics
        baseline_reference = ValidationArtifactReference("FACTOR_ABLATION_RESULT", result.result_id, result.result_hash)
    return _build_alpha_suite(
        protocol=protocol,
        panel_reference=panel_reference,
        results=tuple(results),
        slices=tuple(slices),
        created_at=created_at,
    )


def run_precomputed_alpha_ablation_suite(
    *,
    protocol: AblationProtocol,
    panel_reference: ValidationArtifactReference,
    evaluation_sessions: Iterable[
        Mapping[str, tuple[PrecomputedAblationObservation, ...]]
    ],
    created_at: datetime,
) -> AlphaAblationSuite:
    """Aggregate canonical session scores/weights without ranking or selection."""

    if (
        protocol.scoring_contract
        != "WITHIN_SESSION_TIE_AWARE_EXACT_RATIONAL_FACTOR_PERCENTILE_MEAN_V2"
    ):
        raise ValueError("Precomputed Ablation requires the frozen V2 scorer")
    accumulators = {
        variant_id: _MetricAccumulator(protocol.top_k)
        for variant_id in protocol.comparison_sequence
    }
    observed = False
    for session in evaluation_sessions:
        if set(session) != set(protocol.comparison_sequence):
            raise ValueError(
                "Precomputed Ablation session must cover the frozen sequence"
            )
        observed = True
        for variant_id in protocol.comparison_sequence:
            rows = session[variant_id]
            accumulators[variant_id].add_precomputed_session(
                tuple((item.observation, item.score) for item in rows),
                top_weights={
                    item.observation.symbol: item.top_weight for item in rows
                },
                bottom_weights={
                    item.observation.symbol: item.bottom_weight for item in rows
                },
            )
    if not observed:
        raise ValueError("Precomputed Ablation requires evaluation sessions")
    variant_by_id = {item.variant_id: item for item in protocol.variants}
    results: list[FactorAblationResult] = []
    baseline_metrics: AblationMetrics | None = None
    baseline_reference: ValidationArtifactReference | None = None
    protocol_reference = ValidationArtifactReference(
        "ABLATION_PROTOCOL",
        protocol.protocol_id,
        protocol.protocol_hash,
    )
    for variant_id in protocol.comparison_sequence:
        metrics = accumulators[variant_id].metrics(baseline_metrics)
        result = FactorAblationResult.create(
            protocol_reference=protocol_reference,
            panel_reference=panel_reference,
            variant=variant_by_id[variant_id],
            metrics=metrics,
            baseline_result=baseline_reference,
            created_at=created_at,
        )
        results.append(result)
        baseline_metrics = metrics
        baseline_reference = ValidationArtifactReference(
            "FACTOR_ABLATION_RESULT",
            result.result_id,
            result.result_hash,
        )
    return _build_alpha_suite(
        protocol=protocol,
        panel_reference=panel_reference,
        results=tuple(results),
        slices=(),
        created_at=created_at,
    )


def _build_alpha_suite(
    *,
    protocol: AblationProtocol,
    panel_reference: ValidationArtifactReference,
    results: tuple[FactorAblationResult, ...],
    slices: tuple[AblationSliceEvaluation, ...],
    created_at: datetime,
) -> AlphaAblationSuite:
    protocol_reference = ValidationArtifactReference("ABLATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash)
    limitations = tuple(
        sorted(
            {
                *ENGINEERING_LIMITATIONS,
                "EXPLORATORY",
                "NOT_FORMAL_ALPHA_EVIDENCE",
                "SLICES_ARE_DIAGNOSTIC_NOT_CAUSAL",
            }
        )
    )
    values = {
        "schema_version": "alpha-ablation-suite/v1",
        "protocol_reference": protocol_reference.to_canonical_dict(),
        "panel_reference": panel_reference.to_canonical_dict(),
        "comparison_sequence": list(protocol.comparison_sequence),
        "result_references": [
            {
                "artifact_kind": "FACTOR_ABLATION_RESULT",
                "artifact_id": str(item.result_id),
                "content_hash": item.result_hash,
            }
            for item in results
        ],
        "slice_evaluations": [item.to_canonical_dict() for item in slices],
        "created_at": timestamp(created_at),
        "authority": ResearchEvidenceAuthority.EXPLORATORY.value,
        "limitations": list(limitations),
    }
    suite_id, digest = content_identity("alpha-ablation-suite", values)
    return AlphaAblationSuite(
        suite_id,
        digest,
        protocol_reference,
        panel_reference,
        protocol.comparison_sequence,
        results,
        slices,
        created_at,
        ResearchEvidenceAuthority.EXPLORATORY,
        limitations,
    )


def _metrics(
    scored: tuple[tuple[AblationObservation, Decimal], ...],
    *,
    top_k: int,
    baseline: AblationMetrics | None,
) -> AblationMetrics:
    if not scored:
        return _empty_metrics()
    by_session: dict[str, list[tuple[AblationObservation, Decimal]]] = {}
    for pair in scored:
        by_session.setdefault(pair[0].session_key, []).append(pair)
    session_dates: dict[str, date | None] = {}
    for item, _score in scored:
        prior = session_dates.setdefault(item.session_key, item.trading_date)
        if prior != item.trading_date:
            raise ValueError("Ablation session has inconsistent trading dates")
    if any(value is None for value in session_dates.values()):
        raise ValueError("Ablation path metrics require a canonical trading date for every session")
    canonical_dates = tuple(value for value in session_dates.values() if value is not None)
    if len(set(canonical_dates)) != len(canonical_dates):
        raise ValueError("Ablation path metrics require one session per trading date")
    ordered_sessions = tuple(
        sorted(
            by_session,
            key=lambda key: (session_dates[key], key),
        )
    )
    accumulator = _MetricAccumulator(top_k)
    for session_key in ordered_sessions:
        accumulator.add_session(tuple(by_session[session_key]))
    return accumulator.metrics(baseline)


class _MetricAccumulator:
    """Fixed-dimension sufficient statistics for one ordered research path."""

    def __init__(self, top_k: int) -> None:
        self._top_k = top_k
        self._sample_count = 0
        self._session_count = 0
        self._last_order: tuple[date, str] | None = None
        self._all_return_sum = 0.0
        self._top_return_sum = Decimal("0")
        self._top_return_weight = Decimal("0")
        self._top_hit_weight = Decimal("0")
        self._bottom_return_sum = Decimal("0")
        self._bottom_return_weight = Decimal("0")
        self._mfe_sum = 0.0
        self._mfe_count = 0
        self._mae_sum = 0.0
        self._mae_count = 0
        self._turnover_sum = 0.0
        self._turnover_count = 0
        self._overlap_sum = 0.0
        self._overlap_count = 0
        self._gross_sum = Decimal("0")
        self._cost_sum = Decimal("0")
        self._session_ics = _RunningMoments()
        self._session_rank_ics = _RunningMoments()
        self._wealth = 1.0
        self._peak_wealth = 1.0
        self._maximum_drawdown = 0.0
        self._previous_weights: dict[str, Decimal] | None = None

    def add_session(
        self,
        scored: tuple[tuple[AblationObservation, Decimal], ...],
    ) -> None:
        if not scored:
            raise ValueError("Ablation session batch cannot be empty")
        symbols = [item.symbol for item, _score in scored]
        if len(symbols) != len(set(symbols)):
            raise ValueError("Ablation session/symbol observations must be unique")
        score_by_symbol = {item.symbol: score for item, score in scored}
        top_selection = fractional_boundary_weights(
            score_by_symbol,
            slots=self._top_k,
            higher_is_better=True,
        )
        bottom_candidates = {
            symbol: score
            for symbol, score in score_by_symbol.items()
            if top_selection.weights[symbol] == 0
        }
        bottom_selection = fractional_boundary_weights(
            bottom_candidates,
            slots=self._top_k,
            higher_is_better=False,
        )
        self.add_precomputed_session(
            scored,
            top_weights=top_selection.weights,
            bottom_weights={
                symbol: bottom_selection.weights.get(symbol, Decimal("0"))
                for symbol in symbols
            },
        )

    def add_precomputed_session(
        self,
        scored: tuple[tuple[AblationObservation, Decimal], ...],
        *,
        top_weights: Mapping[str, Decimal],
        bottom_weights: Mapping[str, Decimal],
    ) -> None:
        if not scored:
            raise ValueError("Ablation session batch cannot be empty")
        session_keys = {item.session_key for item, _score in scored}
        trading_dates = {item.trading_date for item, _score in scored}
        symbols = [item.symbol for item, _score in scored]
        if len(session_keys) != 1 or len(trading_dates) != 1:
            raise ValueError("Ablation batch must contain one session")
        if len(symbols) != len(set(symbols)):
            raise ValueError("Ablation session/symbol observations must be unique")
        symbol_set = set(symbols)
        if set(top_weights) != symbol_set or set(bottom_weights) != symbol_set:
            raise ValueError("precomputed Ablation weights must cover the session")
        if any(
            not weight.is_finite() or not Decimal("0") <= weight <= Decimal("1")
            for weight in (*top_weights.values(), *bottom_weights.values())
        ):
            raise ValueError("precomputed Ablation weights must be finite within [0, 1]")
        if any(
            top_weights[symbol] > 0 and bottom_weights[symbol] > 0
            for symbol in symbol_set
        ):
            raise ValueError("precomputed Ablation top/bottom weights must be disjoint")
        expected_top_slots = min(self._top_k, len(scored))
        session_top_weight = fractional_slot_weight_total(
            top_weights,
            slots=expected_top_slots,
        )
        trading_date = next(iter(trading_dates))
        if trading_date is None:
            raise ValueError("Ablation path metrics require a canonical trading date for every session")
        session_key = next(iter(session_keys))
        order = trading_date, session_key
        if self._last_order is not None and order <= self._last_order:
            raise ValueError("Ablation sessions must be added in canonical order")
        if self._last_order is not None and trading_date == self._last_order[0]:
            raise ValueError("Ablation path metrics require one session per trading date")
        self._last_order = order
        self._session_count += 1
        self._sample_count += len(scored)
        item_by_symbol = {item.symbol: item for item, _score in scored}
        for item, _score in scored:
            self._all_return_sum += float(item.realized_return)
            if item.mfe is not None:
                self._mfe_sum += float(item.mfe)
                self._mfe_count += 1
            if item.mae is not None:
                self._mae_sum += float(item.mae)
                self._mae_count += 1
        for symbol, weight in top_weights.items():
            if weight == 0:
                continue
            item = item_by_symbol[symbol]
            self._top_return_sum += item.realized_return * weight
            self._top_return_weight += weight
            if item.realized_return > 0:
                self._top_hit_weight += weight
            self._gross_sum += item.realized_return * weight
            self._cost_sum += item.cost_return * weight
        for symbol, weight in bottom_weights.items():
            if weight == 0:
                continue
            self._bottom_return_sum += item_by_symbol[symbol].realized_return * weight
            self._bottom_return_weight += weight
        selected = {
            symbol for symbol, weight in top_weights.items() if weight > 0
        }
        full_selected = {item.symbol for item, _score in scored if item.selected}
        self._overlap_sum += len(selected & full_selected) / max(1, len(selected | full_selected))
        self._overlap_count += 1
        current_weights = {
            symbol: weight / session_top_weight
            for symbol, weight in top_weights.items()
            if weight > 0
        }
        if self._previous_weights is not None:
            weight_symbols = set(self._previous_weights) | set(current_weights)
            self._turnover_sum += float(
                sum(
                    abs(current_weights.get(symbol, Decimal("0")) - self._previous_weights.get(symbol, Decimal("0")))
                    for symbol in weight_symbols
                )
                / Decimal("2")
            )
            self._turnover_count += 1
        self._previous_weights = current_weights
        session_net_return = float(
            sum(
                (
                    (item_by_symbol[symbol].realized_return - item_by_symbol[symbol].cost_return)
                    * weight
                    for symbol, weight in top_weights.items()
                ),
                Decimal("0"),
            )
            / session_top_weight
        )
        self._wealth *= 1.0 + session_net_return
        self._peak_wealth = max(self._peak_wealth, self._wealth)
        self._maximum_drawdown = min(
            self._maximum_drawdown,
            self._wealth / self._peak_wealth - 1.0,
        )
        session_scores = [float(score) for _item, score in scored]
        session_returns = [float(item.realized_return) for item, _score in scored]
        session_ic = _correlation(session_scores, session_returns)
        score_ranks = rank_percentiles(
            dict(enumerate(session_scores)),
            higher_is_better=True,
        )
        return_ranks = rank_percentiles(
            dict(enumerate(session_returns)),
            higher_is_better=True,
        )
        session_rank_ic = _correlation(
            [float(score_ranks.percentiles[index]) for index in range(len(session_scores))],
            [float(return_ranks.percentiles[index]) for index in range(len(session_returns))],
        )
        if session_ic is not None:
            self._session_ics.add(session_ic)
        if session_rank_ic is not None:
            self._session_rank_ics.add(session_rank_ic)

    def metrics(self, baseline: AblationMetrics | None) -> AblationMetrics:
        if self._sample_count == 0:
            return _empty_metrics()
        top_mean = self._top_return_sum / self._top_return_weight
        gross = self._gross_sum / self._top_return_weight
        cost = self._cost_sum / self._top_return_weight
        baseline_return = None if baseline is None else baseline.top_k_return
        return AblationMetrics(
            sample_count=self._sample_count,
            session_count=self._session_count,
            ic=self._session_ics.mean_decimal(),
            rank_ic=self._session_rank_ics.mean_decimal(),
            icir=self._session_ics.information_ratio(),
            top_k_return=top_mean,
            spread=(None if not self._bottom_return_weight else top_mean - self._bottom_return_sum / self._bottom_return_weight),
            hit_rate=self._top_hit_weight / self._top_return_weight,
            mean_return=_decimal(self._all_return_sum / self._sample_count),
            mean_mfe=(None if not self._mfe_count else _decimal(self._mfe_sum / self._mfe_count)),
            mean_mae=(None if not self._mae_count else _decimal(self._mae_sum / self._mae_count)),
            turnover=(None if not self._turnover_count else _decimal(self._turnover_sum / self._turnover_count)),
            max_drawdown=_decimal(self._maximum_drawdown),
            overlap=_decimal(self._overlap_sum / self._overlap_count),
            incremental_lift=(None if baseline_return is None else top_mean - baseline_return),
            gross_return=gross,
            cost_return=cost,
            net_return=gross - cost,
        )


class _RunningMoments:
    """Deterministic population moments without retaining observations."""

    def __init__(self) -> None:
        self._count = 0
        self._mean = 0.0
        self._m2 = 0.0

    def add(self, value: float) -> None:
        self._count += 1
        delta = value - self._mean
        self._mean += delta / self._count
        self._m2 += delta * (value - self._mean)

    def mean_decimal(self) -> Decimal | None:
        return None if not self._count else _decimal(self._mean)

    def information_ratio(self) -> Decimal | None:
        if self._count < 2:
            return None
        dispersion = sqrt(self._m2 / self._count)
        return None if dispersion == 0 else _decimal(self._mean / dispersion)


def _v2_within_session_scores(
    observations: tuple[AblationObservation, ...],
    variants: tuple[AblationVariant, ...],
) -> Mapping[tuple[str, str], Decimal]:
    if len({item.observation_id for item in observations}) != len(observations):
        raise ValueError("Ablation observation identities must be unique")
    grouped: dict[tuple[FactorFamily, str], dict[str, Decimal]] = {}
    for item in observations:
        for family, factor_id, value in item.factor_values:
            values = grouped.setdefault((family, factor_id), {})
            if item.observation_id in values:
                raise ValueError("Ablation observation repeats one Factor identity")
            values[item.observation_id] = value
    entities = tuple(item.observation_id for item in observations)
    result: dict[tuple[str, str], Decimal] = {}
    for variant in variants:
        factors = tuple(
            FactorCrossSection(
                factor_id=f"{family.value}:{factor_id}",
                values=values,
                higher_is_better=True,
                weight=Decimal("1"),
            )
            for (family, factor_id), values in sorted(
                grouped.items(),
                key=lambda item: (item[0][0].value, item[0][1]),
            )
            if variant.includes(family, factor_id)
        )
        scores = (
            {entity: Decimal("0.5") for entity in entities}
            if not factors
            else composite_percentile_scores(factors, entities=entities).scores
        )
        for observation_id, score in scores.items():
            result[(variant.variant_id, observation_id)] = score
    return result


def _empty_metrics() -> AblationMetrics:
    return AblationMetrics(
        sample_count=0,
        session_count=0,
        ic=None,
        rank_ic=None,
        icir=None,
        top_k_return=None,
        spread=None,
        hit_rate=None,
        mean_return=None,
        mean_mfe=None,
        mean_mae=None,
        turnover=None,
        max_drawdown=None,
        overlap=None,
        incremental_lift=None,
        gross_return=None,
        cost_return=None,
        net_return=None,
    )


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    lm, rm = fmean(left), fmean(right)
    numerator = sum((x - lm) * (y - rm) for x, y in zip(left, right, strict=True))
    denominator = sqrt(sum((x - lm) ** 2 for x in left) * sum((y - rm) ** 2 for y in right))
    return None if denominator == 0 else numerator / denominator


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _result_payload(
    protocol_reference: ValidationArtifactReference,
    panel_reference: ValidationArtifactReference,
    variant: AblationVariant,
    metrics: AblationMetrics,
    baseline_result: ValidationArtifactReference | None,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "factor-ablation-result/v1",
        "protocol_reference": protocol_reference.to_canonical_dict(),
        "panel_reference": panel_reference.to_canonical_dict(),
        "variant": {
            "variant_id": variant.variant_id,
            "kind": variant.kind.value,
            "included_families": [item.value for item in variant.included_families],
            "deleted_families": [item.value for item in variant.deleted_families],
            "deleted_factor_ids": list(variant.deleted_factor_ids),
        },
        "metrics": metrics.to_canonical_dict(),
        "baseline_result": None if baseline_result is None else baseline_result.to_canonical_dict(),
        "created_at": timestamp(created_at),
        "authority": ResearchEvidenceAuthority.EXPLORATORY.value,
        "limitations": list(tuple(sorted({*ENGINEERING_LIMITATIONS, "NOT_GOVERNANCE_QUALIFICATION"}))),
    }


def _variant_payload(variant: AblationVariant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "kind": variant.kind.value,
        "included_families": [item.value for item in variant.included_families],
        "deleted_families": [item.value for item in variant.deleted_families],
        "deleted_factor_ids": list(variant.deleted_factor_ids),
    }
