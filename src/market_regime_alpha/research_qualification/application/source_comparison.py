"""Bounded source sensitivity derived from reconciled Backtest owner inputs.

Fixed-model replay is a read-only inference diagnostic. It does not mint a new
Forecast, Outcome or Evaluation, and native retrained predictions remain visible.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any, Callable, TYPE_CHECKING
from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest import BacktestSessionRole
from market_regime_alpha.research_qualification.domain import DecisionInputDatasetManifest
from market_regime_alpha.research_qualification.domain.historical_comparison import _diagnostics
from market_regime_alpha.research_qualification.domain.validity_statistics import ValidityPair
from market_regime_alpha.research_qualification.errors import BacktestReportIntegrityError
from market_regime_alpha.research_qualification.ports.model_execution import ModelPredictionBatch, ModelPredictionRow, ModelPredictor
from market_regime_alpha.research_qualification.ports.source_comparison import SourceComparisonInputs, SourceComparisonModel
from market_regime_alpha.shared.hashing import canonical_json_sha256


if TYPE_CHECKING:
    from market_regime_alpha.research_qualification.application.historical_comparison import HistoricalComparisonInputs, HistoricalSpecificationReader


MODES = ("FIXED_MODEL_REPLAY", "FIXED_PROTOCOL_RETRAIN", "FIXED_DATA_MODELS")


def source_comparison(specifications: HistoricalSpecificationReader, comparison_inputs: HistoricalComparisonInputs,
                      project: Callable[[UUID], dict[str, Any]], inputs: SourceComparisonInputs, predictor: ModelPredictor, **arguments) -> dict[str, Any]:
    with localcontext() as context:
        context.prec, context.rounding = 38, ROUND_HALF_EVEN
        return _source_comparison(specifications, comparison_inputs, project, inputs, predictor, **arguments)


def _source_comparison(specifications: HistoricalSpecificationReader, comparison_inputs: HistoricalComparisonInputs,
                       project: Callable[[UUID], dict[str, Any]], inputs: SourceComparisonInputs, predictor: ModelPredictor, *,
                      left_run_id: UUID, right_run_id: UUID, left_arm: str, right_arm: str,
                      start_date: date, end_date: date, mode: str) -> dict[str, Any]:
    if mode not in MODES or start_date > end_date:
        raise ValueError("source comparison requires an explicit supported mode and ordered dates")
    run_ids = (left_run_id, right_run_id)
    unique_runs = tuple(dict.fromkeys(run_ids))
    loaded_specs = {r: specifications.load_specification(r) for r in unique_runs}
    specs = tuple(loaded_specs[r] for r in run_ids)
    members = tuple(tuple(m.instrument_id for m in s.sample_members) for s in specs)
    if members[0] != members[1] or len(members[0]) > 32 or specs[0].target != specs[1].target:
        raise ValueError("source comparison requires the same exact Target and ordered population of at most 32")
    dates = tuple(tuple(s.session_date for f in spec.folds for s in f.sessions
        if s.role is BacktestSessionRole.EVALUATION and start_date <= s.session_date <= end_date) for spec in specs)
    if dates[0] != dates[1] or not dates[0] or len(dates[0]) > 20 or len(set(dates[0])) != len(dates[0]):
        raise ValueError("source comparison requires one to twenty identical non-repeated actual Calendar dates")
    same_source = (specs[0].market_archive, specs[0].market_archive_seal) == (specs[1].market_archive, specs[1].market_archive_seal)
    if same_source != (mode == "FIXED_DATA_MODELS"):
        raise ValueError("source comparison mode disagrees with the exact sealed source identities")
    arms = []
    for spec, code in zip(specs, (left_arm, right_arm), strict=True):
        found = [a for a in spec.arms if a.arm_code == code]
        if len(found) != 1:
            raise ValueError("source comparison arm code must resolve exactly once")
        arms.append(found[0])
    # Reconcile completed canonical results before inspecting labels or features.
    loaded_projections = {r: project(r) for r in unique_runs}
    projections = tuple(loaded_projections[r] for r in run_ids)
    exclusions = []
    for spec, arm, projection in zip(specs, arms, projections, strict=True):
        session_dates = {str(s.exploratory_backtest_fold_session_id): s.session_date for f in spec.folds for s in f.sessions}
        exclusions.append({(session_dates[m["session_id"]], m["instrument_id"]): m
            for m in projection["pre_candidate_exclusions"] if m["arm_id"] == str(arm.exploratory_backtest_arm_id)})
    loaded_points = {r: comparison_inputs.load(r) for r in unique_runs}
    points = tuple(tuple(p for p in loaded_points[r] if p.arm_id == arm.exploratory_backtest_arm_id
        and p.session_date in dates[0]) for r, arm in zip(run_ids, arms, strict=True))
    indexed = tuple({p.key: p for p in side} for side in points)
    if any(len(index) != len(side) for index, side in zip(indexed, points, strict=True)):
        raise BacktestReportIntegrityError("source comparison contains duplicate canonical Evaluation inputs")
    dataset_ids = {p.dataset_id for side in points for p in side}
    datasets = {identity: inputs.dataset(identity) for identity in sorted(dataset_ids, key=str)}
    model_ids = {p.model_version_id for side in points for p in side if p.model_version_id is not None}
    models = {identity: inputs.model(identity) for identity in model_ids}
    if not models or any(m.target_id != specs[0].target.authority_id for m in models.values()):
        raise BacktestReportIntegrityError("source comparison Model owner Target does not match frozen experiment")
    if mode in {"FIXED_PROTOCOL_RETRAIN", "FIXED_MODEL_REPLAY"}:
        def schedule(spec):
            return tuple((f.purpose, f.purge_sessions, f.embargo_sessions, f.evaluation_protocol,
                tuple((s.session_date, s.role) for s in f.sessions)) for f in spec.folds)
        if schedule(specs[0]) != schedule(specs[1]):
            raise ValueError("fixed protocol comparison cannot change training or evaluation windows/protocol")
        recipes = {(m.payload.algorithm_code, m.payload.algorithm_version, m.payload.implementation_sha256,
            m.payload.feature_definition_ids, m.payload.hyperparameters, m.payload.seed) for m in models.values()}
        if len(recipes) != 1:
            raise ValueError("fixed protocol comparison cannot change algorithm, Feature order, parameters or seed")
    rows: list[dict[str, Any]] = []
    replayed: dict[tuple[UUID, UUID], dict[UUID, Decimal]] = {}
    for day in dates[0]:
        day_models = {p.model_version_id for p in points[0] if p.session_date == day and p.model_version_id is not None}
        if mode == "FIXED_MODEL_REPLAY" and len(day_models) != 1:
            raise BacktestReportIntegrityError("fixed replay requires exactly one original ModelVersion per date")
        fixed = models[next(iter(day_models))] if mode == "FIXED_MODEL_REPLAY" else None
        for instrument in members[0]:
            key = (day, instrument)
            sides: list[dict[str, Any]] = []
            for index in range(2):
                point = indexed[index].get(key)
                if point is None:
                    reason = exclusions[index].get((day, str(instrument)))
                    if reason is None:
                        raise BacktestReportIntegrityError("source comparison lacks the exclusion for a declared population slot")
                    sides.append({"state": "NO_CANONICAL_CANDIDATE", "canonical_exclusion": reason,
                        "prediction": None, "label": None, "features": ()})
                    continue
                manifest = datasets[point.dataset_id]
                candidates = [r for r in manifest.rows if r.instrument_id == instrument]
                if len(candidates) != 1:
                    raise BacktestReportIntegrityError("source comparison candidate lacks its exact Dataset population row")
                prediction = point.prediction
                replay_state = "CANONICAL_PREDICTION"
                if fixed is not None:
                    replay_key = (fixed.model_version_id, manifest.dataset_id)
                    if replay_key not in replayed:
                        replayed[replay_key] = replay_model_batch(fixed, manifest, predictor)
                    prediction = replayed[replay_key].get(instrument)
                    if prediction is None:
                        prediction, replay_state = None, "FEATURE_NOT_ESTIMABLE"
                    else:
                        replay_state = "READ_ONLY_FROZEN_MODEL_INFERENCE"
                        if index == 0 and point.prediction is not None and prediction != point.prediction:
                            raise BacktestReportIntegrityError("fixed model replay differs from original canonical Forecast")
                sides.append({"state": point.input_state, "reason_code": point.reason_code,
                    "estimable": point.estimable and prediction is not None,
                    "prediction": prediction, "native_prediction": point.prediction, "label": point.label,
                    "prediction_authority": replay_state, "fixed_model_version_id": None if fixed is None else fixed.model_version_id,
                    "canonical_input": asdict(point), "dataset_sha256": str(manifest.content_sha256),
                    "features": tuple(asdict(c) for c in candidates[0].cells)})
            both = all(s.get("estimable", False) for s in sides)
            features = tuple({c["feature_definition_id"]: c for c in side["features"]} for side in sides)
            feature_deltas = tuple({"feature_definition_id": identity,
                "left": features[0].get(identity), "right": features[1].get(identity),
                "value_delta": _numeric_delta(features[0].get(identity, {}).get("value"), features[1].get(identity, {}).get("value"))}
                for identity in sorted(set(features[0]) | set(features[1]), key=str))
            rows.append({"session_date": day, "instrument_id": instrument, "left": sides[0], "right": sides[1],
                "feature_deltas": feature_deltas,
                "paired_estimable": both, "prediction_delta": sides[1]["prediction"] - sides[0]["prediction"] if both else None,
                "label_delta": sides[1]["label"] - sides[0]["label"] if both else None,
                "absolute_error_delta": abs(sides[1]["prediction"] - sides[1]["label"]) - abs(sides[0]["prediction"] - sides[0]["label"]) if both else None})
    statistics = {}
    for side in ("left", "right"):
        for population in ("own", "paired"):
            pairs = tuple(ValidityPair(r[side]["canonical_input"]["commitment_id"], r["session_date"], r[side]["prediction"],
                Decimal(0), r[side]["label"], r["instrument_id"]) for r in rows
                if r[side].get("estimable", False) and (population == "own" or r["paired_estimable"]))
            statistics[side + "_" + population] = _diagnostics(pairs, dates[0])
    raw = tuple(inputs.bars(tuple(sorted({p.dataset_id for p in side}, key=str)),
        tuple(sorted({p.outcome_revision_id for p in side}, key=str))) for side in points)
    result = {"schema": "mra-source-sensitivity-v1", "mode": mode,
        "authority": "READ_ONLY_RECONCILED_INPUT_PROJECTION_NO_NEW_FORECAST_OR_EVALUATION",
        "target": asdict(specs[0].target), "dates": dates[0], "population": members[0],
        "run_ids": (left_run_id, right_run_id), "arms": (left_arm, right_arm),
        "specification_sha256": tuple(str(s.content_sha256) for s in specs),
        "canonical_projection_sha256": tuple(p["projection_sha256"] for p in projections),
        "archives": tuple((asdict(s.market_archive), asdict(s.market_archive_seal)) for s in specs),
        "models": tuple({"model_version_id": m.model_version_id, "content_sha256": m.content_sha256,
            "fitted_content_sha256": str(m.payload.fitted_content_sha256), "last_fit_decision": m.last_fit_decision,
            "last_fit_label_cutoff": m.last_fit_label_cutoff, "feature_order": m.payload.feature_definition_ids} for m in sorted(models.values(), key=lambda m: str(m.model_version_id))),
        "declared_slots": len(rows), "paired_estimable": sum(r["paired_estimable"] for r in rows),
        "raw_revisions": {"left": raw[0], "right": raw[1]}, "raw_differences": raw_differences(*raw),
        "rows": tuple(rows), "statistics": statistics,
        "limitations": ("NO_PROVIDER_OR_ADJUSTMENT_EQUIVALENCE_CLAIM", "ACTUAL_BACKFILL_KNOWLEDGE_NOT_PIT",
            "DESCRIPTIVE_SOURCE_SENSITIVITY_NOT_MODEL_SELECTION", "NOT_ACCOUNT_NAV_OR_TRADABLE_ALPHA")}
    result["projection_sha256"] = canonical_json_sha256(result)
    return result


def replay_model_batch(model: SourceComparisonModel, manifest: DecisionInputDatasetManifest,
                       predictor: ModelPredictor) -> dict[UUID, Decimal]:
    """One exact immutable input batch; fitted preprocessing is never refit."""
    if max(model.last_fit_decision, model.last_fit_label_cutoff) >= manifest.decision_time.value:
        raise BacktestReportIntegrityError("fixed model replay would use a future FIT decision or unmatured label")
    rows = []
    for row in manifest.rows:
        cells = {c.feature_definition_id: c for c in row.cells}
        required = tuple(cells.get(f) for f in model.payload.feature_definition_ids)
        if any(c is None or c.status.value != "AVAILABLE" or not isinstance(c.value, Decimal) for c in required):
            continue
        rows.append(ModelPredictionRow(row.instrument_id,
            tuple(c.value for c in required if c is not None and isinstance(c.value, Decimal))))
    if not rows:
        return {}
    predicted = predictor.predict(model.payload, ModelPredictionBatch(tuple(rows)))
    if (len(predicted) != len(rows) or {p.row_id for p in predicted} != {r.row_id for r in rows}
            or any(not isinstance(p.point_estimate, Decimal) or not p.point_estimate.is_finite() for p in predicted)):
        raise BacktestReportIntegrityError("fixed model adapter returned an unexpected or nonfinite prediction roster")
    return {p.row_id: p.point_estimate for p in predicted}


def _numeric_delta(left, right):
    if isinstance(left, Decimal) and isinstance(right, Decimal):
        with localcontext() as context:
            context.prec, context.rounding = 38, ROUND_HALF_EVEN
            return right - left
    return None


def raw_differences(left: tuple[dict, ...], right: tuple[dict, ...]) -> tuple[dict, ...]:
    """Align exact semantic bar keys; never pick one of conflicting revisions."""
    from collections import defaultdict
    indexed = []
    for side in (left, right):
        rows = defaultdict(list)
        for row in side:
            key = tuple(row[k] for k in ("instrument_id", "timeframe", "price_basis", "event_start", "event_end"))
            rows[key].append(row)
        indexed.append(rows)
    result = []
    for key in sorted(set(indexed[0]) | set(indexed[1]), key=str):
        a, b = indexed[0][key], indexed[1][key]
        matched = len(a) == len(b) == 1
        result.append({"semantic_key": key,
            "state": "PAIRED" if matched else "MISSING_SIDE" if not a or not b else "AMBIGUOUS_REVISION_ROSTER",
            "left_revision_ids": tuple(r["bar_revision_id"] for r in a),
            "right_revision_ids": tuple(r["bar_revision_id"] for r in b),
            "right_minus_left": {name: _numeric_delta(a[0][name], b[0][name]) for name in
                ("open_value", "high_value", "low_value", "close_value", "volume_value", "turnover_value")} if matched else None})
    return tuple(result)
