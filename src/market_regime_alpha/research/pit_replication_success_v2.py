"""Pure success pipeline for sealed PIT Candidate replication v2 evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
import math
from statistics import median
from typing import Any, Iterable, Mapping

from market_regime_alpha.research.mr1_candidate_baselines import (
    reference_trade_economics,
    select_matched_k_symbols,
)
from market_regime_alpha.research.mr1_research_runner import mr1_cost_scenarios
from market_regime_alpha.research.pit_partition_v2 import (
    PartitionOpenReceipt,
    PartitionSealArtifact,
    ValidationPartitionSpecification,
)
from market_regime_alpha.research.pit_replication_success_v2_features import (
    frozen_b1e_feature_registry,
    reconstruct_b1e_scores,
)
from market_regime_alpha.research.pit_replication_success_v2_protocol import (
    PITCandidateReplicationProtocolV2,
)
from market_regime_alpha.research.pit_replication_success_v2_statistics import (
    PITReplicationAssessment,
    assess_daily_replication,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    canonical_identity_hash,
    selected_symbols_hash,
)


Row = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PITReplicationSuccessInputs:
    provider_artifact_id: str
    provider_source_hashes: tuple[str, ...]
    provider_source_content_hash: str
    pit_qualification: Mapping[str, Any]
    partition_specification: ValidationPartitionSpecification
    partition_seal: PartitionSealArtifact
    partition_open_receipt: PartitionOpenReceipt
    amount_unit_contract: Mapping[str, Any]
    universe_rows: tuple[Row, ...]
    eligibility_rows: tuple[Row, ...]
    orderability_rows: tuple[Row, ...]
    population_rows: tuple[Row, ...]
    feature_rows: tuple[Row, ...]
    evaluation_mark_rows: tuple[Row, ...]
    path_rows: tuple[Row, ...]
    test_only: bool


@dataclass(frozen=True, slots=True)
class PITReplicationSuccessResults:
    inputs: PITReplicationSuccessInputs
    protocol: PITCandidateReplicationProtocolV2
    model_score_rows: tuple[dict[str, Any], ...]
    ranking_rows: tuple[dict[str, Any], ...]
    selection_rows: tuple[dict[str, Any], ...]
    matched_k_return_rows: tuple[dict[str, Any], ...]
    daily_metric_rows: tuple[dict[str, Any], ...]
    path_diagnostic_rows: tuple[dict[str, Any], ...]
    path_status: str
    assessment: PITReplicationAssessment


def build_pit_replication_success_results(
    inputs: PITReplicationSuccessInputs,
    *,
    protocol: PITCandidateReplicationProtocolV2,
) -> PITReplicationSuccessResults:
    if inputs.test_only != (protocol.authority_ceiling == "TEST_ONLY_NOT_RESEARCH_EVIDENCE"):
        raise ValueError("test-only input and Protocol authority mismatch")
    if inputs.partition_seal.protocol_id != protocol.protocol_id:
        raise ValueError("partition seal does not bind the Protocol")
    if inputs.partition_seal.partition_content_hash != inputs.partition_open_receipt.partition_hash:
        raise ValueError("partition open receipt does not bind the seal")
    population_keys = _validate_population_lineage(inputs)
    _validate_feature_lineage(inputs, population_keys)
    scores, rankings = reconstruct_b1e_scores(inputs.feature_rows, protocol=protocol)
    eligible_ranking_keys = {
        (str(row["decision_date"]), str(row["symbol"]))
        for row in rankings
        if row["eligible_for_ranking"] is True
    }
    if not eligible_ranking_keys or not eligible_ranking_keys <= population_keys:
        raise ValueError("B1-E model population must be a non-empty Candidate population subset")
    model_population_rows = tuple(
        row
        for row in inputs.population_rows
        if (str(row["decision_date"]), str(row["symbol"])) in eligible_ranking_keys
    )
    model_sizes: dict[str, int] = defaultdict(int)
    for decision_date, _ in eligible_ranking_keys:
        model_sizes[decision_date] += 1
    if any(value < protocol.top_k for value in model_sizes.values()):
        raise ValueError("B1-E model population is smaller than frozen Top-K")
    evaluation = _evaluation_index(inputs.evaluation_mark_rows, protocol=protocol)
    if set(evaluation) != population_keys:
        raise ValueError("10:30 evaluation evidence must cover the Candidate population exactly")
    selections, matched_returns, daily = _build_comparators(
        population_rows=model_population_rows,
        ranking_rows=rankings,
        evaluation=evaluation,
        protocol=protocol,
        provider_artifact_id=inputs.provider_artifact_id,
    )
    path_status = "AVAILABLE" if inputs.path_rows else "PATH_DIAGNOSTICS_UNAVAILABLE"
    path_rows = tuple(dict(row) for row in inputs.path_rows) if inputs.path_rows else ()
    assessment = assess_daily_replication(daily, protocol=protocol)
    return PITReplicationSuccessResults(
        inputs,
        protocol,
        scores,
        rankings,
        selections,
        matched_returns,
        daily,
        path_rows,
        path_status,
        assessment,
    )


def _validate_population_lineage(
    inputs: PITReplicationSuccessInputs,
) -> set[tuple[str, str]]:
    universe = _unique_index(inputs.universe_rows, "Universe")
    eligibility = _unique_index(inputs.eligibility_rows, "Eligibility")
    orderability = _unique_index(inputs.orderability_rows, "Orderability")
    population = _unique_index(inputs.population_rows, "Candidate population")
    if set(universe) != set(eligibility) or set(universe) != set(orderability):
        raise ValueError("Universe, Eligibility, and Orderability evidence scopes differ")
    expected_population = {
        key
        for key in universe
        if universe[key].get("is_member") is True
        and eligibility[key].get("status") == "ELIGIBLE"
        and orderability[key].get("orderability_status") == "RESEARCH_ORDERABLE"
    }
    if set(population) != expected_population:
        raise ValueError(
            "Candidate population is not reconstructible from ELIGIBLE and "
            "RESEARCH_ORDERABLE evidence"
        )
    sealed_dates = {value.isoformat() for value in inputs.partition_seal.included_sessions}
    if {decision_date for decision_date, _ in population} != sealed_dates:
        raise ValueError("Candidate population does not cover the sealed Decision Dates")
    for row in inputs.population_rows:
        key = (str(row["decision_date"]), str(row["symbol"]))
        if universe.get(key, {}).get("is_member") is not True:
            raise ValueError("Candidate population lacks PIT Universe membership")
        if eligibility.get(key, {}).get("status") != "ELIGIBLE":
            raise ValueError("Candidate population lacks ELIGIBLE evidence")
        if orderability.get(key, {}).get("orderability_status") != "RESEARCH_ORDERABLE":
            raise ValueError("Candidate population lacks RESEARCH_ORDERABLE evidence")
        expected_lineage = {
            "universe_row_id": universe[key].get("row_id"),
            "eligibility_row_id": eligibility[key].get("row_id"),
            "orderability_evidence_id": orderability[key].get("evidence_id"),
        }
        if any(row.get(field) != value for field, value in expected_lineage.items()):
            raise ValueError("Candidate population lineage identity mismatch")
        if row.get("dataset_id") != inputs.provider_artifact_id:
            raise ValueError("Candidate population provider lineage mismatch")
        decision_times = {
            row.get("decision_time"),
            universe[key].get("decision_time"),
            eligibility[key].get("decision_time"),
            orderability[key].get("decision_time"),
        }
        if None in decision_times or len(decision_times) != 1:
            raise ValueError("Candidate population Decision-Time lineage mismatch")
        for field in ("universe_row_id", "eligibility_row_id", "orderability_evidence_id", "decision_time"):
            if not row.get(field):
                raise ValueError(f"Candidate population lineage field is missing: {field}")
    return set(population)


def _validate_feature_lineage(
    inputs: PITReplicationSuccessInputs,
    population_keys: set[tuple[str, str]],
) -> None:
    required_features = {value.feature_id for value in frozen_b1e_feature_registry()}
    expected = {
        (decision_date, symbol, feature_id)
        for decision_date, symbol in population_keys
        for feature_id in required_features
    }
    actual: set[tuple[str, str, str]] = set()
    decision_time_by_key = {
        (str(row["decision_date"]), str(row["symbol"])): str(row["decision_time"])
        for row in inputs.population_rows
    }
    for row in inputs.feature_rows:
        key = (
            str(row.get("decision_date")),
            str(row.get("symbol")),
            str(row.get("feature_id")),
        )
        if key in actual:
            raise ValueError("duplicate Candidate Feature evidence")
        actual.add(key)
        if row.get("decision_time") != decision_time_by_key.get(key[:2]):
            raise ValueError("Feature evidence Decision-Time lineage mismatch")
    if actual != expected:
        raise ValueError("Feature evidence does not exactly cover the Candidate population")


def _evaluation_index(
    rows: Iterable[Row], *, protocol: PITCandidateReplicationProtocolV2
) -> dict[tuple[str, str], dict[str, Any]]:
    output: dict[tuple[str, str], dict[str, Any]] = {}
    for source in rows:
        row = dict(source)
        key = (str(row.get("decision_date")), str(row.get("symbol")))
        if key in output:
            raise ValueError("duplicate evaluation mark")
        if row.get("evaluation_mark_id") != protocol.primary_evaluation_mark_id:
            raise ValueError("ranking Target cannot substitute for the 10:30 evaluation mark")
        if row.get("evaluation_time") != protocol.primary_evaluation_time:
            raise ValueError("evaluation endpoint must be exact 10:30")
        reference_price = row.get("reference_price")
        if not _positive_finite(reference_price):
            raise ValueError("10:30 evaluation evidence requires a positive reference price")
        status = row.get("mark_status")
        if status not in {"AVAILABLE", "UNAVAILABLE"}:
            raise ValueError("10:30 evaluation mark status is invalid")
        if status == "AVAILABLE" and not _positive_finite(row.get("evaluation_price")):
            raise ValueError("available 10:30 mark requires a positive price")
        if status == "UNAVAILABLE" and row.get("evaluation_price") is not None:
            raise ValueError("unavailable 10:30 evidence cannot contain a price")
        if status != "AVAILABLE" and row.get("fallback_close_price") is not None:
            raise ValueError("daily close cannot substitute for missing 10:30 evidence")
        output[key] = row
    return output


def _build_comparators(
    *,
    population_rows: tuple[Row, ...],
    ranking_rows: tuple[dict[str, Any], ...],
    evaluation: Mapping[tuple[str, str], Mapping[str, Any]],
    protocol: PITCandidateReplicationProtocolV2,
    provider_artifact_id: str,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    populations: dict[str, tuple[str, ...]] = {}
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in population_rows:
        grouped[str(row["decision_date"])].append(str(row["symbol"]))
    for decision_date, symbols in grouped.items():
        populations[decision_date] = tuple(sorted(symbols))
    ranks: dict[str, tuple[str, ...]] = {}
    for decision_date in populations:
        candidates = [
            row for row in ranking_rows
            if row["decision_date"] == decision_date and row["eligible_for_ranking"] is True
        ]
        ranks[decision_date] = tuple(
            str(row["symbol"]) for row in sorted(candidates, key=lambda row: int(row["rank"]))
        )
    selections: list[dict[str, Any]] = []
    returns: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    costs = mr1_cost_scenarios()
    for decision_date in sorted(populations):
        population_symbols = populations[decision_date]
        population_hash = canonical_identity_hash(
            {"provider_artifact_id": provider_artifact_id, "decision_date": decision_date, "symbols": list(population_symbols)}
        )
        seed_net: dict[str, dict[int, float]] = {
            scenario: {} for scenario in protocol.cost_robustness_scenarios
        }
        for seed in protocol.matched_k_seed_set:
            selected = select_matched_k_symbols(
                dataset_id=provider_artifact_id,
                decision_date=date.fromisoformat(decision_date),
                symbols=population_symbols,
                top_k=protocol.top_k,
                baseline_seed=seed,
            )
            selection_hash = selected_symbols_hash(selected)
            selection_id = canonical_identity_hash(
                {"population_hash": population_hash, "seed": seed, "symbols": list(selected)}
            )
            for slot, symbol in enumerate(selected, start=1):
                selections.append(
                    {
                        "decision_date": decision_date,
                        "model_id": protocol.ranking_model_id,
                        "seed": seed,
                        "slot_index": slot,
                        "symbol": symbol,
                        "population_hash": population_hash,
                        "selection_id": selection_id,
                        "selected_symbols_hash": selection_hash,
                    }
                )
            for scenario in protocol.cost_robustness_scenarios:
                gross, net, observed = _portfolio_return(
                    decision_date,
                    selected,
                    evaluation,
                    top_k=protocol.top_k,
                    cost_config=costs[scenario],
                )
                seed_net[scenario][seed] = net
                returns.append(
                    {
                        "decision_date": decision_date,
                        "model_id": protocol.ranking_model_id,
                        "cost_scenario": scenario,
                        "seed": seed,
                        "selection_id": selection_id,
                        "population_hash": population_hash,
                        "gross_return": gross,
                        "net_return": net,
                        "observed_weight": observed,
                        "missing_weight": 1.0 - observed,
                    }
                )
        model_symbols = ranks[decision_date][: protocol.top_k]
        model_by_cost = {
            scenario: _portfolio_return(
                decision_date,
                model_symbols,
                evaluation,
                top_k=protocol.top_k,
                cost_config=costs[scenario],
            )
            for scenario in protocol.cost_robustness_scenarios
        }
        model_gross, model_net, model_observed = model_by_cost[protocol.cost_scenario]
        all_gross = _gross_population_return(decision_date, population_symbols, evaluation)
        available_population_count = sum(
            evaluation.get((decision_date, symbol), {}).get("mark_status") == "AVAILABLE"
            for symbol in population_symbols
        )
        median_net_by_cost = {
            scenario: median(values.values()) for scenario, values in seed_net.items()
        }
        median_net = median_net_by_cost[protocol.cost_scenario]
        panel_medians = {
            label: median(
                value
                for seed, value in seed_net[protocol.cost_scenario].items()
                if seed % 4 == remainder
            )
            for label, remainder in zip(("A", "B", "C", "D"), range(4), strict=True)
        }
        daily.append(
            {
                "decision_date": decision_date,
                "model_id": protocol.ranking_model_id,
                "population_hash": population_hash,
                "population_size": len(population_symbols),
                "evaluation_symbol_coverage": available_population_count
                / len(population_symbols),
                "model_gross_return": model_gross,
                "model_net_return": model_net,
                "model_observed_weight": model_observed,
                "all_candidate_gross_return": all_gross,
                "multiseed_matched_k_net_median": median_net,
                "gross_lift_vs_all_candidate": model_gross - all_gross,
                "net_lift_vs_multiseed_median": model_net - median_net,
                **{
                    f"seed_panel_{label}_net_lift": model_net - value
                    for label, value in panel_medians.items()
                },
                **{
                    f"cost_scenario_{scenario}_net_lift": (
                        model_by_cost[scenario][1] - median_net_by_cost[scenario]
                    )
                    for scenario in protocol.cost_robustness_scenarios
                },
            }
        )
    return tuple(selections), tuple(returns), tuple(daily)


def _portfolio_return(
    decision_date: str,
    symbols: tuple[str, ...],
    evaluation: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    top_k: int,
    cost_config: Any,
) -> tuple[float, float, float]:
    weight = 1.0 / top_k
    gross = net = observed = 0.0
    for symbol in symbols:
        row = evaluation.get((decision_date, symbol))
        if row is None or row.get("mark_status") != "AVAILABLE":
            continue
        economics = reference_trade_economics(
            reference_price=float(row["reference_price"]),
            exit_price=float(row["evaluation_price"]),
            weight=weight,
            cost_config=cost_config,
        )
        gross += weight * economics.gross_return
        net += weight * economics.net_return
        observed += weight
    return gross, net, observed


def _gross_population_return(
    decision_date: str,
    symbols: tuple[str, ...],
    evaluation: Mapping[tuple[str, str], Mapping[str, Any]],
) -> float:
    weight = 1.0 / len(symbols)
    return sum(
        weight * (float(row["evaluation_price"]) / float(row["reference_price"]) - 1.0)
        for symbol in symbols
        if (row := evaluation.get((decision_date, symbol))) is not None
        and row.get("mark_status") == "AVAILABLE"
    )


def _unique_index(rows: Iterable[Row], label: str) -> dict[tuple[str, str], Row]:
    output: dict[tuple[str, str], Row] = {}
    for row in rows:
        key = (str(row.get("decision_date")), str(row.get("symbol")))
        if key in output:
            raise ValueError(f"duplicate {label} row")
        output[key] = row
    return output


def _positive_finite(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0
    )


def assessment_payload(value: PITReplicationAssessment) -> dict[str, Any]:
    payload = asdict(value)
    payload["seed_panel_effects"] = list(value.seed_panel_effects)
    payload["reasons"] = list(value.reasons)
    payload["cost_robustness_effects"] = [
        [scenario, effect] for scenario, effect in value.cost_robustness_effects
    ]
    return payload
