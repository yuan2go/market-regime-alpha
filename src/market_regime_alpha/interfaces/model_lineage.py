"""Operator-facing same-model traversal through the existing owner verifiers."""

from hashlib import sha256
from typing import Any
from uuid import UUID

from market_regime_alpha.interfaces.daily_observations import daily_observations


def model_lineage(app: Any, model_version_id: UUID) -> dict[str, Any]:
    result: dict[str, Any] = {"model_version_id": model_version_id, "business_writes": 0,
                             "authority": "READ_ONLY_SAME_MODEL_LINEAGE; NOT_QUALIFICATION"}
    stage = "MODEL_TRAINING_ARTIFACT"
    try:
        graph = app.daily_prediction_reads.model_training_lineage(model_version_id)
        result.update(graph)
        training = graph["training_run"]
        stage = "FIT_EVALUATION"
        fit = app.research_evaluation_verifier.verify_evaluation_run(training["evaluation_run_id"])
        result["fit_evaluation_verification"] = fit
        if not fit.matched:
            return {**result, "first_open_condition": "FIT_EVALUATION_RECONCILIATION_FAILED"}
        stage = "BACKTEST_REPORT"
        backtest = app.backtest_replay.verify(training["exploratory_backtest_run_id"])
        result["backtest_verification"] = backtest
        result["backtest_report_sha256"] = sha256(app.backtest_reports.render_json(training["exploratory_backtest_run_id"])).hexdigest()
        if backtest.integrity_mismatch_codes:
            return {**result, "first_open_condition": "BACKTEST_RECONCILIATION_FAILED"}
        stage = "DAILY_OBSERVATIONS"
        observations = daily_observations(app, model_version_id=model_version_id)
        result["daily_observations"] = observations
        result["first_open_condition"] = (
            "UNATTRIBUTED_HISTORY_REQUIRES_IDENTITY_RECOVERY" if not observations["scope_complete"] else
            "BACKTEST_COMPLETION_UNAVAILABLE" if not backtest.matched else
            "NO_EXPERIMENTAL_MODEL_USE" if not graph["experimental_model_uses"] else
            "NATURALLY_MATURED_DAILY_EVIDENCE_ABSENT" if not observations["cycles"] else
            "UNFINISHED_DAILY_WORK" if observations["unavailable"] else
            "SUSTAINED_REAL_SESSION_AND_RESEARCH_FLOORS_REQUIRE_SEPARATE_VERIFICATION")
    except (RuntimeError, ValueError) as exc:
        result.update(first_open_condition=stage + "_OWNER_READ_FAILED", error_type=type(exc).__name__,
                      reason_code=str(exc), automatic_repair=False)
    return result
