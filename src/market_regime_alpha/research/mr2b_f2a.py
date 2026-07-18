"""Application-neutral MR-2B F2A Context, null, and daily-excess materialization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math
from numbers import Real
from statistics import mean
from typing import Any

from market_regime_alpha.research.mr1_candidate_baselines import (
    build_model_candidate_populations,
)
from market_regime_alpha.research.mr1_research_runner import mr1_cost_scenarios
from market_regime_alpha.research.mr2b_context import (
    MR2B_CONTEXT_DEFINITION_ID,
    AuxiliaryWatchlistContext,
    AuxiliaryWatchlistContextSymbolEvidence,
    ContextDataStatus,
    build_auxiliary_watchlist_context_evidence,
)
from market_regime_alpha.research.mr2b_excess import (
    MR2B_PRIMARY_COST_SCENARIO,
    MR2B_PRIMARY_EXIT_TIME,
    MR2B_PRIMARY_MODEL_ID,
    WatchlistDirection,
)
from market_regime_alpha.research.mr2b_multiseed import (
    MR2B_F2A_SEEDS,
    MultiSeedReferenceEvidence,
    build_multiseed_matched_k_reference,
)
from market_regime_alpha.research.prr_artifact_reader import (
    VerifiedMR1Run,
    VerifiedPRRDataset,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    CandidateBaselineId,
    MR1_BASELINE_PRIMARY_SEED,
    ModelCandidatePopulation,
)


MR2B_F2A_SCHEMA_VERSION = "mr-2b-f2a-conditionality-inputs-v2"
MR2B_DAILY_EXCESS_SCHEMA_VERSION = "mr-2b-daily-candidate-excess-v1"
MR2B_PRIMARY_INPUT_SCHEMA_VERSION = "mr-2b-primary-comparison-input-v1"
MR2B_PRIMARY_PROJECTION_RULE_ID = "mr2b-primary-projection-from-daily-excess-v1"
MR2B_COVERAGE_SCHEMA_VERSION = "mr-2b-f2a-coverage-v2"
F2A_PRIMARY_HYPOTHESIS_ID = "mr2b-primary-b1e-1030-base-watchlist-direction-v1"
F2A_PRIMARY_METRIC_ID = "daily-net-lift-vs-multiseed-matched-k-median-v1"


@dataclass(frozen=True, slots=True)
class F2AInputs:
    contexts: tuple[AuxiliaryWatchlistContext, ...]
    context_symbol_evidence: tuple[AuxiliaryWatchlistContextSymbolEvidence, ...]
    populations: tuple[ModelCandidatePopulation, ...]
    multiseed: MultiSeedReferenceEvidence
    daily_excess_rows: tuple[dict[str, Any], ...]


def build_f2a_inputs(
    *,
    dataset: VerifiedPRRDataset,
    mr1: VerifiedMR1Run,
    seeds: Iterable[int] = MR2B_F2A_SEEDS,
) -> F2AInputs:
    """Build all F2A semantic tables from already verified immutable inputs."""

    if dataset.dataset_id != mr1.dataset_id:
        raise ValueError("Dataset and MR-1 identities do not match")
    populations = build_model_candidate_populations(
        dataset_id=dataset.dataset_id,
        ranking_rows=dataset.ranking_rows,
    )
    context_evidence = build_auxiliary_watchlist_context_evidence(
        dataset_id=dataset.dataset_id,
        accepted_symbols=dataset.prepared.accepted_symbols,
        session_dates=dataset.prepared.common_session_dates,
        bars=dataset.bars,
        decision_dates=dataset.decision_dates,
    )
    top_k = _integer(mr1.manifest.get("top_k"), "MR-1 top_k")
    multiseed = build_multiseed_matched_k_reference(
        dataset_id=dataset.dataset_id,
        mr1_run_id=mr1.run_id,
        populations=populations,
        target_rows=mr1.morning_targets,
        decision_dates=dataset.decision_dates,
        cost_configs=mr1_cost_scenarios(),
        top_k=top_k,
        seeds=seeds,
        primary_seed=MR1_BASELINE_PRIMARY_SEED,
        verified_primary_baseline_rows=mr1.candidate_daily_baselines,
        verified_primary_selection_rows=mr1.matched_k_selections,
        model_equity_rows=mr1.daily_equity,
    )
    daily = build_daily_candidate_excess(
        dataset_id=dataset.dataset_id,
        mr1_run_id=mr1.run_id,
        contexts=context_evidence.contexts,
        populations=populations,
        baseline_rows=mr1.candidate_daily_baselines,
        null_summary_rows=multiseed.null_summary_rows,
        model_equity_rows=mr1.daily_equity,
        seed_set_id=multiseed.seed_set_id,
        primary_seed=MR1_BASELINE_PRIMARY_SEED,
    )
    return F2AInputs(
        contexts=context_evidence.contexts,
        context_symbol_evidence=context_evidence.symbol_evidence,
        populations=populations,
        multiseed=multiseed,
        daily_excess_rows=daily,
    )


def build_daily_candidate_excess(
    *,
    dataset_id: str,
    mr1_run_id: str,
    contexts: Iterable[AuxiliaryWatchlistContext],
    populations: Iterable[ModelCandidatePopulation],
    baseline_rows: Iterable[Mapping[str, Any]],
    null_summary_rows: Iterable[Mapping[str, Any]],
    model_equity_rows: Iterable[Mapping[str, Any]],
    seed_set_id: str,
    primary_seed: int,
) -> tuple[dict[str, Any], ...]:
    """Join verified daily evidence without compounding daily excess values."""

    if not dataset_id or not mr1_run_id or not seed_set_id:
        raise ValueError("daily excess identities must be non-empty")
    context_rows = tuple(contexts)
    context_index = {item.decision_date.isoformat(): item for item in context_rows}
    if len(context_index) != len(context_rows):
        raise ValueError("Context Decision Dates must be unique")
    population_index = {
        (item.decision_date.isoformat(), item.model_id): item for item in populations
    }
    baseline_index: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = {}
    for source in baseline_rows:
        row = dict(source)
        key = _row_key(row, "decision_date")
        family_builder = baseline_index.setdefault(key, {})
        baseline_id = str(row.get("baseline_id"))
        if baseline_id in family_builder:
            raise ValueError("daily baseline family keys must be unique")
        family_builder[baseline_id] = row
    equity_index: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for source in model_equity_rows:
        row = dict(source)
        key = _row_key(row, "session_date")
        if key in equity_index:
            raise ValueError("model daily equity keys must be unique")
        equity_index[key] = row

    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for source in null_summary_rows:
        summary = dict(source)
        key = _row_key(summary, "decision_date")
        if key in seen:
            raise ValueError("daily null summary keys must be unique")
        seen.add(key)
        decision_day, model_id, exit_time, scenario = key
        population = population_index.get((decision_day, model_id))
        if population is None:
            raise ValueError("daily excess population identity is missing")
        if str(summary.get("population_hash")) != population.population_hash:
            raise ValueError("daily excess population identity mismatch")
        context = context_index.get(decision_day)
        if context is None or context.dataset_id != dataset_id:
            raise ValueError("daily excess Context identity mismatch")
        baseline_family = baseline_index.get(key)
        equity = equity_index.get(key)
        if baseline_family is None or equity is None:
            raise ValueError("daily excess join is incomplete")
        if set(baseline_family) != {item.value for item in CandidateBaselineId}:
            raise ValueError("daily excess requires the complete baseline family")
        if any(
            str(row.get("candidate_population_hash")) != population.population_hash
            for row in baseline_family.values()
        ):
            raise ValueError("daily baseline population identity mismatch")
        if int(summary.get("primary_seed", -1)) != primary_seed:
            raise ValueError("daily null primary seed mismatch")
        primary_selection_id = str(summary.get("primary_seed_selection_id") or "")
        matched_net = baseline_family[CandidateBaselineId.MATCHED_K_HASH_NET_V1.value]
        if primary_selection_id != str(matched_net.get("selection_id")):
            raise ValueError("daily primary-seed selection identity mismatch")
        model_gross = _finite(equity.get("gross_return"), "model gross return")
        model_net = _finite(equity.get("net_return"), "model net return")
        all_gross = _finite(
            baseline_family[CandidateBaselineId.ALL_CANDIDATE_GROSS_V1.value].get("gross_return"),
            "all-Candidate gross return",
        )
        primary_gross = _finite(summary.get("primary_seed_gross_return"), "primary-seed gross return")
        primary_net = _finite(summary.get("primary_seed_net_return"), "primary-seed net return")
        median_gross = _finite(summary.get("gross_median"), "multi-seed gross median")
        median_net = _finite(summary.get("net_median"), "multi-seed net median")
        output.append(
            {
                "schema_version": MR2B_DAILY_EXCESS_SCHEMA_VERSION,
                "dataset_id": dataset_id,
                "mr1_run_id": mr1_run_id,
                "decision_date": decision_day,
                "model_id": model_id,
                "exit_time": exit_time,
                "cost_scenario": scenario,
                "context_id": context.context_id,
                "context_label": context.watchlist_direction.value if context.watchlist_direction else None,
                "context_data_status": context.data_status.value,
                "population_hash": population.population_hash,
                "population_size": population.population_size,
                "primary_seed": primary_seed,
                "primary_seed_selection_id": primary_selection_id,
                "seed_set_id": seed_set_id,
                "model_gross_return": model_gross,
                "model_net_return": model_net,
                "all_candidate_gross_return": all_gross,
                "primary_seed_matched_k_gross_return": primary_gross,
                "primary_seed_matched_k_net_return": primary_net,
                "multiseed_gross_median": median_gross,
                "multiseed_net_median": median_net,
                "multiseed_gross_p10": _finite(summary.get("gross_p10"), "gross p10"),
                "multiseed_gross_p90": _finite(summary.get("gross_p90"), "gross p90"),
                "multiseed_net_p10": _finite(summary.get("net_p10"), "net p10"),
                "multiseed_net_p90": _finite(summary.get("net_p90"), "net p90"),
                "gross_lift_vs_all_candidate": model_gross - all_gross,
                "gross_lift_vs_primary_seed": model_gross - primary_gross,
                "net_lift_vs_primary_seed": model_net - primary_net,
                "gross_lift_vs_multiseed_median": model_gross - median_gross,
                "net_lift_vs_multiseed_median": model_net - median_net,
                "model_gross_percentile": _finite(summary.get("model_gross_percentile"), "gross percentile"),
                "model_net_percentile": _finite(summary.get("model_net_percentile"), "net percentile"),
                "cost_drag_model": model_net - model_gross,
                "cost_drag_primary_seed": primary_net - primary_gross,
                "cost_drag_difference_primary_seed": (model_net - model_gross) - (primary_net - primary_gross),
                "data_status": "AVAILABLE" if context.data_status is ContextDataStatus.AVAILABLE else "CONTEXT_UNAVAILABLE",
                "data_eligibility": "EXPLORATORY",
            }
        )
    if set(output_key(row) for row in output) != set(equity_index):
        raise ValueError("daily excess keys must exactly match model daily equity")
    return tuple(sorted(output, key=output_key))


def build_primary_comparison_input(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Freeze the F2B input projection without evaluating or promoting a hypothesis."""

    primary = tuple(
        dict(row)
        for row in rows
        if row.get("model_id") == MR2B_PRIMARY_MODEL_ID
        and row.get("exit_time") == MR2B_PRIMARY_EXIT_TIME
        and row.get("cost_scenario") == MR2B_PRIMARY_COST_SCENARIO
    )
    labels = {label.value: 0 for label in WatchlistDirection}
    unavailable = 0
    values: dict[str, list[float]] = {label.value: [] for label in WatchlistDirection}
    for row in primary:
        if row.get("context_data_status") != "AVAILABLE" or row.get("context_label") is None:
            unavailable += 1
            continue
        label = str(row["context_label"])
        if label not in labels:
            raise ValueError("primary input Context label is invalid")
        labels[label] += 1
        values[label].append(_finite(row.get("net_lift_vs_multiseed_median"), "primary metric"))
    difference = (
        mean(values["UP"]) - mean(values["DOWN"])
        if values["UP"] and values["DOWN"]
        else None
    )
    return {
        "schema_version": MR2B_PRIMARY_INPUT_SCHEMA_VERSION,
        "primary_hypothesis_id": F2A_PRIMARY_HYPOTHESIS_ID,
        "model_id": MR2B_PRIMARY_MODEL_ID,
        "exit_time": MR2B_PRIMARY_EXIT_TIME,
        "cost_scenario": MR2B_PRIMARY_COST_SCENARIO,
        "context_definition_id": MR2B_CONTEXT_DEFINITION_ID,
        "metric_id": F2A_PRIMARY_METRIC_ID,
        "eligible_context_labels": ["UP", "DOWN"],
        "date_count": len(primary),
        "UP_count": labels["UP"],
        "DOWN_count": labels["DOWN"],
        "FLAT_count": labels["FLAT"],
        "unavailable_count": unavailable,
        "descriptive_mean_difference": difference,
        "authority": "DESCRIPTIVE_INPUT_ONLY",
        "data_eligibility": "EXPLORATORY",
    }


def output_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return _row_key(row, "decision_date")


def _row_key(row: Mapping[str, Any], date_field: str) -> tuple[str, str, str, str]:
    return (
        str(row.get(date_field)),
        str(row.get("model_id")),
        str(row.get("exit_time")),
        str(row.get("cost_scenario")),
    )


def build_f2a_coverage(
    contexts: Iterable[AuxiliaryWatchlistContext],
    daily: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    context_rows = tuple(contexts)
    daily_rows = tuple(daily)
    counts = {status.value: 0 for status in ContextDataStatus}
    reasons: dict[str, int] = {}
    labels = {label.value: 0 for label in WatchlistDirection}
    for context in context_rows:
        counts[context.data_status.value] += 1
        if context.missing_reason is not None:
            reasons[context.missing_reason.value] = reasons.get(context.missing_reason.value, 0) + 1
        if context.watchlist_direction is not None:
            labels[context.watchlist_direction.value] += 1
    return {
        "schema_version": MR2B_COVERAGE_SCHEMA_VERSION,
        "context_date_count": len(context_rows),
        "context_status_counts": counts,
        "context_missing_reason_counts": reasons,
        "context_label_counts": labels,
        "daily_excess_row_count": len(daily_rows),
        "data_eligibility": "EXPLORATORY",
    }


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite numeric")
    return result
