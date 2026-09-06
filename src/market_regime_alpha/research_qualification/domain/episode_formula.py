"""Explicit V2 identity/parameter contract and closed-episode result projection."""

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
    if set(values) != expected or formula.formula_code not in SUPPORTED:
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


def evaluate_episode_formula(formula: EvaluationFormulaDefinition, observations: tuple[FormulaObservation, ...]) -> FormulaEvaluationResult:
    episode_contract(formula)
    if not observations or any(item.source_state is not FormulaSourceState.AVAILABLE or item.value is None for item in observations):
        return FormulaEvaluationResult(FormulaResultState.NOT_ESTIMABLE, None, 0, "INCOMPLETE_EPISODE_PATH")
    periods: dict[str, Decimal] = {}
    for item in observations:
        assert item.value is not None
        periods[item.group_key] = periods.get(item.group_key, Decimal(0)) + item.value
    values = tuple(periods.values())
    value = (Decimal(sum(item > 0 for item in values)) / len(values)
             if formula.formula_code is BacktestFormulaCode.WIN_RATE
             else sum(values, Decimal(0)) / len(values))
    return FormulaEvaluationResult(FormulaResultState.ESTIMABLE, value, len(observations), "INDEPENDENT_EPISODES_V2")
