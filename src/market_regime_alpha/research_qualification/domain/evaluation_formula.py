"""Versioned Decimal formula contracts for current generic Backtests.

The contracts in this module are immutable command/projection values.  The
relational Evaluation protocol closure remains Authority and Evaluation remains
the sole owner of persisted metric truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import (
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Decimal,
    localcontext,
)
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")
_ROUNDING_MODES = {
    "ROUND_DOWN": ROUND_DOWN,
    "ROUND_HALF_EVEN": ROUND_HALF_EVEN,
    "ROUND_HALF_UP": ROUND_HALF_UP,
    "ROUND_UP": ROUND_UP,
}


class FormulaParameterType(StrEnum):
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"


class BacktestMetricSurface(StrEnum):
    DATA = "DATA"
    CANDIDATE = "CANDIDATE"
    CONTEXT = "CONTEXT"
    SIGNAL_FORECAST = "SIGNAL_FORECAST"
    PORTFOLIO_RISK = "PORTFOLIO_RISK"
    ECONOMICS = "ECONOMICS"
    STABILITY = "STABILITY"


class BacktestFormulaCode(StrEnum):
    COVERAGE_RATE = "coverage_rate"
    MISSINGNESS_RATE = "missingness_rate"
    SOURCE_GAP_RATE = "source_gap_rate"
    UNAVAILABLE_RATE = "unavailable_rate"
    MEAN = "mean"
    SAMPLE_STDDEV = "sample_stddev"
    ICIR = "icir"
    RANK_IC = "rank_ic"
    TOP_K_RETURN = "top_k_return"
    TOP_BOTTOM_SPREAD = "top_bottom_spread"
    HIT_RATE = "hit_rate"
    SELECTED_RATIO = "selected_ratio"
    PREDICTIVE_BIAS = "predictive_bias"
    PREDICTIVE_MAE = "predictive_mae"
    PREDICTIVE_RMSE = "predictive_rmse"
    GROSS_EXPOSURE = "gross_exposure"
    NET_EXPOSURE = "net_exposure"
    TURNOVER = "turnover"
    NET_RETURN_ASSUMED_COST = "net_return_assumed_cost"
    CUMULATIVE_RETURN = "cumulative_return"
    ANNUALIZED_RETURN = "annualized_return"
    VOLATILITY = "volatility"
    SHARPE = "sharpe"
    SORTINO = "sortino"
    CALMAR = "calmar"
    MAX_DRAWDOWN = "max_drawdown"
    WIN_RATE = "win_rate"
    MFE_MEAN = "mfe_mean"
    MAX_ADVERSE_EXCURSION_MEAN = "max_adverse_excursion_mean"


class FormulaSourceState(StrEnum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    SOURCE_GAP = "SOURCE_GAP"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class FrozenRankingMembership(StrEnum):
    NONE = "NONE"
    ELIGIBLE = "ELIGIBLE"
    SELECTED = "SELECTED"
    TOP = "TOP"
    BOTTOM = "BOTTOM"


class FormulaResultState(StrEnum):
    ESTIMABLE = "ESTIMABLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True, slots=True)
class EvaluationFormulaParameter:
    formula_parameter_id: UUID
    ordinal: int
    parameter_code: str
    value_type: FormulaParameterType
    decimal_value: Decimal | None = None
    integer_value: int | None = None
    boolean_value: bool | None = None
    text_value: str | None = None
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("formula parameter ordinal must be positive")
        if not _CODE.fullmatch(self.parameter_code):
            raise ValueError("formula parameter code has an invalid format")
        values = {
            FormulaParameterType.DECIMAL: self.decimal_value,
            FormulaParameterType.INTEGER: self.integer_value,
            FormulaParameterType.BOOLEAN: self.boolean_value,
            FormulaParameterType.TEXT: self.text_value,
        }
        populated = tuple(kind for kind, value in values.items() if value is not None)
        if populated != (self.value_type,):
            raise ValueError("formula parameter requires exactly one typed scalar")
        if self.integer_value is not None and isinstance(self.integer_value, bool):
            raise ValueError("formula INTEGER parameter cannot be boolean")
        if self.text_value is not None and not self.text_value:
            raise ValueError("formula TEXT parameter cannot be empty")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "boolean_value": self.boolean_value,
                        "decimal_value": self.decimal_value,
                        "formula_parameter_id": self.formula_parameter_id,
                        "integer_value": self.integer_value,
                        "ordinal": self.ordinal,
                        "parameter_code": self.parameter_code,
                        "text_value": self.text_value,
                        "value_type": self.value_type,
                    }
                )
            ),
        )

    @property
    def value(self) -> Decimal | int | bool | str:
        values: tuple[Decimal | int | bool | str | None, ...] = (
            self.decimal_value,
            self.integer_value,
            self.boolean_value,
            self.text_value,
        )
        return next(value for value in values if value is not None)


@dataclass(frozen=True, slots=True)
class EvaluationFormulaDefinition:
    evaluation_protocol_metric_id: UUID
    formula_code: BacktestFormulaCode
    formula_version: int
    decimal_precision: int
    rounding_mode: str
    parameters: tuple[EvaluationFormulaParameter, ...]
    surface: BacktestMetricSurface
    parameter_count: int = field(init=False)
    parameter_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.formula_version, bool) or self.formula_version < 1:
            raise ValueError("formula_version must be positive")
        if (
            isinstance(self.decimal_precision, bool)
            or not 16 <= self.decimal_precision <= 100
        ):
            raise ValueError("decimal_precision must be between 16 and 100")
        if self.rounding_mode not in _ROUNDING_MODES:
            raise ValueError("rounding_mode is unsupported")
        ordinals = tuple(item.ordinal for item in self.parameters)
        if ordinals != tuple(range(1, len(self.parameters) + 1)):
            raise ValueError("formula parameter ordinals must be contiguous")
        if len({item.parameter_code for item in self.parameters}) != len(
            self.parameters
        ):
            raise ValueError("formula parameter codes must be unique")
        roster_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(item.content_sha256),
                        "formula_parameter_id": item.formula_parameter_id,
                        "ordinal": item.ordinal,
                    }
                    for item in self.parameters
                )
            )
        )
        object.__setattr__(self, "parameter_count", len(self.parameters))
        object.__setattr__(self, "parameter_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "decimal_precision": self.decimal_precision,
                        "evaluation_protocol_metric_id": (
                            self.evaluation_protocol_metric_id
                        ),
                        "formula_code": self.formula_code,
                        "formula_version": self.formula_version,
                        "parameter_count": len(self.parameters),
                        "parameter_roster_sha256": str(roster_hash),
                        "rounding_mode": self.rounding_mode,
                        "surface": self.surface,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class FormulaObservation:
    observation_id: UUID
    ordinal: int
    group_key: str
    source_state: FormulaSourceState
    value: Decimal | None
    secondary_value: Decimal | None = None
    ranking_membership: FrozenRankingMembership = FrozenRankingMembership.NONE
    decision_time: datetime | None = None
    outcome_known_at: datetime | None = None
    buy_turnover: Decimal | None = None
    sell_turnover: Decimal | None = None

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("formula observation ordinal must be positive")
        if not self.group_key:
            raise ValueError("formula observation group_key is required")
        if (self.decision_time is None) != (self.outcome_known_at is None):
            raise ValueError(
                "ranking observation needs DecisionTime and Outcome known-time together"
            )
        if self.buy_turnover is not None and self.buy_turnover < 0:
            raise ValueError("buy turnover must be non-negative")
        if self.sell_turnover is not None and self.sell_turnover < 0:
            raise ValueError("sell turnover must be non-negative")


@dataclass(frozen=True, slots=True)
class FormulaEvaluationResult:
    state: FormulaResultState
    decimal_value: Decimal | None
    estimable_count: int
    reason_code: str


def evaluate_backtest_formula(
    formula: EvaluationFormulaDefinition,
    observations: tuple[FormulaObservation, ...],
) -> FormulaEvaluationResult:
    """Execute one explicitly supported V1 formula with Decimal semantics."""

    if formula.formula_version != 1:
        raise ValueError("formula implementation version is unsupported")
    _require_unique_observations(observations)
    with localcontext() as context:
        context.prec = formula.decimal_precision
        context.rounding = _ROUNDING_MODES[formula.rounding_mode]
        return _evaluate_v1(formula, observations)


def _evaluate_v1(
    formula: EvaluationFormulaDefinition,
    observations: tuple[FormulaObservation, ...],
) -> FormulaEvaluationResult:
    code = formula.formula_code
    if code in {
        BacktestFormulaCode.COVERAGE_RATE,
        BacktestFormulaCode.MISSINGNESS_RATE,
        BacktestFormulaCode.SOURCE_GAP_RATE,
        BacktestFormulaCode.UNAVAILABLE_RATE,
    }:
        expected = _integer_parameter(formula, "expected_roster_size")
        if expected <= 0:
            return _not_estimable("EMPTY_EXPECTED_ROSTER")
        if len(observations) != expected:
            return _not_estimable("EXPECTED_ROSTER_MISMATCH")
        wanted = {
            BacktestFormulaCode.COVERAGE_RATE: {FormulaSourceState.AVAILABLE},
            BacktestFormulaCode.MISSINGNESS_RATE: {FormulaSourceState.MISSING},
            BacktestFormulaCode.SOURCE_GAP_RATE: {FormulaSourceState.SOURCE_GAP},
            BacktestFormulaCode.UNAVAILABLE_RATE: {
                FormulaSourceState.UNAVAILABLE,
                FormulaSourceState.FAILED,
                FormulaSourceState.UNKNOWN,
            },
        }[code]
        numerator = sum(item.source_state in wanted for item in observations)
        return _estimated(Decimal(numerator) / Decimal(expected), numerator)

    available = tuple(
        item
        for item in observations
        if item.source_state is FormulaSourceState.AVAILABLE
        and item.value is not None
    )
    minimum = _optional_integer_parameter(formula, "minimum_observations", 1)
    if len(available) < minimum:
        return _not_estimable("INSUFFICIENT_OBSERVATIONS", len(available))

    if code in {
        BacktestFormulaCode.MEAN,
        BacktestFormulaCode.MFE_MEAN,
        BacktestFormulaCode.MAX_ADVERSE_EXCURSION_MEAN,
    }:
        return _estimated(_mean(_values(available)), len(available))
    if code is BacktestFormulaCode.SAMPLE_STDDEV:
        deviation = _sample_std(_values(available))
        return (
            _not_estimable("INSUFFICIENT_OBSERVATIONS", len(available))
            if deviation is None
            else _estimated(deviation, len(available))
        )
    if code is BacktestFormulaCode.ICIR:
        values = _values(available)
        deviation = _sample_std(values)
        if deviation is None:
            return _not_estimable("INSUFFICIENT_OBSERVATIONS", len(values))
        if deviation == 0:
            return _not_estimable("ZERO_VARIANCE", len(values))
        return _estimated(_mean(values) / deviation, len(values))
    if code is BacktestFormulaCode.RANK_IC:
        return _rank_ic(formula, available)
    if code in {
        BacktestFormulaCode.TOP_K_RETURN,
        BacktestFormulaCode.TOP_BOTTOM_SPREAD,
    }:
        return _ranked_return(formula, available)
    if code is BacktestFormulaCode.HIT_RATE:
        selected = tuple(
            item
            for item in available
            if item.ranking_membership
            in {FrozenRankingMembership.SELECTED, FrozenRankingMembership.TOP}
        )
        if not selected:
            return _not_estimable("NO_SELECTED_MEMBERS")
        return _estimated(
            Decimal(sum(item.value > 0 for item in selected))
            / Decimal(len(selected)),
            len(selected),
        )
    if code is BacktestFormulaCode.SELECTED_RATIO:
        eligible = tuple(
            item
            for item in observations
            if item.ranking_membership is not FrozenRankingMembership.NONE
        )
        if not eligible:
            return _not_estimable("NO_ELIGIBLE_MEMBERS")
        selected_count = sum(
            item.ranking_membership
            in {FrozenRankingMembership.SELECTED, FrozenRankingMembership.TOP}
            for item in eligible
        )
        return _estimated(
            Decimal(selected_count) / Decimal(len(eligible)), selected_count
        )
    if code in {
        BacktestFormulaCode.PREDICTIVE_BIAS,
        BacktestFormulaCode.PREDICTIVE_MAE,
        BacktestFormulaCode.PREDICTIVE_RMSE,
    }:
        return _predictive(code, available)
    if code in {
        BacktestFormulaCode.GROSS_EXPOSURE,
        BacktestFormulaCode.NET_EXPOSURE,
        BacktestFormulaCode.TURNOVER,
    }:
        return _portfolio_formula(formula, available)
    if code is BacktestFormulaCode.NET_RETURN_ASSUMED_COST:
        return _net_assumed_cost(formula, available)
    if code in {
        BacktestFormulaCode.CUMULATIVE_RETURN,
        BacktestFormulaCode.ANNUALIZED_RETURN,
        BacktestFormulaCode.VOLATILITY,
        BacktestFormulaCode.SHARPE,
        BacktestFormulaCode.SORTINO,
        BacktestFormulaCode.CALMAR,
        BacktestFormulaCode.MAX_DRAWDOWN,
        BacktestFormulaCode.WIN_RATE,
    }:
        return _economics(formula, available)
    raise ValueError(f"formula adapter is not implemented: {code.value}")


def _rank_ic(
    formula: EvaluationFormulaDefinition,
    observations: tuple[FormulaObservation, ...],
) -> FormulaEvaluationResult:
    minimum = _optional_integer_parameter(formula, "minimum_pairs_per_group", 2)
    grouped = _groups(observations)
    correlations: list[Decimal] = []
    pair_count = 0
    for members in grouped:
        pairs = tuple(
            (item.value, item.secondary_value)
            for item in members
            if item.value is not None and item.secondary_value is not None
        )
        if len(pairs) < minimum:
            continue
        correlation = _spearman(pairs)
        if correlation is not None:
            correlations.append(correlation)
            pair_count += len(pairs)
    if not correlations:
        return _not_estimable("NO_ESTIMABLE_RANK_GROUP")
    return _estimated(_mean(tuple(correlations)), pair_count)


def _ranked_return(
    formula: EvaluationFormulaDefinition,
    observations: tuple[FormulaObservation, ...],
) -> FormulaEvaluationResult:
    width = _integer_parameter(formula, "top_k")
    if width < 1:
        raise ValueError("top_k must be positive")
    if any(
        item.ranking_membership
        in {FrozenRankingMembership.TOP, FrozenRankingMembership.BOTTOM}
        and (
            item.decision_time is None
            or item.outcome_known_at is None
            or item.decision_time >= item.outcome_known_at
        )
        for item in observations
    ):
        return _not_estimable("RANKING_NOT_FROZEN_BEFORE_OUTCOME")
    results: list[Decimal] = []
    count = 0
    for members in _groups(observations):
        top = tuple(
            item.value
            for item in members
            if item.ranking_membership is FrozenRankingMembership.TOP
            and item.value is not None
        )
        bottom = tuple(
            item.value
            for item in members
            if item.ranking_membership is FrozenRankingMembership.BOTTOM
            and item.value is not None
        )
        if len(top) != width:
            continue
        if formula.formula_code is BacktestFormulaCode.TOP_K_RETURN:
            results.append(_mean(top))
            count += len(top)
        elif len(bottom) == width:
            results.append(_mean(top) - _mean(bottom))
            count += len(top) + len(bottom)
    if not results:
        return _not_estimable("INCOMPLETE_FROZEN_RANKING_MEMBERSHIP")
    return _estimated(_mean(tuple(results)), count)


def _predictive(
    code: BacktestFormulaCode,
    observations: tuple[FormulaObservation, ...],
) -> FormulaEvaluationResult:
    pairs = tuple(
        (item.value, item.secondary_value)
        for item in observations
        if item.value is not None and item.secondary_value is not None
    )
    if not pairs:
        return _not_estimable("NO_COMPLETE_FORECAST_OUTCOME_PAIR")
    errors = tuple(forecast - target for forecast, target in pairs)
    if code is BacktestFormulaCode.PREDICTIVE_BIAS:
        value = _mean(errors)
    elif code is BacktestFormulaCode.PREDICTIVE_MAE:
        value = _mean(tuple(abs(item) for item in errors))
    else:
        value = _mean(tuple(item * item for item in errors)).sqrt()
    return _estimated(value, len(pairs))


def _portfolio_formula(
    formula: EvaluationFormulaDefinition,
    observations: tuple[FormulaObservation, ...],
) -> FormulaEvaluationResult:
    if formula.formula_code is BacktestFormulaCode.TURNOVER:
        _boolean_parameter(formula, "initial_cash")
        _boolean_parameter(formula, "final_liquidation")
        _text_parameter(formula, "carry_forward")
        _text_parameter(formula, "corporate_action_convention")
        if any(item.secondary_value is None for item in observations):
            return _not_estimable("INCOMPLETE_PREVIOUS_WEIGHT_ROSTER")
    values: list[Decimal] = []
    count = 0
    for members in _groups(observations):
        weights = _values(members)
        if formula.formula_code is BacktestFormulaCode.GROSS_EXPOSURE:
            value = sum((abs(item) for item in weights), Decimal(0))
        elif formula.formula_code is BacktestFormulaCode.NET_EXPOSURE:
            value = sum(weights, Decimal(0))
        else:
            value = Decimal("0.5") * sum(
                (
                    abs(item.value - item.secondary_value)
                    for item in members
                    if item.value is not None and item.secondary_value is not None
                ),
                Decimal(0),
            )
        values.append(value)
        count += len(members)
    return _estimated(_mean(tuple(values)), count)


def _net_assumed_cost(
    formula: EvaluationFormulaDefinition,
    observations: tuple[FormulaObservation, ...],
) -> FormulaEvaluationResult:
    commission = _decimal_parameter(formula, "commission_bps") / Decimal(10000)
    slippage = _decimal_parameter(formula, "slippage_bps") / Decimal(10000)
    stamp = _decimal_parameter(formula, "stamp_duty_bps") / Decimal(10000)
    net_periods: list[Decimal] = []
    count = 0
    for members in _groups(observations):
        if any(
            item.buy_turnover is None
            or item.sell_turnover is None
            or item.value is None
            for item in members
        ):
            return _not_estimable("INCOMPLETE_COST_TURNOVER", count)
        gross = sum((item.value for item in members if item.value is not None), Decimal(0))
        buy = sum(
            (item.buy_turnover for item in members if item.buy_turnover is not None),
            Decimal(0),
        )
        sell = sum(
            (item.sell_turnover for item in members if item.sell_turnover is not None),
            Decimal(0),
        )
        net_periods.append(
            gross
            - (buy + sell) * (commission + slippage)
            - sell * stamp
        )
        count += len(members)
    return _estimated(_mean(tuple(net_periods)), count)


def _economics(
    formula: EvaluationFormulaDefinition,
    observations: tuple[FormulaObservation, ...],
) -> FormulaEvaluationResult:
    ordered = tuple(sorted(observations, key=lambda item: item.ordinal))
    values = tuple(
        sum(_values(members), Decimal(0)) for members in _groups(ordered)
    )
    code = formula.formula_code
    if code is BacktestFormulaCode.CUMULATIVE_RETURN:
        return _estimated(_cumulative(values), len(values))
    if code is BacktestFormulaCode.MAX_DRAWDOWN:
        return _estimated(_maximum_drawdown(values), len(values))
    if code is BacktestFormulaCode.WIN_RATE:
        return _estimated(
            Decimal(sum(item > 0 for item in values)) / Decimal(len(values)),
            len(values),
        )
    annualization = _integer_parameter(formula, "annualization_sessions")
    if annualization <= 0:
        raise ValueError("annualization_sessions must be positive")
    if code is BacktestFormulaCode.ANNUALIZED_RETURN:
        value = _annualized_return(values, annualization)
        return (
            _not_estimable("NON_POSITIVE_WEALTH", len(values))
            if value is None
            else _estimated(value, len(values))
        )
    if code is BacktestFormulaCode.VOLATILITY:
        deviation = _sample_std(values)
        if deviation is None:
            return _not_estimable("INSUFFICIENT_OBSERVATIONS", len(values))
        return _estimated(deviation * Decimal(annualization).sqrt(), len(values))
    if code is BacktestFormulaCode.SHARPE:
        risk_free = _decimal_parameter(formula, "risk_free_per_session")
        excess = tuple(item - risk_free for item in values)
        deviation = _sample_std(excess)
        if deviation is None:
            return _not_estimable("INSUFFICIENT_OBSERVATIONS", len(values))
        if deviation == 0:
            return _not_estimable("ZERO_VARIANCE", len(values))
        return _estimated(
            _mean(excess) / deviation * Decimal(annualization).sqrt(), len(values)
        )
    if code is BacktestFormulaCode.SORTINO:
        mar = _decimal_parameter(formula, "mar_per_session")
        excess = tuple(item - mar for item in values)
        downside = (
            sum((min(Decimal(0), item) ** 2 for item in excess), Decimal(0))
            / Decimal(len(excess))
        ).sqrt()
        if downside == 0:
            return _not_estimable("NO_DOWNSIDE_DEVIATION", len(values))
        return _estimated(
            _mean(excess) / downside * Decimal(annualization).sqrt(), len(values)
        )
    if code is BacktestFormulaCode.CALMAR:
        annualized = _annualized_return(values, annualization)
        if annualized is None:
            return _not_estimable("NON_POSITIVE_WEALTH", len(values))
        drawdown = _maximum_drawdown(values)
        if drawdown == 0:
            return _not_estimable("ZERO_DRAWDOWN", len(values))
        return _estimated(annualized / abs(drawdown), len(values))
    raise ValueError(f"unsupported economic formula: {code.value}")


def _annualized_return(
    values: tuple[Decimal, ...], annualization: int
) -> Decimal | None:
    wealth = Decimal(1) + _cumulative(values)
    if wealth <= 0:
        return None
    return wealth ** (Decimal(annualization) / Decimal(len(values))) - Decimal(1)


def _cumulative(values: tuple[Decimal, ...]) -> Decimal:
    wealth = Decimal(1)
    for value in values:
        wealth *= Decimal(1) + value
    return wealth - Decimal(1)


def _maximum_drawdown(values: tuple[Decimal, ...]) -> Decimal:
    wealth = Decimal(1)
    peak = wealth
    maximum = Decimal(0)
    for value in values:
        wealth *= Decimal(1) + value
        peak = max(peak, wealth)
        if peak > 0:
            maximum = max(maximum, Decimal(1) - wealth / peak)
    return maximum


def _spearman(
    pairs: tuple[tuple[Decimal, Decimal], ...],
) -> Decimal | None:
    left = _midranks(tuple(item[0] for item in pairs))
    right = _midranks(tuple(item[1] for item in pairs))
    left_mean = _mean(left)
    right_mean = _mean(right)
    numerator = sum(
        ((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True)),
        Decimal(0),
    )
    left_sum = sum(((item - left_mean) ** 2 for item in left), Decimal(0))
    right_sum = sum(((item - right_mean) ** 2 for item in right), Decimal(0))
    denominator = (left_sum * right_sum).sqrt()
    return None if denominator == 0 else numerator / denominator


def _midranks(values: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [Decimal(0)] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        rank = (Decimal(cursor + 1) + Decimal(end)) / Decimal(2)
        for index, _ in ordered[cursor:end]:
            ranks[index] = rank
        cursor = end
    return tuple(ranks)


def _sample_std(values: tuple[Decimal, ...]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = _mean(values)
    return (
        sum(((item - mean) ** 2 for item in values), Decimal(0))
        / Decimal(len(values) - 1)
    ).sqrt()


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    return sum(values, Decimal(0)) / Decimal(len(values))


def _values(observations: tuple[FormulaObservation, ...]) -> tuple[Decimal, ...]:
    return tuple(item.value for item in observations if item.value is not None)


def _groups(
    observations: tuple[FormulaObservation, ...],
) -> tuple[tuple[FormulaObservation, ...], ...]:
    keys = tuple(dict.fromkeys(item.group_key for item in observations))
    return tuple(
        tuple(item for item in observations if item.group_key == key) for key in keys
    )


def _parameter(
    formula: EvaluationFormulaDefinition,
    code: str,
    kind: FormulaParameterType,
) -> Decimal | int | bool | str:
    matches = tuple(
        item
        for item in formula.parameters
        if item.parameter_code == code and item.value_type is kind
    )
    if len(matches) != 1:
        raise ValueError(
            f"formula {formula.formula_code.value} requires one {kind.value} {code}"
        )
    return matches[0].value


def _integer_parameter(formula: EvaluationFormulaDefinition, code: str) -> int:
    value = _parameter(formula, code, FormulaParameterType.INTEGER)
    assert isinstance(value, int) and not isinstance(value, bool)
    return value


def _optional_integer_parameter(
    formula: EvaluationFormulaDefinition, code: str, default: int
) -> int:
    matches = tuple(item for item in formula.parameters if item.parameter_code == code)
    return default if not matches else _integer_parameter(formula, code)


def _decimal_parameter(
    formula: EvaluationFormulaDefinition, code: str
) -> Decimal:
    value = _parameter(formula, code, FormulaParameterType.DECIMAL)
    assert isinstance(value, Decimal)
    return value


def _boolean_parameter(formula: EvaluationFormulaDefinition, code: str) -> bool:
    value = _parameter(formula, code, FormulaParameterType.BOOLEAN)
    assert isinstance(value, bool)
    return value


def _text_parameter(formula: EvaluationFormulaDefinition, code: str) -> str:
    value = _parameter(formula, code, FormulaParameterType.TEXT)
    assert isinstance(value, str)
    return value


def _require_unique_observations(
    observations: tuple[FormulaObservation, ...],
) -> None:
    if len({item.observation_id for item in observations}) != len(observations):
        raise ValueError("formula observation identities must be unique")
    ordinals = tuple(item.ordinal for item in observations)
    if ordinals != tuple(sorted(ordinals)) or len(set(ordinals)) != len(ordinals):
        raise ValueError("formula observation ordinals must be ordered and unique")


def _estimated(value: Decimal, count: int) -> FormulaEvaluationResult:
    if not value.is_finite():
        return _not_estimable("NON_FINITE_RESULT", count)
    return FormulaEvaluationResult(
        FormulaResultState.ESTIMABLE,
        value,
        count,
        "ESTIMATED_BY_FROZEN_FORMULA",
    )


def _not_estimable(
    reason: str, count: int = 0
) -> FormulaEvaluationResult:
    return FormulaEvaluationResult(
        FormulaResultState.NOT_ESTIMABLE,
        None,
        count,
        reason,
    )


__all__ = [
    "BacktestFormulaCode",
    "BacktestMetricSurface",
    "EvaluationFormulaDefinition",
    "EvaluationFormulaParameter",
    "FormulaEvaluationResult",
    "FormulaObservation",
    "FormulaParameterType",
    "FormulaResultState",
    "FormulaSourceState",
    "FrozenRankingMembership",
    "evaluate_backtest_formula",
]
