"""Adapter from the unique MR1 10:30 identity into TargetProtocol."""

from __future__ import annotations

from market_regime_alpha.core.identity import TargetId, UniverseId
from market_regime_alpha.platform.target_evaluation import (
    MissingTargetPolicy,
    PriceMark,
    ReturnBasis,
    TargetKind,
    TargetProtocol,
)
from market_regime_alpha.research.mr1_morning_pop import (
    MR1TargetId,
    MR1_EXACT_ENDPOINT_CONVENTION,
)


def mr1_next_session_1030_target_protocol(
    universe_id: UniverseId,
) -> TargetProtocol:
    """Describe MR1TargetId.NEXT_SESSION_1030_RETURN without a new Target ID."""

    return TargetProtocol(
        target_id=TargetId(MR1TargetId.NEXT_SESSION_1030_RETURN.value),
        name="MR1 Next-session 10:30 Return",
        version="mr1-adapter-v1",
        kind=TargetKind.RETURN,
        decision_time_convention="14:55 Asia/Shanghai exact Decision Price Snapshot",
        horizon="next trading session exact 10:30 five-minute endpoint",
        start_mark=PriceMark.DECISION_PRICE,
        end_mark=PriceMark.NEXT_1030,
        return_basis=ReturnBasis.ABSOLUTE,
        availability_rule=(
            f"{MR1_EXACT_ENDPOINT_CONVENTION}; exact 10:30 bar required; "
            "no later-bar substitution"
        ),
        adjustment_rule=(
            "decision and endpoint marks must declare compatible adjustment basis"
        ),
        missing_policy=MissingTargetPolicy.RETAIN_AS_UNRESOLVED,
        universe_id=universe_id,
        benchmark_ref=None,
        cost_adjusted=False,
        path_required=False,
    )
