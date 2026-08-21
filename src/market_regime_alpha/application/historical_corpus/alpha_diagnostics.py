"""Frozen correctness diagnostics for the discovered intraday factor family.

The functions consume research observations and emit content-addressed engineering
diagnostics.  They do not select a model, mutate a Candidate policy, or grant Alpha.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import Enum
from math import sqrt
from random import Random
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    moving_block_mean_interval,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


_INTRADAY_FACTORS = (
    "intraday_return_to_decision_time",
    "price_vs_vwap_return",
    "vwap_slope",
)


class PlaceboKind(str, Enum):
    SYMBOL_PERMUTATION = "SYMBOL_PERMUTATION"
    TARGET_PERMUTATION = "TARGET_PERMUTATION"
    TARGET_TIME_SHIFT = "TARGET_TIME_SHIFT"
    FACTOR_LAG = "FACTOR_LAG"
    DETERMINISTIC_RANDOM_RANKING = "DETERMINISTIC_RANDOM_RANKING"


@dataclass(frozen=True, slots=True)
class FrozenPlaceboProtocol:
    protocol_id: ArtifactId
    protocol_hash: str
    factor_id: str
    target_id: str
    seed: int
    kinds: tuple[PlaceboKind, ...]
    schema_version: str = "alpha-placebo-protocol/v1"

    def __post_init__(self) -> None:
        if self.factor_id not in _INTRADAY_FACTORS:
            raise ValueError("placebo factor is outside the frozen intraday family")
        if not self.target_id.strip():
            raise ValueError("placebo target must be identified")
        if self.kinds != tuple(sorted(set(self.kinds), key=lambda item: item.value)):
            raise ValueError("placebo kinds must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.protocol_hash:
            raise ValueError("placebo protocol hash mismatch")
        if str(self.protocol_id) != f"alpha-placebo-protocol:{self.protocol_hash[7:]}":
            raise ValueError("placebo protocol identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        factor_id: str,
        target_id: str,
        seed: int,
        kinds: tuple[PlaceboKind, ...],
    ) -> FrozenPlaceboProtocol:
        ordered = tuple(sorted(set(kinds), key=lambda item: item.value))
        payload = {
            "schema_version": "alpha-placebo-protocol/v1",
            "factor_id": factor_id,
            "target_id": target_id,
            "seed": seed,
            "kinds": [item.value for item in ordered],
        }
        digest = canonical_hash(payload)
        return cls(
            ArtifactId(f"alpha-placebo-protocol:{digest[7:]}"),
            digest,
            factor_id,
            target_id,
            seed,
            ordered,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "ALPHA_PLACEBO_PROTOCOL", self.protocol_id, self.protocol_hash
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "factor_id": self.factor_id,
            "target_id": self.target_id,
            "seed": self.seed,
            "kinds": [item.value for item in self.kinds],
        }


@dataclass(frozen=True, slots=True)
class AlphaObservation:
    session: date
    symbol: str
    factor_value: Decimal
    target_return: Decimal


@dataclass(frozen=True, slots=True)
class PlaceboResult:
    protocol_reference: ValidationArtifactReference
    kind: PlaceboKind
    observations: tuple[AlphaObservation, ...]
    result_hash: str


def apply_placebo(
    protocol: FrozenPlaceboProtocol,
    *,
    kind: PlaceboKind,
    observations: tuple[AlphaObservation, ...],
) -> PlaceboResult:
    """Apply one pre-registered deterministic negative control."""

    if kind not in protocol.kinds:
        raise ValueError("placebo kind was not frozen")
    ordered = _ordered_alpha(observations)
    if not ordered:
        raise ValueError("placebo requires observations")
    transformed: list[AlphaObservation] = []
    by_session = _alpha_by_session(ordered)
    if kind in {PlaceboKind.SYMBOL_PERMUTATION, PlaceboKind.TARGET_PERMUTATION}:
        for session, values in by_session.items():
            shuffled = list(range(len(values)))
            _random(protocol.seed, kind.value, session.isoformat()).shuffle(shuffled)
            for index, item in enumerate(values):
                donor = values[shuffled[index]]
                transformed.append(
                    AlphaObservation(
                        session=item.session,
                        symbol=item.symbol,
                        factor_value=(
                            donor.factor_value
                            if kind is PlaceboKind.SYMBOL_PERMUTATION
                            else item.factor_value
                        ),
                        target_return=(
                            donor.target_return
                            if kind is PlaceboKind.TARGET_PERMUTATION
                            else item.target_return
                        ),
                    )
                )
    elif kind is PlaceboKind.DETERMINISTIC_RANDOM_RANKING:
        transformed.extend(
            AlphaObservation(
                item.session,
                item.symbol,
                Decimal(
                    _random(
                        protocol.seed,
                        kind.value,
                        item.session.isoformat(),
                        item.symbol,
                    ).randrange(1, 10**12)
                ),
                item.target_return,
            )
            for item in ordered
        )
    else:
        sessions = tuple(by_session)
        for previous, current in zip(sessions, sessions[1:], strict=False):
            previous_by_symbol = {item.symbol: item for item in by_session[previous]}
            current_by_symbol = {item.symbol: item for item in by_session[current]}
            for symbol in sorted(previous_by_symbol.keys() & current_by_symbol.keys()):
                old = previous_by_symbol[symbol]
                new = current_by_symbol[symbol]
                transformed.append(
                    AlphaObservation(
                        current,
                        symbol,
                        old.factor_value if kind is PlaceboKind.FACTOR_LAG else new.factor_value,
                        new.target_return if kind is PlaceboKind.FACTOR_LAG else old.target_return,
                    )
                )
    result = _ordered_alpha(tuple(transformed))
    digest = canonical_hash(
        {
            "protocol": protocol.reference.to_canonical_dict(),
            "kind": kind.value,
            "observations": [
                {
                    "session": item.session.isoformat(),
                    "symbol": item.symbol,
                    "factor_value": str(item.factor_value),
                    "target_return": str(item.target_return),
                }
                for item in result
            ],
        }
    )
    return PlaceboResult(protocol.reference, kind, result, digest)


class ExecutionPriceProxy(str, Enum):
    DECISION_REFERENCE_ONLY = "DECISION_REFERENCE_ONLY"
    NEXT_OBSERVABLE_PRICE = "NEXT_OBSERVABLE_PRICE"
    NEXT_BAR_OPEN = "NEXT_BAR_OPEN"
    SESSION_CLOSE = "SESSION_CLOSE"


@dataclass(frozen=True, slots=True)
class ExecutionPriceInputs:
    decision_reference: Decimal
    next_observable_price: Decimal | None
    next_bar_open: Decimal | None
    session_close: Decimal | None
    target_price: Decimal


@dataclass(frozen=True, slots=True)
class ExecutionTimingDiagnostic:
    proxy: ExecutionPriceProxy
    information_cutoff_price: Decimal
    entry_price: Decimal
    target_reference_price: Decimal
    gross_return: Decimal
    executable: bool
    limitations: tuple[str, ...]


def diagnose_execution_price(
    inputs: ExecutionPriceInputs,
    proxy: ExecutionPriceProxy,
) -> ExecutionTimingDiagnostic:
    prices = {
        ExecutionPriceProxy.DECISION_REFERENCE_ONLY: inputs.decision_reference,
        ExecutionPriceProxy.NEXT_OBSERVABLE_PRICE: inputs.next_observable_price,
        ExecutionPriceProxy.NEXT_BAR_OPEN: inputs.next_bar_open,
        ExecutionPriceProxy.SESSION_CLOSE: inputs.session_close,
    }
    entry = prices[proxy]
    if entry is None:
        raise ValueError(f"execution proxy unavailable: {proxy.value}")
    if min(inputs.decision_reference, entry, inputs.target_price) <= 0:
        raise ValueError("execution prices must be positive")
    executable = proxy is not ExecutionPriceProxy.DECISION_REFERENCE_ONLY
    return ExecutionTimingDiagnostic(
        proxy=proxy,
        information_cutoff_price=inputs.decision_reference,
        entry_price=entry,
        target_reference_price=inputs.target_price,
        gross_return=inputs.target_price / entry - Decimal("1"),
        executable=executable,
        limitations=(
            ("RESEARCH_REFERENCE_PRICE_NOT_EXECUTABLE",)
            if not executable
            else ("EXECUTION_PROXY_NOT_FILL_PROOF",)
        ),
    )


@dataclass(frozen=True, slots=True)
class FactorObservation:
    session: date
    symbol: str
    factors: Mapping[str, Decimal]
    target_return: Decimal


@dataclass(frozen=True, slots=True)
class FactorPairDiagnostic:
    left: str
    right: str
    correlation: Decimal | None
    rank_correlation: Decimal | None


@dataclass(frozen=True, slots=True)
class FactorIncrementalDiagnostic:
    factor_id: str
    leave_one_out_rank_ic: Decimal | None
    incremental_rank_ic: Decimal | None
    residual_rank_ic: Decimal | None


@dataclass(frozen=True, slots=True)
class FactorRedundancyResult:
    factor_ids: tuple[str, ...]
    full_composite_rank_ic: Decimal | None
    pairs: tuple[FactorPairDiagnostic, ...]
    incremental: tuple[FactorIncrementalDiagnostic, ...]
    status: str


def evaluate_factor_redundancy(
    observations: tuple[FactorObservation, ...],
) -> FactorRedundancyResult:
    if not observations:
        return FactorRedundancyResult((), None, (), (), "NOT_ESTIMABLE")
    factor_ids = tuple(sorted(observations[0].factors))
    if factor_ids != _INTRADAY_FACTORS or any(tuple(sorted(item.factors)) != factor_ids for item in observations):
        raise ValueError("redundancy diagnostic requires the exact intraday factor family")
    pairs: list[FactorPairDiagnostic] = []
    for left_index, left in enumerate(factor_ids):
        for right in factor_ids[left_index + 1 :]:
            left_values = tuple(item.factors[left] for item in observations)
            right_values = tuple(item.factors[right] for item in observations)
            pairs.append(
                FactorPairDiagnostic(
                    left,
                    right,
                    _correlation(left_values, right_values),
                    _correlation(_ranks(left_values), _ranks(right_values)),
                )
            )
    full = _daily_composite_rank_ic(observations, factor_ids)
    incremental: list[FactorIncrementalDiagnostic] = []
    for factor_id in factor_ids:
        others = tuple(item for item in factor_ids if item != factor_id)
        leave_one_out = _daily_composite_rank_ic(observations, others)
        residuals: list[Decimal] = []
        targets: list[Decimal] = []
        for values in _factor_by_session(observations).values():
            factor_rank = _ranks(tuple(item.factors[factor_id] for item in values))
            other_ranks = tuple(
                _ranks(tuple(item.factors[other] for item in values)) for other in others
            )
            for index, item in enumerate(values):
                expected = sum((rank[index] for rank in other_ranks), Decimal("0")) / Decimal(len(other_ranks))
                residuals.append(factor_rank[index] - expected)
                targets.append(item.target_return)
        residual_ic = _correlation(_ranks(tuple(residuals)), _ranks(tuple(targets)))
        incremental.append(
            FactorIncrementalDiagnostic(
                factor_id,
                leave_one_out,
                None if full is None or leave_one_out is None else full - leave_one_out,
                residual_ic,
            )
        )
    estimable_pairs = tuple(
        abs(item.rank_correlation)
        for item in pairs
        if item.rank_correlation is not None
    )
    if not estimable_pairs or full is None:
        status = "NOT_ESTIMABLE"
    elif all(item >= Decimal("0.9") for item in estimable_pairs):
        status = "LATENT_FACTOR_MULTIPLE_EXPRESSIONS"
    elif any(item >= Decimal("0.9") for item in estimable_pairs):
        status = "PARTIALLY_REDUNDANT"
    else:
        status = "DISTINCT_INFORMATION_SUPPORTED"
    return FactorRedundancyResult(
        factor_ids,
        full,
        tuple(pairs),
        tuple(incremental),
        status,
    )


@dataclass(frozen=True, slots=True)
class SessionEstimate:
    session: date
    value: Decimal


@dataclass(frozen=True, slots=True)
class MovingBlockInferenceProtocol:
    protocol_id: ArtifactId
    protocol_hash: str
    iterations: int
    block_lengths: tuple[int, ...]
    confidence_level: Decimal
    seed: int

    @classmethod
    def create(
        cls,
        *,
        iterations: int,
        block_lengths: tuple[int, ...],
        confidence_level: Decimal,
        seed: int,
    ) -> MovingBlockInferenceProtocol:
        ordered = tuple(sorted(set(block_lengths)))
        if iterations <= 0 or not ordered or any(item <= 0 for item in ordered):
            raise ValueError("moving-block protocol dimensions must be positive")
        if not Decimal("0") < confidence_level < Decimal("1"):
            raise ValueError("confidence level must be within (0, 1)")
        payload = {
            "schema_version": "alpha-moving-block-inference/v1",
            "iterations": iterations,
            "block_lengths": list(ordered),
            "confidence_level": str(confidence_level),
            "seed": seed,
        }
        digest = canonical_hash(payload)
        return cls(
            ArtifactId(f"alpha-inference-protocol:{digest[7:]}"),
            digest,
            iterations,
            ordered,
            confidence_level,
            seed,
        )


@dataclass(frozen=True, slots=True)
class BlockSensitivityEstimate:
    block_length: int
    estimate: Decimal
    lower: Decimal
    upper: Decimal


@dataclass(frozen=True, slots=True)
class RobustInferenceResult:
    protocol_reference: ValidationArtifactReference
    observation_count: int
    sensitivity: tuple[BlockSensitivityEstimate, ...]
    temporal_stability: str


def evaluate_robust_inference(
    protocol: MovingBlockInferenceProtocol,
    observations: tuple[SessionEstimate, ...],
) -> RobustInferenceResult:
    ordered = tuple(sorted(observations, key=lambda item: item.session))
    if len(ordered) != len({item.session for item in ordered}):
        raise ValueError("session estimates must be unique")
    if len(ordered) < max(protocol.block_lengths):
        raise ValueError("moving-block sample is shorter than the frozen block length")
    values = tuple(item.value for item in ordered)
    sensitivity: list[BlockSensitivityEstimate] = []
    for block_length in protocol.block_lengths:
        estimate, lower, upper = moving_block_mean_interval(
            values,
            iterations=protocol.iterations,
            block_sessions=block_length,
            confidence_level=protocol.confidence_level,
            seed=f"{protocol.seed}|ALPHA_CORRECTNESS|{block_length}",
        )
        sensitivity.append(
            BlockSensitivityEstimate(
                block_length,
                estimate,
                lower,
                upper,
            )
        )
    midpoint = len(values) // 2
    first = _mean(values[:midpoint])
    second = _mean(values[midpoint:])
    stable = first == 0 or second == 0 or (first > 0) == (second > 0)
    return RobustInferenceResult(
        ValidationArtifactReference(
            "ALPHA_INFERENCE_PROTOCOL", protocol.protocol_id, protocol.protocol_hash
        ),
        len(values),
        tuple(sensitivity),
        "STABLE" if stable else "UNSTABLE",
    )


def _daily_composite_rank_ic(
    observations: tuple[FactorObservation, ...], factor_ids: tuple[str, ...]
) -> Decimal | None:
    daily: list[Decimal] = []
    for values in _factor_by_session(observations).values():
        if len(values) < 3:
            continue
        ranked = tuple(
            _ranks(tuple(item.factors[factor] for item in values))
            for factor in factor_ids
        )
        scores = tuple(
            sum((rank[index] for rank in ranked), Decimal("0")) / Decimal(len(ranked))
            for index in range(len(values))
        )
        target = _ranks(tuple(item.target_return for item in values))
        value = _correlation(scores, target)
        if value is not None:
            daily.append(value)
    return None if not daily else _mean(tuple(daily))


def _factor_by_session(
    observations: tuple[FactorObservation, ...],
) -> dict[date, tuple[FactorObservation, ...]]:
    groups: dict[date, list[FactorObservation]] = {}
    for item in observations:
        groups.setdefault(item.session, []).append(item)
    return {
        key: tuple(sorted(values, key=lambda item: item.symbol))
        for key, values in sorted(groups.items())
    }


def _alpha_by_session(
    observations: tuple[AlphaObservation, ...],
) -> dict[date, tuple[AlphaObservation, ...]]:
    groups: dict[date, list[AlphaObservation]] = {}
    for item in observations:
        groups.setdefault(item.session, []).append(item)
    return {
        key: tuple(sorted(values, key=lambda item: item.symbol))
        for key, values in sorted(groups.items())
    }


def _ordered_alpha(
    observations: tuple[AlphaObservation, ...],
) -> tuple[AlphaObservation, ...]:
    ordered = tuple(sorted(observations, key=lambda item: (item.session, item.symbol)))
    keys = tuple((item.session, item.symbol) for item in ordered)
    if len(keys) != len(set(keys)):
        raise ValueError("alpha observations must be unique by session and symbol")
    return ordered


def _ranks(values: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    indexed = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    result = [Decimal("0")] * len(values)
    position = 0
    while position < len(indexed):
        end = position + 1
        while end < len(indexed) and indexed[end][1] == indexed[position][1]:
            end += 1
        average = (Decimal(position + 1) + Decimal(end)) / Decimal("2")
        for index, _value in indexed[position:end]:
            result[index] = average
        position = end
    return tuple(result)


def _correlation(xs: tuple[Decimal, ...], ys: tuple[Decimal, ...]) -> Decimal | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    with localcontext() as context:
        context.prec = 48
        mean_x = _mean(xs)
        mean_y = _mean(ys)
        covariance = sum(
            ((left - mean_x) * (right - mean_y) for left, right in zip(xs, ys, strict=True)),
            Decimal("0"),
        )
        variance_x = sum(((item - mean_x) ** 2 for item in xs), Decimal("0"))
        variance_y = sum(((item - mean_y) ** 2 for item in ys), Decimal("0"))
        if variance_x == 0 or variance_y == 0:
            return None
        value = covariance / Decimal(str(sqrt(float(variance_x * variance_y))))
        if abs(value - Decimal("1")) < Decimal("1e-24"):
            return Decimal("1")
        if abs(value + Decimal("1")) < Decimal("1e-24"):
            return Decimal("-1")
        return value


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def _random(seed: int, *parts: str) -> Random:
    digest = canonical_hash({"seed": seed, "parts": list(parts)})
    return Random(int(digest[7:23], 16))


__all__ = [
    "AlphaObservation",
    "BlockSensitivityEstimate",
    "ExecutionPriceInputs",
    "ExecutionPriceProxy",
    "ExecutionTimingDiagnostic",
    "FactorIncrementalDiagnostic",
    "FactorObservation",
    "FactorPairDiagnostic",
    "FactorRedundancyResult",
    "FrozenPlaceboProtocol",
    "MovingBlockInferenceProtocol",
    "PlaceboKind",
    "PlaceboResult",
    "RobustInferenceResult",
    "SessionEstimate",
    "apply_placebo",
    "diagnose_execution_price",
    "evaluate_factor_redundancy",
    "evaluate_robust_inference",
]
