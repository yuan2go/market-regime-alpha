"""Read-only research inputs from reconciled published and evaluated daily work."""

from datetime import date
from hashlib import sha256
import json
from typing import Any
from uuid import UUID

from market_regime_alpha.interfaces.daily_health import daily_health
from market_regime_alpha.interfaces.daily_research import decode_daily_plan, encode_daily_plan
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


def daily_observations(
    app: Any, *, target_session_date: date | None = None,
    model_version_id: UUID | None = None, target_definition_id: UUID | None = None,
    target_session_from: date | None = None, target_session_to: date | None = None,
    experimental_model_use_id: UUID | None = None, dataset_id: UUID | None = None,
    decision_run_id: UUID | None = None, completed_only: bool = False,
) -> dict[str, Any]:
    if target_session_from is not None and target_session_to is not None and target_session_from > target_session_to:
        raise ValueError("target session range is reversed")
    if target_session_date is not None and (target_session_from is not None or target_session_to is not None):
        raise ValueError("select an exact target session or a range, not both")
    if type(completed_only) is not bool:
        raise TypeError("completed_only must be boolean")
    health = daily_health(app, complete_history=True)
    cycles = []
    unavailable = []
    for row in health["ledger"]:
        if row["state"] == "INTEGRITY_BLOCKED":
            raise ArtifactIntegrityError("research observation refuses unreconciled daily lineage")
        if any(value is not None and row.get(key) != value for key, value in (
            ("target_session", target_session_date), ("model_version_id", model_version_id),
            ("target_definition_id", target_definition_id),
            ("experimental_model_use_id", experimental_model_use_id), ("dataset_id", dataset_id),
        )):
            continue
        if (target_session_from is not None and row["target_session"] < target_session_from) or (
            target_session_to is not None and row["target_session"] > target_session_to
        ):
            continue
        reads = app.daily_prediction_reads
        content = reads.run_plan_content(row["run_id"])
        if content is None:
            raise ArtifactIntegrityError("research observation requires the original frozen plan")
        plan = decode_daily_plan(content)
        if encode_daily_plan(plan) != content or plan.content_sha256 != row["plan_sha256"]:
            raise ArtifactIntegrityError("research observation frozen plan bytes differ")
        if decision_run_id is not None:
            try:
                decision = reads.decision_run(plan)
            except ArtifactIntegrityError:
                if row["state"] == "COMPLETED":
                    raise
                continue
            if decision != decision_run_id:
                continue
        if row["state"] != "COMPLETED":
            if not completed_only:
                unavailable.append({**{key: row.get(key) for key in (
                    "prediction_id", "run_id", "target_session", "input_session", "state", "reason_code",
                    "model_version_id", "experimental_model_use_id", "target_definition_id", "dataset_id",
                    "plan_sha256", "sampled", "denominators", "population", "forecast_dispositions",
                    "published_at", "input_captures", "decision_time", "input_cutoff",
                )}, "frozen_plan": json.loads(content), "frozen_plan_content": content.decode("utf-8"),
                    "publication": reads.forecast_projection(plan) if row.get("published_at") is not None else None})
            continue
        replay = app.daily_research.replay_completed_cycle(plan)
        if replay.get("matched") is not True or replay.get("mismatch_count") != 0 or replay.get("business_writes") != 0:
            raise ArtifactIntegrityError("research observation refuses a mismatched or writing replay")
        publication = reads.forecast_projection(plan)
        evaluation = reads.evaluation_projection(row["evaluation_id"])
        acquired = reads.evaluation_observations(row["evaluation_id"])
        expected = tuple(sorted((member["commitment_id"] for member in publication["predictions"]
                                 if member["commitment_id"] is not None), key=str))
        reads.require_partition_roster(evaluation["evaluation"]["research_partition_id"], expected)
        observed = tuple(sorted((member["commitment_id"] for member in acquired["observations"]), key=str))
        if expected != observed or len(set(expected)) != len(expected):
            raise ArtifactIntegrityError("research observation acquisition roster differs from the frozen population")
        facts = reads.validity_observation_facts(plan, row["evaluation_id"])
        actual_commitments = tuple(sorted((member["commitment_id"] for member in facts["commitments"]), key=str))
        if expected != actual_commitments:
            raise ArtifactIntegrityError("research observation commitment Authority roster differs from publication")
        cycles.append({
            "prediction_id": plan.prediction_id, "target_session": row["target_session"],
            "input_session": row["input_session"], "plan_sha256": plan.content_sha256,
            "model_version_id": plan.model_version_id, "target_definition_id": plan.target_definition_id,
            "experimental_model_use_id": plan.experimental_model_use_id,
            "dataset_id": plan.dataset_id, "decision_run_id": publication["decision_run_id"],
            "frozen_plan": json.loads(content), "frozen_plan_content": content.decode("utf-8"),
            "frozen_plan_artifact_sha256": sha256(content).hexdigest(),
            "publication": publication, "evaluation": evaluation, **acquired,
            **facts,
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
