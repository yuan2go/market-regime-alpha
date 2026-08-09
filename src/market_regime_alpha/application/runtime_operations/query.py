"""Canonical DAG projection contracts; business facts stay with their owners."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.journal import (
    ChildReferenceDisposition,
    ContinuousChildKind,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.state_system.runtime import StateResearchStage
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


class CanonicalDagNodeType(str, Enum):
    SCHEDULE = "SCHEDULE"
    TICK = "TICK"
    PROVIDER = "PROVIDER"
    EVIDENCE = "EVIDENCE"
    DATASET = "DATASET"
    FEATURE = "FEATURE"
    GOVERNANCE = "GOVERNANCE"
    STATE = "STATE"
    POOL = "POOL"
    CANDIDATE = "CANDIDATE"
    MINUTE = "MINUTE"
    SIGNAL = "SIGNAL"
    FORECAST = "FORECAST"
    SUMMARY = "SUMMARY"


class CanonicalDagNodeStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    REUSED = "REUSED"


@dataclass(frozen=True, slots=True)
class CanonicalDagNode:
    node_id: str
    node_type: CanonicalDagNodeType
    owner: str
    artifact_id: str | None
    content_hash: str | None
    status: CanonicalDagNodeStatus
    observed_at: datetime | None
    parent_node_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    details: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_text("node_id", self.node_id)
        require_text("owner", self.owner)
        if self.artifact_id is not None:
            require_text("artifact_id", self.artifact_id)
        if self.content_hash is not None:
            require_sha256("content_hash", self.content_hash)
        if (self.artifact_id is None) != (self.content_hash is None):
            raise ValueError("DAG Artifact identity and hash are inseparable")
        if self.observed_at is not None and (
            self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() is None
        ):
            raise ValueError("DAG observed_at must be timezone-aware")
        if self.parent_node_ids != tuple(sorted(set(self.parent_node_ids))):
            raise ValueError("DAG parents must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("DAG reasons must be unique and sorted")

    @classmethod
    def create(
        cls,
        *,
        node_type: CanonicalDagNodeType,
        owner: str,
        artifact_id: str | None,
        content_hash: str | None,
        status: CanonicalDagNodeStatus,
        observed_at: datetime | None,
        parent_node_ids: tuple[str, ...] = (),
        reason_codes: tuple[str, ...] = (),
        details: Mapping[str, Any] | None = None,
    ) -> CanonicalDagNode:
        normalized_parents = tuple(sorted(set(parent_node_ids)))
        normalized_reasons = tuple(sorted(set(reason_codes)))
        payload = {
            "node_type": node_type.value,
            "owner": owner,
            "artifact_id": artifact_id,
            "content_hash": content_hash,
            "status": status.value,
            "observed_at": (
                None if observed_at is None else canonical_datetime(observed_at)
            ),
            "parent_node_ids": normalized_parents,
            "reason_codes": normalized_reasons,
            "details": dict(details or {}),
        }
        digest = canonical_hash(payload)
        return cls(
            node_id=f"runtime-dag-node-{digest.split(':', 1)[1][:24]}",
            node_type=node_type,
            owner=owner,
            artifact_id=artifact_id,
            content_hash=content_hash,
            status=status,
            observed_at=observed_at,
            parent_node_ids=normalized_parents,
            reason_codes=normalized_reasons,
            details=details or {},
        )

    @property
    def read_only(self) -> bool:
        return True

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "owner": self.owner,
            "artifact_id": self.artifact_id,
            "content_hash": self.content_hash,
            "status": self.status.value,
            "observed_at": (
                None
                if self.observed_at is None
                else canonical_datetime(self.observed_at)
            ),
            "parent_node_ids": list(self.parent_node_ids),
            "reason_codes": list(self.reason_codes),
            "details": dict(self.details),
            "read_only": True,
        }


@dataclass(frozen=True, slots=True)
class CanonicalRuntimeInspection:
    run_id: ArtifactId
    run_status: str
    nodes: tuple[CanonicalDagNode, ...]
    generated_at: datetime
    schema_version: str = "canonical-runtime-inspection/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "canonical-runtime-inspection/v1":
            raise ValueError("unsupported Canonical Runtime inspection schema")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        identities = tuple(item.node_id for item in self.nodes)
        if identities != tuple(sorted(set(identities))):
            raise ValueError("Canonical DAG nodes must be unique and sorted")

    @property
    def read_only(self) -> bool:
        return True

    def nodes_of_type(
        self, *node_types: CanonicalDagNodeType
    ) -> tuple[CanonicalDagNode, ...]:
        selected = set(node_types)
        return tuple(item for item in self.nodes if item.node_type in selected)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": str(self.run_id),
            "run_status": self.run_status,
            "generated_at": canonical_datetime(self.generated_at),
            "nodes": [item.to_canonical_dict() for item in self.nodes],
            "read_only": True,
            "decision_recomputed": False,
        }


class PostgresCanonicalRuntimeQuery:
    """Reconstruct the DAG solely from existing PostgreSQL owner receipts."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Any | None = None,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be PostgresConnectionFactory")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        from datetime import UTC

        self._factory = factory
        self._clock = clock or (
            lambda: datetime.now(UTC).replace(microsecond=0)
        )
        self._journal = PostgresContinuousResearchJournal(
            factory, apply_migrations=False
        )
        self._decisions = PostgresDecisionSystemRepository(factory)

    def inspect_run(self, run_id: ArtifactId) -> CanonicalRuntimeInspection:
        snapshot = self._journal.get_run(run_id)
        nodes: list[CanonicalDagNode] = []
        schedule_node = self._schedule_node(run_id, snapshot.created_at)
        nodes.append(schedule_node)
        for tick in snapshot.ticks:
            tick_node = CanonicalDagNode.create(
                node_type=CanonicalDagNodeType.TICK,
                owner="CONTINUOUS_RESEARCH",
                artifact_id=str(tick.command.tick_id),
                content_hash=tick.command.tick_hash,
                status=_tick_status(tick.status.value),
                observed_at=tick.command.observed_at,
                parent_node_ids=(schedule_node.node_id,),
                reason_codes=(
                    ()
                    if tick.last_error is None
                    else ("TICK_LAST_ERROR_RECORDED",)
                ),
                details={
                    "tick_id": str(tick.command.tick_id),
                    "tick_sequence": tick.tick_sequence,
                    "session_phase": tick.session_phase.value,
                    "fencing_token": tick.fencing_token,
                    "claim_id": tick.claim_id,
                    "lease_acquired_at": _canonical_optional(
                        tick.lease_acquired_at
                    ),
                    "lease_expires_at": _canonical_optional(
                        tick.lease_expires_at
                    ),
                    "heartbeat_at": _canonical_optional(tick.heartbeat_at),
                    "completed_at": _canonical_optional(tick.completed_at),
                    "last_error": tick.last_error,
                },
            )
            nodes.append(tick_node)
            nodes.extend(
                self._tick_nodes(
                    run_id=run_id,
                    tick_id=tick.command.tick_id,
                    runtime_mode=snapshot.command.authority_mode,
                    tick_node=tick_node,
                )
            )
        return CanonicalRuntimeInspection(
            run_id=run_id,
            run_status=snapshot.status.value,
            nodes=tuple(sorted(nodes, key=lambda item: item.node_id)),
            generated_at=self._clock(),
        )

    def inspect_tick(
        self, run_id: ArtifactId, tick_id: ArtifactId
    ) -> dict[str, Any]:
        inspection = self.inspect_run(run_id)
        tick_nodes = tuple(
            item
            for item in inspection.nodes
            if item.details.get("tick_id") == str(tick_id)
            or item.artifact_id == str(tick_id)
            or item.node_type is CanonicalDagNodeType.SCHEDULE
        )
        if not any(item.node_type is CanonicalDagNodeType.TICK for item in tick_nodes):
            raise KeyError(f"{run_id}:{tick_id}")
        return _inspection_projection(inspection, tick_nodes, "INSPECT_TICK")

    def inspect_provider(
        self, run_id: ArtifactId, *, attempt_id: int | None = None
    ) -> dict[str, Any]:
        return self._typed_projection(
            run_id,
            (CanonicalDagNodeType.PROVIDER,),
            operation="INSPECT_PROVIDER",
            predicate=(
                None
                if attempt_id is None
                else lambda item: item.details.get("attempt_id") == attempt_id
            ),
        )

    def inspect_evidence(self, run_id: ArtifactId) -> dict[str, Any]:
        return self._typed_projection(
            run_id,
            (CanonicalDagNodeType.EVIDENCE,),
            operation="INSPECT_EVIDENCE",
        )

    def inspect_state(self, run_id: ArtifactId) -> dict[str, Any]:
        return self._typed_projection(
            run_id,
            (CanonicalDagNodeType.STATE,),
            operation="INSPECT_STATE",
        )

    def inspect_pool(self, run_id: ArtifactId) -> dict[str, Any]:
        return self._typed_projection(
            run_id,
            (CanonicalDagNodeType.POOL,),
            operation="INSPECT_POOL",
        )

    def inspect_candidate(self, run_id: ArtifactId) -> dict[str, Any]:
        return self._typed_projection(
            run_id,
            (CanonicalDagNodeType.CANDIDATE,),
            operation="INSPECT_CANDIDATE",
        )

    def inspect_minute(self, run_id: ArtifactId) -> dict[str, Any]:
        return self._typed_projection(
            run_id,
            (CanonicalDagNodeType.MINUTE,),
            operation="INSPECT_MINUTE",
        )

    def inspect_model_selection(self, run_id: ArtifactId) -> dict[str, Any]:
        return self._typed_projection(
            run_id,
            (CanonicalDagNodeType.GOVERNANCE,),
            operation="INSPECT_MODEL_SELECTION",
        )

    def inspect_summary(self, run_id: ArtifactId) -> dict[str, Any]:
        return self._typed_projection(
            run_id,
            (CanonicalDagNodeType.SUMMARY,),
            operation="INSPECT_SUMMARY",
        )

    def _typed_projection(
        self,
        run_id: ArtifactId,
        node_types: tuple[CanonicalDagNodeType, ...],
        *,
        operation: str,
        predicate: Any | None = None,
    ) -> dict[str, Any]:
        inspection = self.inspect_run(run_id)
        selected = tuple(
            item
            for item in inspection.nodes
            if item.node_type in node_types
            and (predicate is None or predicate(item))
        )
        return _inspection_projection(inspection, selected, operation)

    def _schedule_node(
        self, run_id: ArtifactId, fallback_time: datetime
    ) -> CanonicalDagNode:
        try:
            schedule = self._journal.get_schedule(run_id)
            return CanonicalDagNode.create(
                node_type=CanonicalDagNodeType.SCHEDULE,
                owner="CONTINUOUS_RESEARCH",
                artifact_id=str(schedule.schedule_id),
                content_hash=schedule.schedule_hash,
                status=(
                    CanonicalDagNodeStatus.AVAILABLE
                    if schedule.status.value in {"ACTIVE", "CLOSED"}
                    else CanonicalDagNodeStatus.BLOCKED
                ),
                observed_at=schedule.created_at,
                details={
                    "schedule_status": schedule.status.value,
                    "next_tick_at": _canonical_optional(schedule.next_tick_at),
                },
            )
        except KeyError:
            return CanonicalDagNode.create(
                node_type=CanonicalDagNodeType.SCHEDULE,
                owner="CONTINUOUS_RESEARCH",
                artifact_id=None,
                content_hash=None,
                status=CanonicalDagNodeStatus.PENDING,
                observed_at=fallback_time,
                reason_codes=("SCHEDULE_NOT_INITIALIZED",),
            )

    def _tick_nodes(
        self,
        *,
        run_id: ArtifactId,
        tick_id: ArtifactId,
        runtime_mode: Any,
        tick_node: CanonicalDagNode,
    ) -> tuple[CanonicalDagNode, ...]:
        nodes: list[CanonicalDagNode] = []
        provider_nodes = self._provider_nodes(run_id, tick_id, tick_node)
        nodes.extend(provider_nodes)
        evidence_nodes = self._evidence_nodes(
            run_id, tick_id, provider_nodes or (tick_node,)
        )
        nodes.extend(evidence_nodes)
        parent = evidence_nodes[-1] if evidence_nodes else tick_node
        child_nodes, child_by_kind = self._child_nodes(
            run_id, tick_id, parent
        )
        nodes.extend(child_nodes)
        try:
            summary = self._decisions.get_research_summary_for_tick(
                run_id=run_id,
                tick_id=tick_id,
                runtime_mode=runtime_mode,
            )
        except KeyError:
            return tuple(nodes)
        state_parent = child_by_kind.get(ContinuousChildKind.STATE_SYSTEM, parent)
        stages = {item.stage: item for item in summary.stages}
        stage_type = {
            StateResearchStage.MARKET_REGIME: CanonicalDagNodeType.STATE,
            StateResearchStage.ETF_ROTATION: CanonicalDagNodeType.STATE,
            StateResearchStage.THEME_ROTATION: CanonicalDagNodeType.STATE,
            StateResearchStage.CAPITAL_STATE: CanonicalDagNodeType.STATE,
            StateResearchStage.DYNAMIC_POOL: CanonicalDagNodeType.POOL,
            StateResearchStage.CANDIDATE: CanonicalDagNodeType.CANDIDATE,
            StateResearchStage.SIGNAL: CanonicalDagNodeType.SIGNAL,
            StateResearchStage.FORECAST: CanonicalDagNodeType.FORECAST,
        }
        stage_nodes: dict[StateResearchStage, CanonicalDagNode] = {}
        previous = state_parent
        for stage in (
            StateResearchStage.MARKET_REGIME,
            StateResearchStage.ETF_ROTATION,
            StateResearchStage.THEME_ROTATION,
            StateResearchStage.CAPITAL_STATE,
            StateResearchStage.DYNAMIC_POOL,
            StateResearchStage.CANDIDATE,
            StateResearchStage.SIGNAL,
            StateResearchStage.FORECAST,
        ):
            evidence = stages[stage]
            output = evidence.output_reference
            node = CanonicalDagNode.create(
                node_type=stage_type[stage],
                owner="STATE_SYSTEM",
                artifact_id=None if output is None else str(output.artifact_id),
                content_hash=None if output is None else output.content_hash,
                status=_stage_status(evidence.status.value),
                observed_at=evidence.stage_completed_at,
                parent_node_ids=(previous.node_id,),
                reason_codes=evidence.reason_codes,
                details={
                    "tick_id": str(tick_id),
                    "stage": stage.value,
                    "result": evidence.result.value,
                    "evidence_available_at": canonical_datetime(
                        evidence.evidence_available_at
                    ),
                    "missing_evidence": list(evidence.missing_evidence),
                    "data_eligibility": evidence.data_eligibility.value,
                    "evidence_ceiling": evidence.evidence_ceiling.value,
                },
            )
            nodes.append(node)
            stage_nodes[stage] = node
            previous = node
        for receipt in summary.model_selection_receipts:
            nodes.append(
                CanonicalDagNode.create(
                    node_type=CanonicalDagNodeType.GOVERNANCE,
                    owner="MODEL_GOVERNANCE",
                    artifact_id=str(receipt.artifact_id),
                    content_hash=receipt.content_hash,
                    status=CanonicalDagNodeStatus.AVAILABLE,
                    observed_at=summary.created_at,
                    parent_node_ids=(state_parent.node_id,),
                    details={"tick_id": str(tick_id)},
                )
            )
        if any("minute" in item.product.lower() for item in summary.provider_contracts):
            minute_parent = stage_nodes.get(
                StateResearchStage.CANDIDATE, state_parent
            )
            nodes.append(
                CanonicalDagNode.create(
                    node_type=CanonicalDagNodeType.MINUTE,
                    owner="CONTROLLED_OPERATION",
                    artifact_id=None,
                    content_hash=None,
                    status=CanonicalDagNodeStatus.AVAILABLE,
                    observed_at=stages[StateResearchStage.SIGNAL].evidence_available_at,
                    parent_node_ids=(minute_parent.node_id,),
                    details={
                        "tick_id": str(tick_id),
                        "contracts": [
                            item.to_canonical_dict()
                            for item in summary.provider_contracts
                            if "minute" in item.product.lower()
                        ],
                        "source_references": [
                            item.to_canonical_dict()
                            for item in summary.provider_source_references
                        ],
                    },
                )
            )
        summary_parent = stage_nodes.get(StateResearchStage.FORECAST, previous)
        nodes.append(
            CanonicalDagNode.create(
                node_type=CanonicalDagNodeType.SUMMARY,
                owner="DECISION_SYSTEM",
                artifact_id=str(summary.summary_id),
                content_hash=summary.content_hash,
                status=CanonicalDagNodeStatus.AVAILABLE,
                observed_at=summary.created_at,
                parent_node_ids=(summary_parent.node_id,),
                reason_codes=summary.reason_codes,
                details={
                    "tick_id": str(tick_id),
                    "runtime_mode": summary.runtime_mode.value,
                    "outcome": summary.outcome.value,
                    "revision": summary.revision,
                    "evidence_ceiling": summary.evidence_ceiling.value,
                    "data_eligibility": summary.data_eligibility.value,
                },
            )
        )
        return tuple(nodes)

    def _provider_nodes(
        self,
        run_id: ArtifactId,
        tick_id: ArtifactId,
        tick_node: CanonicalDagNode,
    ) -> tuple[CanonicalDagNode, ...]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT attempt_id, attempt_number, provider_id, product,
                       started_at, completed_at, status, source_manifest_id,
                       source_manifest_hash, error_code, reason_codes_json,
                       retry_at, fencing_token, lease_expires_at
                FROM continuous_provider_attempt
                WHERE run_id = %s AND tick_id = %s
                ORDER BY attempt_number
                """,
                (str(run_id), str(tick_id)),
            ).fetchall()
        import json

        return tuple(
            CanonicalDagNode.create(
                node_type=CanonicalDagNodeType.PROVIDER,
                owner="CONTINUOUS_RESEARCH",
                artifact_id=None if row[7] is None else str(row[7]),
                content_hash=None if row[8] is None else str(row[8]),
                status=_provider_status(str(row[6])),
                observed_at=row[5] or row[4],
                parent_node_ids=(tick_node.node_id,),
                reason_codes=tuple(str(item) for item in json.loads(str(row[10]))),
                details={
                    "tick_id": str(tick_id),
                    "attempt_id": int(row[0]),
                    "attempt_number": int(row[1]),
                    "provider": str(row[2]),
                    "product": str(row[3]),
                    "started_at": canonical_datetime(row[4]),
                    "completed_at": _canonical_optional(row[5]),
                    "error_code": row[9],
                    "retry_at": _canonical_optional(row[11]),
                    "fencing_token": int(row[12]),
                    "lease_expires_at": canonical_datetime(row[13]),
                },
            )
            for row in rows
        )

    def _evidence_nodes(
        self,
        run_id: ArtifactId,
        tick_id: ArtifactId,
        parents: tuple[CanonicalDagNode, ...],
    ) -> tuple[CanonicalDagNode, ...]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT evidence_commit_id, commit_hash, available_at,
                       quality_status, evidence_qualification, evidence_scope,
                       created_at
                FROM continuous_evidence_commit
                WHERE run_id = %s AND tick_id = %s
                ORDER BY created_at, evidence_commit_id
                """,
                (str(run_id), str(tick_id)),
            ).fetchall()
        parent_ids = tuple(item.node_id for item in parents)
        return tuple(
            CanonicalDagNode.create(
                node_type=CanonicalDagNodeType.EVIDENCE,
                owner="CONTINUOUS_RESEARCH",
                artifact_id=str(row[0]),
                content_hash=str(row[1]),
                status=(
                    CanonicalDagNodeStatus.AVAILABLE
                    if str(row[3]) == "VALIDATED"
                    else CanonicalDagNodeStatus.PARTIAL
                ),
                observed_at=row[6],
                parent_node_ids=parent_ids,
                reason_codes=(
                    ()
                    if str(row[3]) == "VALIDATED"
                    else (f"QUALITY_{row[3]}",)
                ),
                details={
                    "tick_id": str(tick_id),
                    "evidence_scope": str(row[5]),
                    "available_at": canonical_datetime(row[2]),
                    "quality_status": str(row[3]),
                    "evidence_qualification": str(row[4]),
                },
            )
            for row in rows
        )

    def _child_nodes(
        self,
        run_id: ArtifactId,
        tick_id: ArtifactId,
        parent: CanonicalDagNode,
    ) -> tuple[
        tuple[CanonicalDagNode, ...],
        dict[ContinuousChildKind, CanonicalDagNode],
    ]:
        kind_type = {
            ContinuousChildKind.DAILY_DATASET: CanonicalDagNodeType.DATASET,
            ContinuousChildKind.FEATURE_MATERIALIZATION: CanonicalDagNodeType.FEATURE,
            ContinuousChildKind.STATE_SYSTEM: CanonicalDagNodeType.STATE,
        }
        nodes: list[CanonicalDagNode] = []
        by_kind: dict[ContinuousChildKind, CanonicalDagNode] = {}
        previous = parent
        for child in self._journal.get_child_references(run_id, tick_id):
            if child.child_kind not in kind_type:
                continue
            node = CanonicalDagNode.create(
                node_type=kind_type[child.child_kind],
                owner=child.child_kind.value,
                artifact_id=str(
                    child.child_artifact_id or child.child_receipt_id
                ),
                content_hash=(
                    child.child_artifact_hash or child.child_receipt_hash
                ),
                status=(
                    CanonicalDagNodeStatus.REUSED
                    if child.reference_disposition
                    is ChildReferenceDisposition.REUSED
                    else CanonicalDagNodeStatus.AVAILABLE
                ),
                observed_at=child.created_at,
                parent_node_ids=(previous.node_id,),
                details={
                    "tick_id": str(tick_id),
                    "child_run_id": str(child.child_run_id),
                    "receipt_id": str(child.child_receipt_id),
                    "receipt_hash": child.child_receipt_hash,
                    "reference_disposition": child.reference_disposition.value,
                    "source_manifest_id": str(child.source_manifest_id),
                },
            )
            nodes.append(node)
            by_kind[child.child_kind] = node
            previous = node
        return tuple(nodes), by_kind


def _inspection_projection(
    inspection: CanonicalRuntimeInspection,
    nodes: tuple[CanonicalDagNode, ...],
    operation: str,
) -> dict[str, Any]:
    return {
        "schema_version": "canonical-runtime-inspect-projection/v1",
        "operation": operation,
        "run_id": str(inspection.run_id),
        "run_status": inspection.run_status,
        "generated_at": canonical_datetime(inspection.generated_at),
        "nodes": [item.to_canonical_dict() for item in nodes],
        "read_only": True,
        "decision_recomputed": False,
    }


def _tick_status(status: str) -> CanonicalDagNodeStatus:
    return {
        "PENDING": CanonicalDagNodeStatus.PENDING,
        "IN_PROGRESS": CanonicalDagNodeStatus.PARTIAL,
        "COMPLETED": CanonicalDagNodeStatus.AVAILABLE,
        "FAILED": CanonicalDagNodeStatus.FAILED,
        "DATA_BLOCKED": CanonicalDagNodeStatus.BLOCKED,
    }[status]


def _provider_status(status: str) -> CanonicalDagNodeStatus:
    return {
        "STARTED": CanonicalDagNodeStatus.PARTIAL,
        "SUCCEEDED": CanonicalDagNodeStatus.AVAILABLE,
        "FAILED": CanonicalDagNodeStatus.FAILED,
        "TIMED_OUT": CanonicalDagNodeStatus.FAILED,
        "INVALID_RESPONSE": CanonicalDagNodeStatus.FAILED,
        "RATE_LIMITED": CanonicalDagNodeStatus.FAILED,
        "CIRCUIT_OPEN": CanonicalDagNodeStatus.BLOCKED,
        "LEASE_EXPIRED": CanonicalDagNodeStatus.FAILED,
    }[status]


def _stage_status(status: str) -> CanonicalDagNodeStatus:
    return {
        "COMPLETED": CanonicalDagNodeStatus.AVAILABLE,
        "DATA_INSUFFICIENT": CanonicalDagNodeStatus.PARTIAL,
        "MODEL_NOT_QUALIFIED_FOR_MODE": CanonicalDagNodeStatus.BLOCKED,
    }[status]


def _canonical_optional(value: datetime | None) -> str | None:
    return None if value is None else canonical_datetime(value)


__all__ = [
    "CanonicalDagNode",
    "CanonicalDagNodeStatus",
    "CanonicalDagNodeType",
    "CanonicalRuntimeInspection",
    "PostgresCanonicalRuntimeQuery",
]
