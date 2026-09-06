from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.episode_economics import (
    EpisodeLeg, EpisodePolicy, build_episode_path,
)


def leg(day=1, *, risk="AUTHORIZED", weight="0.4", exit_price="11", **kwargs):
    decision = datetime(2026, 1, day, 0, tzinfo=UTC)
    return EpisodeLeg(
        observation_id=UUID(int=day), instrument_id=UUID(int=100),
        episode_key=str(day), arm_key="arm", fold_key="fold",
        decision_time=decision, entry_time=decision + timedelta(hours=1),
        exit_time=decision + timedelta(hours=2), knowledge_cutoff=decision + timedelta(days=10),
        outcome_known_at=decision + timedelta(days=1),
        proposed_weight=D(weight), risk_status=risk,
        entry_price=D("10"), exit_price=D(exit_price), **kwargs,
    )


def policy(**kwargs):
    return EpisodePolicy(initial_capital=D("1000"), buy_fee_bps=D("10"),
                         sell_fee_bps=D("20"), **kwargs)


def test_rejected_buy_then_same_authorized_proposal_is_first_real_simulated_buy():
    result = build_episode_path(policy(), (leg(risk="REJECTED"), leg(2)))
    rejected, bought = result.episodes
    assert rejected.buy_notional == rejected.sell_notional == rejected.fees == D(0)
    assert rejected.final_cash == D("1000")
    # Independent hand calculation: 40 units at 10 -> 440 proceeds at 11.
    # Buy fee .40; sell fee .88. Cash 1000 - 400 - .40 + 440 - .88.
    assert bought.buy_notional == D("400")
    assert bought.sell_notional == D("440")
    assert bought.fees == D("1.28")
    assert bought.final_cash == D("1038.72")
    assert bought.net_return == D(".03872")
    assert bought.final_units == D(0)


@pytest.mark.parametrize("risk", ["REJECTED", "UNKNOWN"])
def test_no_authorization_leaves_cash_without_a_simulated_trade(risk):
    episode = build_episode_path(policy(), (leg(risk=risk),)).episodes[0]
    assert episode.final_cash == D("1000")
    assert episode.fees == episode.buy_notional == episode.sell_notional == D(0)


def test_continuous_account_is_explicitly_unsupported():
    with pytest.raises(ValueError, match="INDEPENDENT_EPISODES"):
        policy(model="CONTINUOUS_PORTFOLIO")


def test_opening_position_is_rejected_including_when_new_proposal_is_rejected():
    with pytest.raises(ValueError, match="opening positions"):
        build_episode_path(policy(), (leg(risk="REJECTED", opening_units=D(40)),))


@pytest.mark.parametrize("availability", ["MISSING", "SUSPENDED", "UNTRADEABLE", "CORPORATE_ACTION"])
def test_unavailable_episode_keeps_its_place_and_has_no_fabricated_value(availability):
    path = build_episode_path(policy(), (leg(availability=availability), leg(2)))
    assert len(path.episodes) == 2
    assert path.episodes[0].net_return is None
    assert path.episodes[0].reason == "UNSUPPORTED_OR_MISSING_MARKET_FACT"
    assert path.episodes[1].net_return == D(".03872")


def test_cash_holdings_fees_reconcile_and_later_pool_does_not_own_exit():
    # Second episode uses a different instrument; the original leg still closes.
    from dataclasses import replace
    path = build_episode_path(policy(), (leg(), replace(leg(2), instrument_id=UUID(int=101))))
    for episode in path.episodes:
        assert episode.cash_after_entry + episode.entry_holdings + D(".40") == D(1000)
        assert episode.final_cash == D(1000) + episode.sell_notional - episode.buy_notional - episode.fees
        assert episode.final_units == 0


def test_fixed_trade_path_higher_fees_cannot_improve_net_and_units_are_unchanged():
    from dataclasses import replace
    base = policy()
    cheap = build_episode_path(base, (leg(),)).episodes[0]
    dear = build_episode_path(replace(base, buy_fee_bps=D(30), sell_fee_bps=D(50)), (leg(),)).episodes[0]
    assert cheap.legs[0].units == dear.legs[0].units == D(40)
    assert dear.net_return == D(".03660") < cheap.net_return


def test_path_then_slice_preserves_values_deduplication_and_capital_roster():
    from dataclasses import replace
    first, second = leg(), leg(2)
    path = build_episode_path(policy(), (first, second))
    assert path == build_episode_path(policy(), (first, second))
    assert path.slice(frozenset({second.observation_id})) == (path.episodes[1],)
    with pytest.raises(ValueError, match="unique"):
        build_episode_path(policy(), (first, first))
    companion = replace(first, observation_id=UUID(int=200), instrument_id=UUID(int=201))
    combined = build_episode_path(policy(), (first, companion))
    assert combined.episodes[0].net_return == D(".07744")
    with pytest.raises(ValueError, match="split"):
        combined.slice(frozenset({first.observation_id}))


def test_fold_reset_does_not_hide_overlapping_funding():
    from dataclasses import replace
    first = leg()
    next_fold = replace(first, observation_id=UUID(int=2), episode_key="2", fold_key="fold2")
    with pytest.raises(ValueError, match="overlapping"):
        build_episode_path(policy(), (first, next_fold))


@pytest.mark.parametrize("kwargs", [{"minimum_fee": D(5)}, {"slippage_bps": D(1)}, {"carry_forward": "PREVIOUS_TARGET_WEIGHT"}, {"final_liquidation": False}])
def test_unsupported_assumptions_are_not_silently_accepted(kwargs):
    with pytest.raises(ValueError):
        policy(**kwargs)


def test_flat_price_has_round_trip_fees_and_missing_exit_has_no_zero_return():
    from dataclasses import replace
    closed = build_episode_path(policy(), (leg(exit_price="10"),)).episodes[0]
    assert closed.net_return == D("-.00120")
    missing = build_episode_path(policy(), (replace(leg(), exit_price=None),)).episodes[0]
    assert missing.net_return is None
    assert missing.reason == "INCOMPLETE_ENTRY_EXIT_PRICE"


def test_insufficient_cash_is_typed_incomplete_not_implicit_borrowing():
    closed = build_episode_path(policy(), (leg(weight="1"),)).episodes[0]
    assert closed.net_return is None
    assert closed.reason == "INSUFFICIENT_CASH_FOR_COSTS"
