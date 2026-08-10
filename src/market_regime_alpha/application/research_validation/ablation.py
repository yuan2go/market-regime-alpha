"""Versioned, deterministic exploratory factor-ablation runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from math import sqrt
from statistics import fmean
from typing import Any, Callable, Iterable

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
    top_k: int
    scoring_contract: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        protocol_version: str,
        variants: tuple[AblationVariant, ...],
        top_k: int,
        scoring_contract: str,
        created_at: datetime,
    ) -> AblationProtocol:
        ordered = tuple(sorted(variants, key=lambda item: item.variant_id))
        if not ordered or len({item.variant_id for item in ordered}) != len(ordered) or top_k <= 0:
            raise ValueError("Ablation Protocol variants/top_k are invalid")
        require_text("scoring_contract", scoring_contract)
        payload = {
            "schema": "ablation-protocol/v1",
            "protocol_version": protocol_version,
            "variants": [_variant_payload(item) for item in ordered],
            "top_k": top_k,
            "scoring_contract": scoring_contract,
            "created_at": timestamp(created_at),
        }
        artifact_id, digest = content_identity("ablation-protocol", payload)
        return cls(artifact_id, digest, protocol_version, ordered, top_k, scoring_contract, created_at)


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

    def __post_init__(self) -> None:
        require_text("observation_id", self.observation_id)
        require_text("session_key", self.session_key)
        require_text("symbol", self.symbol)
        keys = tuple((family.value, factor_id) for family, factor_id, _value in self.factor_values)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("factor values must be unique and sorted")


@dataclass(frozen=True, slots=True)
class AblationMetrics:
    sample_count: int
    ic: Decimal | None
    rank_ic: Decimal | None
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

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "ic": decimal_text(self.ic),
            "rank_ic": decimal_text(self.rank_ic),
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


def _metrics(
    scored: tuple[tuple[AblationObservation, Decimal], ...],
    *,
    top_k: int,
    baseline: AblationMetrics | None,
) -> AblationMetrics:
    scores = [float(score) for _item, score in scored]
    returns = [float(item.realized_return) for item, _score in scored]
    ranked_scores = _ranks(scores)
    ranked_returns = _ranks(returns)
    ic = _correlation(scores, returns)
    rank_ic = _correlation(ranked_scores, ranked_returns)
    by_session: dict[str, list[tuple[AblationObservation, Decimal]]] = {}
    for pair in scored:
        by_session.setdefault(pair[0].session_key, []).append(pair)
    top_returns: list[float] = []
    bottom_returns: list[float] = []
    overlaps: list[float] = []
    turnovers: list[float] = []
    equity_returns: list[float] = []
    for pairs in by_session.values():
        ordered = sorted(pairs, key=lambda pair: (-pair[1], pair[0].symbol))
        top = ordered[: min(top_k, len(ordered))]
        bottom = ordered[-min(top_k, len(ordered)) :]
        top_returns.extend(float(item.realized_return) for item, _score in top)
        bottom_returns.extend(float(item.realized_return) for item, _score in bottom)
        selected = {item.symbol for item, _score in top}
        full_selected = {item.symbol for item, _score in pairs if item.selected}
        previous = {item.symbol for item, _score in pairs if item.previous_selected}
        overlaps.append(len(selected & full_selected) / max(1, len(selected | full_selected)))
        turnovers.append(len(selected.symmetric_difference(previous)) / max(1, len(selected | previous)))
        equity_returns.append(fmean(float(item.realized_return) for item, _score in top))
    mean_return = fmean(returns)
    baseline_return = None if baseline is None or baseline.top_k_return is None else float(baseline.top_k_return)
    return AblationMetrics(
        sample_count=len(scored),
        ic=_decimal(ic),
        rank_ic=_decimal(rank_ic),
        top_k_return=_mean_decimal(top_returns),
        spread=_decimal(fmean(top_returns) - fmean(bottom_returns)) if top_returns and bottom_returns else None,
        hit_rate=_decimal(sum(value > 0 for value in returns) / len(returns)),
        mean_return=_decimal(mean_return),
        mean_mfe=_mean_decimal([float(item.mfe) for item, _score in scored if item.mfe is not None]),
        mean_mae=_mean_decimal([float(item.mae) for item, _score in scored if item.mae is not None]),
        turnover=_mean_decimal(turnovers),
        max_drawdown=_decimal(_max_drawdown(equity_returns)),
        overlap=_mean_decimal(overlaps),
        incremental_lift=None if baseline_return is None or not top_returns else _decimal(fmean(top_returns) - baseline_return),
    )


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
