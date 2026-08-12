"""Versioned, deterministic exploratory factor-ablation runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from math import sqrt
from statistics import fmean, pstdev
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
    PRICE_VOLUME_MARKET_REGIME_ETF_THEME_CAPITAL = (
        "PRICE_VOLUME_MARKET_REGIME_ETF_THEME_CAPITAL"
    )
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
        frozen_sequence = (
            tuple(item.variant_id for item in ordered)
            if comparison_sequence is None
            else comparison_sequence
        )
        if (
            not frozen_sequence
            or len(set(frozen_sequence)) != len(frozen_sequence)
            or set(frozen_sequence) != {item.variant_id for item in ordered}
        ):
            raise ValueError(
                "Ablation comparison sequence must cover frozen variants exactly once"
            )
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
        return (
            ("INDUSTRY", self.industry),
            ("LIQUIDITY", self.liquidity_bucket),
            ("MARKET_CAP", self.market_cap_bucket),
            ("MARKET_REGIME", self.market_regime),
            ("THEME", self.theme),
            ("VOLATILITY", self.volatility_bucket),
        )


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
        if tuple(item.variant.variant_id for item in self.results) != (
            self.comparison_sequence
        ):
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
            "slice_evaluations": [
                item.to_canonical_dict() for item in self.slice_evaluations
            ],
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
        raise ValueError(
            "Ablation score functions must exactly cover the frozen comparison sequence"
        )
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
        for dimension, value in sorted(
            {
                slice_value
                for item in observations
                for slice_value in item.slice_values()
            }
        ):
            scoped = tuple(
                item
                for item in observations
                if (dimension, value) in item.slice_values()
            )
            metrics = _metrics(
                tuple(
                    (item, score_functions[variant_id](item, variant))
                    for item in scoped
                ),
                top_k=protocol.top_k,
                baseline=baseline_slice_metrics.get((dimension, value)),
            )
            next_slice_metrics[(dimension, value)] = metrics
            slices.append(
                AblationSliceEvaluation(variant_id, dimension, value, metrics)
            )
        baseline_slice_metrics = next_slice_metrics
        baseline_metrics = result.metrics
        baseline_reference = ValidationArtifactReference(
            "FACTOR_ABLATION_RESULT", result.result_id, result.result_hash
        )
    protocol_reference = ValidationArtifactReference(
        "ABLATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash
    )
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
        tuple(results),
        tuple(slices),
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
    if len({(item.session_key, item.symbol) for item, _score in scored}) != len(scored):
        raise ValueError("Ablation session/symbol observations must be unique")
    session_dates: dict[str, date | None] = {}
    for item, _score in scored:
        prior = session_dates.setdefault(item.session_key, item.trading_date)
        if prior != item.trading_date:
            raise ValueError("Ablation session has inconsistent trading dates")
    if any(value is not None for value in session_dates.values()) and any(
        value is None for value in session_dates.values()
    ):
        raise ValueError("Ablation trading dates must be complete when provided")
    ordered_sessions = tuple(
        sorted(
            by_session,
            key=lambda key: (
                session_dates[key] is None,
                session_dates[key] or date.max,
                key,
            ),
        )
    )
    top_returns: list[float] = []
    top_costs: list[float] = []
    top_gross_decimals: list[Decimal] = []
    top_cost_decimals: list[Decimal] = []
    bottom_returns: list[float] = []
    overlaps: list[float] = []
    turnovers: list[float] = []
    equity_returns: list[float] = []
    session_ics: list[float] = []
    session_rank_ics: list[float] = []
    previous_weights: dict[str, Decimal] | None = None
    for session_key in ordered_sessions:
        pairs = by_session[session_key]
        ordered = sorted(pairs, key=lambda pair: (-pair[1], pair[0].symbol))
        top = ordered[: min(top_k, len(ordered))]
        bottom = ordered[-min(top_k, len(ordered)) :]
        top_returns.extend(float(item.realized_return) for item, _score in top)
        top_costs.extend(float(item.cost_return) for item, _score in top)
        top_gross_decimals.extend(item.realized_return for item, _score in top)
        top_cost_decimals.extend(item.cost_return for item, _score in top)
        bottom_returns.extend(float(item.realized_return) for item, _score in bottom)
        selected = {item.symbol for item, _score in top}
        full_selected = {item.symbol for item, _score in pairs if item.selected}
        overlaps.append(len(selected & full_selected) / max(1, len(selected | full_selected)))
        current_weight = Decimal("1") / Decimal(len(top))
        current_weights = {item.symbol: current_weight for item, _score in top}
        if previous_weights is not None:
            symbols = set(previous_weights) | set(current_weights)
            turnovers.append(
                float(
                    sum(
                        abs(
                            current_weights.get(symbol, Decimal("0"))
                            - previous_weights.get(symbol, Decimal("0"))
                        )
                        for symbol in symbols
                    )
                    / Decimal("2")
                )
            )
        previous_weights = current_weights
        equity_returns.append(
            fmean(
                float(item.realized_return - item.cost_return)
                for item, _score in top
            )
        )
        session_scores = [float(score) for _item, score in pairs]
        session_returns = [float(item.realized_return) for item, _score in pairs]
        session_ic = _correlation(session_scores, session_returns)
        session_rank_ic = _correlation(
            _ranks(session_scores), _ranks(session_returns)
        )
        if session_ic is not None:
            session_ics.append(session_ic)
        if session_rank_ic is not None:
            session_rank_ics.append(session_rank_ic)
    all_returns = [float(item.realized_return) for item, _score in scored]
    mean_return = fmean(all_returns)
    baseline_return = None if baseline is None or baseline.top_k_return is None else float(baseline.top_k_return)
    gross_return = (
        None
        if not top_gross_decimals
        else sum(top_gross_decimals, Decimal("0"))
        / Decimal(len(top_gross_decimals))
    )
    cost_return = (
        None
        if not top_cost_decimals
        else sum(top_cost_decimals, Decimal("0"))
        / Decimal(len(top_cost_decimals))
    )
    return AblationMetrics(
        sample_count=len(scored),
        session_count=len(by_session),
        ic=_mean_decimal(session_ics),
        rank_ic=_mean_decimal(session_rank_ics),
        icir=_information_ratio(session_ics),
        top_k_return=_mean_decimal(top_returns),
        spread=_decimal(fmean(top_returns) - fmean(bottom_returns)) if top_returns and bottom_returns else None,
        hit_rate=_decimal(
            sum(value > 0 for value in top_returns) / len(top_returns)
        ),
        mean_return=_decimal(mean_return),
        mean_mfe=_mean_decimal([float(item.mfe) for item, _score in scored if item.mfe is not None]),
        mean_mae=_mean_decimal([float(item.mae) for item, _score in scored if item.mae is not None]),
        turnover=_mean_decimal(turnovers),
        max_drawdown=_decimal(_max_drawdown(equity_returns)),
        overlap=_mean_decimal(overlaps),
        incremental_lift=None if baseline_return is None or not top_returns else _decimal(fmean(top_returns) - baseline_return),
        gross_return=gross_return,
        cost_return=cost_return,
        net_return=(
            None
            if gross_return is None or cost_return is None
            else gross_return - cost_return
        ),
    )


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


def _information_ratio(values: list[float]) -> Decimal | None:
    if len(values) < 2:
        return None
    dispersion = pstdev(values)
    return None if dispersion == 0 else _decimal(fmean(values) / dispersion)


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    lm, rm = fmean(left), fmean(right)
    numerator = sum((x - lm) * (y - rm) for x, y in zip(left, right, strict=True))
    denominator = sqrt(sum((x - lm) ** 2 for x in left) * sum((y - rm) ** 2 for y in right))
    return None if denominator == 0 else numerator / denominator


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    result = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2
        for original, _value in ordered[index:end]:
            result[original] = rank
        index = end
    return result


def _max_drawdown(returns: Iterable[float]) -> float:
    wealth = peak = 1.0
    worst = 0.0
    for value in returns:
        wealth *= 1.0 + value
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1.0)
    return worst


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _mean_decimal(values: list[float]) -> Decimal | None:
    return None if not values else _decimal(fmean(values))


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
