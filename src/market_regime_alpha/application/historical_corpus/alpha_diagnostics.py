"""Frozen correctness diagnostics for the discovered intraday factor family.

The functions consume research observations and emit content-addressed engineering
diagnostics.  They do not select a model, mutate a Candidate policy, or grant Alpha.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, localcontext
from enum import Enum
from math import sqrt
from random import Random
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    MultipleTestingMethod,
    adjust_multiple_testing,
    moving_block_mean_interval,
)
from market_regime_alpha.evidence.canonical import canonical_datetime
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

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": str(self.protocol_id),
            "protocol_hash": self.protocol_hash,
            **self.identity_payload(),
        }


@dataclass(frozen=True, slots=True)
class AlphaObservation:
    session: date
    symbol: str
    factor_value: Decimal
    target_return: Decimal


@dataclass(frozen=True, slots=True)
class PlaceboResult:
    protocol: FrozenPlaceboProtocol
    factor_id: str
    target_id: str
    kind: PlaceboKind
    observations: tuple[AlphaObservation, ...]
    result_hash: str

    def __post_init__(self) -> None:
        if (
            self.factor_id != self.protocol.factor_id
            or self.target_id != self.protocol.target_id
            or self.kind not in self.protocol.kinds
        ):
            raise ValueError("placebo result drifted from its frozen protocol")
        ordered = _ordered_alpha(self.observations)
        if ordered != self.observations or not ordered:
            raise ValueError("placebo result observations must be non-empty and sorted")
        if (
            canonical_hash(_placebo_result_payload(self.protocol, self.kind, ordered))
            != self.result_hash
        ):
            raise ValueError("placebo result hash mismatch")

    @property
    def protocol_reference(self) -> ValidationArtifactReference:
        return self.protocol.reference

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol.to_canonical_dict(),
            "factor_id": self.factor_id,
            "target_id": self.target_id,
            "kind": self.kind.value,
            "observations": [
                {
                    "session": item.session.isoformat(),
                    "symbol": item.symbol,
                    "factor_value": str(item.factor_value),
                    "target_return": str(item.target_return),
                }
                for item in self.observations
            ],
            "result_hash": self.result_hash,
        }


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
    digest = canonical_hash(_placebo_result_payload(protocol, kind, result))
    return PlaceboResult(
        protocol,
        protocol.factor_id,
        protocol.target_id,
        kind,
        result,
        digest,
    )


class ExecutionPriceProxy(str, Enum):
    DECISION_REFERENCE_ONLY = "DECISION_REFERENCE_ONLY"
    NEXT_OBSERVABLE_PRICE = "NEXT_OBSERVABLE_PRICE"
    NEXT_BAR_OPEN = "NEXT_BAR_OPEN"
    SESSION_CLOSE = "SESSION_CLOSE"


@dataclass(frozen=True, slots=True)
class TimedPriceObservation:
    price: Decimal
    observed_at: datetime
    available_at: datetime
    source_reference: ValidationArtifactReference

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("execution observation price must be positive")
        canonical_datetime(self.observed_at)
        canonical_datetime(self.available_at)
        if self.available_at < self.observed_at:
            raise ValueError("execution observation cannot be available before observation")


@dataclass(frozen=True, slots=True)
class ExecutionPriceInputs:
    information_cutoff: datetime
    decision_reference: TimedPriceObservation
    next_observable_price: TimedPriceObservation | None
    next_bar_open: TimedPriceObservation | None
    session_close: TimedPriceObservation | None
    target_reference: TimedPriceObservation

    def __post_init__(self) -> None:
        canonical_datetime(self.information_cutoff)
        if (
            self.decision_reference.observed_at > self.information_cutoff
            or self.decision_reference.available_at > self.information_cutoff
        ):
            raise ValueError("Decision reference exceeds Information Cutoff")
        for value in (
            self.next_observable_price,
            self.next_bar_open,
            self.session_close,
        ):
            if value is not None and (
                value.observed_at <= self.information_cutoff
                or value.available_at <= self.information_cutoff
                or value.observed_at >= self.target_reference.observed_at
                or value.available_at > self.target_reference.available_at
            ):
                raise ValueError("executable proxy timing is outside its observable window")
        if self.target_reference.observed_at <= self.information_cutoff:
            raise ValueError("Target reference must follow Information Cutoff")


@dataclass(frozen=True, slots=True)
class ExecutionTimingDiagnostic:
    proxy: ExecutionPriceProxy
    information_cutoff_price: Decimal
    entry_price: Decimal
    target_reference_price: Decimal
    gross_return: Decimal
    executable: bool
    information_cutoff: datetime
    entry_observed_at: datetime
    entry_available_at: datetime
    target_observed_at: datetime
    target_available_at: datetime
    information_cutoff_reference: ValidationArtifactReference
    source_reference: ValidationArtifactReference
    target_source_reference: ValidationArtifactReference
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for price_value in (
            self.information_cutoff_price,
            self.entry_price,
            self.target_reference_price,
        ):
            if price_value <= 0:
                raise ValueError("execution diagnostic prices must be positive")
        for timestamp_value in (
            self.information_cutoff,
            self.entry_observed_at,
            self.entry_available_at,
            self.target_observed_at,
            self.target_available_at,
        ):
            canonical_datetime(timestamp_value)
        if self.entry_observed_at > self.entry_available_at:
            raise ValueError("execution entry availability precedes observation")
        if self.target_observed_at > self.target_available_at:
            raise ValueError("execution Target availability precedes observation")
        if self.proxy is ExecutionPriceProxy.DECISION_REFERENCE_ONLY:
            if self.executable or self.entry_observed_at > self.information_cutoff:
                raise ValueError("Decision reference is research-only, not executable")
        elif (
            not self.executable
            or self.entry_observed_at <= self.information_cutoff
            or self.entry_available_at <= self.information_cutoff
        ):
            raise ValueError("executable proxy is outside its observable window")
        if (
            self.entry_observed_at >= self.target_observed_at
            or self.entry_available_at > self.target_available_at
        ):
            raise ValueError("execution proxy does not precede Target observation")
        if (
            self.gross_return
            != self.target_reference_price / self.entry_price - Decimal("1")
        ):
            raise ValueError("execution diagnostic return disagrees with prices")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "proxy": self.proxy.value,
            "information_cutoff_price": str(self.information_cutoff_price),
            "entry_price": str(self.entry_price),
            "target_reference_price": str(self.target_reference_price),
            "gross_return": str(self.gross_return),
            "executable": self.executable,
            "information_cutoff": canonical_datetime(self.information_cutoff),
            "entry_observed_at": canonical_datetime(self.entry_observed_at),
            "entry_available_at": canonical_datetime(self.entry_available_at),
            "target_observed_at": canonical_datetime(self.target_observed_at),
            "target_available_at": canonical_datetime(self.target_available_at),
            "information_cutoff_reference": self.information_cutoff_reference.to_canonical_dict(),
            "source_reference": self.source_reference.to_canonical_dict(),
            "target_source_reference": self.target_source_reference.to_canonical_dict(),
            "limitations": list(self.limitations),
        }


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
    executable = proxy is not ExecutionPriceProxy.DECISION_REFERENCE_ONLY
    return ExecutionTimingDiagnostic(
        proxy=proxy,
        information_cutoff_price=inputs.decision_reference.price,
        entry_price=entry.price,
        target_reference_price=inputs.target_reference.price,
        gross_return=inputs.target_reference.price / entry.price - Decimal("1"),
        executable=executable,
        information_cutoff=inputs.information_cutoff,
        entry_observed_at=entry.observed_at,
        entry_available_at=entry.available_at,
        target_observed_at=inputs.target_reference.observed_at,
        target_available_at=inputs.target_reference.available_at,
        information_cutoff_reference=inputs.decision_reference.source_reference,
        source_reference=entry.source_reference,
        target_source_reference=inputs.target_reference.source_reference,
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

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "right": self.right,
            "correlation": _decimal_text(self.correlation),
            "rank_correlation": _decimal_text(self.rank_correlation),
        }


@dataclass(frozen=True, slots=True)
class FactorIncrementalDiagnostic:
    factor_id: str
    leave_one_out_rank_ic: Decimal | None
    incremental_rank_ic: Decimal | None
    residual_rank_ic: Decimal | None

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "leave_one_out_rank_ic": _decimal_text(self.leave_one_out_rank_ic),
            "incremental_rank_ic": _decimal_text(self.incremental_rank_ic),
            "residual_rank_ic": _decimal_text(self.residual_rank_ic),
        }


@dataclass(frozen=True, slots=True)
class FactorRedundancyResult:
    factor_ids: tuple[str, ...]
    full_composite_rank_ic: Decimal | None
    pairs: tuple[FactorPairDiagnostic, ...]
    incremental: tuple[FactorIncrementalDiagnostic, ...]
    status: str

    def __post_init__(self) -> None:
        if self.factor_ids != tuple(sorted(set(self.factor_ids))):
            raise ValueError("redundancy Factor identities must be unique and sorted")
        if self.status not in {
            "DISTINCT_INFORMATION_SUPPORTED",
            "LATENT_FACTOR_MULTIPLE_EXPRESSIONS",
            "PARTIALLY_REDUNDANT",
            "NOT_ESTIMABLE",
        }:
            raise ValueError("unsupported redundancy interpretation")
        if self.status != "NOT_ESTIMABLE" and (
            len(self.incremental) != len(self.factor_ids)
            or {item.factor_id for item in self.incremental} != set(self.factor_ids)
        ):
            raise ValueError("redundancy incremental suite is incomplete")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "factor_ids": list(self.factor_ids),
            "full_composite_rank_ic": _decimal_text(self.full_composite_rank_ic),
            "pairs": [item.to_canonical_dict() for item in self.pairs],
            "incremental": [item.to_canonical_dict() for item in self.incremental],
            "status": self.status,
        }


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
            daily_linear: list[Decimal] = []
            daily_rank: list[Decimal] = []
            for values in _factor_by_session(observations).values():
                linear = _correlation(
                    tuple(item.factors[left] for item in values),
                    tuple(item.factors[right] for item in values),
                )
                ranked = _correlation(
                    _ranks(tuple(item.factors[left] for item in values)),
                    _ranks(tuple(item.factors[right] for item in values)),
                )
                if linear is not None:
                    daily_linear.append(linear)
                if ranked is not None:
                    daily_rank.append(ranked)
            pairs.append(
                FactorPairDiagnostic(
                    left,
                    right,
                    None if not daily_linear else _mean(tuple(daily_linear)),
                    None if not daily_rank else _mean(tuple(daily_rank)),
                )
            )
    full = _daily_composite_rank_ic(observations, factor_ids)
    incremental: list[FactorIncrementalDiagnostic] = []
    for factor_id in factor_ids:
        others = tuple(item for item in factor_ids if item != factor_id)
        leave_one_out = _daily_composite_rank_ic(observations, others)
        residual_daily: list[Decimal] = []
        for values in _factor_by_session(observations).values():
            if len(values) < 3:
                continue
            factor_rank = _ranks(tuple(item.factors[factor_id] for item in values))
            other_ranks = tuple(
                _ranks(tuple(item.factors[other] for item in values)) for other in others
            )
            residuals = _orthogonal_residual(factor_rank, other_ranks)
            residual_ic = _correlation(
                _ranks(residuals),
                _ranks(tuple(item.target_return for item in values)),
            )
            if residual_ic is not None:
                residual_daily.append(residual_ic)
        residual_ic = (
            None if not residual_daily else _mean(tuple(residual_daily))
        )
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
    residual_strength = tuple(
        abs(item.residual_rank_ic)
        for item in incremental
        if item.residual_rank_ic is not None
    )
    incremental_strength = tuple(
        abs(item.incremental_rank_ic)
        for item in incremental
        if item.incremental_rank_ic is not None
    )
    if (
        not estimable_pairs
        or full is None
        or not residual_strength
        or not incremental_strength
    ):
        status = "NOT_ESTIMABLE"
    elif all(item >= Decimal("0.9") for item in estimable_pairs) and all(
        item < Decimal("0.02") for item in residual_strength
    ):
        status = "LATENT_FACTOR_MULTIPLE_EXPRESSIONS"
    elif any(item >= Decimal("0.9") for item in estimable_pairs) or any(
        item < Decimal("0.02") for item in residual_strength
    ) or any(item < Decimal("0.005") for item in incremental_strength):
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


def _orthogonal_residual(
    dependent: tuple[Decimal, ...],
    regressors: tuple[tuple[Decimal, ...], ...],
) -> tuple[Decimal, ...]:
    """Residualize ranks against an intercept and the full regressor span."""

    mean_dependent = _mean(dependent)
    residual = tuple(item - mean_dependent for item in dependent)
    basis: list[tuple[Decimal, ...]] = []
    for regressor in regressors:
        centered = tuple(item - _mean(regressor) for item in regressor)
        candidate = list(centered)
        for vector in basis:
            denominator = sum((item * item for item in vector), Decimal("0"))
            if denominator == 0:
                continue
            coefficient = (
                sum(
                    (left * right for left, right in zip(candidate, vector, strict=True)),
                    Decimal("0"),
                )
                / denominator
            )
            candidate = [
                left - coefficient * right
                for left, right in zip(candidate, vector, strict=True)
            ]
        vector = tuple(candidate)
        if sum((item * item for item in vector), Decimal("0")) > 0:
            basis.append(vector)
    for vector in basis:
        denominator = sum((item * item for item in vector), Decimal("0"))
        coefficient = (
            sum(
                (left * right for left, right in zip(residual, vector, strict=True)),
                Decimal("0"),
            )
            / denominator
        )
        residual = tuple(
            left - coefficient * right
            for left, right in zip(residual, vector, strict=True)
        )
    return residual


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
    multiple_testing_method: MultipleTestingMethod

    def __post_init__(self) -> None:
        if (
            self.iterations <= 0
            or self.block_lengths != tuple(sorted(set(self.block_lengths)))
            or not self.block_lengths
            or any(item <= 0 for item in self.block_lengths)
            or not Decimal("0") < self.confidence_level < Decimal("1")
        ):
            raise ValueError("moving-block protocol dimensions are invalid")
        digest = canonical_hash(_moving_block_protocol_payload(self))
        if (
            digest != self.protocol_hash
            or self.protocol_id != ArtifactId(f"alpha-inference-protocol:{digest[7:]}")
        ):
            raise ValueError("moving-block protocol identity mismatch")

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "ALPHA_INFERENCE_PROTOCOL", self.protocol_id, self.protocol_hash
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": str(self.protocol_id),
            "protocol_hash": self.protocol_hash,
            "iterations": self.iterations,
            "block_lengths": list(self.block_lengths),
            "confidence_level": str(self.confidence_level),
            "seed": self.seed,
            "multiple_testing_method": self.multiple_testing_method.value,
        }

    @classmethod
    def create(
        cls,
        *,
        iterations: int,
        block_lengths: tuple[int, ...],
        confidence_level: Decimal,
        seed: int,
        multiple_testing_method: MultipleTestingMethod = (
            MultipleTestingMethod.BENJAMINI_HOCHBERG
        ),
    ) -> MovingBlockInferenceProtocol:
        ordered = tuple(sorted(set(block_lengths)))
        if iterations <= 0 or not ordered or any(item <= 0 for item in ordered):
            raise ValueError("moving-block protocol dimensions must be positive")
        if not Decimal("0") < confidence_level < Decimal("1"):
            raise ValueError("confidence level must be within (0, 1)")
        payload = _moving_block_protocol_payload_values(
            iterations=iterations,
            block_lengths=ordered,
            confidence_level=confidence_level,
            seed=seed,
            multiple_testing_method=multiple_testing_method,
        )
        digest = canonical_hash(payload)
        return cls(
            ArtifactId(f"alpha-inference-protocol:{digest[7:]}"),
            digest,
            iterations,
            ordered,
            confidence_level,
            seed,
            multiple_testing_method,
        )


@dataclass(frozen=True, slots=True)
class BlockSensitivityEstimate:
    block_length: int
    estimate: Decimal
    lower: Decimal
    upper: Decimal

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "block_length": self.block_length,
            "estimate": str(self.estimate),
            "lower": str(self.lower),
            "upper": str(self.upper),
        }


def _moving_block_protocol_payload(
    value: MovingBlockInferenceProtocol,
) -> dict[str, Any]:
    return _moving_block_protocol_payload_values(
        iterations=value.iterations,
        block_lengths=value.block_lengths,
        confidence_level=value.confidence_level,
        seed=value.seed,
        multiple_testing_method=value.multiple_testing_method,
    )


def _moving_block_protocol_payload_values(
    *,
    iterations: int,
    block_lengths: tuple[int, ...],
    confidence_level: Decimal,
    seed: int,
    multiple_testing_method: MultipleTestingMethod,
) -> dict[str, Any]:
    return {
        "schema_version": "alpha-moving-block-inference/v1",
        "iterations": iterations,
        "block_lengths": list(block_lengths),
        "confidence_level": str(confidence_level),
        "seed": seed,
        "multiple_testing_method": multiple_testing_method.value,
    }


@dataclass(frozen=True, slots=True)
class RobustInferenceResult:
    protocol: MovingBlockInferenceProtocol
    observation_count: int
    sensitivity: tuple[BlockSensitivityEstimate, ...]
    temporal_stability: str
    raw_p_value: Decimal
    adjusted_p_value: Decimal
    multiple_testing_method: MultipleTestingMethod

    def __post_init__(self) -> None:
        if (
            self.multiple_testing_method is not self.protocol.multiple_testing_method
            or tuple(item.block_length for item in self.sensitivity)
            != self.protocol.block_lengths
            or self.observation_count < max(self.protocol.block_lengths)
            or not Decimal("0") <= self.raw_p_value <= Decimal("1")
            or not Decimal("0") <= self.adjusted_p_value <= Decimal("1")
        ):
            raise ValueError("robust inference result drifted from frozen protocol")

    @property
    def protocol_reference(self) -> ValidationArtifactReference:
        return self.protocol.reference

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol.to_canonical_dict(),
            "observation_count": self.observation_count,
            "sensitivity": [item.to_canonical_dict() for item in self.sensitivity],
            "temporal_stability": self.temporal_stability,
            "raw_p_value": str(self.raw_p_value),
            "adjusted_p_value": str(self.adjusted_p_value),
            "multiple_testing_method": self.multiple_testing_method.value,
        }


def evaluate_robust_inference(
    protocol: MovingBlockInferenceProtocol,
    observations: tuple[SessionEstimate, ...],
) -> RobustInferenceResult:
    return evaluate_robust_inference_family(
        protocol, {"PRIMARY": observations}
    )["PRIMARY"]


def evaluate_robust_inference_family(
    protocol: MovingBlockInferenceProtocol,
    families: Mapping[str, tuple[SessionEstimate, ...]],
) -> Mapping[str, RobustInferenceResult]:
    if not families:
        raise ValueError("robust inference family must be non-empty")
    ordered_names = tuple(sorted(families))
    provisional = tuple(
        _evaluate_robust_inference_unadjusted(protocol, families[name])
        for name in ordered_names
    )
    adjusted = adjust_multiple_testing(
        tuple(item.raw_p_value for item in provisional),
        protocol.multiple_testing_method,
    )
    return {
        name: RobustInferenceResult(
            protocol,
            item.observation_count,
            item.sensitivity,
            item.temporal_stability,
            item.raw_p_value,
            adjusted_p_value,
            protocol.multiple_testing_method,
        )
        for name, item, adjusted_p_value in zip(
            ordered_names, provisional, adjusted, strict=True
        )
    }


def factor_rank_ic_session_estimates(
    observations: tuple[FactorObservation, ...],
    *,
    factor_id: str,
) -> tuple[SessionEstimate, ...]:
    """Derive the exact per-session RankIC series used by block inference."""

    if factor_id not in _INTRADAY_FACTORS:
        raise ValueError("session RankIC Factor is outside the frozen intraday family")
    estimates: list[SessionEstimate] = []
    for session, values in _factor_by_session(observations).items():
        if len(values) < 3:
            continue
        estimate = _correlation(
            _ranks(tuple(item.factors[factor_id] for item in values)),
            _ranks(tuple(item.target_return for item in values)),
        )
        if estimate is not None:
            estimates.append(SessionEstimate(session, estimate))
    return tuple(estimates)


def _evaluate_robust_inference_unadjusted(
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
    non_positive = Decimal(sum(item <= 0 for item in values)) / Decimal(len(values))
    non_negative = Decimal(sum(item >= 0 for item in values)) / Decimal(len(values))
    raw_p_value = min(Decimal("1"), Decimal("2") * min(non_positive, non_negative))
    return RobustInferenceResult(
        protocol,
        len(values),
        tuple(sensitivity),
        "STABLE" if stable else "UNSTABLE",
        raw_p_value,
        raw_p_value,
        protocol.multiple_testing_method,
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


def _placebo_result_payload(
    protocol: FrozenPlaceboProtocol,
    kind: PlaceboKind,
    observations: tuple[AlphaObservation, ...],
) -> dict[str, Any]:
    return {
        "protocol": protocol.reference.to_canonical_dict(),
        "kind": kind.value,
        "observations": [
            {
                "session": item.session.isoformat(),
                "symbol": item.symbol,
                "factor_value": str(item.factor_value),
                "target_return": str(item.target_return),
            }
            for item in observations
        ],
    }


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


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "AlphaObservation",
    "BlockSensitivityEstimate",
    "ExecutionPriceInputs",
    "ExecutionPriceProxy",
    "ExecutionTimingDiagnostic",
    "TimedPriceObservation",
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
    "evaluate_robust_inference_family",
]
