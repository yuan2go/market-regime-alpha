"""Pure MR-1 Candidate comparator families with matched capital and cost mechanics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
import json
import math
from numbers import Integral
from typing import Any

from market_regime_alpha.research.prr_artifact_schemas import (
    CandidateBaselineId,
    MR1_MATCHED_K_SELECTION_SCHEMA_VERSION,
    MR1_BASELINE_PRIMARY_SEED,
    MR1_CANDIDATE_BASELINE_PRIMARY_KEY,
    MR1_CANDIDATE_BASELINE_SCHEMA_VERSION,
    MR1_CASH_LOCK_POLICY_ID,
    MR1_EXIT_TIMES,
    MR1_MATCHED_K_ALGORITHM_ID,
    MR1_MISSING_WEIGHT_POLICY_ID,
    MatchedKSelection,
    ModelCandidatePopulation,
    matched_k_selection_id,
    model_population_hash,
    selected_symbols_hash,
    canonical_identity_hash,
)
from market_regime_alpha.research.prr_mvp_1 import ExploratoryExecutionCostConfig


@dataclass(frozen=True, slots=True)
class ReferenceTradeEconomics:
    gross_return: float
    net_return: float
    transaction_cost: float
    slippage_cost: float
    entry_price: float
    realized_exit_price: float
    entry_notional: float
    exit_notional: float
    quantity: float
    buy_commission: float
    sell_commission: float
    stamp_duty: float
    transfer_fee: float


@dataclass(frozen=True, slots=True)
class CandidateBaselineBuildResult:
    baseline_rows: tuple[dict[str, Any], ...]
    selection_rows: tuple[dict[str, Any], ...]
    populations: tuple[ModelCandidatePopulation, ...]


_EXIT_TARGETS = {
    "09:35": "NEXT_SESSION_0935_RETURN",
    "10:00": "NEXT_SESSION_1000_RETURN",
    "10:30": "NEXT_SESSION_1030_RETURN",
    "CLOSE": "NEXT_SESSION_CLOSE_RETURN",
}

MR1_RANKING_SOURCE_TARGET_ID = (
    "target-r5-decision-reference-to-next-session-close-return-v1"
)


def build_model_candidate_populations(
    *,
    dataset_id: str,
    ranking_rows: Iterable[Mapping[str, Any]],
    target_id: str = MR1_RANKING_SOURCE_TARGET_ID,
) -> tuple[ModelCandidatePopulation, ...]:
    """Build one fail-closed eligible ranking population per Decision Date and model."""

    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("dataset_id must be non-empty")
    rows = tuple(dict(row) for row in ranking_rows if str(row.get("target_id")) == target_id)
    if not rows:
        raise ValueError("ranking rows must contain the MR-1 source Target")
    grouped: dict[tuple[date, str], list[dict[str, Any]]] = {}
    seen_keys: set[tuple[date, str, str]] = set()
    for row in rows:
        decision_day = date.fromisoformat(str(row.get("decision_date")))
        model_id = str(row.get("model_id") or "")
        symbol = str(row.get("symbol") or "")
        if not model_id or not symbol:
            raise ValueError("ranking model_id and symbol must be non-empty")
        key = (decision_day, model_id, symbol)
        if key in seen_keys:
            raise ValueError("model ranking population symbols must be unique")
        seen_keys.add(key)
        grouped.setdefault((decision_day, model_id), []).append(row)

    populations: list[ModelCandidatePopulation] = []
    for (decision_day, model_id), group in sorted(grouped.items()):
        ranked_symbols: list[tuple[int, str]] = []
        for row in group:
            eligible = row.get("eligible_for_ranking")
            if not isinstance(eligible, bool):
                raise TypeError("eligible_for_ranking must be bool")
            rank = row.get("rank")
            missing_rank = rank is None or (
                isinstance(rank, float) and math.isnan(rank)
            )
            if eligible and missing_rank:
                raise ValueError("eligible symbol must have a rank")
            if not eligible and not missing_rank:
                raise ValueError("ineligible symbol must not have a rank")
            if eligible:
                if isinstance(rank, bool) or not isinstance(rank, Integral) or int(rank) <= 0:
                    raise ValueError("eligible rank must be a positive integer")
                ranked_symbols.append((int(rank), str(row["symbol"])))
        ranks = tuple(rank for rank, _ in ranked_symbols)
        if tuple(sorted(ranks)) != tuple(range(1, len(ranks) + 1)):
            raise ValueError("eligible ranks must be exactly 1..N")
        symbols = tuple(sorted(symbol for _, symbol in ranked_symbols))
        population_hash = model_population_hash(
            dataset_id=dataset_id,
            decision_date=decision_day,
            target_id=target_id,
            symbols=symbols,
        )
        populations.append(
            ModelCandidatePopulation(
                dataset_id=dataset_id,
                decision_date=decision_day,
                model_id=model_id,
                target_id=target_id,
                symbols=symbols,
                population_size=len(symbols),
                population_hash=population_hash,
            )
        )
    return tuple(populations)


def select_matched_k_population(
    population: ModelCandidatePopulation,
    *,
    top_k: int,
    seed: int = MR1_BASELINE_PRIMARY_SEED,
) -> MatchedKSelection:
    symbols = select_matched_k_symbols(
        dataset_id=population.dataset_id,
        decision_date=population.decision_date,
        symbols=population.symbols,
        top_k=top_k,
        baseline_seed=seed,
    )
    symbol_hash = selected_symbols_hash(symbols)
    return MatchedKSelection(
        population=population,
        symbols=symbols,
        top_k=top_k,
        seed=seed,
        selection_id=matched_k_selection_id(
            population_hash=population.population_hash,
            symbols=symbols,
            top_k=top_k,
            seed=seed,
        ),
        selected_symbols_hash=symbol_hash,
    )


def reference_trade_economics(
    *,
    reference_price: float,
    exit_price: float,
    weight: float,
    cost_config: ExploratoryExecutionCostConfig,
) -> ReferenceTradeEconomics:
    """Compute one reference-mark trade under the same mechanics as model replay."""

    for label, value in (("reference_price", reference_price), ("exit_price", exit_price), ("weight", weight)):
        if isinstance(value, bool) or not math.isfinite(float(value)):
            raise ValueError(f"{label} must be finite numeric")
    if reference_price <= 0.0 or exit_price <= 0.0 or weight <= 0.0 or weight > 1.0:
        raise ValueError("reference prices and weight must be positive, with weight at most one")
    entry_price = reference_price * (1.0 + cost_config.entry_slippage_bps / 10_000.0)
    realized_exit = exit_price * (1.0 - cost_config.exit_slippage_bps / 10_000.0)
    entry_notional = cost_config.normalized_trade_notional * weight
    quantity = entry_notional / entry_price
    buy_commission = max(
        entry_notional * cost_config.buy_commission_bps / 10_000.0,
        cost_config.minimum_commission,
    )
    exit_notional = quantity * realized_exit
    sell_commission = max(
        exit_notional * cost_config.sell_commission_bps / 10_000.0,
        cost_config.minimum_commission,
    )
    stamp_duty = exit_notional * cost_config.sell_stamp_duty_bps / 10_000.0
    transfer_fee = (entry_notional + exit_notional) * cost_config.transfer_fee_bps / 10_000.0
    transaction_cost = buy_commission + sell_commission + stamp_duty + transfer_fee
    return ReferenceTradeEconomics(
        gross_return=exit_price / reference_price - 1.0,
        net_return=(exit_notional - transaction_cost - entry_notional) / entry_notional,
        transaction_cost=transaction_cost,
        slippage_cost=quantity * (entry_price - reference_price) + quantity * (exit_price - realized_exit),
        entry_price=entry_price,
        realized_exit_price=realized_exit,
        entry_notional=entry_notional,
        exit_notional=exit_notional,
        quantity=quantity,
        buy_commission=buy_commission,
        sell_commission=sell_commission,
        stamp_duty=stamp_duty,
        transfer_fee=transfer_fee,
    )


def select_matched_k_symbols(
    *,
    dataset_id: str,
    decision_date: date,
    symbols: Iterable[str],
    top_k: int,
    baseline_seed: int = MR1_BASELINE_PRIMARY_SEED,
) -> tuple[str, ...]:
    """Select a deterministic rank-blind K without Target, score, rank, or row order."""

    if not dataset_id.strip():
        raise ValueError("dataset_id must be non-empty")
    if not isinstance(decision_date, date):
        raise TypeError("decision_date must be a date")
    if isinstance(top_k, bool) or top_k <= 0:
        raise ValueError("top_k must be positive")
    if isinstance(baseline_seed, bool) or not isinstance(baseline_seed, int):
        raise TypeError("baseline_seed must be an int")
    values = tuple(symbols)
    if not values or any(not isinstance(symbol, str) or not symbol.strip() for symbol in values):
        raise ValueError("symbols must be non-empty strings")
    if len(values) != len(set(values)):
        raise ValueError("symbols must be unique")
    ranked = sorted(
        values,
        key=lambda symbol: (
            sha256(
                f"{dataset_id}\0{decision_date.isoformat()}\0{symbol}\0{baseline_seed}".encode()
            ).hexdigest(),
            symbol,
        ),
    )
    return tuple(ranked[:top_k])


def build_candidate_daily_baselines(
    *,
    populations: Iterable[ModelCandidatePopulation],
    target_rows: Iterable[Mapping[str, Any]],
    decision_dates: Iterable[date],
    cost_configs: Mapping[str, ExploratoryExecutionCostConfig],
    top_k: int,
    baseline_seed: int = MR1_BASELINE_PRIMARY_SEED,
) -> CandidateBaselineBuildResult:
    """Build model-population comparators and auditable matched-K slot evidence."""

    dates = tuple(decision_dates)
    if not dates or dates != tuple(sorted(dates)) or len(dates) != len(set(dates)):
        raise ValueError("Decision Dates must be non-empty, chronological, and unique")
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if not cost_configs:
        raise ValueError("cost_configs must not be empty")
    targets = tuple(dict(row) for row in target_rows)
    _validate_target_rows(targets)
    population_rows = tuple(populations)
    if not population_rows:
        raise ValueError("model Candidate Populations must not be empty")
    population_keys = tuple(
        (population.decision_date, population.model_id) for population in population_rows
    )
    if len(population_keys) != len(set(population_keys)):
        raise ValueError("each model and Decision Date must have one Candidate Population")
    dataset_ids = {population.dataset_id for population in population_rows}
    if len(dataset_ids) != 1:
        raise ValueError("model Candidate Populations must use one Dataset")
    expected_dates = set(dates)
    model_ids = tuple(sorted({population.model_id for population in population_rows}))
    for model_id in model_ids:
        model_dates = {
            population.decision_date
            for population in population_rows
            if population.model_id == model_id
        }
        if model_dates != expected_dates:
            raise ValueError("each model Candidate Population must cover every Decision Date")
    target_index = {
        (str(row["decision_date"]), str(row["target_id"]), str(row["symbol"])): row
        for row in targets
    }
    rows: list[dict[str, Any]] = []
    selection_rows: list[dict[str, Any]] = []
    population_index = {
        (population.model_id, population.decision_date): population
        for population in population_rows
    }
    for model_id in model_ids:
        for exit_time in MR1_EXIT_TIMES:
            endpoint_target_id = _EXIT_TARGETS[exit_time]
            for scenario in sorted(cost_configs):
                costs = cost_configs[scenario]
                active_until: date | None = None
                for decision_day in dates:
                    population = population_index[(model_id, decision_day)]
                    if population.population_size == 0:
                        raise ValueError("model Candidate Population must not be empty")
                    day_rows = tuple(
                        target_index[(decision_day.isoformat(), endpoint_target_id, symbol)]
                        for symbol in population.symbols
                        if (decision_day.isoformat(), endpoint_target_id, symbol) in target_index
                    )
                    if len(day_rows) != population.population_size:
                        raise ValueError(
                            f"Candidate baseline target coverage missing: {decision_day} "
                            f"{endpoint_target_id} {model_id}"
                        )
                    matched = select_matched_k_population(
                        population,
                        top_k=top_k,
                        seed=baseline_seed,
                    )
                    if exit_time == "CLOSE" and active_until is not None and decision_day <= active_until:
                        rows.extend(
                            _cash_locked_rows(
                                population=population,
                                selection=matched,
                                exit_time=exit_time,
                                scenario=scenario,
                                top_k=top_k,
                                costs=costs,
                            )
                        )
                        continue
                    all_gross, all_net, all_observed, all_missing = _portfolio_returns(
                        rows=day_rows,
                        selected_symbols=population.symbols,
                        declared_slots=population.population_size,
                        costs=costs,
                    )
                    matched_gross, matched_net, matched_observed, matched_missing = _portfolio_returns(
                        rows=day_rows,
                        selected_symbols=matched.symbols,
                        declared_slots=top_k,
                        costs=costs,
                    )
                    all_selection_id = canonical_identity_hash(
                        {
                            "scope": "MODEL_POPULATION_ALL_CANDIDATE_V1",
                            "population_hash": population.population_hash,
                        }
                    )
                    common = {
                        "schema_version": MR1_CANDIDATE_BASELINE_SCHEMA_VERSION,
                        "decision_date": decision_day.isoformat(),
                        "model_id": model_id,
                        "target_id": population.target_id,
                        "exit_time": exit_time,
                        "cost_scenario": scenario,
                        "baseline_seed": baseline_seed,
                        "top_k": top_k,
                        "population_definition_id": population.definition_id,
                        "candidate_population_size": population.population_size,
                        "candidate_symbol_count": population.population_size,
                        "candidate_population_hash": population.population_hash,
                        "cash_locked_weight": 0.0,
                        "baseline_slot_status": "EXECUTED",
                        "cost_policy_id": _cost_policy_id(costs),
                        "cash_lock_policy_id": MR1_CASH_LOCK_POLICY_ID,
                        "missing_weight_policy_id": MR1_MISSING_WEIGHT_POLICY_ID,
                        "data_eligibility": "EXPLORATORY",
                    }
                    rows.extend(
                        (
                            _baseline_row(
                                common,
                                CandidateBaselineId.ALL_CANDIDATE_GROSS_V1,
                                population.population_size,
                                all_gross,
                                all_gross,
                                all_observed,
                                all_missing,
                                "model-population-all-candidate-equal-weight-v1",
                                all_selection_id,
                                selected_symbols_hash(population.symbols),
                            ),
                            _baseline_row(
                                common,
                                CandidateBaselineId.MATCHED_K_HASH_GROSS_V1,
                                len(matched.symbols),
                                matched_gross,
                                matched_gross,
                                matched_observed,
                                matched_missing,
                                MR1_MATCHED_K_ALGORITHM_ID,
                                matched.selection_id,
                                matched.selected_symbols_hash,
                            ),
                            _baseline_row(
                                common,
                                CandidateBaselineId.MATCHED_K_HASH_NET_V1,
                                len(matched.symbols),
                                matched_gross,
                                matched_net,
                                matched_observed,
                                matched_missing,
                                MR1_MATCHED_K_ALGORITHM_ID,
                                matched.selection_id,
                                matched.selected_symbols_hash,
                            ),
                            _baseline_row(
                                common,
                                CandidateBaselineId.ALL_CANDIDATE_NET_DIAGNOSTIC_V1,
                                population.population_size,
                                all_gross,
                                all_net,
                                all_observed,
                                all_missing,
                                "model-population-all-candidate-cost-diagnostic-v1",
                                all_selection_id,
                                selected_symbols_hash(population.symbols),
                            ),
                        )
                    )
                    selection_rows.extend(
                        _selection_evidence_rows(
                            selection=matched,
                            endpoint_target_id=endpoint_target_id,
                            exit_time=exit_time,
                            scenario=scenario,
                            target_index=target_index,
                        )
                    )
                    if exit_time == "CLOSE":
                        target_session_dates = {
                            date.fromisoformat(str(row["target_session_date"]))
                            for row in day_rows
                            if row.get("target_session_date") is not None
                        }
                        if len(target_session_dates) != 1:
                            raise ValueError("CLOSE baseline requires one common target session date")
                        active_until = next(iter(target_session_dates))
    _require_unique_keys(rows, MR1_CANDIDATE_BASELINE_PRIMARY_KEY, "Candidate daily baseline")
    _require_unique_keys(
        selection_rows,
        (
            "decision_date",
            "model_id",
            "exit_time",
            "cost_scenario",
            "baseline_seed",
            "slot_index",
        ),
        "matched-K selection evidence",
    )
    return CandidateBaselineBuildResult(
        baseline_rows=tuple(rows),
        selection_rows=tuple(selection_rows),
        populations=population_rows,
    )


def compound_candidate_baselines(
    rows: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str, str, str], dict[str, float]]:
    """Compound daily rows by baseline, cost scenario, and exit time."""

    result: dict[tuple[str, str, str, str], dict[str, float]] = {}
    for row in rows:
        key = (
            str(row["model_id"]),
            str(row["baseline_id"]),
            str(row["cost_scenario"]),
            str(row["exit_time"]),
        )
        values = result.setdefault(key, {"gross": 1.0, "net": 1.0})
        values["gross"] *= 1.0 + _finite_number(row["gross_return"], "gross_return")
        values["net"] *= 1.0 + _finite_number(row["net_return"], "net_return")
    for values in result.values():
        values["gross"] -= 1.0
        values["net"] -= 1.0
    return result


def daily_selection_lifts(
    *,
    model_gross_return: float,
    model_net_return: float,
    baseline_rows: Iterable[Mapping[str, Any]],
) -> dict[str, float]:
    """Calculate comparator-parity increments for one model/date/exit/cost row."""

    model_gross = _finite_number(model_gross_return, "model_gross_return")
    model_net = _finite_number(model_net_return, "model_net_return")
    indexed = {CandidateBaselineId(str(row["baseline_id"])): row for row in baseline_rows}
    if set(indexed) != set(CandidateBaselineId):
        raise ValueError("daily selection lifts require every baseline family exactly once")
    all_gross = _finite_number(indexed[CandidateBaselineId.ALL_CANDIDATE_GROSS_V1]["gross_return"], "all candidate gross")
    matched_gross = _finite_number(indexed[CandidateBaselineId.MATCHED_K_HASH_GROSS_V1]["gross_return"], "matched-K gross")
    matched_net = _finite_number(indexed[CandidateBaselineId.MATCHED_K_HASH_NET_V1]["net_return"], "matched-K net")
    return selection_lifts(
        model_gross_return=model_gross,
        model_net_return=model_net,
        all_candidate_gross_return=all_gross,
        matched_k_gross_return=matched_gross,
        matched_k_net_return=matched_net,
    )


def selection_lifts(
    *,
    model_gross_return: float,
    model_net_return: float,
    all_candidate_gross_return: float,
    matched_k_gross_return: float,
    matched_k_net_return: float,
) -> dict[str, float]:
    """Apply the same comparator definitions to daily or compounded returns."""

    model_gross = _finite_number(model_gross_return, "model_gross_return")
    model_net = _finite_number(model_net_return, "model_net_return")
    all_gross = _finite_number(all_candidate_gross_return, "all_candidate_gross_return")
    matched_gross = _finite_number(matched_k_gross_return, "matched_k_gross_return")
    matched_net = _finite_number(matched_k_net_return, "matched_k_net_return")
    return {
        "gross_selection_lift_vs_all_candidate": model_gross - all_gross,
        "gross_selection_lift_vs_matched_k": model_gross - matched_gross,
        "net_selection_lift_vs_matched_k": model_net - matched_net,
        "cost_drag_model": model_net - model_gross,
        "cost_drag_matched_k": matched_net - matched_gross,
        "cost_drag_difference": (model_net - model_gross) - (matched_net - matched_gross),
    }


def _portfolio_returns(
    *,
    rows: tuple[dict[str, Any], ...],
    selected_symbols: tuple[str, ...],
    declared_slots: int,
    costs: ExploratoryExecutionCostConfig,
) -> tuple[float, float, float, float]:
    if declared_slots <= 0:
        raise ValueError("declared baseline slots must be positive")
    index = {str(row["symbol"]): row for row in rows}
    weight = 1.0 / declared_slots
    gross = 0.0
    net = 0.0
    observed = 0
    for symbol in selected_symbols:
        target = index[symbol]
        if target.get("status") != "AVAILABLE":
            continue
        economics = reference_trade_economics(
            reference_price=_finite_number(target.get("reference_price"), "reference_price"),
            exit_price=_finite_number(target.get("exit_price"), "exit_price"),
            weight=weight,
            cost_config=costs,
        )
        gross += weight * economics.gross_return
        net += weight * economics.net_return
        observed += 1
    observed_weight = observed * weight
    missing_weight = 1.0 - observed_weight
    _require_weight_reconciliation(observed_weight, missing_weight, 0.0)
    return gross, net, observed_weight, missing_weight


def _baseline_row(
    common: dict[str, Any],
    baseline_id: CandidateBaselineId,
    selected_count: int,
    gross_return: float,
    net_return: float,
    observed_weight: float,
    missing_weight: float,
    algorithm_id: str,
    selection_id: str,
    symbol_set_hash: str,
) -> dict[str, Any]:
    return {
        **common,
        "baseline_id": baseline_id.value,
        "selected_symbol_count": selected_count,
        "gross_return": gross_return,
        "net_return": net_return,
        "observed_weight": observed_weight,
        "missing_weight": missing_weight,
        "selection_algorithm_id": algorithm_id,
        "baseline_selection_id": selection_id,
        "selection_id": selection_id,
        "selected_symbols_hash": symbol_set_hash,
    }


def _cash_locked_rows(
    *,
    population: ModelCandidatePopulation,
    selection: MatchedKSelection,
    exit_time: str,
    scenario: str,
    top_k: int,
    costs: ExploratoryExecutionCostConfig,
) -> tuple[dict[str, Any], ...]:
    empty_hash = selected_symbols_hash(())
    lock_selection_id = canonical_identity_hash(
        {
            "status": "CASH_LOCKED",
            "population_hash": population.population_hash,
            "exit_time": exit_time,
            "cost_scenario": scenario,
            "seed": selection.seed,
            "top_k": top_k,
        }
    )
    common = {
        "schema_version": MR1_CANDIDATE_BASELINE_SCHEMA_VERSION,
        "decision_date": population.decision_date.isoformat(),
        "model_id": population.model_id,
        "target_id": population.target_id,
        "exit_time": exit_time,
        "cost_scenario": scenario,
        "baseline_seed": selection.seed,
        "baseline_selection_id": lock_selection_id,
        "selection_id": lock_selection_id,
        "selected_symbols_hash": empty_hash,
        "top_k": top_k,
        "population_definition_id": population.definition_id,
        "candidate_population_size": population.population_size,
        "candidate_symbol_count": population.population_size,
        "candidate_population_hash": population.population_hash,
        "selected_symbol_count": 0,
        "gross_return": 0.0,
        "net_return": 0.0,
        "observed_weight": 0.0,
        "missing_weight": 0.0,
        "cash_locked_weight": 1.0,
        "baseline_slot_status": "CASH_LOCKED",
        "cost_policy_id": _cost_policy_id(costs),
        "cash_lock_policy_id": MR1_CASH_LOCK_POLICY_ID,
        "missing_weight_policy_id": MR1_MISSING_WEIGHT_POLICY_ID,
        "data_eligibility": "EXPLORATORY",
    }
    return tuple(
        {
            **common,
            "baseline_id": baseline_id.value,
            "selection_algorithm_id": (
                MR1_MATCHED_K_ALGORITHM_ID
                if baseline_id in {
                    CandidateBaselineId.MATCHED_K_HASH_GROSS_V1,
                    CandidateBaselineId.MATCHED_K_HASH_NET_V1,
                }
                else "all-candidate-equal-weight-v1"
            ),
        }
        for baseline_id in CandidateBaselineId
    )


def _selection_evidence_rows(
    *,
    selection: MatchedKSelection,
    endpoint_target_id: str,
    exit_time: str,
    scenario: str,
    target_index: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    population = selection.population
    output: list[dict[str, Any]] = []
    for slot_index, symbol in enumerate(selection.symbols, start=1):
        target = target_index[
            (population.decision_date.isoformat(), endpoint_target_id, symbol)
        ]
        output.append(
            {
                "schema_version": MR1_MATCHED_K_SELECTION_SCHEMA_VERSION,
                "decision_date": population.decision_date.isoformat(),
                "model_id": population.model_id,
                "target_id": population.target_id,
                "exit_time": exit_time,
                "cost_scenario": scenario,
                "baseline_id": "MATCHED_K_HASH_GROSS_NET_V1",
                "baseline_seed": selection.seed,
                "population_definition_id": population.definition_id,
                "population_size": population.population_size,
                "population_hash": population.population_hash,
                "slot_index": slot_index,
                "symbol": symbol,
                "symbol_hash": canonical_identity_hash({"symbol": symbol}),
                "selection_algorithm_id": selection.algorithm_id,
                "selection_id": selection.selection_id,
                "selected_symbols_hash": selection.selected_symbols_hash,
                "selection_status": "EXECUTED",
                "eligible_for_ranking": True,
                "target_observation_status": str(target["status"]),
                "slot_weight": 1.0 / selection.top_k,
                "data_eligibility": "EXPLORATORY",
            }
        )
    return tuple(output)


def _validate_target_rows(rows: tuple[dict[str, Any], ...]) -> None:
    if not rows:
        raise ValueError("target_rows must not be empty")
    _require_unique_keys(rows, ("decision_date", "target_id", "symbol"), "MR-1 target")
    for row in rows:
        if row.get("status") not in {"AVAILABLE", "UNAVAILABLE"}:
            raise ValueError("MR-1 target status is invalid")


def _require_unique_keys(rows: Iterable[Mapping[str, Any]], fields: tuple[str, ...], label: str) -> None:
    keys = [tuple(row.get(field) for field in fields) for row in rows]
    if any(any(value is None for value in key) for key in keys):
        raise ValueError(f"{label} primary key fields must be present")
    if len(keys) != len(set(keys)):
        raise ValueError(f"{label} primary keys must be unique")


def _require_weight_reconciliation(observed: float, missing: float, locked: float) -> None:
    if any(not math.isfinite(value) or value < 0.0 for value in (observed, missing, locked)):
        raise ValueError("baseline weights must be finite and non-negative")
    if abs(observed + missing + locked - 1.0) > 1e-12:
        raise ValueError("baseline weights must reconcile to one")


def _cost_policy_id(costs: ExploratoryExecutionCostConfig) -> str:
    payload = json.dumps(asdict(costs), sort_keys=True, separators=(",", ":"))
    return f"{costs.schema_version}:sha256:{sha256(payload.encode()).hexdigest()}"


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite numeric")
    return result
