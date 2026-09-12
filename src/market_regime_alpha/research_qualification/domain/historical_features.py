"""Ten explicit daily research factors; one kernel for full and incremental input.

Adjusted prices are Provider backward-adjusted percentages, not tradable total
returns. Peer benchmarks use the exact current Dataset population with complete
windows; they are equal-weight peer diagnostics, never an index substitute.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from uuid import UUID

from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class HistoricalFactor:
    name: str
    lookback: int
    group: str
    formula: str
    basis: str

    @property
    def algorithm_code(self) -> str:
        return "historical_" + self.name + "_v1"

    @property
    def algorithm_sha256(self) -> str:
        return canonical_json_sha256({"factor": self, "version": 1,
            "arithmetic": "decimal60_half_even_quantum1e-12", "missing": "EXPLICIT_NO_FILL",
            "peer_population": "exact_dataset_complete_windows_minimum_two",
            "peer_arithmetic": "unrounded_returns_before_final_cell_quantization",
            "availability": "completed_sessions_only", "volume_unit": "SHARE", "amount_unit": "CNY"})


FACTORS = (
    HistoricalFactor("intraday", 0, "intraday", "raw_close/raw_open-1", "RAW_UNADJUSTED"),
    *(HistoricalFactor(f"return_{n}", n, "returns", f"adjusted_close[t]/adjusted_close[t-{n}]-1", "BACKWARD_ADJUSTED") for n in (1, 5, 20)),
    HistoricalFactor("volatility_20", 20, "volatility", "sample_stddev(20_daily_adjusted_returns)", "BACKWARD_ADJUSTED"),
    HistoricalFactor("volume_5_20", 19, "activity", "mean(raw_volume,last5)/mean(raw_volume,last20)-1", "RAW_UNADJUSTED"),
    HistoricalFactor("amount_5_20", 19, "activity", "mean(raw_amount,last5)/mean(raw_amount,last20)-1", "RAW_UNADJUSTED"),
    *(HistoricalFactor(f"peer_relative_{n}", n, "relative", f"return_{n}-equal_weight_complete_peer_return_{n}", "BACKWARD_ADJUSTED") for n in (5, 20)),
    HistoricalFactor("cross_section_5", 5, "relative", "(average_tie_rank(return_5)-1)/(complete_peer_count-1)", "BACKWARD_ADJUSTED"),
)
FACTORS_BY_CODE = {item.algorithm_code: item for item in FACTORS}
PEER_FACTOR_CODES = frozenset(item.algorithm_code for item in FACTORS if item.group == "relative")
_CONTEXT = Context(prec=60, rounding=ROUND_HALF_EVEN)
_QUANTUM = Decimal("0.000000000001")


@dataclass(frozen=True, slots=True)
class HistoricalDailyPoint:
    session_date: date
    raw_open: Decimal | None
    raw_close: Decimal | None
    adjusted_close: Decimal | None
    volume: Decimal | None
    amount: Decimal | None

    def __post_init__(self) -> None:
        for name in ("raw_open", "raw_close", "adjusted_close", "volume", "amount"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite()
                or value < 0 or (name.endswith(("open", "close")) and value == 0)):
                raise ValueError("historical factor inputs require finite prices and nonnegative quantities")


@dataclass(frozen=True, slots=True)
class HistoricalFactorValue:
    value: Decimal | None
    reason: str
    # Exact dates and instruments needed to reproduce computation or its absence.
    dependencies: tuple[tuple[UUID, date], ...]


def calculate_historical_features(
    sessions: tuple[date, ...], population: dict[UUID, tuple[HistoricalDailyPoint, ...]],
) -> dict[UUID, dict[str, HistoricalFactorValue]]:
    """Input sessions come from Market Calendar; missing bars remain None cells."""
    if not sessions or len(sessions) > 21 or sessions != tuple(sorted(set(sessions))):
        raise ValueError("historical factors require 1..21 exact ordered Calendar sessions")
    if any(tuple(p.session_date for p in points) != sessions for points in population.values()):
        raise ValueError("each member must retain every exact Calendar session, including missing bars")
    result: dict[UUID, dict[str, HistoricalFactorValue]] = {i: {} for i in population}
    unrounded_returns: dict[tuple[UUID, str], Decimal | None] = {}
    with localcontext(_CONTEXT):
        for instrument, points in population.items():
            for factor in FACTORS:
                if factor.group == "relative":
                    continue
                window = points[-(factor.lookback + 1):]
                dependencies = tuple((instrument, p.session_date) for p in window)
                value = None
                reason = "FEATURE_WARMUP_INSUFFICIENT"
                if len(window) == factor.lookback + 1:
                    reason = "FEATURE_INPUT_MISSING"
                    if factor.name == "intraday":
                        p = window[-1]
                        if p.raw_open is not None and p.raw_close is not None:
                            value = p.raw_close / p.raw_open - 1
                    elif factor.group in {"returns", "volatility"}:
                        prices = tuple(p.adjusted_close for p in window)
                        if all(p is not None for p in prices):
                            exact = tuple(p for p in prices if p is not None)
                            if factor.group == "returns":
                                value = exact[-1] / exact[0] - 1
                            else:
                                returns = tuple(b / a - 1 for a, b in zip(exact, exact[1:]))
                                mean = sum(returns, Decimal(0)) / len(returns)
                                value = (sum(((r - mean) ** 2 for r in returns), Decimal(0)) / (len(returns) - 1)).sqrt()
                    else:
                        quantities = tuple(p.volume if factor.name.startswith("volume") else p.amount for p in window)
                        if all(q is not None for q in quantities):
                            exact = tuple(q for q in quantities if q is not None)
                            if sum(exact) == 0:
                                reason = "FEATURE_ZERO_ACTIVITY_DENOMINATOR"
                            else:
                                value = 4 * sum(exact[-5:], Decimal(0)) / sum(exact, Decimal(0)) - 1
                if factor.group == "returns":
                    unrounded_returns[(instrument, factor.name)] = value
                result[instrument][factor.name] = HistoricalFactorValue(
                    None if value is None else value.quantize(_QUANTUM),
                    reason if value is None else "EXACT_HISTORICAL_FACTOR", dependencies)
        for factor in FACTORS:
            if factor.group != "relative":
                continue
            n = 20 if factor.name.endswith("20") else 5
            peers = {i: result[i][f"return_{n}"] for i in population}
            valid = tuple(value for i in population if (value := unrounded_returns[(i, f"return_{n}")]) is not None)
            dependencies = tuple(sorted({d for p in peers.values() for d in p.dependencies}, key=lambda d: (str(d[0]), d[1])))
            for instrument in population:
                own = peers[instrument]
                own_value = unrounded_returns[(instrument, f"return_{n}")]
                value = None
                reason = own.reason if own.value is None else "FEATURE_PEER_POPULATION_INSUFFICIENT"
                if own_value is not None and len(valid) >= 2:
                    if factor.name.startswith("peer_relative"):
                        value = own_value - sum(valid, Decimal(0)) / len(valid)
                    else:
                        less = sum(v < own_value for v in valid)
                        equal = sum(v == own_value for v in valid)
                        value = (Decimal(less) + Decimal(equal - 1) / 2) / (len(valid) - 1)
                result[instrument][factor.name] = HistoricalFactorValue(
                    None if value is None else value.quantize(_QUANTUM),
                    reason if value is None else "EXACT_HISTORICAL_FACTOR", dependencies)
    return result


def append_historical_session(
    sessions: tuple[date, ...], population: dict[UUID, tuple[HistoricalDailyPoint, ...]],
    next_points: dict[UUID, HistoricalDailyPoint],
) -> tuple[tuple[date, ...], dict[UUID, tuple[HistoricalDailyPoint, ...]]]:
    """Bounded incremental state supplied by caller; no implicit calendar or cache."""
    if not next_points or set(population) != set(next_points):
        raise ValueError("incremental factors require an unchanged explicit population")
    dates = {point.session_date for point in next_points.values()}
    if len(dates) != 1 or (sessions and next(iter(dates)) <= sessions[-1]):
        raise ValueError("incremental factor session must be unique and strictly later")
    updated = (sessions + (next(iter(dates)),))[-21:]
    points = {i: (population[i] + (next_points[i],))[-21:] for i in population}
    calculate_historical_features(updated, points)  # Validate alignment; no imputation.
    return updated, points
