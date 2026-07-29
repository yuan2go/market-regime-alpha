from __future__ import annotations

from dataclasses import replace

import pytest

from market_regime_alpha.research.market_regime.contracts import (
    MarketState,
    TradePermission,
)
from market_regime_alpha.research.market_regime.model import (
    evaluate_market_regime_v0,
)
from market_regime_alpha.research.platform_v2.configs import (
    MarketRegimeModelConfig,
)
from market_regime_alpha.research.platform_v2.inputs import ResearchInputBundle


@pytest.mark.parametrize(
    ("direction", "breadth", "amount", "intraday_range", "expected_state", "permission"),
    (
        (0.02, 0.80, 0.50, 0.005, MarketState.RISK_ON, TradePermission.ALLOW),
        (0.00, 0.50, 0.00, 0.020, MarketState.RISK_NEUTRAL, TradePermission.RESTRICT),
        (-0.01, 0.30, -0.20, 0.030, MarketState.RISK_OFF, TradePermission.RESTRICT),
        (-0.03, 0.05, -0.60, 0.050, MarketState.EXTREME_RISK, TradePermission.PROHIBIT),
    ),
)
def test_market_regime_states(
    research_input_bundle: ResearchInputBundle,
    direction: float,
    breadth: float,
    amount: float,
    intraday_range: float,
    expected_state: MarketState,
    permission: TradePermission,
) -> None:
    observation = replace(
        research_input_bundle.market_observation,
        market_direction_return=direction,
        candidate_breadth_at_cutoff=breadth,
        market_amount_change_same_cutoff=amount,
        market_intraday_range_to_cutoff=intraday_range,
        limit_structure_score=direction,
    )
    snapshot = evaluate_market_regime_v0(
        replace(research_input_bundle, market_observation=observation),
        MarketRegimeModelConfig(),
        code_revision="test-revision",
    )

    assert snapshot.market_state is expected_state
    assert snapshot.trade_permission is permission
    assert 0.0 <= snapshot.maximum_gross_exposure <= 1.0
    snapshot.envelope.verify_payload(snapshot.artifact_payload())


def test_market_regime_insufficient_data_is_fail_closed(
    research_input_bundle: ResearchInputBundle,
) -> None:
    snapshot = evaluate_market_regime_v0(
        replace(research_input_bundle, market_observation=None),
        MarketRegimeModelConfig(),
        code_revision="test-revision",
    )

    assert snapshot.market_state is MarketState.DATA_INSUFFICIENT
    assert snapshot.trade_permission is TradePermission.PROHIBIT
    assert snapshot.maximum_gross_exposure == 0.0
    assert "MARKET_REGIME_DATA_INSUFFICIENT" in snapshot.reason_codes

