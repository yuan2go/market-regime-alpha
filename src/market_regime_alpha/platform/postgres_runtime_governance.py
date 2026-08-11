"""PostgreSQL authority for model qualification and Runtime selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.data.pit_authority import (
    FormalPITEvidenceArtifact,
    PITValidationOutcome,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.native_repository import (
    PostgresConnection,
    acquire_scope_lock,
)
from market_regime_alpha.platform.postgres_governance import (
    PostgresModelRegistryRepository,
)
from market_regime_alpha.platform.governance_serialization import (
    model_registration_from_dict,
    model_registration_to_dict,
    model_transition_from_dict,
)
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    ModelLifecycleStatus,
)
from market_regime_alpha.platform.model_registry import (
    ModelRegistration,
    ModelRegistry,
)
from market_regime_alpha.platform.repositories import VersionConflictError
from market_regime_alpha.platform.runtime_governance import (
    AssignmentLane,
    AssignmentStatus,
    ModelGovernancePolicy,
    ModelQualificationDecision,
    ModelQualificationEvidence,
    ModelRuntimeAssignment,
    ModelSelectionReceipt,
    ModelSelectionRequest,
    ModelVersionLineage,
    QualificationEvidenceKind,
    QualificationEvidenceOutcome,
    QualificationStatus,
    RuntimeModelLineage,
    RuntimePurpose,
    evaluate_qualification,
)


class ModelGovernanceIntegrityError(RuntimeError):
    """Stored governance evidence cannot be reconstructed unambiguously."""


@dataclass(frozen=True, slots=True)
class FormalResearchModelLineageResolution:
    """Freeze-time Model Governance answer for one exact research lineage."""

    resolution_id: ArtifactId
    resolution_hash: str
    lineage: ModelVersionLineage
    registration: ModelRegistration
    registry_version: int
    registry_governance_revision: int
    registry_action_type: str
    registry_action_hash: str
    lineage_governance_revision: int
    lineage_action_hash: str
    owner_recorded_at: datetime
    schema_version: str = "formal-research-model-lineage-resolution/v1"

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "lineage": self.lineage.to_canonical_dict(),
            "registration": model_registration_to_dict(self.registration),
            "registry_version": self.registry_version,
            "registry_governance_revision": self.registry_governance_revision,
            "registry_action_type": self.registry_action_type,
            "registry_action_hash": self.registry_action_hash,
            "lineage_governance_revision": self.lineage_governance_revision,
            "lineage_action_hash": self.lineage_action_hash,
            "owner_recorded_at": self.owner_recorded_at.isoformat(),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "resolution_id": str(self.resolution_id),
            "resolution_hash": self.resolution_hash,
            **self.identity_payload(),
        }


def resolve_formal_research_model_lineage(
    connection: Any,
    *,
    lineage_id: ArtifactId,
    lineage_hash: str,
) -> FormalResearchModelLineageResolution:
    """Return the Model Governance-owned current research eligibility receipt."""

    row = connection.execute(
        """
        SELECT lineage.lineage_hash, lineage.payload_json, lineage.created_at,
               lineage.governance_revision, registration.registration_json,
               registration.definition_hash, registration.lifecycle_status,
               registration.evidence_level, registration.version
        FROM model_version_lineage AS lineage
        JOIN model_registrations AS registration
          ON registration.model_id = lineage.model_id
        WHERE lineage.lineage_id = %s
        """,
        (str(lineage_id),),
    ).fetchone()
    if row is None or not isinstance(row[1], Mapping):
        raise ModelGovernanceIntegrityError("Model Version Lineage owner is missing")
    try:
        lineage = ModelVersionLineage.from_canonical_dict(dict(row[1]))
        registration, registry_action = _replay_formal_model_registration(
            connection,
            registration_payload_json=str(row[4]),
            stored_definition_hash=str(row[5]),
            stored_lifecycle_status=str(row[6]),
            stored_evidence_level=str(row[7]),
            stored_version=int(row[8]),
        )
        lineage.validate_definition(registration.definition)
        lifecycle_status = ModelLifecycleStatus(str(row[6]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelGovernanceIntegrityError(
            "Model Version Lineage governance replay failed"
        ) from exc
    if (
        lineage.lineage_id != lineage_id
        or lineage.lineage_hash != lineage_hash
        or str(row[0]) != lineage_hash
        or str(row[5]) != lineage.definition_hash
        or registration.lifecycle_status is not lifecycle_status
        or registration.evidence_level.value != str(row[7])
        or int(row[8]) != len(registration.transitions)
    ):
        raise ModelGovernanceIntegrityError(
            "Model Version Lineage governance binding mismatch"
        )
    if lifecycle_status in {
        ModelLifecycleStatus.SUSPENDED,
        ModelLifecycleStatus.RETIRED,
    }:
        raise ModelGovernanceIntegrityError(
            f"Model Version Lineage lifecycle is terminal: {lifecycle_status.value}"
        )
    lineage_action = connection.execute(
        """
        SELECT governance_revision, action_type, aggregate_id, action_hash,
               actor, reason, payload_json, created_at
        FROM model_governance_action
        WHERE governance_revision = %s
        """,
        (int(row[3]),),
    ).fetchone()
    expected_lineage_action = {
        "lineage": lineage.to_canonical_dict(),
        "actor": None if lineage_action is None else str(lineage_action[4]),
        "reason": None if lineage_action is None else str(lineage_action[5]),
        "created_at": lineage.created_at.isoformat(),
    }
    if (
        lineage_action is None
        or int(lineage_action[0]) != int(row[3])
        or str(lineage_action[1]) != "MODEL_VERSION_LINEAGE"
        or str(lineage_action[2]) != str(lineage.lineage_id)
        or not isinstance(lineage_action[6], Mapping)
        or dict(lineage_action[6]) != expected_lineage_action
        or str(lineage_action[3]) != canonical_hash(expected_lineage_action)
        or lineage_action[7] != lineage.created_at
        or row[2] != lineage.created_at
    ):
        raise ModelGovernanceIntegrityError(
            "Model Version Lineage action replay mismatch"
        )
    owner_recorded_at = max(row[2], lineage_action[7], registry_action[3]).replace(
        microsecond=0
    )
    values = {
        "lineage": lineage,
        "registration": registration,
        "registry_version": int(row[8]),
        "registry_governance_revision": int(registry_action[0]),
        "registry_action_type": str(registry_action[1]),
        "registry_action_hash": str(registry_action[2]),
        "lineage_governance_revision": int(row[3]),
        "lineage_action_hash": str(lineage_action[3]),
        "owner_recorded_at": owner_recorded_at,
    }
    identity_payload = {
        "schema_version": "formal-research-model-lineage-resolution/v1",
        "lineage": lineage.to_canonical_dict(),
        "registration": model_registration_to_dict(registration),
        **{
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in values.items()
            if key not in {"lineage", "registration"}
        },
    }
    digest = canonical_hash(identity_payload)
    return FormalResearchModelLineageResolution(
        resolution_id=ArtifactId(
            f"formal-research-model-lineage-resolution:{digest[7:]}"
        ),
        resolution_hash=digest,
        **values,
    )


def _replay_formal_model_registration(
    connection: Any,
    *,
    registration_payload_json: str,
    stored_definition_hash: str,
    stored_lifecycle_status: str,
    stored_evidence_level: str,
    stored_version: int,
) -> tuple[ModelRegistration, tuple[Any, ...]]:
    """Rebuild current Registry state from its append-only transition owner."""

    try:
        projected_payload = json.loads(registration_payload_json)
        if not isinstance(projected_payload, Mapping):
            raise ValueError("Model Registration payload must be an object")
        projected = model_registration_from_dict(projected_payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelGovernanceIntegrityError(
            "Model Registration projection replay failed"
        ) from exc
    model_id = projected.definition.model_id
    initial = ModelRegistration(
        definition=projected.definition,
        lifecycle_status=ModelLifecycleStatus.DRAFT,
        evidence_level=EvidenceLevel.UNQUALIFIED,
        transitions=(),
    )
    initial_payload = model_registration_to_dict(initial)
    register_rows = connection.execute(
        """
        SELECT action.governance_revision, action.action_type,
               action.action_hash, action.created_at, action.aggregate_id,
               action.payload_json, command.aggregate_type,
               command.aggregate_id, command.payload_hash,
               command.result_version
        FROM model_governance_action AS action
        JOIN governance_commands AS command
          ON command.idempotency_key = action.idempotency_key
        WHERE action.aggregate_id = %s
          AND action.action_type = 'MODEL_REGISTER'
          AND command.result_version = 0
        ORDER BY action.governance_revision
        """,
        (str(model_id),),
    ).fetchall()
    register_action = next(
        (
            item
            for item in register_rows
            if str(item[2]) == canonical_hash(initial_payload)
            and str(item[4]) == str(model_id)
            and isinstance(item[5], Mapping)
            and dict(item[5]) == initial_payload
            and str(item[6]) == "MODEL"
            and str(item[7]) == str(model_id)
            and str(item[8]) == str(item[2])
            and int(item[9]) == 0
        ),
        None,
    )
    if register_action is None:
        raise ModelGovernanceIntegrityError(
            "Model Registration create action replay mismatch"
        )
    transition_rows = connection.execute(
        """
        SELECT transition.sequence, transition.transition_json,
               action.governance_revision, action.action_type,
               action.action_hash, action.created_at, action.aggregate_id,
               action.actor, action.reason, action.payload_json,
               command.aggregate_type, command.aggregate_id,
               command.payload_hash, command.result_version
        FROM model_lifecycle_transitions AS transition
        JOIN model_governance_action AS action
          ON action.idempotency_key = transition.idempotency_key
        JOIN governance_commands AS command
          ON command.idempotency_key = transition.idempotency_key
        WHERE transition.model_id = %s
        ORDER BY transition.sequence
        """,
        (str(model_id),),
    ).fetchall()
    if [int(item[0]) for item in transition_rows] != list(
        range(1, stored_version + 1)
    ):
        raise ModelGovernanceIntegrityError(
            "Model Registration transition sequence is incomplete"
        )
    transitions = []
    current_action = register_action
    for item in transition_rows:
        try:
            transition_payload = json.loads(str(item[1]))
            if not isinstance(transition_payload, Mapping):
                raise ValueError("transition payload must be an object")
            transition = model_transition_from_dict(transition_payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelGovernanceIntegrityError(
                "Model Registration transition replay failed"
            ) from exc
        sequence = int(item[0])
        command_base = {
            "operation": "MODEL_TRANSITION",
            "model_id": str(model_id),
            "expected_version": sequence - 1,
            "to_status": transition.to_status.value,
            "changed_at": transition.changed_at.isoformat(),
            "reason": transition.reason,
            "evidence_refs": list(transition.evidence_refs),
            "approval_ref": transition.approval_ref,
        }
        command_hashes = {
            canonical_hash({**command_base, "evidence_level": None}),
            canonical_hash(
                {
                    **command_base,
                    "evidence_level": transition.evidence_level.value,
                }
            ),
        }
        if (
            transition.model_id != model_id
            or str(item[3]) != "MODEL_LIFECYCLE_TRANSITION"
            or str(item[4]) not in command_hashes
            or item[5] != transition.changed_at
            or str(item[6]) != str(model_id)
            or str(item[7])
            != (transition.approval_ref or "MODEL_REGISTRY_APPLICATION_SERVICE")
            or str(item[8]) != transition.reason
            or not isinstance(item[9], Mapping)
            or dict(item[9]) != dict(transition_payload)
            or str(item[10]) != "MODEL"
            or str(item[11]) != str(model_id)
            or str(item[12]) != str(item[4])
            or int(item[13]) != sequence
        ):
            raise ModelGovernanceIntegrityError(
                "Model Registration transition action replay mismatch"
            )
        transitions.append(transition)
        current_action = (item[2], item[3], item[4], item[5])
    registration = ModelRegistration(
        definition=projected.definition,
        lifecycle_status=(
            ModelLifecycleStatus.DRAFT
            if not transitions
            else transitions[-1].to_status
        ),
        evidence_level=(
            EvidenceLevel.UNQUALIFIED
            if not transitions
            else transitions[-1].evidence_level
        ),
        transitions=tuple(transitions),
    )
    try:
        ModelRegistry().restore(registration)
    except ValueError as exc:
        raise ModelGovernanceIntegrityError(
            "Model Registration transition history is invalid"
        ) from exc
    if (
        registration != projected
        or registration.definition.definition_hash != stored_definition_hash
        or registration.lifecycle_status.value != stored_lifecycle_status
        or registration.evidence_level.value != stored_evidence_level
        or len(registration.transitions) != stored_version
    ):
        raise ModelGovernanceIntegrityError(
            "Model Registration projection diverges from append-only history"
        )
    return registration, current_action


class ModelSelectionRejected(RuntimeError):
    """Raised by the strict Runtime seam after a rejection receipt is stored."""

    def __init__(self, receipt: ModelSelectionReceipt) -> None:
        self.receipt = receipt
        super().__init__(",".join(receipt.reason_codes))


class PostgresModelGovernanceRepository(PostgresModelRegistryRepository):
    """One PostgreSQL boundary spanning Registry, qualification and selection."""

    def current_revision(self) -> int:
        with self._connect() as connection:
            return _current_revision(connection)

    def list_models(self) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT model_id, version FROM model_registrations ORDER BY model_id"
            ).fetchall()
            result = []
            for row in rows:
                versioned = self._load_at(
                    connection,
                    ModelId(str(row["model_id"])),
                    int(row["version"]),
                )
                result.append(
                    {
                        "model_id": str(versioned.registration.definition.model_id),
                        "model_version": versioned.registration.definition.version,
                        "definition_hash": versioned.registration.definition.definition_hash,
                        "lifecycle_status": versioned.registration.lifecycle_status.value,
                        "evidence_level": versioned.registration.evidence_level.value,
                        "registry_version": versioned.version,
                    }
                )
            return tuple(result)

    def inspect_model(self, model_id: ModelId) -> dict[str, Any]:
        with self._connect() as connection:
            versioned = self._load_at(
                connection,
                model_id,
                _current_model_version(connection, model_id),
            )
            lineage_rows = connection.execute(
                "SELECT payload_json FROM model_version_lineage "
                "WHERE model_id = %s ORDER BY governance_revision",
                (str(model_id),),
            ).fetchall()
            qualification_rows = connection.execute(
                "SELECT payload_json, registry_version "
                "FROM model_qualification_decision WHERE model_id = %s "
                "ORDER BY governance_revision",
                (str(model_id),),
            ).fetchall()
            evidence_rows = connection.execute(
                "SELECT payload_json FROM model_qualification_evidence "
                "WHERE model_id = %s ORDER BY governance_revision",
                (str(model_id),),
            ).fetchall()
            policy_rows = connection.execute(
                "SELECT DISTINCT policy.payload_json "
                "FROM model_governance_policy AS policy "
                "LEFT JOIN model_qualification_decision AS qualification "
                "ON qualification.policy_id = policy.policy_id "
                "LEFT JOIN model_runtime_assignment AS assignment "
                "ON assignment.policy_id = policy.policy_id "
                "WHERE qualification.model_id = %s OR assignment.model_id = %s "
                "ORDER BY policy.payload_json",
                (str(model_id), str(model_id)),
            ).fetchall()
            assignment_rows = connection.execute(
                "SELECT payload_json FROM model_runtime_assignment "
                "WHERE model_id = %s ORDER BY governance_revision",
                (str(model_id),),
            ).fetchall()
            action_rows = connection.execute(
                "SELECT governance_revision, action_type, action_hash, actor, "
                "reason, created_at FROM model_governance_action "
                "WHERE aggregate_id = %s ORDER BY governance_revision",
                (str(model_id),),
            ).fetchall()
            return {
                "governance_revision": _current_revision(connection),
                "registration": model_registration_to_dict(
                    versioned.registration
                ),
                "registry_version": versioned.version,
                "version_lineages": [
                    dict(_object(row["payload_json"])) for row in lineage_rows
                ],
                "qualification_decisions": [
                    {
                        **dict(_object(row["payload_json"])),
                        "registry_version": int(row["registry_version"]),
                    }
                    for row in qualification_rows
                ],
                "qualification_evidence": [
                    dict(_object(row["payload_json"]))
                    for row in evidence_rows
                ],
                "governance_policies": [
                    dict(_object(row["payload_json"])) for row in policy_rows
                ],
                "assignment_events": [
                    dict(_object(row["payload_json"])) for row in assignment_rows
                ],
                "governance_actions": [
                    {
                        "governance_revision": int(row["governance_revision"]),
                        "action_type": str(row["action_type"]),
                        "action_hash": str(row["action_hash"]),
                        "actor": str(row["actor"]),
                        "reason": str(row["reason"]),
                        "created_at": row["created_at"].isoformat(),
                    }
                    for row in action_rows
                ],
            }

    def inspect_policy(self, policy_id: ArtifactId) -> dict[str, Any]:
        with self._connect() as connection:
            policy = _load_policy(connection, policy_id)
            decisions = connection.execute(
                "SELECT payload_json, registry_version "
                "FROM model_qualification_decision WHERE policy_id = %s "
                "ORDER BY governance_revision",
                (str(policy_id),),
            ).fetchall()
            assignments = connection.execute(
                "SELECT payload_json FROM model_runtime_assignment "
                "WHERE policy_id = %s ORDER BY governance_revision",
                (str(policy_id),),
            ).fetchall()
            return {
                "governance_revision": _current_revision(connection),
                "policy": policy.to_canonical_dict(),
                "qualification_decisions": [
                    {
                        **dict(_object(row["payload_json"])),
                        "registry_version": int(row["registry_version"]),
                    }
                    for row in decisions
                ],
                "assignment_events": [
                    dict(_object(row["payload_json"]))
                    for row in assignments
                ],
            }

    def inspect_evidence(self, evidence_id: ArtifactId) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT governance_revision, payload_json "
                "FROM model_qualification_evidence WHERE evidence_id = %s",
                (str(evidence_id),),
            ).fetchone()
            if row is None:
                raise KeyError(str(evidence_id))
            return {
                "governance_revision": int(row["governance_revision"]),
                "evidence": dict(_object(row["payload_json"])),
            }

    def record_version_lineage(
        self,
        lineage: ModelVersionLineage,
        *,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> ModelVersionLineage:
        payload = lineage.to_canonical_dict()
        action_payload = {
            "lineage": payload,
            "actor": actor,
            "reason": reason,
            "created_at": lineage.created_at.isoformat(),
        }
        with self._connect() as connection:
            acquire_scope_lock(
                connection, namespace="model-registry", identity=lineage.model_id
            )
            _acquire_governance_revision_lock(connection)
            try:
                existing_lineage = connection.execute(
                    "SELECT governance_revision, payload_json "
                    "FROM model_version_lineage WHERE lineage_id = %s",
                    (str(lineage.lineage_id),),
                ).fetchone()
                if existing_lineage is not None:
                    existing_action = _find_action(connection, idempotency_key)
                    if existing_action is None:
                        raise ValueError(
                            "Model Version Lineage semantic duplicate requires "
                            "the original idempotency key"
                        )
                    _validate_action(
                        existing_action,
                        "MODEL_VERSION_LINEAGE",
                        action_payload,
                    )
                    if int(existing_action["governance_revision"]) != int(
                        existing_lineage["governance_revision"]
                    ):
                        raise ModelGovernanceIntegrityError(
                            "Model Version Lineage action/event revision mismatch"
                        )
                    restored = ModelVersionLineage.from_canonical_dict(
                        _object(existing_lineage["payload_json"])
                    )
                    if restored != lineage:
                        raise ValueError(
                            "Model Version Lineage identity conflict"
                        )
                    connection.commit()
                    return restored
                registration = self._load_at(
                    connection,
                    lineage.model_id,
                    _current_model_version(connection, lineage.model_id),
                )
                lineage.validate_definition(registration.registration.definition)
                revision, duplicate = _record_action(
                    connection,
                    action_type="MODEL_VERSION_LINEAGE",
                    aggregate_id=str(lineage.lineage_id),
                    action_payload=action_payload,
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    created_at=lineage.created_at,
                )
                if not duplicate:
                    connection.execute(
                        """
                        INSERT INTO model_version_lineage(
                            lineage_id, lineage_hash, model_id, definition_hash,
                            governance_revision, payload_json, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (lineage_id) DO NOTHING
                        """,
                        (
                            str(lineage.lineage_id),
                            lineage.lineage_hash,
                            str(lineage.model_id),
                            lineage.definition_hash,
                            revision,
                            _json(payload),
                            lineage.created_at,
                        ),
                    )
                restored = _load_lineage(connection, lineage.lineage_id)
                if restored != lineage:
                    raise ValueError("Model Version Lineage identity conflict")
                connection.commit()
                return restored
            except Exception:
                connection.rollback()
                raise

    def record_evidence(
        self,
        evidence: ModelQualificationEvidence,
        *,
        idempotency_key: str,
    ) -> ModelQualificationEvidence:
        payload = evidence.to_canonical_dict()
        with self._connect() as connection:
            acquire_scope_lock(
                connection, namespace="model-registry", identity=evidence.model_id
            )
            _acquire_governance_revision_lock(connection)
            try:
                lineage = _load_lineage(connection, evidence.lineage_id)
                if (
                    lineage.model_id != evidence.model_id
                    or lineage.definition_hash != evidence.definition_hash
                    or lineage.lineage_hash != evidence.lineage_hash
                ):
                    raise ValueError("Qualification Evidence lineage mismatch")
                if (
                    evidence.validation_protocol_ref
                    not in lineage.validation_protocol_refs
                ):
                    raise ValueError(
                        "Qualification Evidence validation protocol mismatch"
                    )
                if evidence.evidence_kind is QualificationEvidenceKind.FORMAL_PIT:
                    _verify_formal_pit_evidence(connection, evidence)
                revision, duplicate = _record_action(
                    connection,
                    action_type="QUALIFICATION_EVIDENCE",
                    aggregate_id=str(evidence.evidence_id),
                    action_payload=payload,
                    actor=evidence.actor,
                    reason=evidence.reason,
                    idempotency_key=idempotency_key,
                    created_at=evidence.recorded_at,
                )
                if not duplicate:
                    connection.execute(
                        """
                        INSERT INTO model_qualification_evidence(
                            evidence_id, evidence_hash, model_id, lineage_id,
                            evidence_kind, outcome, governance_revision,
                            payload_json, available_at, recorded_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(evidence.evidence_id),
                            evidence.evidence_hash,
                            str(evidence.model_id),
                            str(evidence.lineage_id),
                            evidence.evidence_kind.value,
                            evidence.outcome.value,
                            revision,
                            _json(payload),
                            evidence.available_at,
                            evidence.recorded_at,
                        ),
                    )
                restored = _load_evidence(connection, evidence.evidence_id)
                if restored != evidence:
                    raise ValueError("Qualification Evidence identity conflict")
                connection.commit()
                return restored
            except Exception:
                connection.rollback()
                raise

    def record_policy(
        self,
        policy: ModelGovernancePolicy,
        *,
        actor: str,
        reason: str,
        created_at: datetime,
        idempotency_key: str,
    ) -> ModelGovernancePolicy:
        payload = policy.to_canonical_dict()
        action_payload = {
            "policy": payload,
            "actor": actor,
            "reason": reason,
            "created_at": created_at.isoformat(),
        }
        with self._connect() as connection:
            acquire_scope_lock(
                connection, namespace="model-governance-policy", identity=policy.policy_id
            )
            _acquire_governance_revision_lock(connection)
            try:
                revision, duplicate = _record_action(
                    connection,
                    action_type="GOVERNANCE_POLICY",
                    aggregate_id=str(policy.policy_id),
                    action_payload=action_payload,
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    created_at=created_at,
                )
                if not duplicate:
                    connection.execute(
                        """
                        INSERT INTO model_governance_policy(
                            policy_id, policy_hash, purpose,
                            production_authorization, governance_revision,
                            payload_json, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(policy.policy_id),
                            policy.policy_hash,
                            policy.purpose.value,
                            policy.production_authorization,
                            revision,
                            _json(payload),
                            created_at,
                        ),
                    )
                restored = _load_policy(connection, policy.policy_id)
                if restored != policy:
                    raise ValueError("Model Governance Policy identity conflict")
                connection.commit()
                return restored
            except Exception:
                connection.rollback()
                raise

    def qualify(
        self,
        *,
        model_id: ModelId,
        policy_id: ArtifactId,
        actor: str,
        reason: str,
        approval_ref: str | None,
        decided_at: datetime,
        expected_registry_version: int,
        idempotency_key: str,
    ) -> ModelQualificationDecision:
        command = {
            "model_id": str(model_id),
            "policy_id": str(policy_id),
            "actor": actor,
            "reason": reason,
            "approval_ref": approval_ref,
            "decided_at": decided_at.isoformat(),
            "expected_registry_version": expected_registry_version,
        }
        with self._connect() as connection:
            acquire_scope_lock(
                connection, namespace="model-registry", identity=model_id
            )
            _acquire_governance_revision_lock(connection)
            try:
                existing = _find_action(connection, idempotency_key)
                if existing is not None:
                    _validate_action(existing, "QUALIFICATION_DECISION", command)
                    decision = _load_qualification_by_revision(
                        connection, int(existing["governance_revision"])
                    )[0]
                    connection.commit()
                    return decision
                current_version = _current_model_version(connection, model_id)
                if current_version != expected_registry_version:
                    raise VersionConflictError(
                        f"model {model_id} expected version "
                        f"{expected_registry_version}, found {current_version}"
                    )
                registration = self._load_at(
                    connection, model_id, current_version
                ).registration
                lineage = _load_lineage_for_model(connection, model_id)
                policy = _load_policy(connection, policy_id)
                if lineage.created_at > decided_at or (
                    _policy_created_at(connection, policy_id) > decided_at
                ):
                    raise ValueError(
                        "qualification cannot precede Lineage or Policy authority"
                    )
                revision, _ = _record_action(
                    connection,
                    action_type="QUALIFICATION_DECISION",
                    aggregate_id=str(model_id),
                    action_payload=command,
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    created_at=decided_at,
                )
                evidence = _latest_evidence(
                    connection, lineage.lineage_id, revision
                )
                decision = evaluate_qualification(
                    registration=registration,
                    lineage=lineage,
                    policy=policy,
                    evidence=evidence,
                    decided_at=decided_at,
                    actor=actor,
                    reason=reason,
                    approval_ref=approval_ref,
                    governance_revision=revision,
                    authority_rejection_codes=(
                        (
                            "PRODUCTION_EVIDENCE_OWNER_RESOLUTION_NOT_IMPLEMENTED",
                        )
                        if policy.purpose is RuntimePurpose.PRODUCTION_DECISION
                        else ()
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO model_qualification_decision(
                        decision_id, decision_hash, model_id, lineage_id,
                        policy_id, purpose, qualification_status,
                        production_authorized, registry_version,
                        governance_revision, payload_json, decided_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(decision.decision_id),
                        decision.decision_hash,
                        str(decision.model_id),
                        str(decision.lineage_id),
                        str(decision.policy_id),
                        decision.purpose.value,
                        decision.status.value,
                        decision.production_authorized,
                        current_version,
                        revision,
                        _json(decision.to_canonical_dict()),
                        decision.decided_at,
                    ),
                )
                connection.commit()
                return decision
            except Exception:
                connection.rollback()
                raise

    def assign(
        self,
        *,
        runtime_scope: str,
        model_slot: str,
        purpose: RuntimePurpose,
        lane: AssignmentLane,
        model_id: ModelId,
        policy_id: ArtifactId,
        expected_governance_revision: int,
        effective_at: datetime,
        actor: str,
        reason: str,
        approval_ref: str,
        idempotency_key: str,
    ) -> ModelRuntimeAssignment:
        command = {
            "runtime_scope": runtime_scope,
            "model_slot": model_slot,
            "purpose": purpose.value,
            "lane": lane.value,
            "model_id": str(model_id),
            "policy_id": str(policy_id),
            "expected_governance_revision": expected_governance_revision,
            "effective_at": effective_at.isoformat(),
            "actor": actor,
            "reason": reason,
            "approval_ref": approval_ref,
        }
        scope = f"{runtime_scope}:{model_slot}:{purpose.value}"
        with self._connect() as connection:
            acquire_scope_lock(
                connection, namespace="model-runtime-assignment", identity=scope
            )
            _acquire_governance_revision_lock(connection)
            try:
                existing = _find_action(connection, idempotency_key)
                if existing is not None:
                    _validate_action(existing, "RUNTIME_ASSIGNMENT", command)
                    assignment = _load_assignment_by_revision(
                        connection, int(existing["governance_revision"])
                    )
                    connection.commit()
                    return assignment
                actual_revision = _current_revision(connection)
                if actual_revision != expected_governance_revision:
                    raise VersionConflictError(
                        "governance revision compare-and-swap failed: "
                        f"expected {expected_governance_revision}, found {actual_revision}"
                    )
                policy = _load_policy(connection, policy_id)
                if policy.purpose is not purpose:
                    raise ValueError("assignment Policy purpose mismatch")
                registration = self._load_at(
                    connection,
                    model_id,
                    _current_model_version(connection, model_id),
                )
                if registration.registration.definition.definition_hash != (
                    _load_lineage_for_model(connection, model_id).definition_hash
                ):
                    raise ValueError("assignment Model Registry/lineage mismatch")
                qualification, qualified_registry_version = _latest_qualification(
                    connection,
                    model_id,
                    policy_id,
                    actual_revision,
                    as_of=effective_at,
                )
                if (
                    qualification.status is not QualificationStatus.QUALIFIED
                    or qualified_registry_version != registration.version
                    or (
                        purpose is RuntimePurpose.PRODUCTION_DECISION
                        and not qualification.production_authorized
                    )
                    or not _qualification_evidence_is_current(
                        connection,
                        qualification,
                        _load_lineage_for_model(connection, model_id),
                        actual_revision,
                        as_of=effective_at,
                    )
                ):
                    raise ValueError("assignment requires current qualification")
                active = _current_assignments(
                    connection,
                    runtime_scope=runtime_scope,
                    model_slot=model_slot,
                    purpose=purpose,
                    revision=actual_revision,
                    as_of=datetime.max.replace(tzinfo=UTC),
                )
                if lane is AssignmentLane.CHAMPION and any(
                    item.lane is AssignmentLane.CHAMPION for item in active
                ):
                    raise ValueError("duplicate active Champion authority")
                if any(item.lane is lane and item.model_id == model_id for item in active):
                    raise ValueError("duplicate active Runtime assignment")
                revision, _ = _record_action(
                    connection,
                    action_type="RUNTIME_ASSIGNMENT",
                    aggregate_id=scope,
                    action_payload=command,
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    created_at=effective_at,
                )
                assignment = ModelRuntimeAssignment.create(
                    runtime_scope=runtime_scope,
                    model_slot=model_slot,
                    purpose=purpose,
                    lane=lane,
                    model_id=model_id,
                    definition_hash=registration.registration.definition.definition_hash,
                    policy_id=policy.policy_id,
                    policy_hash=policy.policy_hash,
                    effective_at=effective_at,
                    actor=actor,
                    reason=reason,
                    approval_ref=approval_ref,
                    governance_revision=revision,
                )
                _insert_assignment(connection, assignment)
                connection.commit()
                return assignment
            except Exception:
                connection.rollback()
                raise

    def transition_assignment(
        self,
        assignment_id: ArtifactId,
        *,
        expected_version: int,
        status: AssignmentStatus,
        effective_at: datetime,
        actor: str,
        reason: str,
        approval_ref: str,
        idempotency_key: str,
    ) -> ModelRuntimeAssignment:
        if status is AssignmentStatus.ACTIVE:
            raise ValueError("assignment transition cannot reactivate authority")
        with self._connect() as connection:
            current = _load_assignment(connection, assignment_id)
            scope = (
                f"{current.runtime_scope}:{current.model_slot}:"
                f"{current.purpose.value}"
            )
            acquire_scope_lock(
                connection, namespace="model-runtime-assignment", identity=scope
            )
            _acquire_governance_revision_lock(connection)
            command = {
                "assignment_id": str(assignment_id),
                "expected_version": expected_version,
                "status": status.value,
                "effective_at": effective_at.isoformat(),
                "actor": actor,
                "reason": reason,
                "approval_ref": approval_ref,
            }
            try:
                existing = _find_action(connection, idempotency_key)
                if existing is not None:
                    _validate_action(existing, "RUNTIME_ASSIGNMENT", command)
                    result = _load_assignment_by_revision(
                        connection, int(existing["governance_revision"])
                    )
                    connection.commit()
                    return result
                superseding = connection.execute(
                    "SELECT assignment_id FROM model_runtime_assignment "
                    "WHERE supersedes_assignment_id = %s",
                    (str(assignment_id),),
                ).fetchone()
                if current.version != expected_version or superseding is not None:
                    raise VersionConflictError("assignment compare-and-swap failed")
                revision, _ = _record_action(
                    connection,
                    action_type="RUNTIME_ASSIGNMENT",
                    aggregate_id=scope,
                    action_payload=command,
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    created_at=effective_at,
                )
                result = ModelRuntimeAssignment.create(
                    runtime_scope=current.runtime_scope,
                    model_slot=current.model_slot,
                    purpose=current.purpose,
                    lane=current.lane,
                    status=status,
                    model_id=current.model_id,
                    definition_hash=current.definition_hash,
                    policy_id=current.policy_id,
                    policy_hash=current.policy_hash,
                    effective_at=effective_at,
                    actor=actor,
                    reason=reason,
                    approval_ref=approval_ref,
                    governance_revision=revision,
                    version=current.version + 1,
                    supersedes_assignment_id=current.assignment_id,
                )
                _insert_assignment(connection, result)
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def replace_champion(
        self,
        current_assignment_id: ArtifactId,
        *,
        new_model_id: ModelId,
        policy_id: ArtifactId,
        expected_version: int,
        expected_governance_revision: int,
        effective_at: datetime,
        actor: str,
        reason: str,
        approval_ref: str,
        idempotency_key: str,
    ) -> ModelRuntimeAssignment:
        """Atomically close one Champion and activate its replacement."""

        with self._connect() as connection:
            current = _load_assignment(connection, current_assignment_id)
            scope = (
                f"{current.runtime_scope}:{current.model_slot}:"
                f"{current.purpose.value}"
            )
            acquire_scope_lock(
                connection,
                namespace="model-runtime-assignment",
                identity=scope,
            )
            _acquire_governance_revision_lock(connection)
            command = {
                "current_assignment_id": str(current_assignment_id),
                "new_model_id": str(new_model_id),
                "policy_id": str(policy_id),
                "expected_version": expected_version,
                "expected_governance_revision": expected_governance_revision,
                "effective_at": effective_at.isoformat(),
                "actor": actor,
                "reason": reason,
                "approval_ref": approval_ref,
            }
            try:
                existing = _find_action(connection, idempotency_key)
                if existing is not None:
                    _validate_action(
                        existing,
                        "RUNTIME_CHAMPION_REPLACEMENT",
                        command,
                    )
                    result = _load_assignment_by_revision(
                        connection,
                        int(existing["governance_revision"]),
                    )
                    connection.commit()
                    return result
                actual_revision = _current_revision(connection)
                if actual_revision != expected_governance_revision:
                    raise VersionConflictError(
                        "governance revision compare-and-swap failed: "
                        f"expected {expected_governance_revision}, "
                        f"found {actual_revision}"
                    )
                current = _load_assignment(connection, current_assignment_id)
                superseding = connection.execute(
                    "SELECT assignment_id FROM model_runtime_assignment "
                    "WHERE supersedes_assignment_id = %s",
                    (str(current_assignment_id),),
                ).fetchone()
                if (
                    current.lane is not AssignmentLane.CHAMPION
                    or current.status is not AssignmentStatus.ACTIVE
                    or current.version != expected_version
                    or superseding is not None
                    or current.model_id == new_model_id
                ):
                    raise VersionConflictError(
                        "Champion replacement compare-and-swap failed"
                    )
                policy = _load_policy(connection, policy_id)
                if policy.purpose is not current.purpose:
                    raise ValueError("replacement Policy purpose mismatch")
                registration = self._load_at(
                    connection,
                    new_model_id,
                    _current_model_version(connection, new_model_id),
                )
                lineage = _load_lineage_for_model(connection, new_model_id)
                lineage.validate_definition(registration.registration.definition)
                qualification, qualified_registry_version = _latest_qualification(
                    connection,
                    new_model_id,
                    policy_id,
                    actual_revision,
                    as_of=effective_at,
                )
                if (
                    qualification.status is not QualificationStatus.QUALIFIED
                    or qualified_registry_version != registration.version
                    or not _qualification_evidence_is_current(
                        connection,
                        qualification,
                        lineage,
                        actual_revision,
                        as_of=effective_at,
                    )
                    or (
                        current.purpose is RuntimePurpose.PRODUCTION_DECISION
                        and not qualification.production_authorized
                    )
                ):
                    raise ValueError(
                        "replacement requires current qualified authority"
                    )
                active_assignments = _current_assignments(
                    connection,
                    runtime_scope=current.runtime_scope,
                    model_slot=current.model_slot,
                    purpose=current.purpose,
                    revision=actual_revision,
                    as_of=effective_at,
                )
                promoted_challengers = tuple(
                    item
                    for item in active_assignments
                    if item.lane is AssignmentLane.CHALLENGER
                    and item.model_id == new_model_id
                )
                if len(promoted_challengers) > 1:
                    raise ModelGovernanceIntegrityError(
                        "replacement Challenger authority is ambiguous"
                    )
                if promoted_challengers:
                    challenger = promoted_challengers[0]
                    challenger_payload = {
                        **command,
                        "operation": "CLOSE_PROMOTED_CHALLENGER",
                        "assignment_id": str(challenger.assignment_id),
                    }
                    challenger_revision, _ = _record_action(
                        connection,
                        action_type="RUNTIME_ASSIGNMENT",
                        aggregate_id=scope,
                        action_payload=challenger_payload,
                        actor=actor,
                        reason=reason,
                        idempotency_key=f"{idempotency_key}:close-challenger",
                        created_at=effective_at,
                    )
                    closed_challenger = ModelRuntimeAssignment.create(
                        runtime_scope=challenger.runtime_scope,
                        model_slot=challenger.model_slot,
                        purpose=challenger.purpose,
                        lane=challenger.lane,
                        status=AssignmentStatus.REPLACED,
                        model_id=challenger.model_id,
                        definition_hash=challenger.definition_hash,
                        policy_id=challenger.policy_id,
                        policy_hash=challenger.policy_hash,
                        effective_at=effective_at,
                        actor=actor,
                        reason=reason,
                        approval_ref=approval_ref,
                        governance_revision=challenger_revision,
                        version=challenger.version + 1,
                        supersedes_assignment_id=challenger.assignment_id,
                    )
                    _insert_assignment(connection, closed_challenger)
                close_payload = {
                    **command,
                    "operation": "CLOSE_CURRENT_CHAMPION",
                }
                close_revision, _ = _record_action(
                    connection,
                    action_type="RUNTIME_ASSIGNMENT",
                    aggregate_id=scope,
                    action_payload=close_payload,
                    actor=actor,
                    reason=reason,
                    idempotency_key=f"{idempotency_key}:close",
                    created_at=effective_at,
                )
                closed = ModelRuntimeAssignment.create(
                    runtime_scope=current.runtime_scope,
                    model_slot=current.model_slot,
                    purpose=current.purpose,
                    lane=current.lane,
                    status=AssignmentStatus.REPLACED,
                    model_id=current.model_id,
                    definition_hash=current.definition_hash,
                    policy_id=current.policy_id,
                    policy_hash=current.policy_hash,
                    effective_at=effective_at,
                    actor=actor,
                    reason=reason,
                    approval_ref=approval_ref,
                    governance_revision=close_revision,
                    version=current.version + 1,
                    supersedes_assignment_id=current.assignment_id,
                )
                _insert_assignment(connection, closed)
                replacement_revision, _ = _record_action(
                    connection,
                    action_type="RUNTIME_CHAMPION_REPLACEMENT",
                    aggregate_id=scope,
                    action_payload=command,
                    actor=actor,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    created_at=effective_at,
                )
                replacement = ModelRuntimeAssignment.create(
                    runtime_scope=current.runtime_scope,
                    model_slot=current.model_slot,
                    purpose=current.purpose,
                    lane=AssignmentLane.CHAMPION,
                    model_id=new_model_id,
                    definition_hash=(
                        registration.registration.definition.definition_hash
                    ),
                    policy_id=policy.policy_id,
                    policy_hash=policy.policy_hash,
                    effective_at=effective_at,
                    actor=actor,
                    reason=reason,
                    approval_ref=approval_ref,
                    governance_revision=replacement_revision,
                )
                _insert_assignment(connection, replacement)
                connection.commit()
                return replacement
            except Exception:
                connection.rollback()
                raise

    def resolve_champion(
        self,
        *,
        runtime_scope: str,
        model_slot: str,
        purpose: RuntimePurpose,
        as_of: datetime,
    ) -> ModelRuntimeAssignment:
        """Resolve the one effective Champion before building dynamic lineage."""

        scope = f"{runtime_scope}:{model_slot}:{purpose.value}"
        with self._connect() as connection:
            try:
                acquire_scope_lock(
                    connection,
                    namespace="model-runtime-assignment",
                    identity=scope,
                )
                _acquire_governance_revision_lock(connection)
                assignments = _current_assignments(
                    connection,
                    runtime_scope=runtime_scope,
                    model_slot=model_slot,
                    purpose=purpose,
                    revision=_current_revision(connection),
                    as_of=as_of,
                )
                champions = tuple(
                    item
                    for item in assignments
                    if item.lane is AssignmentLane.CHAMPION
                )
                if len(champions) != 1:
                    raise ModelGovernanceIntegrityError(
                        "Champion authority is missing or ambiguous"
                    )
                connection.commit()
                return champions[0]
            except Exception:
                connection.rollback()
                raise

    def get_version_lineage_for_model(
        self,
        model_id: ModelId,
    ) -> ModelVersionLineage:
        """Load the one immutable lineage used to validate Runtime execution."""

        with self._connect() as connection:
            return _load_lineage_for_model(connection, model_id)

    def select(self, request: ModelSelectionRequest) -> ModelSelectionReceipt:
        with self._connect() as connection:
            scope = (
                f"{request.runtime_scope}:{request.model_slot}:"
                f"{request.purpose.value}"
            )
            acquire_scope_lock(
                connection, namespace="model-runtime-assignment", identity=scope
            )
            acquire_scope_lock(
                connection,
                namespace="model-selection-request",
                identity=request.idempotency_key,
            )
            _acquire_governance_revision_lock(connection)
            try:
                existing = connection.execute(
                    "SELECT request_hash, payload_json FROM model_selection_receipt "
                    "WHERE idempotency_key = %s",
                    (request.idempotency_key,),
                ).fetchone()
                if existing is not None:
                    if existing["request_hash"] != request.request_hash:
                        raise ValueError(
                            "selection idempotency key was reused for a different request"
                        )
                    receipt = ModelSelectionReceipt.from_canonical_dict(
                        _object(existing["payload_json"])
                    )
                    connection.commit()
                    return receipt
                _record_runtime_lineage(connection, request)
                revision = _current_revision(connection)
                try:
                    receipt = self._evaluate_selection(
                        connection,
                        request,
                        revision=revision,
                    )
                except (KeyError, ValueError, ModelGovernanceIntegrityError):
                    receipt = ModelSelectionReceipt.rejected(
                        request_hash=request.request_hash,
                        runtime_scope=request.runtime_scope,
                        model_slot=request.model_slot,
                        purpose=request.purpose,
                        governance_revision=revision,
                        runtime_lineage_hash=(
                            request.runtime_lineage.runtime_lineage_hash
                        ),
                        reason_codes=("GOVERNANCE_INTEGRITY_ERROR",),
                        selected_at=request.selected_at,
                    )
                _insert_selection(connection, request, receipt)
                connection.commit()
                return receipt
            except Exception:
                connection.rollback()
                raise

    def select_strict(self, request: ModelSelectionRequest) -> ModelSelectionReceipt:
        receipt = self.select(request)
        if receipt.status.value != "SELECTED":
            raise ModelSelectionRejected(receipt)
        return receipt

    def get_selection_receipt(
        self, receipt_id: ArtifactId
    ) -> ModelSelectionReceipt:
        with self._connect() as connection:
            return _load_selection(connection, receipt_id)[1]

    def export_replay_bundle(
        self, receipt_ids: tuple[ArtifactId, ...]
    ) -> dict[str, Any]:
        """Export the exact global governance snapshot used by selections."""

        ordered_ids = tuple(sorted(set(receipt_ids), key=str))
        if not ordered_ids:
            raise ValueError("Model Governance replay requires Selection receipts")
        with self._connect() as connection:
            selection_rows = connection.execute(
                "SELECT governance_revision FROM model_selection_receipt "
                "WHERE receipt_id = ANY(%s)",
                ([str(item) for item in ordered_ids],),
            ).fetchall()
            if len(selection_rows) != len(ordered_ids):
                raise KeyError("Model Selection replay receipt is missing")
            revision = max(int(row["governance_revision"]) for row in selection_rows)
            action_rows = _json_rows(
                connection,
                "SELECT * FROM model_governance_action "
                "WHERE governance_revision <= %s "
                "ORDER BY governance_revision",
                (revision,),
            )
            model_ids = tuple(
                sorted(
                    {
                        str(row["aggregate_id"])
                        for row in action_rows
                        if row["action_type"] == "MODEL_REGISTER"
                    }
                )
            )
            registrations = []
            for raw_model_id in model_ids:
                model_id = ModelId(raw_model_id)
                version = _registry_version_at_revision(
                    connection, model_id, revision
                )
                versioned = self._load_at(connection, model_id, version)
                registration = versioned.registration
                registrations.append(
                    {
                        "model_id": raw_model_id,
                        "registration_json": _json(
                            model_registration_to_dict(registration)
                        ),
                        "definition_hash": (
                            registration.definition.definition_hash
                        ),
                        "lifecycle_status": registration.lifecycle_status.value,
                        "evidence_level": registration.evidence_level.value,
                        "version": version,
                    }
                )
            tables = {
                "model_registrations": registrations,
                "governance_commands": _json_rows(
                    connection,
                    "SELECT command.* FROM governance_commands AS command "
                    "JOIN model_governance_action AS action USING (idempotency_key) "
                    "WHERE action.governance_revision <= %s "
                    "ORDER BY command.created_at, command.idempotency_key",
                    (revision,),
                ),
                "model_lifecycle_transitions": _json_rows(
                    connection,
                    "SELECT transition.* FROM model_lifecycle_transitions AS transition "
                    "JOIN model_governance_action AS action USING (idempotency_key) "
                    "WHERE action.governance_revision <= %s "
                    "ORDER BY transition.model_id, transition.sequence",
                    (revision,),
                ),
                "model_governance_action": action_rows,
                "model_version_lineage": _governance_rows_at_revision(
                    connection, "model_version_lineage", revision
                ),
                "model_qualification_evidence": _governance_rows_at_revision(
                    connection, "model_qualification_evidence", revision
                ),
                "model_governance_policy": _governance_rows_at_revision(
                    connection, "model_governance_policy", revision
                ),
                "model_qualification_decision": _governance_rows_at_revision(
                    connection, "model_qualification_decision", revision
                ),
                "model_runtime_assignment": _governance_rows_at_revision(
                    connection, "model_runtime_assignment", revision
                ),
                "model_runtime_lineage": _json_rows(
                    connection,
                    "SELECT lineage.* FROM model_runtime_lineage AS lineage "
                    "JOIN model_selection_receipt AS receipt "
                    "ON receipt.runtime_lineage_id = lineage.runtime_lineage_id "
                    "WHERE receipt.receipt_id = ANY(%s) "
                    "ORDER BY lineage.runtime_lineage_id",
                    ([str(item) for item in ordered_ids],),
                ),
                "model_selection_receipt": _json_rows(
                    connection,
                    "SELECT * FROM model_selection_receipt "
                    "WHERE receipt_id = ANY(%s) ORDER BY receipt_id",
                    ([str(item) for item in ordered_ids],),
                ),
            }
        return {
            "schema_version": "model-governance-replay-bundle/v1",
            "governance_revision": revision,
            "receipt_ids": [str(item) for item in ordered_ids],
            "tables": tables,
        }

    def import_replay_bundle(self, bundle: Mapping[str, Any]) -> None:
        """Restore one immutable governance snapshot into an isolated PG schema."""

        _validate_replay_bundle_shape(bundle)
        tables = _mapping(bundle["tables"])
        with self._connect() as connection:
            _acquire_governance_revision_lock(connection)
            try:
                for table, columns in _GOVERNANCE_REPLAY_TABLES:
                    rows = _sequence(tables[table])
                    for raw_row in rows:
                        row = _mapping(raw_row)
                        if set(row) != set(columns):
                            raise ValueError(
                                f"Model Governance replay {table} fields mismatch"
                            )
                        placeholders = ", ".join(["%s"] * len(columns))
                        identity_override = (
                            " OVERRIDING SYSTEM VALUE"
                            if table == "model_governance_action"
                            else ""
                        )
                        connection.execute(
                            f"INSERT INTO {table} ({', '.join(columns)})"  # noqa: S608
                            f"{identity_override} VALUES ({placeholders}) "
                            "ON CONFLICT DO NOTHING",
                            tuple(
                                _replay_import_value(table, column, row[column])
                                for column in columns
                            ),
                        )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        receipt_ids = tuple(
            ArtifactId(_string(item))
            for item in _sequence(bundle["receipt_ids"])
        )
        if self.export_replay_bundle(receipt_ids) != dict(bundle):
            raise ModelGovernanceIntegrityError(
                "imported Model Governance replay bundle differs from source"
            )

    def replay_selection(
        self, receipt_id: ArtifactId
    ) -> ModelSelectionReceipt:
        with self._connect() as connection:
            request, stored = _load_selection(connection, receipt_id)
            try:
                rebuilt = self._evaluate_selection(
                    connection,
                    request,
                    revision=stored.governance_revision,
                    historical=True,
                )
            except (KeyError, ValueError, ModelGovernanceIntegrityError):
                if "GOVERNANCE_INTEGRITY_ERROR" not in stored.reason_codes:
                    raise
                rebuilt = ModelSelectionReceipt.rejected(
                    request_hash=request.request_hash,
                    runtime_scope=request.runtime_scope,
                    model_slot=request.model_slot,
                    purpose=request.purpose,
                    governance_revision=stored.governance_revision,
                    runtime_lineage_hash=(
                        request.runtime_lineage.runtime_lineage_hash
                    ),
                    reason_codes=("GOVERNANCE_INTEGRITY_ERROR",),
                    selected_at=request.selected_at,
                )
            if rebuilt != stored:
                raise ModelGovernanceIntegrityError(
                    "historical Model Selection does not replay exactly"
                )
            return rebuilt

    def list_assignments(
        self,
        *,
        runtime_scope: str,
        model_slot: str,
        purpose: RuntimePurpose,
        revision: int | None = None,
    ) -> tuple[ModelRuntimeAssignment, ...]:
        with self._connect() as connection:
            return _current_assignments(
                connection,
                runtime_scope=runtime_scope,
                model_slot=model_slot,
                purpose=purpose,
                revision=_current_revision(connection) if revision is None else revision,
                as_of=datetime.max.replace(tzinfo=UTC),
            )

    def _evaluate_selection(
        self,
        connection: PostgresConnection,
        request: ModelSelectionRequest,
        *,
        revision: int,
        historical: bool = False,
    ) -> ModelSelectionReceipt:
        assignments = _current_assignments(
            connection,
            runtime_scope=request.runtime_scope,
            model_slot=request.model_slot,
            purpose=request.purpose,
            revision=revision,
            as_of=request.selected_at,
        )
        champions = tuple(
            item for item in assignments if item.lane is AssignmentLane.CHAMPION
        )
        challengers = tuple(
            item for item in assignments if item.lane is AssignmentLane.CHALLENGER
        )
        reasons: set[str] = set(request.preselection_rejection_codes)
        champion = champions[0] if len(champions) == 1 else None
        if not champions:
            reasons.add("CHAMPION_AUTHORITY_MISSING")
        elif len(champions) > 1:
            reasons.add("DUPLICATE_CHAMPION_AUTHORITY")
        policy: ModelGovernancePolicy | None = None
        if champion is not None:
            if champion.effective_at > request.selected_at:
                reasons.add("CHAMPION_NOT_YET_EFFECTIVE")
            try:
                policy = _load_policy(connection, champion.policy_id)
            except KeyError:
                reasons.add("GOVERNANCE_POLICY_MISSING")
            if policy is not None and policy.purpose is not request.purpose:
                reasons.add("GOVERNANCE_POLICY_PURPOSE_MISMATCH")
            if policy is not None and (
                request.runtime_lineage.data_eligibility
                not in policy.allowed_data_eligibilities
            ):
                reasons.add("RUNTIME_DATA_ELIGIBILITY_NOT_ALLOWED")
            if request.runtime_lineage.model_id != champion.model_id:
                reasons.add("RUNTIME_MODEL_NOT_CHAMPION")
            if request.runtime_lineage.definition_hash != champion.definition_hash:
                reasons.add("MODEL_DEFINITION_CONFLICT")
        registration = None
        lineage = None
        qualification = None
        qualified_registry_version = None
        if champion is not None and policy is not None:
            try:
                model_version = (
                    _registry_version_at_revision(
                        connection, champion.model_id, revision
                    )
                    if historical
                    else _current_model_version(connection, champion.model_id)
                )
                registration = self._load_at(
                    connection, champion.model_id, model_version
                )
                lineage = _load_lineage_for_model(connection, champion.model_id)
                qualification, qualified_registry_version = _latest_qualification(
                    connection,
                    champion.model_id,
                    policy.policy_id,
                    revision,
                    as_of=request.selected_at,
                )
            except KeyError:
                reasons.add("QUALIFICATION_AUTHORITY_MISSING")
            if registration is not None and (
                registration.registration.definition.definition_hash
                != champion.definition_hash
            ):
                reasons.add("REGISTRY_VERSION_CONFLICT")
            if qualification is not None and registration is not None:
                if qualification.status is not QualificationStatus.QUALIFIED:
                    reasons.add("MODEL_NOT_QUALIFIED")
                if qualified_registry_version != registration.version:
                    reasons.add("QUALIFICATION_REGISTRY_VERSION_STALE")
                if request.purpose is RuntimePurpose.PRODUCTION_DECISION and not (
                    qualification.production_authorized
                ):
                    reasons.add("PRODUCTION_AUTHORIZATION_MISSING")
                if lineage is not None:
                    if not _qualification_evidence_is_current(
                        connection,
                        qualification,
                        lineage,
                        revision,
                        as_of=request.selected_at,
                    ):
                        reasons.add("QUALIFICATION_EVIDENCE_STALE")
            if lineage is not None:
                try:
                    request.runtime_lineage.validate_against(lineage)
                except ValueError:
                    reasons.add("RUNTIME_LINEAGE_MISMATCH")
        if reasons or champion is None or policy is None or qualification is None or registration is None:
            return ModelSelectionReceipt.rejected(
                request_hash=request.request_hash,
                runtime_scope=request.runtime_scope,
                model_slot=request.model_slot,
                purpose=request.purpose,
                governance_revision=revision,
                runtime_lineage_hash=request.runtime_lineage.runtime_lineage_hash,
                reason_codes=tuple(sorted(reasons or {"GOVERNANCE_AUTHORITY_INCOMPLETE"})),
                selected_at=request.selected_at,
                policy=policy,
                champion=champion,
                challengers=challengers,
            )
        return ModelSelectionReceipt.accepted(
            request_hash=request.request_hash,
            runtime_scope=request.runtime_scope,
            model_slot=request.model_slot,
            purpose=request.purpose,
            governance_revision=revision,
            policy=policy,
            champion=champion,
            challengers=challengers,
            qualification_decision_id=qualification.decision_id,
            qualification_decision_hash=qualification.decision_hash,
            selected_registry_version=registration.version,
            runtime_lineage_hash=request.runtime_lineage.runtime_lineage_hash,
            evidence_ids=qualification.evidence_ids,
            selected_at=request.selected_at,
            production_authorized=qualification.production_authorized,
        )


def _record_action(
    connection: PostgresConnection,
    *,
    action_type: str,
    aggregate_id: str,
    action_payload: Mapping[str, Any],
    actor: str,
    reason: str,
    idempotency_key: str,
    created_at: datetime,
) -> tuple[int, bool]:
    existing = _find_action(connection, idempotency_key)
    if existing is not None:
        _validate_action(existing, action_type, action_payload)
        return int(existing["governance_revision"]), True
    digest = canonical_hash(action_payload)
    row = connection.execute(
        """
        INSERT INTO model_governance_action(
            idempotency_key, action_type, aggregate_id, action_hash,
            actor, reason, payload_json, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING governance_revision
        """,
        (
            idempotency_key,
            action_type,
            aggregate_id,
            digest,
            actor,
            reason,
            _json(action_payload),
            created_at,
        ),
    ).fetchone()
    if row is None:
        raise ModelGovernanceIntegrityError("governance revision was not allocated")
    return int(row["governance_revision"]), False


def _acquire_governance_revision_lock(connection: PostgresConnection) -> None:
    acquire_scope_lock(
        connection,
        namespace="model-governance-revision",
        identity="global",
    )


def _find_action(
    connection: PostgresConnection, idempotency_key: str
) -> dict[str, Any] | None:
    return connection.execute(
        "SELECT * FROM model_governance_action WHERE idempotency_key = %s",
        (idempotency_key,),
    ).fetchone()


def _validate_action(
    row: Mapping[str, Any], action_type: str, payload: Mapping[str, Any]
) -> None:
    if row["action_type"] != action_type or row["action_hash"] != canonical_hash(payload):
        raise ValueError("governance idempotency key was reused for another action")


def _current_revision(connection: PostgresConnection) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(governance_revision), 0) AS revision "
        "FROM model_governance_action"
    ).fetchone()
    return 0 if row is None else int(row["revision"])


def _current_model_version(connection: PostgresConnection, model_id: ModelId) -> int:
    row = connection.execute(
        "SELECT version FROM model_registrations WHERE model_id = %s",
        (str(model_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(model_id))
    return int(row["version"])


def _registry_version_at_revision(
    connection: PostgresConnection,
    model_id: ModelId,
    revision: int,
) -> int:
    row = connection.execute(
        """
        SELECT command.result_version
        FROM model_governance_action AS action
        JOIN governance_commands AS command
          ON command.idempotency_key = action.idempotency_key
        WHERE action.aggregate_id = %s
          AND action.action_type IN ('MODEL_REGISTER', 'MODEL_LIFECYCLE_TRANSITION')
          AND action.governance_revision <= %s
        ORDER BY action.governance_revision DESC
        LIMIT 1
        """,
        (str(model_id), revision),
    ).fetchone()
    if row is None:
        raise KeyError(f"Registry revision missing: {model_id}:{revision}")
    return int(row["result_version"])


def _load_lineage(
    connection: PostgresConnection, lineage_id: ArtifactId
) -> ModelVersionLineage:
    row = connection.execute(
        "SELECT payload_json FROM model_version_lineage WHERE lineage_id = %s",
        (str(lineage_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(lineage_id))
    return ModelVersionLineage.from_canonical_dict(_object(row["payload_json"]))


def _load_lineage_for_model(
    connection: PostgresConnection, model_id: ModelId
) -> ModelVersionLineage:
    rows = connection.execute(
        "SELECT payload_json FROM model_version_lineage WHERE model_id = %s",
        (str(model_id),),
    ).fetchall()
    if len(rows) != 1:
        raise KeyError(f"ambiguous or missing Model Version Lineage: {model_id}")
    return ModelVersionLineage.from_canonical_dict(_object(rows[0]["payload_json"]))


def _verify_formal_pit_evidence(
    connection: PostgresConnection,
    evidence: ModelQualificationEvidence,
) -> None:
    if (
        evidence.outcome is not QualificationEvidenceOutcome.SATISFIED
        or evidence.evidence.reference_kind != "FORMAL_PIT_VALIDATION"
    ):
        raise ValueError("FORMAL_PIT requires a satisfied Formal PIT validation reference")
    row = connection.execute(
        "SELECT payload_json FROM formal_pit_validation_evidence WHERE evidence_id = %s",
        (str(evidence.evidence.artifact_id),),
    ).fetchone()
    if row is None:
        raise ValueError("FORMAL_PIT evidence is not owned by PIT Data Authority")
    pit = FormalPITEvidenceArtifact.from_canonical_dict(_object(row["payload_json"]))
    expected_protocol = pit.lineage.validation_protocol
    mismatches = []
    for label, governance_value, pit_value in (
        ("hash", evidence.evidence.content_hash, pit.evidence_hash),
        ("model", evidence.model_id, pit.lineage.model_id),
        ("definition", evidence.definition_hash, pit.lineage.definition_hash),
        ("lineage_id", evidence.lineage_id, pit.lineage.model_lineage_id),
        ("lineage_hash", evidence.lineage_hash, pit.lineage.model_lineage_hash),
        ("available_at", evidence.available_at, pit.available_at),
        ("recorded_at", evidence.recorded_at, pit.recorded_at),
        (
            "validation_protocol",
            evidence.validation_protocol_ref.to_canonical_dict(),
            expected_protocol.to_canonical_dict(),
        ),
    ):
        if governance_value != pit_value:
            mismatches.append(label)
    if pit.outcome is not PITValidationOutcome.SATISFIED:
        mismatches.append("outcome")
    if mismatches:
        raise ValueError("FORMAL_PIT authority mismatch: " + ",".join(mismatches))


def _load_evidence(
    connection: PostgresConnection, evidence_id: ArtifactId
) -> ModelQualificationEvidence:
    row = connection.execute(
        "SELECT payload_json FROM model_qualification_evidence WHERE evidence_id = %s",
        (str(evidence_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(evidence_id))
    return ModelQualificationEvidence.from_canonical_dict(_object(row["payload_json"]))


def _latest_evidence(
    connection: PostgresConnection,
    lineage_id: ArtifactId,
    revision: int,
    *,
    as_of: datetime = datetime.max.replace(tzinfo=UTC),
) -> tuple[ModelQualificationEvidence, ...]:
    rows = connection.execute(
        """
        SELECT DISTINCT ON (evidence_kind) payload_json
        FROM model_qualification_evidence
        WHERE lineage_id = %s AND governance_revision <= %s
          AND available_at <= %s AND recorded_at <= %s
        ORDER BY evidence_kind, governance_revision DESC
        """,
        (str(lineage_id), revision, as_of, as_of),
    ).fetchall()
    return tuple(
        sorted(
            (
                ModelQualificationEvidence.from_canonical_dict(
                    _object(row["payload_json"])
                )
                for row in rows
            ),
            key=lambda item: str(item.evidence_id),
        )
    )


def _qualification_evidence_is_current(
    connection: PostgresConnection,
    qualification: ModelQualificationDecision,
    lineage: ModelVersionLineage,
    revision: int,
    *,
    as_of: datetime,
) -> bool:
    latest = tuple(
        sorted(
            _latest_evidence(
                connection,
                lineage.lineage_id,
                revision,
                as_of=as_of,
            ),
            key=lambda item: str(item.evidence_id),
        )
    )
    return (
        tuple(item.evidence_id for item in latest)
        == qualification.evidence_ids
        and tuple(item.evidence_hash for item in latest)
        == qualification.evidence_hashes
    )


def _load_policy(
    connection: PostgresConnection, policy_id: ArtifactId
) -> ModelGovernancePolicy:
    row = connection.execute(
        "SELECT payload_json FROM model_governance_policy WHERE policy_id = %s",
        (str(policy_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(policy_id))
    return ModelGovernancePolicy.from_canonical_dict(_object(row["payload_json"]))


def _policy_created_at(
    connection: PostgresConnection, policy_id: ArtifactId
) -> datetime:
    row = connection.execute(
        "SELECT created_at FROM model_governance_policy WHERE policy_id = %s",
        (str(policy_id),),
    ).fetchone()
    if row is None or not isinstance(row["created_at"], datetime):
        raise KeyError(str(policy_id))
    return row["created_at"]


def _latest_qualification(
    connection: PostgresConnection,
    model_id: ModelId,
    policy_id: ArtifactId,
    revision: int,
    *,
    as_of: datetime,
) -> tuple[ModelQualificationDecision, int]:
    row = connection.execute(
        """
        SELECT payload_json, registry_version
        FROM model_qualification_decision
        WHERE model_id = %s AND policy_id = %s AND governance_revision <= %s
          AND decided_at <= %s
        ORDER BY governance_revision DESC LIMIT 1
        """,
        (str(model_id), str(policy_id), revision, as_of),
    ).fetchone()
    if row is None:
        raise KeyError(f"qualification missing: {model_id}:{policy_id}")
    return (
        ModelQualificationDecision.from_canonical_dict(_object(row["payload_json"])),
        int(row["registry_version"]),
    )


def _load_qualification_by_revision(
    connection: PostgresConnection, revision: int
) -> tuple[ModelQualificationDecision, int]:
    row = connection.execute(
        "SELECT payload_json, registry_version FROM model_qualification_decision "
        "WHERE governance_revision = %s",
        (revision,),
    ).fetchone()
    if row is None:
        raise ModelGovernanceIntegrityError("qualification action has no decision")
    return (
        ModelQualificationDecision.from_canonical_dict(_object(row["payload_json"])),
        int(row["registry_version"]),
    )


def _insert_assignment(
    connection: PostgresConnection, assignment: ModelRuntimeAssignment
) -> None:
    connection.execute(
        """
        INSERT INTO model_runtime_assignment(
            assignment_id, assignment_hash, runtime_scope, model_slot,
            purpose, lane, assignment_status, model_id, policy_id, version,
            supersedes_assignment_id, governance_revision, payload_json,
            effective_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(assignment.assignment_id),
            assignment.assignment_hash,
            assignment.runtime_scope,
            assignment.model_slot,
            assignment.purpose.value,
            assignment.lane.value,
            assignment.status.value,
            str(assignment.model_id),
            str(assignment.policy_id),
            assignment.version,
            (
                None
                if assignment.supersedes_assignment_id is None
                else str(assignment.supersedes_assignment_id)
            ),
            assignment.governance_revision,
            _json(assignment.to_canonical_dict()),
            assignment.effective_at,
        ),
    )


def _load_assignment(
    connection: PostgresConnection, assignment_id: ArtifactId
) -> ModelRuntimeAssignment:
    row = connection.execute(
        "SELECT payload_json FROM model_runtime_assignment WHERE assignment_id = %s",
        (str(assignment_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(assignment_id))
    return ModelRuntimeAssignment.from_canonical_dict(_object(row["payload_json"]))


def _load_assignment_by_revision(
    connection: PostgresConnection, revision: int
) -> ModelRuntimeAssignment:
    row = connection.execute(
        "SELECT payload_json FROM model_runtime_assignment "
        "WHERE governance_revision = %s",
        (revision,),
    ).fetchone()
    if row is None:
        raise ModelGovernanceIntegrityError("assignment action has no event")
    return ModelRuntimeAssignment.from_canonical_dict(_object(row["payload_json"]))


_GOVERNANCE_REPLAY_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "model_registrations",
        (
            "model_id",
            "registration_json",
            "definition_hash",
            "lifecycle_status",
            "evidence_level",
            "version",
        ),
    ),
    (
        "governance_commands",
        (
            "idempotency_key",
            "aggregate_type",
            "aggregate_id",
            "payload_hash",
            "result_version",
            "created_at",
        ),
    ),
    (
        "model_lifecycle_transitions",
        ("model_id", "sequence", "transition_json", "idempotency_key"),
    ),
    (
        "model_governance_action",
        (
            "governance_revision",
            "idempotency_key",
            "action_type",
            "aggregate_id",
            "action_hash",
            "actor",
            "reason",
            "payload_json",
            "created_at",
        ),
    ),
    (
        "model_version_lineage",
        (
            "lineage_id",
            "lineage_hash",
            "model_id",
            "definition_hash",
            "governance_revision",
            "payload_json",
            "created_at",
        ),
    ),
    (
        "model_qualification_evidence",
        (
            "evidence_id",
            "evidence_hash",
            "model_id",
            "lineage_id",
            "evidence_kind",
            "outcome",
            "governance_revision",
            "payload_json",
            "available_at",
            "recorded_at",
        ),
    ),
    (
        "model_governance_policy",
        (
            "policy_id",
            "policy_hash",
            "purpose",
            "production_authorization",
            "governance_revision",
            "payload_json",
            "created_at",
        ),
    ),
    (
        "model_qualification_decision",
        (
            "decision_id",
            "decision_hash",
            "model_id",
            "lineage_id",
            "policy_id",
            "purpose",
            "qualification_status",
            "production_authorized",
            "registry_version",
            "governance_revision",
            "payload_json",
            "decided_at",
        ),
    ),
    (
        "model_runtime_lineage",
        (
            "runtime_lineage_id",
            "runtime_lineage_hash",
            "model_id",
            "payload_json",
            "recorded_at",
        ),
    ),
    (
        "model_runtime_assignment",
        (
            "assignment_id",
            "assignment_hash",
            "runtime_scope",
            "model_slot",
            "purpose",
            "lane",
            "assignment_status",
            "model_id",
            "policy_id",
            "version",
            "supersedes_assignment_id",
            "governance_revision",
            "payload_json",
            "effective_at",
        ),
    ),
    (
        "model_selection_receipt",
        (
            "receipt_id",
            "receipt_hash",
            "request_hash",
            "idempotency_key",
            "runtime_scope",
            "model_slot",
            "purpose",
            "selection_status",
            "governance_revision",
            "selected_model_id",
            "selected_registry_version",
            "runtime_lineage_id",
            "request_json",
            "payload_json",
            "selected_at",
        ),
    ),
)


def _json_rows(
    connection: PostgresConnection,
    query: str,
    parameters: tuple[Any, ...],
) -> list[dict[str, Any]]:
    return [
        {
            str(key): _canonical_db_value(value)
            for key, value in row.items()
        }
        for row in connection.execute(query, parameters).fetchall()
    ]


def _governance_rows_at_revision(
    connection: PostgresConnection,
    table: str,
    revision: int,
) -> list[dict[str, Any]]:
    if table not in {
        "model_version_lineage",
        "model_qualification_evidence",
        "model_governance_policy",
        "model_qualification_decision",
        "model_runtime_assignment",
    }:
        raise ValueError("unsupported governance replay table")
    return _json_rows(
        connection,
        f"SELECT * FROM {table} WHERE governance_revision <= %s "  # noqa: S608
        "ORDER BY governance_revision",
        (revision,),
    )


def _canonical_db_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_db_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_db_value(item) for item in value]
    return value


def _validate_replay_bundle_shape(bundle: Mapping[str, Any]) -> None:
    if set(bundle) != {
        "schema_version",
        "governance_revision",
        "receipt_ids",
        "tables",
    } or bundle.get("schema_version") != "model-governance-replay-bundle/v1":
        raise ValueError("Model Governance replay bundle fields mismatch")
    revision = bundle.get("governance_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("Model Governance replay revision is invalid")
    receipt_ids = _sequence(bundle["receipt_ids"])
    if (
        not receipt_ids
        or any(not isinstance(item, str) or not item for item in receipt_ids)
        or tuple(receipt_ids)
        != tuple(sorted({str(item) for item in receipt_ids}))
    ):
        raise ValueError("Model Governance replay receipt identities are invalid")
    tables = _mapping(bundle["tables"])
    if set(tables) != {item[0] for item in _GOVERNANCE_REPLAY_TABLES}:
        raise ValueError("Model Governance replay table set mismatch")


def _replay_import_value(table: str, column: str, value: Any) -> Any:
    jsonb_columns = {
        ("model_governance_action", "payload_json"),
        ("model_version_lineage", "payload_json"),
        ("model_qualification_evidence", "payload_json"),
        ("model_governance_policy", "payload_json"),
        ("model_qualification_decision", "payload_json"),
        ("model_runtime_lineage", "payload_json"),
        ("model_runtime_assignment", "payload_json"),
        ("model_selection_receipt", "request_json"),
        ("model_selection_receipt", "payload_json"),
    }
    if (table, column) in jsonb_columns:
        return _json(_mapping(value))
    return value


def _current_assignments(
    connection: PostgresConnection,
    *,
    runtime_scope: str,
    model_slot: str,
    purpose: RuntimePurpose,
    revision: int,
    as_of: datetime,
) -> tuple[ModelRuntimeAssignment, ...]:
    rows = connection.execute(
        """
        WITH latest AS (
            SELECT payload_json, assignment_status,
                   row_number() OVER (
                       PARTITION BY lane, model_id
                       ORDER BY governance_revision DESC
                   ) AS ordinal
            FROM model_runtime_assignment
            WHERE runtime_scope = %s AND model_slot = %s
              AND purpose = %s AND governance_revision <= %s
              AND effective_at <= %s
        )
        SELECT payload_json FROM latest
        WHERE ordinal = 1 AND assignment_status = 'ACTIVE'
        """,
        (runtime_scope, model_slot, purpose.value, revision, as_of),
    ).fetchall()
    return tuple(
        sorted(
            (
                ModelRuntimeAssignment.from_canonical_dict(
                    _object(row["payload_json"])
                )
                for row in rows
            ),
            key=lambda item: (item.lane.value, str(item.model_id)),
        )
    )


def _record_runtime_lineage(
    connection: PostgresConnection, request: ModelSelectionRequest
) -> None:
    lineage = request.runtime_lineage
    connection.execute(
        """
        INSERT INTO model_runtime_lineage(
            runtime_lineage_id, runtime_lineage_hash, model_id,
            payload_json, recorded_at
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (runtime_lineage_id) DO NOTHING
        """,
        (
            str(lineage.runtime_lineage_id),
            lineage.runtime_lineage_hash,
            str(lineage.model_id),
            _json(lineage.to_canonical_dict()),
            request.selected_at,
        ),
    )
    row = connection.execute(
        "SELECT payload_json FROM model_runtime_lineage "
        "WHERE runtime_lineage_id = %s",
        (str(lineage.runtime_lineage_id),),
    ).fetchone()
    if row is None or RuntimeModelLineage.from_canonical_dict(
        _object(row["payload_json"])
    ) != lineage:
        raise ValueError("Runtime Model Lineage identity conflict")


def _insert_selection(
    connection: PostgresConnection,
    request: ModelSelectionRequest,
    receipt: ModelSelectionReceipt,
) -> None:
    connection.execute(
        """
        INSERT INTO model_selection_receipt(
            receipt_id, receipt_hash, request_hash, idempotency_key,
            runtime_scope, model_slot, purpose, selection_status,
            governance_revision, selected_model_id, selected_registry_version,
            runtime_lineage_id, request_json, payload_json, selected_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(receipt.receipt_id),
            receipt.receipt_hash,
            receipt.request_hash,
            request.idempotency_key,
            receipt.runtime_scope,
            receipt.model_slot,
            receipt.purpose.value,
            receipt.status.value,
            receipt.governance_revision,
            None if receipt.selected_model_id is None else str(receipt.selected_model_id),
            receipt.selected_registry_version,
            str(request.runtime_lineage.runtime_lineage_id),
            _json(request.to_canonical_dict()),
            _json(receipt.to_canonical_dict()),
            receipt.selected_at,
        ),
    )


def _load_selection(
    connection: PostgresConnection, receipt_id: ArtifactId
) -> tuple[ModelSelectionRequest, ModelSelectionReceipt]:
    row = connection.execute(
        "SELECT request_json, payload_json FROM model_selection_receipt "
        "WHERE receipt_id = %s",
        (str(receipt_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(receipt_id))
    return (
        ModelSelectionRequest.from_canonical_dict(_object(row["request_json"])),
        ModelSelectionReceipt.from_canonical_dict(_object(row["payload_json"])),
    )


def _json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _object(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, Mapping):
            return parsed
    raise ModelGovernanceIntegrityError("stored governance JSON is not an object")


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected governance replay object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError("expected governance replay array")
    return tuple(value)


def _string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("expected governance replay text")
    return value


__all__ = [
    "ModelGovernanceIntegrityError",
    "ModelSelectionRejected",
    "PostgresModelGovernanceRepository",
]
