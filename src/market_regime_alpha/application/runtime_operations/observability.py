"""Read-only trace and metrics derived from Canonical Runtime authorities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any

from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


@dataclass(frozen=True, slots=True)
class RuntimeStageObservation:
    trace_id: str
    run_id: ArtifactId
    tick_id: ArtifactId
    stage: str
    provider: str | None
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    status: str
    reason_codes: tuple[str, ...]
    retry_count: int
    coverage: float | None
    deadline_margin_seconds: float | None
    fencing_token: int
    lease_expires_at: datetime | None

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "run_id": str(self.run_id),
            "tick_id": str(self.tick_id),
            "stage": self.stage,
            "provider": self.provider,
            "started_at": canonical_datetime(self.started_at),
            "completed_at": (None if self.completed_at is None else canonical_datetime(self.completed_at)),
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "retry_count": self.retry_count,
            "coverage": self.coverage,
            "deadline_margin_seconds": self.deadline_margin_seconds,
            "fencing_token": self.fencing_token,
            "lease_expires_at": (None if self.lease_expires_at is None else canonical_datetime(self.lease_expires_at)),
        }


class PostgresRuntimeObservability:
    """Project trace/metrics without creating an observability fact store."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Any | None = None,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be PostgresConnectionFactory")
        self._factory = factory
        self._clock = clock or (lambda: datetime.now(UTC).replace(microsecond=0))
        self._journal = PostgresContinuousResearchJournal(factory, apply_migrations=False)
        self._decisions = PostgresDecisionSystemRepository(factory)

    def trace_run(self, run_id: ArtifactId) -> dict[str, Any]:
        snapshot = self._journal.get_run(run_id)
        observations: list[RuntimeStageObservation] = []
        for tick in snapshot.ticks:
            trace_id = _trace_id(run_id, tick.command.tick_id)
            observations.append(
                RuntimeStageObservation(
                    trace_id=trace_id,
                    run_id=run_id,
                    tick_id=tick.command.tick_id,
                    stage="TICK",
                    provider=None,
                    started_at=tick.created_at,
                    completed_at=tick.completed_at,
                    duration_seconds=_duration(tick.created_at, tick.completed_at),
                    status=tick.status.value,
                    reason_codes=(() if tick.last_error is None else ("TICK_LAST_ERROR_RECORDED",)),
                    retry_count=_event_count(
                        snapshot.events,
                        tick.command.tick_id,
                        "RUN_RECOVERED",
                    ),
                    coverage=None,
                    deadline_margin_seconds=None,
                    fencing_token=tick.fencing_token,
                    lease_expires_at=tick.lease_expires_at,
                )
            )
            attempts = self._attempt_observations(run_id, tick.command.tick_id, tick.command.observed_at, trace_id)
            observations.extend(attempts)
            try:
                summary = self._decisions.get_research_summary_for_tick(
                    run_id=run_id,
                    tick_id=tick.command.tick_id,
                    runtime_mode=snapshot.command.authority_mode,
                )
            except KeyError:
                continue
            for stage in summary.stages:
                observations.append(
                    RuntimeStageObservation(
                        trace_id=trace_id,
                        run_id=run_id,
                        tick_id=tick.command.tick_id,
                        stage=stage.stage.value,
                        provider=None,
                        started_at=stage.evidence_available_at,
                        completed_at=stage.stage_completed_at,
                        duration_seconds=_duration(
                            stage.evidence_available_at,
                            stage.stage_completed_at,
                        ),
                        status=stage.status.value,
                        reason_codes=stage.reason_codes,
                        retry_count=0,
                        coverage=None,
                        deadline_margin_seconds=(summary.decision_time - stage.evidence_available_at).total_seconds(),
                        fencing_token=tick.fencing_token,
                        lease_expires_at=tick.lease_expires_at,
                    )
                )
            observations.append(
                RuntimeStageObservation(
                    trace_id=trace_id,
                    run_id=run_id,
                    tick_id=tick.command.tick_id,
                    stage="SUMMARY",
                    provider=None,
                    started_at=max(item.stage_completed_at for item in summary.stages),
                    completed_at=summary.created_at,
                    duration_seconds=_duration(
                        max(item.stage_completed_at for item in summary.stages),
                        summary.created_at,
                    ),
                    status=summary.outcome.value,
                    reason_codes=summary.reason_codes,
                    retry_count=0,
                    coverage=None,
                    deadline_margin_seconds=(
                        summary.decision_time - max(item.evidence_available_at for item in summary.stages)
                    ).total_seconds(),
                    fencing_token=tick.fencing_token,
                    lease_expires_at=tick.lease_expires_at,
                )
            )
        ordered = tuple(
            sorted(
                observations,
                key=lambda item: (
                    str(item.tick_id),
                    item.started_at,
                    item.stage,
                    item.provider or "",
                ),
            )
        )
        return {
            "schema_version": "canonical-runtime-trace/v1",
            "run_id": str(run_id),
            "generated_at": canonical_datetime(self._clock()),
            "observations": [item.to_canonical_dict() for item in ordered],
            "derived_from_authority": True,
            "decision_input": False,
        }

    def metrics(self, run_id: ArtifactId) -> dict[str, Any]:
        trace = self.trace_run(run_id)
        observations = trace["observations"]
        providers = [item for item in observations if item["provider"] is not None]
        stages = [item for item in observations if item["provider"] is None]
        with self._factory.connection(read_only=True) as connection:
            counts = connection.execute(
                """
                SELECT
                  count(*) FILTER (WHERE event_type = 'RUN_RECOVERED'),
                  count(*) FILTER (WHERE event_type = 'LEASE_EXPIRED'),
                  count(*) FILTER (WHERE event_type = 'TICK_FAILED')
                FROM continuous_runtime_event WHERE run_id = %s
                """,
                (str(run_id),),
            ).fetchone()
            summary_rows = connection.execute(
                """
                SELECT outcome, count(*) FROM research_daily_summary
                WHERE run_id = %s GROUP BY outcome ORDER BY outcome
                """,
                (str(run_id),),
            ).fetchall()
            candidate_count = connection.execute(
                """
                SELECT count(*),
                       COALESCE(sum(jsonb_array_length(payload_json->'records')), 0)
                FROM state_runtime_candidate_artifact
                WHERE run_id = %s
                """,
                (str(run_id),),
            ).fetchone()
            minute_coverage = connection.execute(
                """
                SELECT count(*), COALESCE(sum(i.minute_success_count), 0),
                       COALESCE(sum(i.minute_failure_count), 0)
                FROM continuous_child_run c
                JOIN longitudinal_operational_index i
                  ON i.operation_run_id = c.child_run_id
                WHERE c.run_id = %s AND c.child_kind = 'CONTROLLED_OPERATION'
                """,
                (str(run_id),),
            ).fetchone()
        if counts is None or candidate_count is None or minute_coverage is None:
            raise RuntimeError("Runtime metrics aggregate returned no row")
        minute_observed = int(minute_coverage[0]) > 0
        minute_successes = int(minute_coverage[1]) if minute_observed else None
        minute_failures = int(minute_coverage[2]) if minute_observed else None
        minute_total = minute_successes + minute_failures if minute_successes is not None and minute_failures is not None else None
        minute_ratio: float | None = None
        if minute_successes is not None and minute_total is not None and minute_total != 0:
            minute_ratio = minute_successes / minute_total
        return {
            "schema_version": "canonical-runtime-metrics/v2",
            "run_id": str(run_id),
            "generated_at": trace["generated_at"],
            "provider_latency_seconds": _latency_summary(providers),
            "stage_latency_seconds": _latency_summary(stages),
            "provider_failures": sum(item["status"] not in {"STARTED", "SUCCEEDED"} for item in providers),
            "retries": sum(item["retry_count"] for item in providers),
            "deadline_misses": sum((item["deadline_margin_seconds"] or 0) < 0 for item in observations),
            "candidate_artifact_count": int(candidate_count[0]),
            "candidate_count": int(candidate_count[1]),
            "minute_coverage": {
                "observation_status": ("OBSERVED" if minute_observed else "NOT_OBSERVED"),
                "succeeded_count": minute_successes,
                "failed_count": minute_failures,
                "total_count": minute_total,
                "ratio": minute_ratio,
            },
            "recovery_count": int(counts[0]),
            "lease_expiration_count": int(counts[1]),
            "tick_failure_count": int(counts[2]),
            # CAS/fence rejections and replay failures roll back or are reported
            # by callers; there is no durable attempt authority from which an
            # exact count can currently be reconstructed.
            "fence_rejection_count": None,
            "fence_rejection_observation_status": "NOT_OBSERVED",
            "replay_failure_count": None,
            "replay_failure_observation_status": "NOT_OBSERVED",
            "summary_outcomes": {str(row[0]): int(row[1]) for row in summary_rows},
            "decision_input": False,
        }

    def _attempt_observations(
        self,
        run_id: ArtifactId,
        tick_id: ArtifactId,
        decision_time: datetime,
        trace_id: str,
    ) -> tuple[RuntimeStageObservation, ...]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT provider_id, product, started_at, completed_at, status,
                       attempt_number, reason_codes_json, fencing_token,
                       lease_expires_at
                FROM continuous_provider_attempt
                WHERE run_id = %s AND tick_id = %s
                ORDER BY attempt_number
                """,
                (str(run_id), str(tick_id)),
            ).fetchall()
        return tuple(
            RuntimeStageObservation(
                trace_id=trace_id,
                run_id=run_id,
                tick_id=tick_id,
                stage=f"PROVIDER:{row[1]}",
                provider=str(row[0]),
                started_at=row[2],
                completed_at=row[3],
                duration_seconds=_duration(row[2], row[3]),
                status=str(row[4]),
                reason_codes=tuple(str(item) for item in json.loads(str(row[6]))),
                retry_count=max(0, int(row[5]) - 1),
                coverage=None,
                deadline_margin_seconds=(decision_time - (row[3] or row[2])).total_seconds(),
                fencing_token=int(row[7]),
                lease_expires_at=row[8],
            )
            for row in rows
        )


def _trace_id(run_id: ArtifactId, tick_id: ArtifactId) -> str:
    digest = canonical_hash({"run_id": str(run_id), "tick_id": str(tick_id)})
    return f"runtime-trace-{digest.split(':', 1)[1][:24]}"


def _duration(started_at: datetime, completed_at: datetime | None) -> float | None:
    if completed_at is None:
        return None
    return (completed_at - started_at).total_seconds()


def _event_count(events: tuple[Any, ...], tick_id: ArtifactId, event_type: str) -> int:
    return sum(item.event_type == event_type and (item.tick_id is None or item.tick_id == tick_id) for item in events)


def _latency_summary(items: list[dict[str, Any]]) -> dict[str, float | None]:
    values = sorted(float(item["duration_seconds"]) for item in items if item["duration_seconds"] is not None)
    if not values:
        return {"count": 0.0, "minimum": None, "maximum": None, "average": None}
    return {
        "count": float(len(values)),
        "minimum": values[0],
        "maximum": values[-1],
        "average": sum(values) / len(values),
    }


__all__ = ["PostgresRuntimeObservability", "RuntimeStageObservation"]
