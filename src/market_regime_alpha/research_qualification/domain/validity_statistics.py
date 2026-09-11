"""Versioned read-only Evaluation statistics over canonical common pairs.

This owner never acquires prices or derives labels. Its caller must reconcile
the frozen Prediction, Outcome and Evaluation roster and temporal eligibility.
Version 1 uses equal observation weights for pooled errors and equal session
weights for cross-session statistics. It never treats instruments as sessions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from market_regime_alpha.research_qualification.domain.evaluation_formula import (
    BacktestFormulaCode,
    BacktestMetricSurface,
    EvaluationFormulaDefinition,
    EvaluationFormulaParameter,
    FormulaObservation,
    FormulaParameterType,
    FormulaSourceState,
    evaluate_backtest_formula,
)


FORMULA_VERSION = 1
DECIMAL_PRECISION = 38
ROUNDING_MODE = "ROUND_HALF_EVEN"
MINIMUM_RANK_PAIRS = 3
_ZERO = Decimal(0)
_ERROR_CODES = {
    "bias": BacktestFormulaCode.PREDICTIVE_BIAS,
    "mae": BacktestFormulaCode.PREDICTIVE_MAE,
    "rmse": BacktestFormulaCode.PREDICTIVE_RMSE,
}


@dataclass(frozen=True, slots=True)
class ValidityPair:
    commitment_id: UUID
    session: date
    model: Decimal
    baseline: Decimal
    label: Decimal
    instrument_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.commitment_id, UUID):
            raise ValueError("validity commitment identity must be a UUID")
        if not isinstance(self.session, date) or isinstance(self.session, datetime):
            raise ValueError("validity session must be an exact session date")
        if self.instrument_id is not None and not isinstance(self.instrument_id, UUID):
            raise ValueError("validity instrument identity must be a UUID")
        if any(not isinstance(value, Decimal) or not value.is_finite()
               for value in (self.model, self.baseline, self.label)):
            raise ValueError("validity pairs require finite canonical Decimal values")


def validity_statistics(
    pairs: tuple[ValidityPair, ...],
    *,
    minimum_sessions: int,
    minimum_observations: int,
    rolling_sessions: int = 20,
    ranking_k: int = 5,
    quantiles: int = 5,
    session_roster: tuple[date, ...] | None = None,
) -> dict[str, Any]:
    """Evaluate all supplied common pairs without selecting sessions by result.

    Insufficient samples retain descriptive statistics and explicit gates.
    Ranking is forecast-only, with commitment UUID ascending as the tie rule;
    diagnostic baskets are hypothetical and do not establish tradability.
    """
    parameters = (minimum_sessions, minimum_observations, rolling_sessions, ranking_k, quantiles)
    if any(type(value) is not int or value < 1 for value in parameters) or quantiles < 2:
        raise ValueError("validity sample/window/K parameters must be positive integers; quantiles >= 2")
    if len({(pair.session, pair.commitment_id) for pair in pairs}) != len(pairs):
        raise ValueError("duplicate session/commitment in common population")
    observed_sessions = {pair.session for pair in pairs}
    if session_roster is not None:
        if any(not isinstance(session, date) or isinstance(session, datetime) for session in session_roster):
            raise ValueError("session roster requires exact session dates")
        if session_roster != tuple(sorted(set(session_roster))):
            raise ValueError("session roster must be ordered and unique")
        if not observed_sessions.issubset(set(session_roster)):
            raise ValueError("pairs contain a session outside the declared session roster")
    sessions = tuple(sorted(observed_sessions)) if session_roster is None else session_roster
    grouped = {session: tuple(sorted((pair for pair in pairs if pair.session == session),
                                    key=lambda pair: str(pair.commitment_id))) for session in sessions}
    for members in grouped.values():
        instruments = tuple(pair.instrument_id for pair in members if pair.instrument_id is not None)
        if len(instruments) != len(set(instruments)):
            raise ValueError("duplicate session/instrument in common population")
    ordered_pairs = tuple(pair for session in sessions for pair in grouped[session])
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        per_session = tuple(_session_report(grouped[session], session, ranking_k, quantiles) for session in sessions)
        cumulative_count = 0
        for row in per_session:
            cumulative_count += row["common_observation_count"]
            row["cumulative_common_observation_count"] = cumulative_count
        reasons = _sample_reasons(len(observed_sessions), len(pairs), minimum_sessions, minimum_observations)
        return {
            "formula_version": FORMULA_VERSION,
            "decimal_precision": DECIMAL_PRECISION,
            "rounding_mode": ROUNDING_MODE,
            "state": reasons[0] if reasons else "DESCRIPTIVE_STATISTICS_AVAILABLE",
            "reason_codes": reasons,
            "session_count": len(observed_sessions),
            "estimable_session_count": len(observed_sessions),
            "expected_session_count": len(sessions),
            "common_observation_count": len(pairs),
            "population_basis": "EXACT_COMMON_CANONICAL_FORECAST_OUTCOME_PAIRS",
            "session_roster": sessions,
            "minimum_sessions": minimum_sessions,
            "minimum_observations": minimum_observations,
            "per_session": per_session,
            "aggregate": _aggregate(ordered_pairs, per_session, minimum_sessions, minimum_observations),
            "rolling": tuple(
                {
                    "through_session": session,
                    "requested_sessions": rolling_sessions,
                    "session_roster": sessions[max(0, index + 1 - rolling_sessions):index + 1],
                    "window_state": "COMPLETE_WINDOW" if index + 1 >= rolling_sessions else "PARTIAL_WINDOW",
                    "aggregate": _aggregate(
                        tuple(pair for day in sessions[max(0, index + 1 - rolling_sessions):index + 1]
                              for pair in grouped[day]),
                        per_session[max(0, index + 1 - rolling_sessions):index + 1], minimum_sessions, minimum_observations,
                    ),
                }
                for index, session in enumerate(sessions)
            ),
            "rank_stability": tuple(_stability(grouped[left], grouped[right], left, right)
                                    for left, right in zip(sessions, sessions[1:])),
            "uncertainty_policy": "DESCRIPTIVE_SESSION_SE_ONLY; NO_CONFIDENCE_INTERVAL; SESSION_INDEPENDENCE_UNPROVEN",
            "ranking_policy": {
                "ranking_k": ranking_k,
                "quantiles": quantiles,
                "sort": "FORECAST_DESCENDING_THEN_COMMITMENT_UUID_ASCENDING",
                "quantile_assignment": "DISJOINT_TOP_AND_BOTTOM_TAILS_EACH_FLOOR_N_DIVIDED_BY_QUANTILES",
                "weighting": "EQUAL_WEIGHT_WITHIN_EACH_BASKET",
                "evidence_class": "HYPOTHETICAL_NONTRADABLE; NOT_ACCOUNT_PNL",
            },
        }


def _sample_reasons(sessions: int, observations: int, minimum_sessions: int, minimum_observations: int) -> tuple[str, ...]:
    return tuple(reason for failed, reason in (
        (sessions < minimum_sessions, "INSUFFICIENT_SESSIONS"),
        (observations < minimum_observations, "INSUFFICIENT_OBSERVATIONS"),
    ) if failed)


def _metric(value: Decimal | None, count: int, code: str, *, reason: str = "ESTIMATED_BY_FROZEN_FORMULA",
            denominator_kind: str = "COMMON_OBSERVATIONS", numerator: int | None = None) -> dict[str, Any]:
    return {
        "state": "ESTIMABLE" if value is not None else "NOT_ESTIMABLE",
        "value": value,
        "observation_count": count,
        "denominator": count,
        "denominator_kind": denominator_kind,
        "numerator": numerator,
        "reason_code": reason,
        "formula_code": code,
        "formula_version": FORMULA_VERSION,
    }


def _formula(code: BacktestFormulaCode, values: tuple[Decimal, ...],
             secondary: tuple[Decimal, ...] | None = None, *, denominator_kind: str = "COMMON_OBSERVATIONS") -> dict[str, Any]:
    minimum = MINIMUM_RANK_PAIRS if code is BacktestFormulaCode.RANK_IC else 1
    parameters = tuple(EvaluationFormulaParameter(
        uuid5(NAMESPACE_URL, f"mra:validity:v1:{code}:{name}:{value}"), ordinal, name,
        FormulaParameterType.INTEGER, integer_value=value,
    ) for ordinal, (name, value) in enumerate(
        (("minimum_observations", minimum),)
        + ((("minimum_pairs_per_group", minimum),) if code is BacktestFormulaCode.RANK_IC else ()), 1))
    definition = EvaluationFormulaDefinition(
        uuid5(NAMESPACE_URL, f"mra:validity:v1:{code}"), code, FORMULA_VERSION,
        DECIMAL_PRECISION, ROUNDING_MODE, parameters, BacktestMetricSurface.SIGNAL_FORECAST,
    )
    result = evaluate_backtest_formula(definition, tuple(FormulaObservation(
        UUID(int=index), index, "exact-common", FormulaSourceState.AVAILABLE, value,
        None if secondary is None else secondary[index - 1],
    ) for index, value in enumerate(values, 1)))
    return _metric(result.decimal_value, len(values), code.value, reason=result.reason_code,
                   denominator_kind=denominator_kind)


def _ratio(numerator: int, denominator: int, code: str, *, kind: str = "COMMON_OBSERVATIONS") -> dict[str, Any]:
    return _metric(None if denominator == 0 else Decimal(numerator) / Decimal(denominator),
                   denominator, code, numerator=numerator, denominator_kind=kind,
                   reason="EMPTY_DENOMINATOR" if denominator == 0 else "ESTIMATED_BY_FROZEN_FORMULA")


def _sign(value: Decimal) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _distribution(values: tuple[Decimal, ...], code: str) -> dict[str, Any]:
    return {
        "observation_count": len(values),
        "positive_count": sum(value > 0 for value in values),
        "negative_count": sum(value < 0 for value in values),
        "flat_count": sum(value == 0 for value in values),
        "positive_proportion": _ratio(sum(value > 0 for value in values), len(values), f"{code}_positive_proportion"),
        "mean": _formula(BacktestFormulaCode.MEAN, values),
        "sample_std": _formula(BacktestFormulaCode.SAMPLE_STDDEV, values),
        "minimum": _metric(min(values) if values else None, len(values), f"{code}_minimum",
                           reason="ESTIMATED_BY_FROZEN_FORMULA" if values else "INSUFFICIENT_OBSERVATIONS"),
        "maximum": _metric(max(values) if values else None, len(values), f"{code}_maximum",
                           reason="ESTIMATED_BY_FROZEN_FORMULA" if values else "INSUFFICIENT_OBSERVATIONS"),
    }


def _pair_metrics(forecasts: tuple[Decimal, ...], labels: tuple[Decimal, ...], *, rank_ic: bool = False) -> dict[str, Any]:
    result = {name: _formula(code, forecasts, labels) for name, code in _ERROR_CODES.items()}
    if rank_ic:
        result["rank_ic"] = _formula(BacktestFormulaCode.RANK_IC, forecasts, labels)
    result["directional_hit_rate"] = _ratio(sum(_sign(forecast) == _sign(label) for forecast, label in zip(forecasts, labels, strict=True)),
                                           len(forecasts), "directional_hit_rate_exact_zero_flat")
    result["predicted_positive_proportion"] = _ratio(sum(value > 0 for value in forecasts), len(forecasts), "predicted_positive_proportion")
    result["actual_positive_proportion"] = _ratio(sum(value > 0 for value in labels), len(labels), "actual_positive_proportion")
    result["forecast_dispersion"] = _formula(BacktestFormulaCode.SAMPLE_STDDEV, forecasts)
    result["actual_dispersion"] = _formula(BacktestFormulaCode.SAMPLE_STDDEV, labels)
    result.update(_calibration(forecasts, labels))
    return result


def _calibration(forecasts: tuple[Decimal, ...], labels: tuple[Decimal, ...]) -> dict[str, Any]:
    slope: Decimal | None = None
    intercept: Decimal | None = None
    reason = "INSUFFICIENT_OBSERVATIONS"
    if len(forecasts) >= 3:
        xmean = sum(forecasts, _ZERO) / Decimal(len(forecasts))
        ymean = sum(labels, _ZERO) / Decimal(len(labels))
        xx = sum(((value - xmean) ** 2 for value in forecasts), _ZERO)
        if xx == 0:
            reason = "ZERO_FORECAST_VARIANCE"
        else:
            slope = sum(((x - xmean) * (y - ymean) for x, y in zip(forecasts, labels, strict=True)), _ZERO) / xx
            intercept = ymean - slope * xmean
            reason = "ESTIMATED_BY_FROZEN_FORMULA"
    return {"calibration_slope": _metric(slope, len(forecasts), "ols_actual_on_forecast_slope", reason=reason),
            "calibration_intercept": _metric(intercept, len(forecasts), "ols_actual_on_forecast_intercept", reason=reason)}


def _comparison(model: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {name: _metric(
        None if metric["value"] is None or baseline[name]["value"] is None else metric["value"] - baseline[name]["value"],
        metric["denominator"], f"model_minus_baseline_{name}", denominator_kind=metric["denominator_kind"],
        reason="COMPARISON_MEMBER_NOT_ESTIMABLE" if metric["value"] is None or baseline[name]["value"] is None else "ESTIMATED_BY_FROZEN_FORMULA",
    ) for name, metric in model.items()}


def _session_report(pairs: tuple[ValidityPair, ...], session: date, ranking_k: int, quantiles: int) -> dict[str, Any]:
    labels = tuple(pair.label for pair in pairs)
    model = _pair_metrics(tuple(pair.model for pair in pairs), labels, rank_ic=True)
    baseline = _pair_metrics(tuple(pair.baseline for pair in pairs), labels, rank_ic=True)
    model_ranking = _ranking(pairs, "model", ranking_k, quantiles)
    baseline_ranking = _ranking(pairs, "baseline", ranking_k, quantiles)
    return {
        "session": session,
        "state": "DESCRIPTIVE_STATISTICS_AVAILABLE" if pairs else "NOT_ESTIMABLE",
        "reason_code": "EXACT_COMMON_PAIRS" if pairs else "SESSION_COMMON_POPULATION_UNAVAILABLE",
        "common_observation_count": len(pairs),
        "commitment_roster": tuple(pair.commitment_id for pair in pairs),
        "model": model, "baseline": baseline, "delta": _comparison(model, baseline),
        "model_forecast_distribution": _distribution(tuple(pair.model for pair in pairs), "model_forecast"),
        "baseline_forecast_distribution": _distribution(tuple(pair.baseline for pair in pairs), "baseline_forecast"),
        "actual_distribution": _distribution(labels, "actual"),
        "ranking": {"model": model_ranking, "baseline": baseline_ranking,
                    "delta": _comparison(model_ranking["metrics"], baseline_ranking["metrics"])},
    }


def _ranking(pairs: tuple[ValidityPair, ...], role: str, k: int, quantiles: int) -> dict[str, Any]:
    ordered = tuple(sorted(pairs, key=lambda pair: (getattr(pair, role).copy_negate(), str(pair.commitment_id))))
    top = ordered[:k] if len(ordered) >= 2 * k else ()
    bottom = ordered[-k:] if len(ordered) >= 2 * k else ()
    # Both K baskets must be disjoint even when every frozen forecast is tied.
    def basket(members: tuple[ValidityPair, ...], code: str) -> dict[str, Any]:
        value = None if not members else sum((pair.label for pair in members), _ZERO) / Decimal(len(members))
        return _metric(value, len(members), code, reason="INSUFFICIENT_OBSERVATIONS" if not members else "ESTIMATED_BY_FROZEN_FORMULA")
    top_metric = basket(top, "forecast_top_k_equal_weight_label_mean")
    bottom_metric = basket(bottom, "forecast_bottom_k_equal_weight_label_mean")
    quantile_tail_size = len(ordered) // quantiles
    quantile_rosters = ((ordered[:quantile_tail_size], ordered[-quantile_tail_size:])
                        if quantile_tail_size else ())
    quantile_metrics = tuple(basket(members, "forecast_quantile_equal_weight_label_mean") for members in quantile_rosters)
    spread = None if len(ordered) < 2 * k else top_metric["value"] - bottom_metric["value"]
    qspread = None if not quantile_metrics else quantile_metrics[0]["value"] - quantile_metrics[-1]["value"]
    return {
        "metrics": {
            "top_k_realized_return": top_metric,
            "bottom_k_realized_return": bottom_metric,
            "top_bottom_spread": _metric(spread, 2 * k if spread is not None else len(ordered), "forecast_disjoint_top_minus_bottom_k",
                                         reason="INSUFFICIENT_DISJOINT_RANKING_MEMBERS" if spread is None else "ESTIMATED_BY_FROZEN_FORMULA"),
            "quantile_spread": _metric(qspread, 2 * quantile_tail_size, "forecast_top_minus_bottom_quantile",
                                       reason="INSUFFICIENT_QUANTILE_MEMBERS" if qspread is None else "ESTIMATED_BY_FROZEN_FORMULA"),
        },
        "top_commitments": tuple(pair.commitment_id for pair in top),
        "bottom_commitments": tuple(pair.commitment_id for pair in bottom),
        "quantile_tail_size": quantile_tail_size,
        "unselected_quantile_middle_count": len(ordered) - 2 * quantile_tail_size,
        "quantiles": tuple({"bucket": 1 if index == 0 else quantiles, "tail": "TOP" if index == 0 else "BOTTOM",
                            "commitments": tuple(pair.commitment_id for pair in members), "metric": metric}
                           for index, (members, metric) in enumerate(zip(quantile_rosters, quantile_metrics, strict=True))),
        "evidence_class": "HYPOTHETICAL_NONTRADABLE; NOT_ACCOUNT_PNL",
    }


def _summary(values: tuple[Decimal, ...], minimum_sessions: int, *, include_icir: bool = False) -> dict[str, Any]:
    mean = _formula(BacktestFormulaCode.MEAN, values, denominator_kind="ESTIMABLE_COMMON_SESSIONS")
    std = _formula(BacktestFormulaCode.SAMPLE_STDDEV, values, denominator_kind="ESTIMABLE_COMMON_SESSIONS")
    ordered = tuple(sorted(values))
    midpoint = len(ordered) // 2
    median = None if not values else ordered[midpoint] if len(values) % 2 else (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)
    def session_metric(value: Decimal | None, code: str) -> dict[str, Any]:
        return _metric(value, len(values), code, denominator_kind="ESTIMABLE_COMMON_SESSIONS",
                       reason="INSUFFICIENT_SESSIONS" if value is None else "ESTIMATED_BY_FROZEN_FORMULA")
    result = {
        "state": "INSUFFICIENT_SESSIONS" if len(values) < minimum_sessions else "DESCRIPTIVE_STATISTICS_AVAILABLE",
        "session_count": len(values),
        "mean": mean,
        "median": session_metric(median, "session_median"),
        "sample_std": std,
        "positive_count": sum(value > 0 for value in values),
        "negative_count": sum(value < 0 for value in values),
        "zero_count": sum(value == 0 for value in values),
        "positive_session_ratio": _ratio(sum(value > 0 for value in values), len(values), "positive_session_ratio", kind="ESTIMABLE_COMMON_SESSIONS"),
        "minimum": session_metric(min(values) if values else None, "session_minimum"),
        "maximum": session_metric(max(values) if values else None, "session_maximum"),
        "descriptive_standard_error": session_metric(None if std["value"] is None else std["value"] / Decimal(len(values)).sqrt(), "session_sample_std_div_sqrt_n"),
        "uncertainty_class": "DESCRIPTIVE_SE_NOT_CONFIDENCE_INTERVAL; SESSION_INDEPENDENCE_UNPROVEN",
    }
    if include_icir:
        result["icir"] = _formula(BacktestFormulaCode.ICIR, values, denominator_kind="ESTIMABLE_COMMON_SESSIONS")
    return result


def _paired_session_summary(rows: tuple[dict[str, Any], ...], metric: str, minimum_sessions: int,
                            *, include_icir: bool = False) -> dict[str, Any]:
    common = tuple(row for row in rows if row["model"][metric]["value"] is not None and row["baseline"][metric]["value"] is not None)
    model_values = tuple(row["model"][metric]["value"] for row in common)
    baseline_values = tuple(row["baseline"][metric]["value"] for row in common)
    return {
        "model_estimable_session_count": sum(row["model"][metric]["value"] is not None for row in rows),
        "baseline_estimable_session_count": sum(row["baseline"][metric]["value"] is not None for row in rows),
        "common_estimable_session_count": len(common),
        "common_session_roster": tuple(row["session"] for row in common),
        "common_observation_count": sum(row["common_observation_count"] for row in common),
        "excluded_sessions": tuple({"session": row["session"], "model_reason": row["model"][metric]["reason_code"],
                                    "baseline_reason": row["baseline"][metric]["reason_code"]} for row in rows if row not in common),
        "model": _summary(model_values, minimum_sessions, include_icir=include_icir),
        "baseline": _summary(baseline_values, minimum_sessions, include_icir=include_icir),
        "paired_delta": _summary(tuple(model - baseline for model, baseline in zip(model_values, baseline_values, strict=True)), minimum_sessions),
    }


def _aggregate(pairs: tuple[ValidityPair, ...], rows: tuple[dict[str, Any], ...], minimum_sessions: int,
               minimum_observations: int) -> dict[str, Any]:
    labels = tuple(pair.label for pair in pairs)
    model = _pair_metrics(tuple(pair.model for pair in pairs), labels)
    baseline = _pair_metrics(tuple(pair.baseline for pair in pairs), labels)
    estimable_sessions = sum(row["common_observation_count"] > 0 for row in rows)
    reasons = _sample_reasons(estimable_sessions, len(pairs), minimum_sessions, minimum_observations)
    return {
        "state": reasons[0] if reasons else "DESCRIPTIVE_STATISTICS_AVAILABLE",
        "reason_codes": reasons,
        "session_count": estimable_sessions,
        "estimable_session_count": estimable_sessions,
        "expected_session_count": len(rows), "common_observation_count": len(pairs),
        "pooled": {"model": model, "baseline": baseline, "delta": _comparison(model, baseline)},
        "daily_rank_ic": _paired_session_summary(rows, "rank_ic", minimum_sessions, include_icir=True),
        "daily_error_metrics": {metric: _paired_session_summary(rows, metric, minimum_sessions) for metric in _ERROR_CODES},
        "daily_ranking_diagnostics": {
            metric: _paired_session_summary(tuple({"session": row["session"],
                                                   "common_observation_count": row["common_observation_count"],
                                                   "model": row["ranking"]["model"]["metrics"],
                                                   "baseline": row["ranking"]["baseline"]["metrics"]} for row in rows),
                                            metric, minimum_sessions)
            for metric in ("top_k_realized_return", "bottom_k_realized_return", "top_bottom_spread", "quantile_spread")
        },
        "actual_distribution": _distribution(labels, "actual"),
        "model_forecast_distribution": _distribution(tuple(pair.model for pair in pairs), "model_forecast"),
        "baseline_forecast_distribution": _distribution(tuple(pair.baseline for pair in pairs), "baseline_forecast"),
    }


def _stability(previous: tuple[ValidityPair, ...], current: tuple[ValidityPair, ...], left: date, right: date) -> dict[str, Any]:
    missing_identity = any(pair.instrument_id is None for pair in previous + current)
    unavailable_reason = ("SESSION_COMMON_POPULATION_UNAVAILABLE" if not previous or not current
                          else "INSTRUMENT_IDENTITY_UNAVAILABLE" if missing_identity else None)
    previous_by_id = {pair.instrument_id: pair for pair in previous}
    current_by_id = {pair.instrument_id: pair for pair in current}
    overlap = tuple(sorted((set(previous_by_id) & set(current_by_id)) - {None}, key=str))
    metrics: dict[str, Any] = {}
    for role in ("model", "baseline"):
        metrics[role] = _metric(None, len(overlap), "adjacent_observed_session_forecast_rank_ic",
                                reason=unavailable_reason) if unavailable_reason else _formula(
            BacktestFormulaCode.RANK_IC,
            tuple(getattr(previous_by_id[identifier], role) for identifier in overlap),
            tuple(getattr(current_by_id[identifier], role) for identifier in overlap),
        )
    return {
        "previous_session": left, "session": right,
        "adjacency_basis": "ADJACENT_SUPPLIED_SESSION_ROSTER; CALENDAR_CONTIGUITY_NOT_INFERRED",
        "common_instrument_count": len(overlap), "common_instrument_roster": overlap,
        "previous_common_population_count": len(previous),
        "current_common_population_count": len(current),
        "instrument_union_count": len((set(previous_by_id) | set(current_by_id)) - {None}),
        "population_identity_complete": not missing_identity,
        "model": metrics["model"], "baseline": metrics["baseline"],
        "delta": _comparison({"rank_ic": metrics["model"]}, {"rank_ic": metrics["baseline"]})["rank_ic"],
        "common_population_jaccard": _metric(None, 0, "adjacent_common_population_jaccard", reason=unavailable_reason,
                                               denominator_kind="COMMON_POPULATION_INSTRUMENT_UNION")
        if unavailable_reason else _ratio(len(overlap), len(set(previous_by_id) | set(current_by_id)), "adjacent_common_population_jaccard", kind="COMMON_POPULATION_INSTRUMENT_UNION"),
    }


__all__ = ["DECIMAL_PRECISION", "FORMULA_VERSION", "MINIMUM_RANK_PAIRS", "ROUNDING_MODE", "ValidityPair", "validity_statistics"]
