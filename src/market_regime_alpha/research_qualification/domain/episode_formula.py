"""Explicit V2 identity/parameter contract and closed-episode result projection."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.research_qualification.domain.episode_economics import EpisodePolicy
from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestFormulaCode, EvaluationFormulaDefinition, FormulaEvaluationResult,
    FormulaObservation, FormulaResultState, FormulaSourceState,
)


SUPPORTED = frozenset({BacktestFormulaCode.MEAN, BacktestFormulaCode.NET_RETURN_ASSUMED_COST,
                       BacktestFormulaCode.TURNOVER, BacktestFormulaCode.GROSS_EXPOSURE,
                       BacktestFormulaCode.NET_EXPOSURE, BacktestFormulaCode.WIN_RATE})


def episode_contract(formula: EvaluationFormulaDefinition) -> tuple[EpisodePolicy, UUID, UUID]:
    values = {item.parameter_code: item.value for item in formula.parameters}
    expected = {"economic_model", "execution_assumption", "price_basis", "initial_capital",
                "buy_fee_bps", "sell_fee_bps", "minimum_fee", "slippage_bps",
                "final_liquidation", "carry_forward", "entry_checkpoint_id", "exit_checkpoint_id"}
    episode_selector(formula)
    if set(values) - {"episode_slice_kind", "episode_slice_key"} != expected or formula.formula_code not in SUPPORTED:
        raise ValueError("unsupported or incomplete V2 independent episode formula contract")
    for name in ("initial_capital", "buy_fee_bps", "sell_fee_bps", "minimum_fee", "slippage_bps"):
        if not isinstance(values[name], Decimal):
            raise ValueError("episode currency/cost parameters must be Decimal")
    if values["final_liquidation"] is not True or formula.rounding_mode != "ROUND_HALF_EVEN":
        raise ValueError("episode requires explicit liquidation and ROUND_HALF_EVEN")
    entry, exit = UUID(str(values["entry_checkpoint_id"])), UUID(str(values["exit_checkpoint_id"]))
    if entry == exit:
        raise ValueError("episode entry and exit checkpoints must differ")
    return EpisodePolicy(
        initial_capital=Decimal(str(values["initial_capital"])),
        buy_fee_bps=Decimal(str(values["buy_fee_bps"])), sell_fee_bps=Decimal(str(values["sell_fee_bps"])),
        model=str(values["economic_model"]), execution=str(values["execution_assumption"]),
        price_basis=str(values["price_basis"]), final_liquidation=True,
        carry_forward=str(values["carry_forward"]), minimum_fee=Decimal(str(values["minimum_fee"])),
        slippage_bps=Decimal(str(values["slippage_bps"])), decimal_precision=formula.decimal_precision,
    ), entry, exit


def episode_selector(formula: EvaluationFormulaDefinition) -> tuple[str, str | None]:
    values = {item.parameter_code: item.value for item in formula.parameters}
    kind, key = str(values.get("episode_slice_kind", "ALL")), values.get("episode_slice_key")
    if kind == "ALL" and key is None:
        return kind, None
    if not isinstance(key, str):
        raise ValueError("episode slice requires an exact key")
    if kind == "FOLD":
        UUID(key)
    elif kind == "TIME_MONTH":
        try:
            if len(key) != 7 or date.fromisoformat(key + "-01").strftime("%Y-%m") != key:
                raise ValueError
        except ValueError as exc:
            raise ValueError("episode slice month must be YYYY-MM") from exc
    else:
        raise ValueError("unsupported episode slice")
    return kind, key


def evaluate_episode_formula(formula: EvaluationFormulaDefinition, observations: tuple[FormulaObservation, ...]) -> FormulaEvaluationResult:
    policy, _, _ = episode_contract(formula)
    if not observations or any(item.source_state is not FormulaSourceState.AVAILABLE or item.value is None for item in observations):
        return FormulaEvaluationResult(FormulaResultState.NOT_ESTIMABLE, None, 0, "INCOMPLETE_EPISODE_PATH")
    periods: dict[str, Decimal] = {}
    for item in observations:
        assert item.value is not None
        periods[item.group_key] = periods.get(item.group_key, Decimal(0)) + item.value
    values = tuple(periods.values())
    value = (Decimal(sum(item > 0 for item in values)) / len(values)
             if formula.formula_code is BacktestFormulaCode.WIN_RATE
             else sum(values, Decimal(0)) / (policy.initial_capital * len(values)))
    return FormulaEvaluationResult(FormulaResultState.ESTIMABLE, value, len(values), "INDEPENDENT_EPISODES_V2")
