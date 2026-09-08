"""Pure Evaluation input transforms; V1 is immutable historical arithmetic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from market_regime_alpha.outcome.domain.economic_prices import OutcomeEpisodePrices
from market_regime_alpha.research_qualification.domain.episode_economics import EpisodeLeg, build_episode_path
from market_regime_alpha.research_qualification.domain.episode_formula import episode_contract, episode_selector


from market_regime_alpha.research_qualification.domain.evaluation import (
    EvaluationInput,
    ProtocolMetricDefinition,
)
from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestFormulaCode,
    FormulaObservation,
    FormulaSourceState,
    FrozenRankingMembership,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    CandidateDisposition,
    EvaluationSourceKind,
    EvaluationSourceMeasure,
    EvaluationSliceKind,
    ExploratoryBacktestArmKind,
)
from market_regime_alpha.research_qualification.errors import (
    EvaluationReconciliationError,
)


@dataclass(frozen=True, slots=True)
class _ResolvedMetricInput:
    source: tuple[Any, ...]
    input: EvaluationInput
    turnover: Decimal | None = None
    previous_weight: Decimal | None = None
    buy_turnover: Decimal | None = None
    sell_turnover: Decimal | None = None
    effective_weight: Decimal | None = None
    gross_return: Decimal | None = None
    net_return: Decimal | None = None
    economic_path_sha256: str | None = None
    economic_numerator: Decimal | None = None
    economic_selected: bool = True


def resolve_metric_inputs(
    metric: ProtocolMetricDefinition,
    source_rows: list[tuple[Any, ...]],
    session_dates: tuple[tuple[UUID, date], ...] = (),
) -> tuple[_ResolvedMetricInput, ...]:
    if metric.formula is not None and metric.formula.formula_version == 2:
        return _episode_inputs(metric, source_rows, session_dates)
    resolved: list[_ResolvedMetricInput] = []
    previous_weights: dict[tuple[object, object], Decimal] = {}
    for source in source_rows:
        try:
            arm_kind = ExploratoryBacktestArmKind(str(source[17])) if source[17] is not None else None
        except ValueError:
            # Current generic arm codes are exact relational lineage, not
            # the private legacy WP arm vocabulary.
            arm_kind = None
        has_backtest_arm = source[14] is not None and source[17] is not None
        if (
            metric.slice_kind is EvaluationSliceKind.EXPLORATORY_BACKTEST_ARM
            or metric.source_kind is not EvaluationSourceKind.OUTCOME_METRIC
        ) and metric.source_kind is not EvaluationSourceKind.EXPERIMENTAL_FORECAST_OUTCOME_PAIR and not has_backtest_arm:
            raise EvaluationReconciliationError("exploratory metric source lacks exact Backtest arm lineage")
        if metric.source_kind is EvaluationSourceKind.EXPERIMENTAL_FORECAST_OUTCOME_PAIR:
            if len(source) != 46 or source[45] != metric.experimental_model_use_id or has_backtest_arm:
                raise EvaluationReconciliationError("experimental forecast source lacks its exact independent model use")
        value_status = str(source[5])
        decimal_value = source[6]
        boolean_value = source[7]
        secondary_decimal_value: Decimal | None = None
        turnover: Decimal | None = None
        previous_weight: Decimal | None = None
        buy_turnover: Decimal | None = None
        sell_turnover: Decimal | None = None
        effective_weight: Decimal | None = None
        gross_return: Decimal | None = None
        net_return: Decimal | None = None
        if metric.source_kind is EvaluationSourceKind.CANDIDATE_DISPOSITION:
            decimal_value = None
            boolean_value = str(source[3]) == CandidateDisposition.SELECTED.value
            value_status = "COMPLETE"
        elif metric.source_kind is EvaluationSourceKind.SIGNAL_STATUS:
            if source[24] is None:
                raise EvaluationReconciliationError("Signal source is absent")
            signal_status = str(source[25])
            if signal_status in {"UNKNOWN", "NOT_ESTIMABLE"}:
                boolean_value = None
                value_status = "UNAVAILABLE"
            else:
                boolean_value = signal_status == "PRESENT"
                value_status = "COMPLETE"
            decimal_value = None
        elif metric.source_kind in {EvaluationSourceKind.FORECAST_OUTCOME_PAIR, EvaluationSourceKind.EXPERIMENTAL_FORECAST_OUTCOME_PAIR}:
            if source[26] is None or source[28] is None:
                raise EvaluationReconciliationError("Forecast source is absent or ambiguous")
            decimal_value = source[29]
            secondary_decimal_value = source[6]
            boolean_value = None
            if (
                str(source[27]) != "AVAILABLE"
                or decimal_value is None
                or secondary_decimal_value is None
                or str(source[5]) not in {"COMPLETE", "PARTIAL"}
            ):
                value_status = "UNAVAILABLE"
            else:
                value_status = str(source[5])
        elif metric.source_kind is EvaluationSourceKind.CANDIDATE_OUTCOME_PAIR:
            outcome_value = source[6]
            outcome_available = outcome_value is not None and str(source[5]) in {"COMPLETE", "PARTIAL"}
            if metric.source_measure is EvaluationSourceMeasure.CANDIDATE_SCORE_VS_TARGET:
                decimal_value = source[37]
                secondary_decimal_value = outcome_value
                boolean_value = None
                if decimal_value is None or not outcome_available:
                    value_status = "UNAVAILABLE"
            elif metric.source_measure is EvaluationSourceMeasure.CANDIDATE_TOP_K_RETURN:
                decimal_value = outcome_value if str(source[3]) == CandidateDisposition.SELECTED.value and outcome_available else None
                boolean_value = None
                if decimal_value is None:
                    value_status = "UNAVAILABLE"
            else:
                decimal_value = None
                boolean_value = (
                    Decimal(outcome_value) > 0 if str(source[3]) == CandidateDisposition.SELECTED.value and outcome_available else None
                )
                if boolean_value is None:
                    value_status = "UNAVAILABLE"
        elif metric.source_kind in {
            EvaluationSourceKind.PORTFOLIO_LINE,
            EvaluationSourceKind.PORTFOLIO_OUTCOME,
        }:
            if source[30] is None or source[31] is None or source[34] is None:
                raise EvaluationReconciliationError("Portfolio source is absent or ambiguous")
            proposed_weight = Decimal(source[33])
            weight_key = (source[14], source[11])
            prior = previous_weights.get(weight_key, Decimal(0))
            previous_weight = prior
            turnover = abs(proposed_weight - prior)
            buy_turnover = max(proposed_weight - prior, Decimal(0))
            sell_turnover = max(prior - proposed_weight, Decimal(0))
            previous_weights[weight_key] = proposed_weight
            if metric.source_kind is EvaluationSourceKind.PORTFOLIO_LINE:
                decimal_value = proposed_weight if metric.source_measure is EvaluationSourceMeasure.TARGET_WEIGHT else turnover
                boolean_value = None
                value_status = "COMPLETE"
            else:
                if source[34] is None:
                    raise EvaluationReconciliationError("Risk Gate source is absent")
                risk_status = str(source[35])
                if risk_status == "UNKNOWN":
                    decimal_value = None
                    value_status = "UNAVAILABLE"
                elif source[6] is None or str(source[5]) not in {"COMPLETE", "PARTIAL"}:
                    decimal_value = None
                    value_status = "UNAVAILABLE"
                else:
                    effective_weight = proposed_weight if risk_status == "AUTHORIZED" else Decimal(0)
                    gross_return = effective_weight * Decimal(source[6])
                    if source[21] is None or source[23] is None:
                        raise EvaluationReconciliationError("assumed-cost roster is absent")
                    if metric.formula is not None:
                        if source[41] is None or source[42] is None:
                            raise EvaluationReconciliationError("Formula cost sources require explicit charge sides")
                        assumed_cost = (buy_turnover * Decimal(source[41]) + sell_turnover * Decimal(source[42])) / Decimal(10_000)
                    else:
                        # The original non-formula reducer's frozen contract
                        # charged its total bps per unit turnover. Replay of
                        # that historical contract must not be reinterpreted.
                        assumed_cost = turnover * Decimal(source[23]) / Decimal(10_000)
                    net_return = gross_return - assumed_cost
                    decimal_value = gross_return if metric.source_measure is EvaluationSourceMeasure.GROSS_PORTFOLIO_RETURN else net_return
                    value_status = str(source[5])
                boolean_value = None
        elif metric.source_kind is EvaluationSourceKind.RISK_DECISION:
            if source[34] is None:
                raise EvaluationReconciliationError("Risk source is absent")
            risk_status = str(source[35])
            if risk_status == "UNKNOWN":
                boolean_value = None
                value_status = "UNAVAILABLE"
            else:
                boolean_value = risk_status == "REJECTED"
                value_status = "COMPLETE"
            decimal_value = None
        group_key = f"{source[14] or 'UNBOUND'}:{source[12].isoformat()}"
        item = EvaluationInput(
            evaluation_observation_id=UUID(str(source[0])),
            candidate_disposition=CandidateDisposition(str(source[3])),
            source_value_status=value_status,
            decimal_value=decimal_value,
            boolean_value=boolean_value,
            secondary_decimal_value=secondary_decimal_value,
            backtest_arm_kind=arm_kind,
            group_key=group_key,
        )
        resolved.append(
            _ResolvedMetricInput(
                source=source,
                input=item,
                turnover=turnover,
                previous_weight=previous_weight,
                buy_turnover=buy_turnover,
                sell_turnover=sell_turnover,
                effective_weight=effective_weight,
                gross_return=gross_return,
                net_return=net_return,
            )
        )
    return tuple(resolved)


def formula_observations(
    metric: ProtocolMetricDefinition,
    resolved: tuple[_ResolvedMetricInput, ...],
) -> tuple[FormulaObservation, ...]:
    assert metric.formula is not None
    code = metric.formula.formula_code
    if metric.formula.formula_version == 2:
        return tuple(
            FormulaObservation(
                observation_id=item.input.evaluation_observation_id,
                ordinal=ordinal,
                group_key=item.input.group_key or "ALL",
                source_state=FormulaSourceState.AVAILABLE,
                value=item.economic_numerator,
            )
            for ordinal, item in enumerate(resolved, 1)
            if item.economic_selected
        )
    ranked_membership: dict[UUID, FrozenRankingMembership] = {}
    if code in {
        BacktestFormulaCode.TOP_K_RETURN,
        BacktestFormulaCode.TOP_BOTTOM_SPREAD,
    }:
        width = next(int(parameter.value) for parameter in metric.formula.parameters if parameter.parameter_code == "top_k")
        group_keys = tuple(dict.fromkeys(item.input.group_key or "ALL" for item in resolved))
        for group_key in group_keys:
            members = tuple(item for item in resolved if (item.input.group_key or "ALL") == group_key)
            ranking_index = 29 if metric.source_kind in {EvaluationSourceKind.FORECAST_OUTCOME_PAIR, EvaluationSourceKind.EXPERIMENTAL_FORECAST_OUTCOME_PAIR} else 37
            if any(item.source[ranking_index] is None for item in members):
                continue
            ranked = tuple(
                sorted(
                    members,
                    key=lambda item: (
                        -Decimal(item.source[ranking_index]),
                        str(item.source[11]),
                    ),
                )
            )
            for item in ranked[:width]:
                ranked_membership[item.input.evaluation_observation_id] = FrozenRankingMembership.TOP
            if code is BacktestFormulaCode.TOP_BOTTOM_SPREAD:
                for item in ranked[-width:]:
                    identity = item.input.evaluation_observation_id
                    if identity in ranked_membership:
                        # Overlap is intentionally not coerced into a
                        # fabricated spread; the formula sees incomplete
                        # bottom membership and returns NOT_ESTIMABLE.
                        continue
                    ranked_membership[identity] = FrozenRankingMembership.BOTTOM
    observations: list[FormulaObservation] = []
    for ordinal, item in enumerate(resolved, start=1):
        source_status = item.input.source_value_status
        source_state = {
            "COMPLETE": FormulaSourceState.AVAILABLE,
            "PARTIAL": FormulaSourceState.AVAILABLE,
            "UNAVAILABLE": FormulaSourceState.UNAVAILABLE,
            "FAILED": FormulaSourceState.FAILED,
        }.get(source_status, FormulaSourceState.UNKNOWN)
        if code is BacktestFormulaCode.SOURCE_GAP_RATE and item.source[43]:
            source_state = FormulaSourceState.SOURCE_GAP
        elif code is BacktestFormulaCode.MISSINGNESS_RATE and item.source[44]:
            source_state = FormulaSourceState.MISSING
        value = item.input.decimal_value
        secondary_value = item.input.secondary_decimal_value
        if item.input.boolean_value is not None:
            value = Decimal(1 if item.input.boolean_value else 0)
        if code in {
            BacktestFormulaCode.GROSS_EXPOSURE,
            BacktestFormulaCode.NET_EXPOSURE,
            BacktestFormulaCode.TURNOVER,
        }:
            value = None if item.source[33] is None else Decimal(item.source[33])
            secondary_value = item.previous_weight
        elif code is BacktestFormulaCode.NET_RETURN_ASSUMED_COST:
            value = item.gross_return
        membership = ranked_membership.get(
            item.input.evaluation_observation_id,
            (
                FrozenRankingMembership.SELECTED
                if item.input.candidate_disposition is CandidateDisposition.SELECTED
                else FrozenRankingMembership.ELIGIBLE
            ),
        )
        observations.append(
            FormulaObservation(
                observation_id=item.input.evaluation_observation_id,
                ordinal=ordinal,
                group_key=item.input.group_key or "ALL",
                source_state=source_state,
                value=value,
                secondary_value=secondary_value,
                ranking_membership=membership,
                decision_time=item.source[12],
                outcome_known_at=item.source[40],
                buy_turnover=item.buy_turnover,
                sell_turnover=item.sell_turnover,
            )
        )
    return tuple(observations)


def _episode_inputs(
    metric: ProtocolMetricDefinition, rows: list[tuple[Any, ...]], session_dates: tuple[tuple[UUID, date], ...]
) -> tuple[_ResolvedMetricInput, ...]:
    assert metric.formula is not None
    policy, entry_id, exit_id = episode_contract(metric.formula)
    legs = []
    for row in rows:
        if any(row[index] is None for index in (14, 30, 31, 34, 41, 42)):
            raise EvaluationReconciliationError("episode requires exact Portfolio/Risk/arm/cost Authority")
        if Decimal(row[41]) != policy.buy_fee_bps or Decimal(row[42]) != policy.sell_fee_bps:
            raise EvaluationReconciliationError("episode formula differs from frozen directional cost roster")
        if len(row) != 46 or not isinstance(row[45], OutcomeEpisodePrices):
            raise EvaluationReconciliationError("episode requires exact Outcome-owned checkpoint facts")
        prices = row[45]
        if prices.revision_id != row[2] or prices.entry_checkpoint_id != entry_id or prices.exit_checkpoint_id != exit_id:
            raise EvaluationReconciliationError("episode Outcome identity differs")
        legs.append(
            EpisodeLeg(
                observation_id=UUID(str(row[0])),
                instrument_id=UUID(str(row[11])),
                episode_key=f"{row[14]}:{row[9]}",
                arm_key=str(row[14]),
                fold_key=str(row[15]),
                decision_time=row[12],
                entry_time=prices.entry_time,
                exit_time=prices.exit_time,
                knowledge_cutoff=prices.knowledge_cutoff,
                outcome_known_at=prices.known_at,
                proposed_weight=Decimal(row[33]),
                risk_status=str(row[35]),
                entry_price=prices.entry_close,
                exit_price=prices.exit_close,
                price_basis=prices.price_basis,
                availability="AVAILABLE" if row[32] in {"INCLUDED", "EXCLUDED"} else "UNKNOWN",
            )
        )
    path = build_episode_path(policy, tuple(legs))
    if any(episode.reason != "EPISODE_CLOSED" for episode in path.episodes):
        raise EvaluationReconciliationError("episode cannot close: " + ",".join(episode.reason for episode in path.episodes))
    selector, key = episode_selector(metric.formula)
    dates = dict(session_dates)
    if selector == "FOLD" and key not in {leg.fold_key for leg in legs}:
        raise EvaluationReconciliationError("episode slice fold is not in the exact parent")
    if selector == "TIME_MONTH" and any(row[16] not in dates for row in rows):
        raise EvaluationReconciliationError("episode time slice requires canonical Decision TradingSession dates")
    selected_ids = frozenset(
        leg.observation_id
        for row, leg in zip(rows, legs, strict=True)
        if selector == "ALL"
        or selector == "FOLD"
        and leg.fold_key == key
        or selector == "TIME_MONTH"
        and dates[row[16]].strftime("%Y-%m") == key
    )
    # Selection cannot discard incomplete episodes or redefine their capital.
    path.slice(selected_ids)
    trades = {trade.observation_id: trade for episode in path.episodes for trade in episode.legs}
    results = []
    for row, leg in zip(rows, legs, strict=True):
        trade = trades[leg.observation_id]
        gross, net = trade.gross_profit / policy.initial_capital, trade.net_profit / policy.initial_capital
        buy, sell = trade.buy_notional / policy.initial_capital, trade.sell_notional / policy.initial_capital
        code = metric.formula.formula_code
        numerator = (
            trade.buy_notional + trade.sell_notional
            if code is BacktestFormulaCode.TURNOVER
            else trade.buy_notional
            if code in {BacktestFormulaCode.GROSS_EXPOSURE, BacktestFormulaCode.NET_EXPOSURE}
            else trade.gross_profit
            if metric.source_measure is EvaluationSourceMeasure.GROSS_PORTFOLIO_RETURN
            else trade.net_profit
        )
        results.append(
            _ResolvedMetricInput(
                source=row,
                input=EvaluationInput(
                    leg.observation_id,
                    CandidateDisposition(str(row[3])),
                    "COMPLETE",
                    gross if metric.source_measure is EvaluationSourceMeasure.GROSS_PORTFOLIO_RETURN else net,
                    None,
                    group_key=leg.episode_key,
                ),
                turnover=buy + sell,
                previous_weight=Decimal(0),
                buy_turnover=buy,
                sell_turnover=sell,
                effective_weight=buy,
                gross_return=gross,
                net_return=net,
                economic_path_sha256=path.content_sha256,
                economic_numerator=numerator,
                economic_selected=leg.observation_id in selected_ids,
            )
        )
    return tuple(results)
