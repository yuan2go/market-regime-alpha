"""V2 hypothetical, independently funded, closed mark-execution episodes.

No actual Fill/Account/Position, continuous wealth series, or market label is
created here. Prices must come from exact canonical Outcome checkpoints.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, localcontext
from uuid import UUID

from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.time import require_utc


ZERO = Decimal(0)
CENT = Decimal(".01")


@dataclass(frozen=True, slots=True)
class EpisodePolicy:
    initial_capital: Decimal
    buy_fee_bps: Decimal
    sell_fee_bps: Decimal
    model: str = "INDEPENDENT_EPISODES"
    execution: str = "ASSUMED_CHECKPOINT_CLOSE_FRACTIONAL"
    price_basis: str = "RAW_UNADJUSTED"
    final_liquidation: bool = True
    carry_forward: str = "NONE"
    minimum_fee: Decimal = ZERO
    slippage_bps: Decimal = ZERO
    decimal_precision: int = 34

    def __post_init__(self) -> None:
        if self.model != "INDEPENDENT_EPISODES":
            raise ValueError("only INDEPENDENT_EPISODES is supported")
        if (
            self.execution != "ASSUMED_CHECKPOINT_CLOSE_FRACTIONAL"
            or self.price_basis != "RAW_UNADJUSTED"
            or not self.final_liquidation
            or self.carry_forward != "NONE"
        ):
            raise ValueError("unsupported episode execution/price/termination contract")
        if not 34 <= self.decimal_precision <= 100:
            raise ValueError("episode precision must be 34..100")
        for value in (self.initial_capital, self.buy_fee_bps, self.sell_fee_bps, self.minimum_fee, self.slippage_bps):
            if not value.is_finite() or value < 0:
                raise ValueError("capital and costs must be finite and nonnegative")
        with localcontext() as context:
            context.prec = self.decimal_precision
            context.rounding = ROUND_HALF_EVEN
            if self.initial_capital <= 0 or self.initial_capital != self.initial_capital.quantize(CENT):
                raise ValueError("initial capital must be positive currency cents")
        if self.minimum_fee != 0 or self.slippage_bps != 0:
            raise ValueError("V2 supports explicitly zero minimum fee and slippage only")


@dataclass(frozen=True, slots=True)
class EpisodeLeg:
    observation_id: UUID
    instrument_id: UUID
    episode_key: str
    arm_key: str
    fold_key: str
    decision_time: datetime
    entry_time: datetime
    exit_time: datetime
    knowledge_cutoff: datetime
    outcome_known_at: datetime
    proposed_weight: Decimal
    risk_status: str
    entry_price: Decimal | None
    exit_price: Decimal | None
    price_basis: str = "RAW_UNADJUSTED"
    availability: str = "AVAILABLE"
    opening_units: Decimal = ZERO

    def __post_init__(self) -> None:
        for name in ("decision_time", "entry_time", "exit_time", "knowledge_cutoff", "outcome_known_at"):
            require_utc(getattr(self, name), field=name)
        if not self.decision_time < self.entry_time < self.exit_time <= self.outcome_known_at <= self.knowledge_cutoff:
            raise ValueError("episode Decision/entry/exit/known-time ordering is invalid")
        if not self.proposed_weight.is_finite() or not ZERO <= self.proposed_weight <= 1:
            raise ValueError("proposed weight must be a finite allocation fraction")
        if self.opening_units != 0:
            raise ValueError("independent episodes cannot accept opening positions")
        if self.risk_status not in {"AUTHORIZED", "REJECTED", "UNKNOWN", "NO_ACTION"}:
            raise ValueError("unknown Risk vocabulary")
        for price in (self.entry_price, self.exit_price):
            if price is not None and (not price.is_finite() or price <= 0):
                raise ValueError("episode price must be finite and positive")


@dataclass(frozen=True, slots=True)
class EpisodeLegResult:
    observation_id: UUID
    units: Decimal
    buy_notional: Decimal
    sell_notional: Decimal
    buy_fee: Decimal
    sell_fee: Decimal
    gross_profit: Decimal
    net_profit: Decimal


@dataclass(frozen=True, slots=True)
class EpisodeResult:
    episode_key: str
    observation_ids: tuple[UUID, ...]
    reason: str
    initial_cash: Decimal
    cash_after_entry: Decimal | None
    entry_holdings: Decimal | None
    final_cash: Decimal | None
    final_units: Decimal | None
    buy_notional: Decimal | None
    sell_notional: Decimal | None
    fees: Decimal | None
    gross_return: Decimal | None
    net_return: Decimal | None
    legs: tuple[EpisodeLegResult, ...]


@dataclass(frozen=True, slots=True)
class EpisodePath:
    episodes: tuple[EpisodeResult, ...]
    content_sha256: str

    def slice(self, observation_ids: frozenset[UUID]) -> tuple[EpisodeResult, ...]:
        """Project completed episodes; partial capital rosters cannot be sliced."""
        known = {key for episode in self.episodes for key in episode.observation_ids}
        if not observation_ids <= known:
            raise ValueError("slice contains unknown observations")
        selected = []
        for episode in self.episodes:
            members = frozenset(episode.observation_ids)
            if members & observation_ids:
                if not members <= observation_ids:
                    raise ValueError("slice cannot split an episode capital roster")
                selected.append(episode)
        return tuple(selected)


def build_episode_path(policy: EpisodePolicy, legs: tuple[EpisodeLeg, ...]) -> EpisodePath:
    if not legs or len({leg.observation_id for leg in legs}) != len(legs):
        raise ValueError("episode observation roster must be nonempty and unique")
    groups: dict[str, list[EpisodeLeg]] = {}
    for leg in legs:
        groups.setdefault(leg.episode_key, []).append(leg)
    ordered = sorted(groups.values(), key=lambda group: (group[0].decision_time, group[0].episode_key))
    ends: dict[str, datetime] = {}
    results = []
    with localcontext() as context:
        context.prec = policy.decimal_precision
        context.rounding = ROUND_HALF_EVEN
        for group in ordered:
            first = group[0]
            shape = (first.arm_key, first.fold_key, first.decision_time, first.entry_time, first.exit_time)
            if any((leg.arm_key, leg.fold_key, leg.decision_time, leg.entry_time, leg.exit_time) != shape for leg in group):
                raise ValueError("episode must have one complete capital/time/fold roster")
            if len({leg.instrument_id for leg in group}) != len(group):
                raise ValueError("duplicate instrument capital allocation")
            if sum((leg.proposed_weight for leg in group), ZERO) > 1:
                raise ValueError("episode allocation exceeds initial capital")
            if first.arm_key in ends and first.entry_time < ends[first.arm_key]:
                raise ValueError("overlapping episode capital occupation is unsupported")
            ends[first.arm_key] = first.exit_time
            results.append(_close_episode(policy, tuple(sorted(group, key=lambda leg: str(leg.instrument_id)))))
    episodes = tuple(results)
    return EpisodePath(episodes, canonical_json_sha256({"version": 2, "policy": policy, "inputs": legs, "episodes": episodes}))


def _close_episode(policy: EpisodePolicy, legs: tuple[EpisodeLeg, ...]) -> EpisodeResult:
    def incomplete(reason: str) -> EpisodeResult:
        return EpisodeResult(
            legs[0].episode_key,
            tuple(leg.observation_id for leg in legs),
            reason,
            policy.initial_capital,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            (),
        )

    trades = []
    for leg in legs:
        if leg.risk_status != "AUTHORIZED" or leg.proposed_weight == 0:
            trades.append(EpisodeLegResult(leg.observation_id, ZERO, ZERO, ZERO, ZERO, ZERO, ZERO, ZERO))
            continue
        if leg.availability != "AVAILABLE":
            return incomplete("UNSUPPORTED_OR_MISSING_MARKET_FACT")
        if leg.price_basis != policy.price_basis:
            return incomplete("INCOMPATIBLE_PRICE_BASIS")
        if leg.entry_price is None or leg.exit_price is None:
            return incomplete("INCOMPLETE_ENTRY_EXIT_PRICE")
        units = (policy.initial_capital * leg.proposed_weight / leg.entry_price).quantize(Decimal("1e-18"), rounding=ROUND_DOWN)
        buy = (units * leg.entry_price).quantize(CENT)
        sell = (units * leg.exit_price).quantize(CENT)
        buy_fee = (buy * policy.buy_fee_bps / 10000).quantize(CENT)
        sell_fee = (sell * policy.sell_fee_bps / 10000).quantize(CENT)
        trades.append(
            EpisodeLegResult(leg.observation_id, units, buy, sell, buy_fee, sell_fee, sell - buy, sell - buy - buy_fee - sell_fee)
        )
    buy = sum((trade.buy_notional for trade in trades), ZERO)
    sell = sum((trade.sell_notional for trade in trades), ZERO)
    buy_fees = sum((trade.buy_fee for trade in trades), ZERO)
    fees = buy_fees + sum((trade.sell_fee for trade in trades), ZERO)
    cash = policy.initial_capital - buy - buy_fees
    if cash < 0:
        return incomplete("INSUFFICIENT_CASH_FOR_COSTS")
    final = policy.initial_capital + sell - buy - fees
    if final < 0:
        return incomplete("INSUFFICIENT_CASH_FOR_EXIT_COSTS")
    return EpisodeResult(
        legs[0].episode_key,
        tuple(leg.observation_id for leg in legs),
        "EPISODE_CLOSED",
        policy.initial_capital,
        cash,
        buy,
        final,
        ZERO,
        buy,
        sell,
        fees,
        (sell - buy) / policy.initial_capital,
        (final - policy.initial_capital) / policy.initial_capital,
        tuple(trades),
    )
