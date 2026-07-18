"""Coverage-first statistical wrappers for MR-2B F2B v3."""

from __future__ import annotations

from dataclasses import dataclass, replace

from market_regime_alpha.research.mr2b_f2b_statistics import (
    BootstrapResult,
    PrimaryObservationSet,
    linear_quantile,
    moving_block_bootstrap,
    temporal_stability,
)
from market_regime_alpha.research.mr2b_f2b_v3_protocol import F2BProtocolV3


@dataclass(frozen=True, slots=True)
class PrimaryCoverageAssessment:
    total_date_count: int
    up_count: int
    down_count: int
    flat_count: int
    unavailable_count: int
    context_complete: bool
    sufficient_for_statistics: bool
    insufficiency_reasons: tuple[str, ...]


def assess_primary_coverage(
    primary: PrimaryObservationSet,
    *,
    up_count: int,
    down_count: int,
    protocol: F2BProtocolV3,
) -> PrimaryCoverageAssessment:
    reasons: list[str] = []
    if up_count < protocol.minimum_slice_size:
        reasons.append("INSUFFICIENT_UP_SLICE")
    if down_count < protocol.minimum_slice_size:
        reasons.append("INSUFFICIENT_DOWN_SLICE")
    if primary.unavailable_count:
        reasons.append("CONTEXT_COVERAGE_INCOMPLETE")
    return PrimaryCoverageAssessment(
        total_date_count=primary.total_date_count,
        up_count=up_count,
        down_count=down_count,
        flat_count=primary.flat_count,
        unavailable_count=primary.unavailable_count,
        context_complete=primary.unavailable_count == 0,
        sufficient_for_statistics=not reasons,
        insufficiency_reasons=tuple(reasons),
    )


def protocol_bootstrap(
    primary: PrimaryObservationSet,
    *,
    block_length: int,
    protocol: F2BProtocolV3,
) -> BootstrapResult:
    result = moving_block_bootstrap(
        primary.observations,
        draws=protocol.bootstrap_draws,
        block_length=block_length,
        seed=protocol.bootstrap_seed,
        minimum_slice_size=protocol.minimum_slice_size,
        effect_floor=protocol.economic_effect_floor,
    )
    alpha = (1.0 - protocol.bootstrap_interval) / 2.0
    return replace(
        result,
        ci_lower_95=linear_quantile(result.effects, alpha),
        ci_upper_95=linear_quantile(result.effects, 1.0 - alpha),
    )


def protocol_temporal_stability(primary: PrimaryObservationSet, *, protocol: F2BProtocolV3):
    return temporal_stability(
        primary.observations,
        half_minimum_slice_size=protocol.half_minimum_slice_size,
        rolling_window=protocol.rolling_window,
    )
