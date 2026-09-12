"""Paired robustness projections from exact canonical Evaluation observations.

V2 adds pair-specific denominators and two separately declared estimands. It
does not select models, manufacture labels, or modify the v1 comparison bytes.
"""

from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from typing import Any
from uuid import UUID

from market_regime_alpha.research_qualification.domain.evaluation_formula import _spearman
from market_regime_alpha.research_qualification.domain.historical_comparison import HistoricalEvaluationPoint, _pair, _diagnostics, paired_block_uncertainty


def robustness_statistics(points: tuple[HistoricalEvaluationPoint, ...], *, arms: tuple[tuple[UUID, str], ...],
                          sessions: tuple, instruments: tuple[UUID, ...], contiguous_folds: frozenset[UUID]) -> dict[str, Any]:
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 38, ROUND_HALF_EVEN
        return _statistics(points, arms, sessions, instruments, contiguous_folds)


def _statistics(points, arms, sessions, instruments, contiguous_folds):
    names = {name: identity for identity, name in arms}
    controls = ("zero", "training_mean", "training_median")
    if not set((*controls,"ridge_v2")) <= set(names):
        raise ValueError("robustness v2 requires the frozen simple controls and original Ridge")
    models = tuple(name for _,name in arms if name not in controls)
    comparisons = tuple((name,control) for name in models for control in controls) + tuple((name,"ridge_v2") for name in models if name!="ridge_v2")
    days = tuple(day for _,_,day in sessions)
    if len(set(days)) != len(days) or days != tuple(sorted(days)):
        raise ValueError("robustness cannot count repeated or unordered validation dates")
    by_arm = {identity: {} for identity,_ in arms}
    allowed = {(fold,session,day) for fold,session,day in sessions}
    for point in points:
        if point.arm_id not in by_arm or point.instrument_id not in instruments or (point.fold_id,point.session_id,point.session_date) not in allowed or point.key in by_arm[point.arm_id]:
            raise ValueError("robustness inputs have duplicate or undeclared identities")
        by_arm[point.arm_id][point.key] = point
    labels = {}
    for point in points:
        if point.label_status in {"COMPLETE","PARTIAL"} and point.label is not None:
            if point.key in labels and labels[point.key] != point.label:
                raise ValueError("robustness paired canonical labels conflict")
            labels[point.key] = point.label
    eligible = {identity: {key for key,p in rows.items() if p.estimable} for identity,rows in by_arm.items()}
    common = set.intersection(*eligible.values())
    verified = {fold for fold,_,_ in sessions} <= contiguous_folds
    results = []
    for model,reference in comparisons:
        left,right = by_arm[names[model]],by_arm[names[reference]]
        keys = tuple(sorted(eligible[names[model]] & eligible[names[reference]],key=lambda key:(key[0],str(key[1]))))
        pairs = tuple(_pair(left[key],right[key]) for key in keys)
        daily_pairs = {day: tuple(p for p in pairs if p.session==day) for day in days}
        daily = []
        mae_inputs,ic_inputs = [],[]
        security = {identity: [0,Decimal(0)] for identity in instruments}
        for fold,_,day in sessions:
            items = daily_pairs[day]
            total = sum((abs(p.model-p.label)-abs(p.baseline-p.label) for p in items),Decimal(0))
            left_ic = _spearman(tuple((p.model,p.label) for p in items)) if len(items)>=3 else None
            right_ic = _spearman(tuple((p.baseline,p.label) for p in items)) if len(items)>=3 else None
            delta_ic = None if left_ic is None or right_ic is None else left_ic-right_ic
            daily.append({"fold_id":fold,"session":day,"paired_observations":len(items),
                "mae_delta":None if not items else total/len(items), "absolute_error_delta_sum":total if items else None,
                "model_rank_ic":left_ic,"reference_rank_ic":right_ic,"rank_ic_delta":delta_ic,
                "rank_state":"NOT_ESTIMABLE" if delta_ic is None else "DESCRIPTIVE"})
            mae_inputs.append((fold,day,len(items),total))
            ic_inputs.append((fold,day,0 if delta_ic is None else 1,Decimal(0) if delta_ic is None else delta_ic))
            for p in items:
                security[p.instrument_id][0] += 1
                security[p.instrument_id][1] += abs(p.model-p.label)-abs(p.baseline-p.label)
        total_delta = sum((row[3] for row in mae_inputs),Decimal(0))
        estimable_mae = tuple(row["mae_delta"] for row in daily if row["mae_delta"] is not None)
        estimable_ic = tuple(row["rank_ic_delta"] for row in daily if row["rank_ic_delta"] is not None)
        slices = []
        for kind,values in (("FOLD",tuple(dict.fromkeys(f for f,_,_ in sessions))),
                            ("MONTH",tuple(dict.fromkeys(str(d)[:7] for d in days))),
                            ("YEAR",tuple(dict.fromkeys(str(d)[:4] for d in days)))):
            for value in values:
                selected = tuple(row for row in daily if (row["fold_id"]==value if kind=="FOLD" else str(row["session"]).startswith(value)))
                selected_days = tuple(row["session"] for row in selected)
                slices.append({"kind":kind,"value":value,"statistics":_diagnostics(tuple(p for p in pairs if p.session in selected_days),selected_days),
                    "mean_daily_rank_ic_delta":_mean(tuple(row["rank_ic_delta"] for row in selected if row["rank_ic_delta"] is not None))})
        sensitivity = []
        for instrument in sorted(instruments,key=str):
            count,error = security[instrument]
            remaining = len(pairs)-count
            rank_deltas = []
            # Constant-reference IC is intrinsically unavailable; removing a
            # security cannot make it a meaningful ranking comparator.
            if reference not in controls:
                for items in daily_pairs.values():
                    reduced = tuple(p for p in items if p.instrument_id!=instrument)
                    a = _spearman(tuple((p.model,p.label) for p in reduced)) if len(reduced)>=3 else None
                    b = _spearman(tuple((p.baseline,p.label) for p in reduced)) if len(reduced)>=3 else None
                    if a is not None and b is not None:
                        rank_deltas.append(a-b)
            sensitivity.append({"excluded_instrument_id":instrument,"removed_observations":count,
                "removed_absolute_error_delta_sum":error,"remaining_observations":remaining,
                "remaining_mae_delta":None if remaining==0 else (total_delta-error)/remaining,
                "remaining_mean_daily_rank_ic_delta":_mean(rank_deltas),"remaining_estimable_ic_days":len(rank_deltas),
                "use":"POST_HOC_SENSITIVITY_NOT_MAIN_POPULATION_SELECTION"})
        ic_interval = paired_block_uncertainty(tuple(ic_inputs),calendar_verified=verified)
        ic_interval["estimand"] = "MEAN_PAIRED_DAILY_RANK_IC_DELTA"
        results.append({"model":model,"reference":reference,"expected_observations":len(days)*len(instruments),
            "model_own_observations":len(eligible[names[model]]),"reference_own_observations":len(eligible[names[reference]]),
            "paired_observations":len(pairs),"all_arm_common_observations":len(common),"paired_population":keys,
            "comparison":_diagnostics(pairs,days),"per_day":tuple(daily),"time_slices":tuple(slices),
            "mae_delta":None if not pairs else total_delta/len(pairs),"mean_daily_rank_ic_delta":_mean(estimable_ic),
            "mae_day_signs":_signs(estimable_mae,len(days)),"ic_day_signs":_signs(estimable_ic,len(days)),
            "worst_mae_day":None if not estimable_mae else max((row for row in daily if row["mae_delta"] is not None),key=lambda row:row["mae_delta"]),
            "paired_mae_uncertainty":paired_block_uncertainty(tuple(mae_inputs),calendar_verified=verified),
            "paired_daily_ic_uncertainty":ic_interval,"leave_one_security_out":tuple(sensitivity)})
    return {"schema":"mra-robustness-statistics-v2","primary_point_metric":"PAIRED_COMMON_MAE",
        "primary_ordering_diagnostic":"PAIRED_DAILY_RANK_IC","comparisons":tuple(results),
        "distinct_validation_days":len(days),"validation_months":tuple(sorted({str(d)[:7] for d in days})),
        "validation_years":tuple(sorted({d.year for d in days})),"all_arm_common_observations":len(common),
        "all_comparisons_reported":True,"multiple_comparisons":"UNADJUSTED_DESCRIPTIVE_INTERVALS_NO_SIGNIFICANCE_OR_PROMOTION_CLAIM",
        "economic_validity":"NOT_ESTIMABLE_NO_CONTINUOUS_CASH_INVENTORY_FILL_COST_VALUATION_PATH"}


def _mean(values):
    return None if not values else sum(values,Decimal(0))/len(values)


def _signs(values,total):
    return {"positive":sum(v>0 for v in values),"negative":sum(v<0 for v in values),"zero":sum(v==0 for v in values),
        "not_estimable":total-len(values),"estimable_days":len(values),
        "positive_fraction":None if not values else Decimal(sum(v>0 for v in values))/len(values),
        "negative_fraction":None if not values else Decimal(sum(v<0 for v in values))/len(values)}
