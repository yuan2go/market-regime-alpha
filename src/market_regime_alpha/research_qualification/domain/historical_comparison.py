"""Descriptive Evaluation projections over reconciled historical input pairs."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import random
from typing import Any
from uuid import UUID

from market_regime_alpha.research_qualification.domain.validity_statistics import ValidityPair, validity_statistics
from market_regime_alpha.research_qualification.domain.evaluation_formula import _spearman


@dataclass(frozen=True, slots=True)
class HistoricalEvaluationPoint:
    arm_id: UUID
    fold_id: UUID
    session_id: UUID
    session_date: date
    instrument_id: UUID
    commitment_id: UUID
    evaluation_run_id: UUID
    evaluation_observation_id: UUID
    metric_observation_id: UUID
    outcome_revision_id: UUID
    outcome_metric_id: UUID
    dataset_id: UUID
    model_version_id: UUID | None
    input_state: str
    reason_code: str
    forecast_status: str | None
    label_status: str
    prediction: Decimal | None
    label: Decimal | None
    input_sha256: str
    source_sha256: str | None

    def __post_init__(self) -> None:
        if any(v is not None and (not isinstance(v, Decimal) or not v.is_finite()) for v in (self.prediction, self.label)):
            raise ValueError("historical Evaluation pairs require finite Decimal values")

    @property
    def estimable(self) -> bool:
        return (
            self.input_state == "INCLUDED"
            and self.forecast_status == "AVAILABLE"
            and self.label_status in {"COMPLETE", "PARTIAL"}
            and self.prediction is not None
            and self.label is not None
        )

    @property
    def key(self) -> tuple[date, UUID]:
        return self.session_date, self.instrument_id


def _diagnostics(pairs: tuple[ValidityPair, ...], sessions: tuple[date, ...]) -> dict[str, Any]:
    result = validity_statistics(
        pairs, minimum_sessions=50, minimum_observations=1, rolling_sessions=1, ranking_k=1, quantiles=2, session_roster=sessions
    )
    aggregate = result["aggregate"]
    return {
        "pooled": aggregate["pooled"],
        "daily_rank_ic": aggregate["daily_rank_ic"],
        "daily_error_metrics": aggregate["daily_error_metrics"],
        "prediction_distribution": aggregate["model_forecast_distribution"],
        "label_distribution": aggregate["actual_distribution"],
        "daily": tuple(
            {k: row[k] for k in ("session", "state", "reason_code", "common_observation_count", "model", "baseline", "delta")}
            for row in result["per_session"]
        ),
        "expected_session_count": len(sessions),
        "estimable_session_count": result["estimable_session_count"],
        "observation_count": len(pairs),
        "uncertainty": "DESCRIPTIVE_ONLY; SEE_PREDECLARED_PAIRED_BLOCK_BOOTSTRAP",
    }


def paired_block_uncertainty(points: tuple[tuple[UUID, date, int, Decimal], ...], *, calendar_verified: bool = False) -> dict[str, Any]:
    """Paired MAE delta: moving blocks within each exact fold, never across gaps.

    Each row holds one complete declared day, its paired observation count and
    summed absolute-error difference. Ten effective five-session blocks are
    required. Missing common days remain visible and prevent interval claims.
    """
    policy: dict[str, Any] = {
        "method": "STRATIFIED_MOVING_BLOCK_PERCENTILE_V1",
        "block_sessions": 5,
        "draws": 1000,
        "seed": 18,
        "minimum_effective_blocks": 10,
        "confidence_level": "0.95",
        "estimand": "POOLED_COMMON_MAE_DELTA",
        "state": "NOT_ESTIMABLE",
        "lower": None,
        "upper": None,
    }
    if len({(f, d) for f, d, _, _ in points}) != len(points) or any(
        type(n) is not int or n < 0 or not v.is_finite() for _, _, n, v in points
    ):
        raise ValueError("block uncertainty requires unique complete finite daily inputs")
    folds: dict[UUID, list[tuple[int, Decimal]]] = defaultdict(list)
    for fold, _, n, total in sorted(points, key=lambda row: (str(row[0]), row[1])):
        folds[fold].append((n, total))
    blocks = sum(len(rows) // 5 for rows in folds.values())
    policy.update(session_count=len(points), effective_block_count=blocks, empty_common_day_count=sum(n == 0 for _, _, n, _ in points))
    if any(n == 0 for _, _, n, _ in points):
        return policy | {"reason_code": "EMPTY_COMMON_DAY"}
    if not folds or blocks < 10 or any(len(rows) < 5 for rows in folds.values()):
        return policy | {"reason_code": "INSUFFICIENT_TRADING_DAY_BLOCKS"}
    if not calendar_verified:
        return policy | {"reason_code": "CONTIGUOUS_MARKET_CALENDAR_NOT_VERIFIED"}
    rng = random.Random(18)
    draws = []
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = ROUND_HALF_EVEN
        for _ in range(1000):
            sampled = []
            for rows in folds.values():
                chosen: list[tuple[int, Decimal]] = []
                while len(chosen) < len(rows):
                    start = rng.randrange(len(rows) - 4)
                    chosen.extend(rows[start : start + 5])
                sampled.extend(chosen[: len(rows)])
            draws.append(sum((value for _, value in sampled), Decimal(0)) / sum(n for n, _ in sampled))
    draws.sort()
    # Fixed nearest-rank percentile indices (ceil(p*N)-1), no parametric SE.
    return policy | {
        "state": "DESCRIPTIVE_DEPENDENCE_AWARE_INTERVAL",
        "reason_code": "PREDECLARED_BLOCK_RESAMPLING",
        "lower": draws[24],
        "upper": draws[974],
        "multiple_testing_adjustment": "NONE; ALL_CANDIDATES_REPORTED",
    }


def historical_comparison_statistics(
    points: tuple[HistoricalEvaluationPoint, ...],
    *,
    arms: tuple[tuple[UUID, str], ...],
    sessions: tuple[tuple[UUID, UUID, date], ...],
    instruments: tuple[UUID, ...],
    baseline_arm_id: UUID,
    contiguous_folds: frozenset[UUID] = frozenset(),
) -> dict[str, Any]:
    """Every arm retains full, own-estimable and all-arm-common denominators."""
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = ROUND_HALF_EVEN
        return _comparison(
            points,
            arms=arms,
            sessions=sessions,
            instruments=instruments,
            baseline_arm_id=baseline_arm_id,
            contiguous_folds=contiguous_folds,
        )


def _pair(point: HistoricalEvaluationPoint, baseline: HistoricalEvaluationPoint) -> ValidityPair:
    if not point.estimable or not baseline.estimable or point.key != baseline.key or point.label != baseline.label:
        raise ValueError("historical diagnostics require an exact estimable pair")
    assert point.prediction is not None and baseline.prediction is not None and point.label is not None
    return ValidityPair(point.commitment_id, point.session_date, point.prediction, baseline.prediction, point.label, point.instrument_id)


def _comparison(
    points: tuple[HistoricalEvaluationPoint, ...],
    *,
    arms: tuple[tuple[UUID, str], ...],
    sessions: tuple[tuple[UUID, UUID, date], ...],
    instruments: tuple[UUID, ...],
    baseline_arm_id: UUID,
    contiguous_folds: frozenset[UUID],
) -> dict[str, Any]:
    if not arms or baseline_arm_id not in {identity for identity, _ in arms}:
        raise ValueError("comparison requires its exact baseline arm")
    days = tuple(sorted({day for _, _, day in sessions}))
    if len(days) != len(sessions) or len(set(instruments)) != len(instruments) or len({i for i, _ in arms}) != len(arms):
        raise ValueError("comparison requires unique separated evaluation dates and member/arm rosters")
    allowed = {(fold, session, day) for fold, session, day in sessions}
    by_arm: dict[UUID, dict[tuple[date, UUID], HistoricalEvaluationPoint]] = {identity: {} for identity, _ in arms}
    for point in points:
        if (
            point.arm_id not in by_arm
            or point.instrument_id not in instruments
            or (point.fold_id, point.session_id, point.session_date) not in allowed
        ):
            raise ValueError("Evaluation input is outside the frozen comparison population")
        if point.key in by_arm[point.arm_id]:
            raise ValueError("duplicate Evaluation input for arm/day/instrument")
        by_arm[point.arm_id][point.key] = point
    eligible = {arm: {key for key, p in members.items() if p.estimable} for arm, members in by_arm.items()}
    common = set.intersection(*eligible.values())
    ordered_common = tuple(sorted(common, key=lambda key: (key[0], str(key[1]))))
    reference = by_arm[baseline_arm_id]
    all_keys = {(day, instrument) for day in days for instrument in instruments}
    labels: dict[tuple[date, UUID], Decimal] = {}
    for point in points:
        if point.label is not None and point.label_status in {"COMPLETE", "PARTIAL"}:
            if point.key in labels and labels[point.key] != point.label:
                raise ValueError("paired arms have conflicting canonical labels")
            labels[point.key] = point.label
    result: list[dict[str, Any]] = []
    for arm_id, name in arms:
        members = by_arm[arm_id]
        own = tuple(members[key] for key in sorted(eligible[arm_id], key=lambda key: (key[0], str(key[1]))))
        own_pairs = tuple(_pair(p, p) for p in own)
        paired = tuple(_pair(members[key], reference[key]) for key in ordered_common)
        complete = _diagnostics(own_pairs, days)
        comparison = _diagnostics(paired, days)
        fold_reports = []
        for fold in dict.fromkeys(fold for fold, _, _ in sessions):
            fold_days = tuple(day for f, _, day in sessions if f == fold)
            fold_reports.append(
                {"fold_id": fold, "statistics": _diagnostics(tuple(p for p in paired if p.session in fold_days), fold_days)}
            )
        months = tuple(sorted({str(day)[:7] for day in days}))
        monthly = tuple(
            {
                "month": month,
                "statistics": _diagnostics(
                    tuple(p for p in paired if str(p.session).startswith(month)), tuple(day for day in days if str(day).startswith(month))
                ),
            }
            for month in months
        )
        errors: dict[UUID, Decimal] = defaultdict(Decimal)
        counts: Counter[UUID] = Counter()
        for p in paired:
            assert p.instrument_id is not None
            counts[p.instrument_id] += 1
            errors[p.instrument_id] += abs(p.model - p.label)
        total_error = sum(errors.values(), Decimal(0))
        daily_deltas = tuple(
            (
                fold,
                day,
                sum(p.session == day for p in paired),
                sum((abs(p.model - p.label) - abs(p.baseline - p.label) for p in paired if p.session == day), Decimal(0)),
            )
            for fold, _, day in sessions
        )
        result.append(
            {
                "arm_id": arm_id,
                "arm_code": name,
                "expected_observations": len(all_keys),
                "evaluation_observations": len(members),
                "prediction_available": sum(p.forecast_status == "AVAILABLE" and p.prediction is not None for p in members.values()),
                "label_available": sum(p.label_status in {"COMPLETE", "PARTIAL"} and p.label is not None for p in members.values()),
                "own_estimable_observations": len(own),
                "all_arm_common_observations": len(paired),
                "missing_evaluation_members": tuple(sorted(all_keys - set(members), key=lambda k: (k[0], str(k[1])))),
                "excluded_inputs": tuple(
                    {
                        "session": p.session_date,
                        "instrument_id": p.instrument_id,
                        "input_state": p.input_state,
                        "reason_code": p.reason_code,
                        "forecast_status": p.forecast_status,
                        "label_status": p.label_status,
                    }
                    for p in members.values()
                    if not p.estimable
                ),
                "own_population": complete,
                "common_population": comparison,
                "per_fold": tuple(fold_reports),
                "per_month": monthly,
                "paired_mae_uncertainty": paired_block_uncertainty(
                    daily_deltas, calendar_verified={fold for fold, _, _ in sessions}.issubset(contiguous_folds)
                ),
                "security_concentration": tuple(
                    {
                        "instrument_id": i,
                        "common_observation_count": counts[i],
                        "absolute_error_sum": errors[i],
                        "absolute_error_share": None if total_error == 0 else errors[i] / total_error,
                    }
                    for i in sorted(counts, key=str)
                ),
            }
        )
    pairwise = []
    for left in result:
        for right in result:
            if left["arm_id"] == right["arm_id"]:
                continue
            lm = left["common_population"]["pooled"]["model"]
            rm = right["common_population"]["pooled"]["model"]
            pairwise.append(
                {
                    "model": left["arm_code"],
                    "reference": right["arm_code"],
                    "common_observations": len(common),
                    "deltas": {
                        metric: None
                        if lm[metric]["value"] is None or rm[metric]["value"] is None
                        else lm[metric]["value"] - rm[metric]["value"]
                        for metric in ("bias", "mae", "rmse")
                    },
                }
            )
    rank_equivalence = []
    controls = {name: identity for identity, name in arms if name in {"rule", "feature", "inverse_feature", "ridge_v1", "ridge_v2"}}
    if "feature" in controls:
        for name, identity in controls.items():
            if name == "feature":
                continue
            for day in days:
                keys = tuple(key for key in ordered_common if key[0] == day)
                pairs = tuple(_pair(by_arm[identity][key], by_arm[controls["feature"]][key]) for key in keys)
                rho = _spearman(tuple((p.model, p.baseline) for p in pairs)) if len(pairs) >= 3 else None
                rank_equivalence.append(
                    {
                        "arm_code": name,
                        "reference": "feature",
                        "session": day,
                        "common_observations": len(keys),
                        "prediction_rank_correlation": rho,
                        "state": "NOT_ESTIMABLE" if rho is None else "DESCRIPTIVE",
                        "label": "PREDICTION_VS_PREDICTION_ORDERING; NOT_TARGET_RANK_IC",
                    }
                )
    return {
        "formula_owner": "CANONICAL_EVALUATION_VALIDITY_STATISTICS_V1",
        "expected_sessions": days,
        "expected_population": tuple(sorted(all_keys, key=lambda k: (k[0], str(k[1])))),
        "label_available_population": tuple(sorted(labels, key=lambda k: (k[0], str(k[1])))),
        "common_population": ordered_common,
        "baseline_arm_id": baseline_arm_id,
        "arms": tuple(result),
        "pairwise_error_differences": tuple(pairwise),
        "single_factor_ordering_equivalence": tuple(rank_equivalence),
        "economic_validity": "NOT_ESTIMABLE: NEXT_SESSION_OPEN_CLOSE_LABEL_IS_NOT_EXECUTABLE_RETURN",
        "formal_pit": False,
        "formal_oos": False,
        "alpha_proven": False,
    }
