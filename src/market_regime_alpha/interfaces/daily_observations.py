"""Read-only research inputs from reconciled published and evaluated daily work."""

from datetime import date
from typing import Any
from uuid import UUID

from market_regime_alpha.interfaces.daily_health import daily_health
from market_regime_alpha.interfaces.daily_research import decode_daily_plan
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


def daily_observations(
    app: Any, *, target_session_date: date | None = None,
    model_version_id: UUID | None = None, target_definition_id: UUID | None = None,
) -> dict[str, Any]:
    health = daily_health(app)
    cycles = []
    unavailable = []
    for row in health["ledger"]:
        if row["state"] == "INTEGRITY_BLOCKED":
            raise ArtifactIntegrityError("research observation refuses unreconciled daily lineage")
        if any(value is not None and row.get(key) != value for key, value in (
            ("target_session", target_session_date), ("model_version_id", model_version_id),
            ("target_definition_id", target_definition_id),
        )):
            continue
        if row["state"] != "COMPLETED":
            unavailable.append({key: row.get(key) for key in (
                "prediction_id", "run_id", "target_session", "state", "reason_code",
            )})
            continue
        reads = app.daily_prediction_reads
        content = reads.run_plan_content(row["run_id"])
        if content is None:
            raise ArtifactIntegrityError("research observation requires the original frozen plan")
        plan = decode_daily_plan(content)
        replay = app.daily_research.replay_completed_cycle(plan)
        publication = reads.forecast_projection(plan)
        evaluation = reads.evaluation_projection(row["evaluation_id"])
        acquired = reads.evaluation_observations(row["evaluation_id"])
        expected = tuple(sorted((member["commitment_id"] for member in publication["predictions"]
                                 if member["commitment_id"] is not None), key=str))
        reads.require_partition_roster(evaluation["evaluation"]["research_partition_id"], expected)
        observed = tuple(sorted((member["commitment_id"] for member in acquired["observations"]), key=str))
        if expected != observed or len(set(expected)) != len(expected):
            raise ArtifactIntegrityError("research observation acquisition roster differs from the frozen population")
        cycles.append({
            "prediction_id": plan.prediction_id, "target_session": row["target_session"],
            "input_session": row["input_session"], "plan_sha256": plan.content_sha256,
            "model_version_id": plan.model_version_id, "target_definition_id": plan.target_definition_id,
            "publication": publication, "evaluation": evaluation, **acquired,
            "baseline_comparison": {
                role: [metric for metric in evaluation["metrics"] if metric["metric_code"].startswith(prefix)]
                for role, prefix in (("model", "model_"), ("baseline", "rule_baseline_"))
            },
            "replay": replay,
        })
    return {
        "schema": "canonical-daily-research-observations-v1",
        "authority": "READ_ONLY_CANONICAL_OBSERVATION_PROJECTION",
        "observed_at": health["observed_at"], "cycles": cycles, "unavailable": unavailable,
        "business_writes": 0, "research_evidence": "DESCRIPTIVE / NOT_ALPHA_EVIDENCE",
    }
