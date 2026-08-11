"""PostgreSQL owner-resolved C6-C9 evidence gates.

The owner can prove sustained prospective Shadow from live Runtime facts.  It
persists explicit BLOCKED/ACCUMULATING outcomes for qualifications whose
replayable evidence or external authority does not yet exist.  It never emits
an Order or grants Broker mutation authority.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.admission import (
    AdmissionFloor,
    AdmissionFloorAssessment,
    AdmissionFloorStatus,
    ProductionAdmissionDecision,
    evaluate_production_admission,
    production_admission_from_canonical_dict,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.calibration_qualification import (
    CalibrationQualificationDecision,
)
from market_regime_alpha.application.research_validation.phase_c_gates import (
    EntryHoldingExitQualificationPolicy,
    PhaseCStage,
    PhaseCStageDecision,
    PhaseCStageOutcome,
    ProspectiveShadowQualificationPolicy,
)
from market_regime_alpha.application.research_validation.qualification import (
    FormalOOSQualificationDecision,
)
from market_regime_alpha.application.research_validation.entry_qualification import (
    EntryResearchAssessment,
    EntryResearchDecision,
    EntryResearchModel,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationPartition,
    FormalEvaluationProtocol,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    FormalProtocolConflict,
    load_formal_protocol_owner,
)
from market_regime_alpha.application.continuous_research.runtime_authority_evidence import (
    RuntimeAuthorityEvidence,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    ProspectiveShadowOutcome,
)
from market_regime_alpha.application.shadow_research.attestation import (
    ClockMode,
    ProspectiveEvidenceAttestation,
    RuntimeOrigin,
)
from market_regime_alpha.application.governance.access_control import (
    ApprovalAction,
    ApprovalDecisionKind,
    SecurityApproval,
    SecurityApprovalDecision,
)
from market_regime_alpha.application.strategy_shadow.operations import (
    StrategyShadowArtifactKind,
    StrategyShadowArtifactRecord,
    replay_strategy_shadow,
    strategy_shadow_session_from_canonical_dict,
)
from market_regime_alpha.application.strategy_shadow.contracts import (
    HoldingRuleKind,
    ShadowEntry,
    ShadowFill,
    ShadowPosition,
    StrategyOutcome,
    restore_strategy_shadow_artifact,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowPortfolioDayState,
    ShadowPortfolioPolicy,
    ShadowParameterProvenance,
)
from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.data.pit_authority import FormalPITEvidenceArtifact
from market_regime_alpha.data.pit_contracts import PITValidationOutcome
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.native_repository import (
    acquire_scope_lock,
)


class PhaseCGateConflict(ValueError):
    """A Phase C owner or immutable evidence invariant failed."""


class PostgresPhaseCGateAuthority:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def record_entry_holding_exit_policy(
        self, policy: EntryHoldingExitQualificationPolicy
    ) -> EntryHoldingExitQualificationPolicy:
        self._factory.run_transaction(
            lambda connection: _record_entry_holding_exit_policy(
                connection,
                formal_protocol_id=None,
                policy=policy,
            )
        )
        return policy

    def resolve_entry_holding_exit(
        self,
        *,
        formal_protocol_id: ArtifactId,
        policy: EntryHoldingExitQualificationPolicy | None = None,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> PhaseCStageDecision:
        resolved_policy = policy or self._entry_policy_for_protocol(
            formal_protocol_id
        )
        scope_id = str(formal_protocol_id)
        command = {
            "stage": PhaseCStage.ENTRY_HOLDING_EXIT_QUALIFICATION.value,
            "scope_id": scope_id,
            "policy_hash": (
                None if resolved_policy is None else resolved_policy.policy_hash
            ),
            "actor": actor,
            "reason": reason,
        }

        def assess(connection: Any) -> tuple[
            PhaseCStageOutcome,
            tuple[str, ...],
            tuple[ValidationArtifactReference, ...],
        ]:
            if resolved_policy is not None:
                _record_entry_holding_exit_policy(
                    connection,
                    formal_protocol_id=formal_protocol_id,
                    policy=resolved_policy,
                )
            return _assess_entry_holding_exit(
                connection,
                formal_protocol_id=formal_protocol_id,
                policy=resolved_policy,
            )

        return self._resolve_stage(
            stage=PhaseCStage.ENTRY_HOLDING_EXIT_QUALIFICATION,
            scope_id=scope_id,
            policy_reference=(
                None
                if resolved_policy is None
                else ValidationArtifactReference(
                    "ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY",
                    resolved_policy.policy_id,
                    resolved_policy.policy_hash,
                )
            ),
            command=command,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            assessor=assess,
        )

    def _entry_policy_for_protocol(
        self, formal_protocol_id: ArtifactId
    ) -> EntryHoldingExitQualificationPolicy | None:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT p.policy_json
                FROM formal_research_protocol f
                JOIN entry_holding_exit_qualification_policy p
                  ON p.policy_id =
                    f.payload_json->'entry_holding_exit_qualification_policy_reference'->>'artifact_id'
                 AND p.policy_hash =
                    f.payload_json->'entry_holding_exit_qualification_policy_reference'->>'content_hash'
                WHERE f.protocol_id = %s
                """,
                (str(formal_protocol_id),),
            ).fetchone()
        if row is None:
            return None
        return EntryHoldingExitQualificationPolicy.from_canonical_dict(
            _mapping(row[0])
        )

    def resolve_prospective_shadow(
        self,
        *,
        policy: ProspectiveShadowQualificationPolicy,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> PhaseCStageDecision:
        scope_id = str(policy.policy_id)
        command = {
            "stage": PhaseCStage.PROSPECTIVE_STRATEGY_SHADOW.value,
            "scope_id": scope_id,
            "policy_hash": policy.policy_hash,
            "actor": actor,
            "reason": reason,
        }

        def assess(connection: Any) -> tuple[
            PhaseCStageOutcome,
            tuple[str, ...],
            tuple[ValidationArtifactReference, ...],
        ]:
            _record_prospective_policy(connection, policy)
            return _assess_prospective_shadow(connection, policy)

        return self._resolve_stage(
            stage=PhaseCStage.PROSPECTIVE_STRATEGY_SHADOW,
            scope_id=scope_id,
            policy_reference=ValidationArtifactReference(
                "PROSPECTIVE_SHADOW_QUALIFICATION_POLICY",
                policy.policy_id,
                policy.policy_hash,
            ),
            command=command,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            assessor=assess,
        )

    def resolve_production_admission(
        self,
        *,
        formal_protocol_id: ArtifactId,
        governance_version: str,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> ProductionAdmissionDecision:
        command = {
            "stage": "PRODUCTION_ADMISSION",
            "formal_protocol_id": str(formal_protocol_id),
            "governance_version": governance_version,
            "actor": actor,
            "reason": reason,
        }
        command_hash = canonical_hash(command)

        def operation(connection: Any) -> ArtifactId:
            acquire_scope_lock(
                connection,
                namespace="production-admission",
                identity=str(formal_protocol_id),
            )
            duplicate = _duplicate_command(
                connection,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
                result_kind="PRODUCTION_ADMISSION_DECISION",
            )
            if duplicate is not None:
                return duplicate
            _formal_protocol_reference(connection, formal_protocol_id)
            now = _postgres_now(connection)
            assessments = _resolve_admission_floors(
                connection, formal_protocol_id=formal_protocol_id
            )
            decision = evaluate_production_admission(
                governance_version=governance_version,
                assessments=assessments,
                evaluated_at=now,
            )
            latest = connection.execute(
                """
                SELECT decision_id, revision
                FROM production_admission_decision_authority
                WHERE formal_protocol_id = %s
                ORDER BY revision DESC LIMIT 1
                """,
                (str(formal_protocol_id),),
            ).fetchone()
            revision = 1 if latest is None else int(latest[1]) + 1
            supersedes = None if latest is None else str(latest[0])
            payload = {
                "decision_id": str(decision.decision_id),
                "decision_hash": decision.decision_hash,
                **decision.identity_payload(),
                "owner_actor": actor,
                "owner_reason": reason,
            }
            # Actor/reason are audit metadata rather than identity inputs.  The
            # immutable decision identity remains the exact floor projection.
            if latest is not None and str(latest[0]) == str(decision.decision_id):
                _record_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    result_kind="PRODUCTION_ADMISSION_DECISION",
                    result_id=decision.decision_id,
                    created_at=now,
                )
                return decision.decision_id
            connection.execute(
                """
                INSERT INTO production_admission_decision_authority(
                    decision_id, decision_hash, formal_protocol_id, status,
                    production_authorized, revision, supersedes_decision_id,
                    payload_json, evaluated_at
                ) VALUES (%s, %s, %s, 'BLOCKED', false, %s, %s, %s, %s)
                """,
                (
                    str(decision.decision_id),
                    decision.decision_hash,
                    str(formal_protocol_id),
                    revision,
                    supersedes,
                    Jsonb(payload),
                    now,
                ),
            )
            _record_command(
                connection,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
                result_kind="PRODUCTION_ADMISSION_DECISION",
                result_id=decision.decision_id,
                created_at=now,
            )
            return decision.decision_id

        return self.get_production_admission(
            self._factory.run_transaction(operation)
        )

    def resolve_controlled_execution(
        self,
        *,
        formal_protocol_id: ArtifactId,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> PhaseCStageDecision:
        scope_id = str(formal_protocol_id)
        command = {
            "stage": PhaseCStage.CONTROLLED_EXECUTION_READINESS.value,
            "scope_id": scope_id,
            "actor": actor,
            "reason": reason,
        }

        def assess(connection: Any) -> tuple[
            PhaseCStageOutcome,
            tuple[str, ...],
            tuple[ValidationArtifactReference, ...],
        ]:
            _formal_protocol_reference(connection, formal_protocol_id)
            admission = _latest_production_admission_reference(
                connection, formal_protocol_id=formal_protocol_id
            )
            references = () if admission[0] is None else (admission[0],)
            reasons = {
                "AUTHENTICATED_BROKER_SESSION_MISSING",
                "BROKER_CONTRACT_MISSING",
                "BROKER_READ_ONLY_RECONCILIATION_MISSING",
                "CONTROLLED_EXECUTION_PREFLIGHT_MISSING",
                "HUMAN_APPROVED_ORDER_AUTHORITY_MISSING",
                "KILL_SWITCH_EVIDENCE_MISSING",
                "ORDER_PREVIEW_DRY_RUN_EVIDENCE_MISSING",
                "PAPER_BROKER_VALIDATION_MISSING",
                "PRODUCTION_ADMISSION_BLOCKED",
                "RISK_GATE_EVIDENCE_MISSING",
                "TINY_CAPITAL_APPROVAL_MISSING",
            }
            return PhaseCStageOutcome.BLOCKED, tuple(sorted(reasons)), references

        return self._resolve_stage(
            stage=PhaseCStage.CONTROLLED_EXECUTION_READINESS,
            scope_id=scope_id,
            policy_reference=None,
            command=command,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            assessor=assess,
        )

    def get_stage(self, decision_id: ArtifactId) -> PhaseCStageDecision:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, decision_hash
                FROM phase_c_stage_decision WHERE decision_id = %s
                """,
                (str(decision_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(decision_id))
        decision = PhaseCStageDecision.from_canonical_dict(_mapping(row[0]))
        if decision.decision_hash != str(row[1]):
            raise PhaseCGateConflict("Phase C Stage storage hash mismatch")
        return decision

    def get_production_admission(
        self, decision_id: ArtifactId
    ) -> ProductionAdmissionDecision:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, decision_hash
                FROM production_admission_decision_authority
                WHERE decision_id = %s
                """,
                (str(decision_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(decision_id))
        payload = dict(_mapping(row[0]))
        payload.pop("owner_actor", None)
        payload.pop("owner_reason", None)
        decision = production_admission_from_canonical_dict(payload)
        if decision.decision_hash != str(row[1]):
            raise PhaseCGateConflict("Production Admission storage hash mismatch")
        return decision

    def _resolve_stage(
        self,
        *,
        stage: PhaseCStage,
        scope_id: str,
        policy_reference: ValidationArtifactReference | None,
        command: Mapping[str, Any],
        actor: str,
        reason: str,
        idempotency_key: str,
        assessor: Any,
    ) -> PhaseCStageDecision:
        command_hash = canonical_hash(dict(command))

        def operation(connection: Any) -> ArtifactId:
            acquire_scope_lock(
                connection,
                namespace="phase-c-stage",
                identity=f"{stage.value}:{scope_id}",
            )
            duplicate = _duplicate_command(
                connection,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
                result_kind="PHASE_C_STAGE_DECISION",
            )
            if duplicate is not None:
                return duplicate
            outcome, reasons, evidence = assessor(connection)
            now = _postgres_now(connection)
            latest = connection.execute(
                """
                SELECT decision_id, revision
                FROM phase_c_stage_decision
                WHERE stage = %s AND scope_id = %s
                ORDER BY revision DESC LIMIT 1
                """,
                (stage.value, scope_id),
            ).fetchone()
            revision = 1 if latest is None else int(latest[1]) + 1
            supersedes = None if latest is None else ArtifactId(str(latest[0]))
            decision = PhaseCStageDecision.create(
                stage=stage,
                scope_id=scope_id,
                policy_reference=policy_reference,
                evidence_references=evidence,
                outcome=outcome,
                qualification_established=(outcome is PhaseCStageOutcome.SATISFIED),
                revision=revision,
                supersedes_decision_id=supersedes,
                evaluated_at=now,
                actor=actor,
                reason=reason,
                reason_codes=reasons,
            )
            connection.execute(
                """
                INSERT INTO phase_c_stage_decision(
                    decision_id, decision_hash, stage, scope_id, policy_id,
                    outcome, qualification_established, revision,
                    supersedes_decision_id, payload_json, evaluated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(decision.decision_id),
                    decision.decision_hash,
                    stage.value,
                    scope_id,
                    (
                        None
                        if policy_reference is None
                        else str(policy_reference.artifact_id)
                    ),
                    outcome.value,
                    decision.qualification_established,
                    revision,
                    None if supersedes is None else str(supersedes),
                    Jsonb(decision.to_canonical_dict()),
                    now,
                ),
            )
            _record_command(
                connection,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
                result_kind="PHASE_C_STAGE_DECISION",
                result_id=decision.decision_id,
                created_at=now,
            )
            return decision.decision_id

        return self.get_stage(self._factory.run_transaction(operation))


def _assess_prospective_shadow(
    connection: Any,
    policy: ProspectiveShadowQualificationPolicy,
) -> tuple[
    PhaseCStageOutcome,
    tuple[str, ...],
    tuple[ValidationArtifactReference, ...],
]:
    rows = connection.execute(
        """
        SELECT session_id, session_hash, trading_date, runtime_run_id,
               runtime_tick_id, research_shadow_id, status, payload_json
        FROM strategy_shadow_session
        WHERE policy_id = %s AND created_at >= %s AND scheduled_for >= %s
        ORDER BY trading_date, session_id
        """,
        (
            str(policy.strategy_policy_reference.artifact_id),
            policy.locked_at,
            policy.locked_at,
        ),
    ).fetchall()
    if not rows:
        return (
            PhaseCStageOutcome.ACCUMULATING,
            ("NO_POST_LOCK_PROSPECTIVE_STRATEGY_SHADOW_SESSIONS",),
            (),
        )
    references: list[ValidationArtifactReference] = []
    settled_days: set[Any] = set()
    missing: set[str] = set()
    failed = 0
    settled = 0
    provider_failures = 0
    session_ids: list[str] = []
    for row in rows:
        payload = _mapping(row[7])
        event_rows = connection.execute(
            """
            SELECT payload_json FROM strategy_shadow_event
            WHERE session_id = %s ORDER BY sequence
            """,
            (str(row[0]),),
        ).fetchall()
        try:
            session = strategy_shadow_session_from_canonical_dict(
                {
                    **payload,
                    "events": [_mapping(item[0]) for item in event_rows],
                }
            )
            replay_strategy_shadow(session)
        except (KeyError, TypeError, ValueError) as exc:
            raise PhaseCGateConflict(
                "Strategy Shadow Session exact replay failed"
            ) from exc
        if (
            str(session.session_id) != str(row[0])
            or session.session_hash != str(row[1])
            or session.trading_date != row[2]
            or str(session.runtime_run_reference.artifact_id) != str(row[3])
            or str(session.runtime_tick_reference.artifact_id) != str(row[4])
            or str(session.research_shadow_reference.artifact_id) != str(row[5])
            or session.status.value != str(row[6])
        ):
            raise PhaseCGateConflict("Strategy Shadow Session owner projection drift")
        session_policy = ValidationArtifactReference.from_canonical_dict(
            _mapping(payload["policy_reference"])
        )
        if session_policy != policy.strategy_policy_reference:
            raise PhaseCGateConflict("Strategy Shadow Session policy hash mismatch")
        session_ids.append(str(row[0]))
        references.append(
            ValidationArtifactReference(
                "STRATEGY_SHADOW_SESSION", ArtifactId(str(row[0])), str(row[1])
            )
        )
        if str(row[6]) == "FAILED":
            failed += 1
            continue
        if str(row[6]) != "SETTLED":
            continue
        settled += 1
        settled_days.add(row[2])
        attempts = connection.execute(
            """
            SELECT status, source_manifest_id, source_manifest_hash
            FROM continuous_provider_attempt
            WHERE run_id = %s AND tick_id = %s
            ORDER BY attempt_number
            """,
            (str(row[3]), str(row[4])),
        ).fetchall()
        successful_attempts = tuple(
            item
            for item in attempts
            if str(item[0]) == "SUCCEEDED"
            and item[1] is not None
            and item[2] is not None
        )
        provider_failures += sum(
            str(item[0]) not in {"STARTED", "SUCCEEDED"} for item in attempts
        )
        if any(str(item[0]) == "STARTED" for item in attempts):
            missing.add("PROVIDER_ATTEMPT_INCOMPLETE")
        if len(successful_attempts) != 1:
            missing.add("SUCCESSFUL_SOURCE_ACQUISITION_MISSING")
        else:
            references.append(
                ValidationArtifactReference(
                    "SOURCE_MANIFEST",
                    ArtifactId(str(successful_attempts[0][1])),
                    str(successful_attempts[0][2]),
                )
            )
        authority = connection.execute(
            """
            SELECT evidence_id, evidence_hash, clock_mode, runtime_origin,
                   payload_json
            FROM continuous_runtime_authority_evidence
            WHERE run_id = %s AND tick_id = %s
            """,
            (str(row[3]), str(row[4])),
        ).fetchone()
        runtime_evidence = None
        if authority is not None:
            try:
                runtime_evidence = _runtime_authority_from_payload(
                    _mapping(authority[4])
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PhaseCGateConflict(
                    "Runtime Authority exact replay failed"
                ) from exc
        if authority is None or runtime_evidence is None or (
            str(authority[0]) != str(runtime_evidence.evidence_id)
            or str(authority[1]) != runtime_evidence.evidence_hash
            or runtime_evidence.clock_mode is not ClockMode.LIVE_TRUSTED
            or runtime_evidence.runtime_origin is not RuntimeOrigin.LIVE_ACQUISITION
            or str(runtime_evidence.run_id) != str(row[3])
            or str(runtime_evidence.tick_id) != str(row[4])
        ):
            missing.add("LIVE_RUNTIME_AUTHORITY_EVIDENCE_MISSING")
        else:
            references.append(
                ValidationArtifactReference(
                    "RUNTIME_AUTHORITY_EVIDENCE",
                    ArtifactId(str(authority[0])),
                    str(authority[1]),
                )
            )
        attestation = connection.execute(
            """
            SELECT attestation_id, attestation_hash,
                   runtime_authority_evidence_id, payload_json
            FROM prospective_evidence_attestation
            WHERE shadow_decision_id = %s AND run_id = %s AND tick_id = %s
              AND status = 'ENGINEERING_ATTESTABLE'
              AND clock_mode = 'LIVE_TRUSTED'
              AND runtime_origin = 'LIVE_ACQUISITION'
            ORDER BY created_at DESC LIMIT 1
            """,
            (str(row[5]), str(row[3]), str(row[4])),
        ).fetchone()
        restored_attestation = None
        if attestation is not None:
            try:
                restored_attestation = (
                    ProspectiveEvidenceAttestation.from_canonical_dict(
                        _mapping(attestation[3])
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PhaseCGateConflict(
                    "Prospective Attestation exact replay failed"
                ) from exc
        if attestation is None or restored_attestation is None or (
            str(attestation[0]) != str(restored_attestation.attestation_id)
            or str(attestation[1]) != restored_attestation.attestation_hash
            or restored_attestation.runtime_authority_evidence is None
            or str(attestation[2])
            != str(restored_attestation.runtime_authority_evidence.artifact_id)
            or authority is None
            or str(attestation[2]) != str(authority[0])
        ):
            missing.add("LIVE_PROSPECTIVE_ATTESTATION_MISSING")
        else:
            references.append(
                ValidationArtifactReference(
                    "PROSPECTIVE_ATTESTATION",
                    ArtifactId(str(attestation[0])),
                    str(attestation[1]),
                )
            )
        factual_outcome = connection.execute(
            """
            SELECT settlement_id, settlement_hash, availability_status,
                   payload_json
            FROM prospective_outcome_settlement
            WHERE shadow_decision_id = %s AND run_id = %s AND tick_id = %s
            """,
            (str(row[5]), str(row[3]), str(row[4])),
        ).fetchall()
        if len(factual_outcome) != 1:
            missing.add("T_PLUS_ONE_FACTUAL_OUTCOME_MISSING")
        else:
            try:
                restored_outcome = ProspectiveShadowOutcome.from_canonical_dict(
                    _mapping(factual_outcome[0][3])
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PhaseCGateConflict(
                    "T+1 factual Outcome exact replay failed"
                ) from exc
            if (
                str(restored_outcome.settlement_id) != str(factual_outcome[0][0])
                or restored_outcome.settlement_hash != str(factual_outcome[0][1])
                or restored_outcome.availability_status
                is not OutcomeAvailabilityStatus.COMPLETE
                or str(factual_outcome[0][2]) != "COMPLETE"
                or str(restored_outcome.shadow_decision.artifact_id) != str(row[5])
                or str(restored_outcome.run_id) != str(row[3])
                or str(restored_outcome.tick_id) != str(row[4])
            ):
                missing.add("T_PLUS_ONE_FACTUAL_OUTCOME_INCOMPLETE")
            else:
                references.append(
                    ValidationArtifactReference(
                        "PROSPECTIVE_SHADOW_OUTCOME",
                        restored_outcome.settlement_id,
                        restored_outcome.settlement_hash,
                    )
                )
        outcome = connection.execute(
            """
            SELECT artifact_id, artifact_hash, payload_json, created_at
            FROM strategy_shadow_artifact
            WHERE session_id = %s AND artifact_kind = 'STRATEGY_OUTCOME'
            """,
            (str(row[0]),),
        ).fetchall()
        strategy_research_sources: set[ValidationArtifactReference] = set()
        if len(outcome) != 1:
            missing.add("STRATEGY_OUTCOME_OWNER_MISSING")
        else:
            try:
                StrategyShadowArtifactRecord(
                    artifact_reference=ValidationArtifactReference(
                        "STRATEGY_OUTCOME",
                        ArtifactId(str(outcome[0][0])),
                        str(outcome[0][1]),
                    ),
                    artifact_kind=StrategyShadowArtifactKind.STRATEGY_OUTCOME,
                    session_id=session.session_id,
                    payload=_mapping(outcome[0][2]),
                    created_at=outcome[0][3],
                )
                restored_strategy_outcome = restore_strategy_shadow_artifact(
                    artifact_kind="STRATEGY_OUTCOME",
                    artifact_id=ArtifactId(str(outcome[0][0])),
                    artifact_hash=str(outcome[0][1]),
                    payload=dict(_mapping(outcome[0][2])),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PhaseCGateConflict(
                    "Strategy Outcome owner replay failed"
                ) from exc
            if not isinstance(restored_strategy_outcome, StrategyOutcome):
                raise PhaseCGateConflict("Strategy Outcome restored invalid type")
            entry_row = connection.execute(
                """
                SELECT artifact_hash, payload_json
                FROM strategy_shadow_artifact
                WHERE session_id = %s AND artifact_kind = 'ENTRY'
                  AND artifact_id = %s
                """,
                (
                    str(row[0]),
                    str(restored_strategy_outcome.entry_reference.artifact_id),
                ),
            ).fetchone()
            if entry_row is None:
                raise PhaseCGateConflict("Strategy Outcome Entry owner is missing")
            try:
                restored_entry = restore_strategy_shadow_artifact(
                    artifact_kind="ENTRY",
                    artifact_id=restored_strategy_outcome.entry_reference.artifact_id,
                    artifact_hash=str(entry_row[0]),
                    payload=dict(_mapping(entry_row[1])),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PhaseCGateConflict("Strategy Entry owner replay failed") from exc
            if (
                not isinstance(restored_entry, ShadowEntry)
                or restored_entry.entry_hash
                != restored_strategy_outcome.entry_reference.content_hash
            ):
                raise PhaseCGateConflict("Strategy Outcome Entry lineage drift")
            entry_assessment = _load_entry_assessment(
                connection, restored_entry.assessment_reference
            )
            strategy_research_sources = {
                item
                for item in entry_assessment.source_references
                if item.artifact_kind in {"CANDIDATE_SET", "RESEARCH_PANEL_V2"}
            }
            if {item.artifact_kind for item in strategy_research_sources} != {
                "CANDIDATE_SET",
                "RESEARCH_PANEL_V2",
            }:
                missing.add("STRATEGY_RESEARCH_LINEAGE_INCOMPLETE")
            references.append(
                ValidationArtifactReference(
                    "STRATEGY_OUTCOME",
                    ArtifactId(str(outcome[0][0])),
                    str(outcome[0][1]),
                )
            )
        portfolio = connection.execute(
            """
            SELECT d.state_id, d.state_hash, d.payload_json
            FROM strategy_shadow_portfolio p
            JOIN strategy_shadow_portfolio_day d ON d.portfolio_id = p.portfolio_id
            WHERE p.policy_id = %s AND p.policy_hash = %s
              AND d.trading_date = %s
            """,
            (
                str(policy.portfolio_policy_reference.artifact_id),
                policy.portfolio_policy_reference.content_hash,
                row[2],
            ),
        ).fetchall()
        if len(portfolio) != 1:
            missing.add("STRATEGY_SHADOW_PORTFOLIO_DAY_MISSING")
        else:
            try:
                portfolio_state = ShadowPortfolioDayState.from_canonical_dict(
                    _mapping(portfolio[0][2])
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PhaseCGateConflict(
                    "Strategy Shadow Portfolio day replay failed"
                ) from exc
            if (
                str(portfolio_state.state_id) != str(portfolio[0][0])
                or portfolio_state.state_hash != str(portfolio[0][1])
                or portfolio_state.policy_reference
                != policy.portfolio_policy_reference
                or portfolio_state.trading_date != row[2]
            ):
                raise PhaseCGateConflict(
                    "Strategy Shadow Portfolio day owner projection drift"
                )
            if not strategy_research_sources.issubset(
                set(portfolio_state.source_references)
            ):
                missing.add("STRATEGY_PORTFOLIO_RESEARCH_LINEAGE_MISMATCH")
            references.append(
                ValidationArtifactReference(
                    "STRATEGY_SHADOW_PORTFOLIO_DAY",
                    ArtifactId(str(portfolio[0][0])),
                    str(portfolio[0][1]),
                )
            )
    if failed:
        return (
            PhaseCStageOutcome.REJECTED,
            ("PROSPECTIVE_STRATEGY_SHADOW_FAILED_SESSION",),
            _ordered_references(references),
        )
    if missing:
        return (
            PhaseCStageOutcome.BLOCKED,
            tuple(sorted(missing)),
            _ordered_references(references),
        )
    incidents = _event_count(connection, session_ids, "INCIDENT_RECORDED")
    drifts = _event_count(connection, session_ids, "DRIFT_RECORDED")
    if incidents > policy.maximum_incidents or drifts > policy.maximum_drifts:
        return (
            PhaseCStageOutcome.REJECTED,
            ("PROSPECTIVE_INCIDENT_OR_DRIFT_FLOOR_EXCEEDED",),
            _ordered_references(references),
        )
    if provider_failures > policy.maximum_provider_failures:
        return (
            PhaseCStageOutcome.REJECTED,
            ("PROSPECTIVE_PROVIDER_FAILURE_FLOOR_EXCEEDED",),
            _ordered_references(references),
        )
    if (
        settled < policy.minimum_sessions
        or len(settled_days) < policy.minimum_distinct_days
    ):
        return (
            PhaseCStageOutcome.ACCUMULATING,
            ("PROSPECTIVE_DURATION_OR_SESSION_FLOOR_ACCUMULATING",),
            _ordered_references(references),
        )
    return PhaseCStageOutcome.SATISFIED, (), _ordered_references(references)


def _record_entry_holding_exit_policy(
    connection: Any,
    *,
    formal_protocol_id: ArtifactId | None,
    policy: EntryHoldingExitQualificationPolicy,
) -> None:
    if formal_protocol_id is not None:
        formal = _load_formal_protocol(connection, formal_protocol_id)
        expected = ValidationArtifactReference(
            "ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY",
            policy.policy_id,
            policy.policy_hash,
        )
        if formal.entry_holding_exit_qualification_policy_reference != expected:
            raise PhaseCGateConflict(
                "Formal Protocol Entry/Holding/Exit Policy identity mismatch"
            )
        if policy.locked_at > formal.locked_at:
            raise PhaseCGateConflict(
                "Entry/Holding/Exit Policy was not locked before the Formal Protocol"
            )
        if (
            formal.strategy_policy_reference != policy.strategy_policy_reference
            or formal.cost_policy_reference != policy.portfolio_policy_reference
        ):
            raise PhaseCGateConflict(
                "Formal Protocol strategy/cost policy lineage mismatch"
            )
    model_rows = connection.execute(
        """
        SELECT artifact_hash, artifact_kind, payload_json
        FROM research_validation_artifact WHERE artifact_id = %s
        """,
        (str(policy.entry_model_reference.artifact_id),),
    ).fetchall()
    if len(model_rows) != 1 or (
        str(model_rows[0][0]) != policy.entry_model_reference.content_hash
        or str(model_rows[0][1]) != "ENTRY_RESEARCH_MODEL"
    ):
        raise PhaseCGateConflict("Entry Research Model owner mismatch")
    try:
        EntryResearchModel.from_canonical_dict(
            model_id=ModelId(str(policy.entry_model_reference.artifact_id)),
            model_hash=str(model_rows[0][0]),
            value=dict(_mapping(model_rows[0][2])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Entry Research Model exact replay failed") from exc
    strategy_rows = connection.execute(
        """
        SELECT policy_hash, policy_json
        FROM strategy_shadow_policy_authority WHERE policy_id = %s
        """,
        (str(policy.strategy_policy_reference.artifact_id),),
    ).fetchall()
    if len(strategy_rows) != 1 or str(strategy_rows[0][0]) != (
        policy.strategy_policy_reference.content_hash
    ):
        raise PhaseCGateConflict("Strategy Shadow Policy owner mismatch")
    try:
        restore_strategy_shadow_artifact(
            artifact_kind="POLICY",
            artifact_id=policy.strategy_policy_reference.artifact_id,
            artifact_hash=str(strategy_rows[0][0]),
            payload=dict(_mapping(strategy_rows[0][1])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Strategy Shadow Policy exact replay failed") from exc
    portfolio_rows = connection.execute(
        """
        SELECT policy_hash, policy_json
        FROM strategy_shadow_portfolio WHERE policy_id = %s
        """,
        (str(policy.portfolio_policy_reference.artifact_id),),
    ).fetchall()
    if len(portfolio_rows) != 1 or str(portfolio_rows[0][0]) != (
        policy.portfolio_policy_reference.content_hash
    ):
        raise PhaseCGateConflict("Shadow Portfolio Policy owner mismatch")
    try:
        ShadowPortfolioPolicy.from_canonical_dict(_mapping(portfolio_rows[0][1]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Shadow Portfolio Policy exact replay failed") from exc
    now = _postgres_now(connection)
    connection.execute(
        """
        INSERT INTO entry_holding_exit_qualification_policy(
            policy_id, policy_hash, entry_model_id, strategy_policy_id,
            portfolio_policy_id, policy_json, locked_at, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (policy_id) DO NOTHING
        """,
        (
            str(policy.policy_id),
            policy.policy_hash,
            str(policy.entry_model_reference.artifact_id),
            str(policy.strategy_policy_reference.artifact_id),
            str(policy.portfolio_policy_reference.artifact_id),
            Jsonb(policy.to_canonical_dict()),
            policy.locked_at,
            now,
        ),
    )
    stored = connection.execute(
        """
        SELECT policy_hash, policy_json
        FROM entry_holding_exit_qualification_policy WHERE policy_id = %s
        """,
        (str(policy.policy_id),),
    ).fetchone()
    if stored is None or (
        str(stored[0]) != policy.policy_hash
        or stored[1] != policy.to_canonical_dict()
    ):
        raise PhaseCGateConflict(
            "Entry/Holding/Exit Policy immutable identity conflict"
        )


def _assess_entry_holding_exit(
    connection: Any,
    *,
    formal_protocol_id: ArtifactId,
    policy: EntryHoldingExitQualificationPolicy | None,
) -> tuple[
    PhaseCStageOutcome,
    tuple[str, ...],
    tuple[ValidationArtifactReference, ...],
]:
    formal = _load_formal_protocol(connection, formal_protocol_id)
    oos = _latest_formal_oos_reference(
        connection, formal_protocol_id=formal_protocol_id
    )
    calibration = _latest_calibration_reference(
        connection, formal_protocol_id=formal_protocol_id
    )
    references = [item for item in (oos[0], calibration[0]) if item]
    reasons: set[str] = set()
    outcomes: list[str] = []
    if policy is None:
        reasons.add("ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY_MISSING")
    else:
        references.append(
            ValidationArtifactReference(
                "ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY",
                policy.policy_id,
                policy.policy_hash,
            )
        )
    if oos[0] is None:
        reasons.add("FORMAL_OOS_QUALIFICATION_MISSING")
    else:
        outcomes.append(oos[1])
    if calibration[0] is None:
        reasons.add("CALIBRATION_QUALIFICATION_MISSING")
    else:
        outcomes.append(calibration[1])
    if reasons:
        return (
            PhaseCStageOutcome.BLOCKED,
            tuple(sorted(reasons)),
            _ordered_references(references),
        )
    if any(item == "REJECTED" for item in outcomes):
        return (
            PhaseCStageOutcome.REJECTED,
            ("UPSTREAM_FORMAL_EVIDENCE_REJECTED",),
            _ordered_references(references),
        )
    if any(item == "NOT_ESTIMABLE" for item in outcomes):
        return (
            PhaseCStageOutcome.NOT_ESTIMABLE,
            ("UPSTREAM_FORMAL_EVIDENCE_NOT_ESTIMABLE",),
            _ordered_references(references),
        )
    if any(item != "SATISFIED" for item in outcomes):
        return (
            PhaseCStageOutcome.BLOCKED,
            ("UPSTREAM_FORMAL_EVIDENCE_BLOCKED",),
            _ordered_references(references),
        )
    assert policy is not None and oos[0] is not None
    evaluation = _load_formal_evaluation_protocol(connection, formal)
    locked_windows = tuple(
        item
        for item in evaluation.windows
        if item.partition is EvaluationPartition.LOCKED_OOS
    )
    rows = connection.execute(
        """
        SELECT session_id, session_hash, trading_date, runtime_run_id,
               runtime_tick_id, research_shadow_id, status, payload_json
        FROM strategy_shadow_session
        WHERE policy_id = %s AND status = 'SETTLED'
          AND created_at >= %s AND scheduled_for >= %s
        ORDER BY trading_date, session_id
        """,
        (
            str(policy.strategy_policy_reference.artifact_id),
            policy.locked_at,
            policy.locked_at,
        ),
    ).fetchall()
    rows = tuple(
        row
        for row in rows
        if any(
            window.start_date <= row[2] <= window.end_date
            for window in locked_windows
        )
    )
    if not rows:
        return (
            PhaseCStageOutcome.NOT_ESTIMABLE,
            ("LOCKED_OOS_ENTRY_HOLDING_EXIT_SAMPLE_NOT_ESTIMABLE",),
            _ordered_references(references),
        )
    allowed = set(policy.allowed_result_provenance)
    portfolio_policy = _load_portfolio_policy(
        connection, policy.portfolio_policy_reference
    )
    if any(item.provenance not in allowed for item in portfolio_policy.parameters):
        return (
            PhaseCStageOutcome.REJECTED,
            ("COST_CAPACITY_PARAMETER_PROVENANCE_REJECTED",),
            _ordered_references(references),
        )
    resolved_outcomes: list[StrategyOutcome] = []
    observed_rules: set[HoldingRuleKind] = set()
    provenance_rejected = False
    for row in rows:
        session = _restore_strategy_session(connection, row)
        session_reference = ValidationArtifactReference(
            "STRATEGY_SHADOW_SESSION",
            session.session_id,
            session.session_hash,
        )
        references.append(session_reference)
        artifacts = connection.execute(
            """
            SELECT artifact_id, artifact_hash, artifact_kind,
                   payload_json, created_at
            FROM strategy_shadow_artifact WHERE session_id = %s
            ORDER BY artifact_kind, created_at, artifact_id
            """,
            (str(session.session_id),),
        ).fetchall()
        restored: dict[tuple[str, str], Any] = {}
        liquidity_payloads: list[Mapping[str, Any]] = []
        for artifact in artifacts:
            kind = str(artifact[2])
            if kind == "LIQUIDITY_OBSERVATION":
                if canonical_hash(dict(_mapping(artifact[3]))) != str(artifact[1]):
                    raise PhaseCGateConflict(
                        "Strategy liquidity observation hash mismatch"
                    )
                liquidity_payloads.append(_mapping(artifact[3]))
                references.append(
                    ValidationArtifactReference(
                        "FREE_DATA_SHADOW_LIQUIDITY_OBSERVATION",
                        ArtifactId(str(artifact[0])),
                        str(artifact[1]),
                    )
                )
                continue
            try:
                value = restore_strategy_shadow_artifact(
                    artifact_kind=kind,
                    artifact_id=ArtifactId(str(artifact[0])),
                    artifact_hash=str(artifact[1]),
                    payload=dict(_mapping(artifact[3])),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PhaseCGateConflict(
                    "Strategy Shadow qualification artifact replay failed"
                ) from exc
            restored[(kind, str(artifact[0]))] = value
        outcome_values = tuple(
            item for (kind, _artifact_id), item in restored.items()
            if kind == "STRATEGY_OUTCOME"
        )
        if len(outcome_values) != 1 or not isinstance(
            outcome_values[0], StrategyOutcome
        ):
            raise PhaseCGateConflict("Strategy Outcome owner is not unique")
        outcome = outcome_values[0]
        entry = restored.get(("ENTRY", str(outcome.entry_reference.artifact_id)))
        fill = restored.get(("FILL", str(outcome.fill_reference.artifact_id)))
        position = restored.get(
            ("POSITION", str(outcome.position_reference.artifact_id))
        )
        exit_value = restored.get(
            ("EXIT_ASSESSMENT", str(outcome.exit_reference.artifact_id))
        )
        if (
            not isinstance(entry, ShadowEntry)
            or not isinstance(fill, ShadowFill)
            or not isinstance(position, ShadowPosition)
            or exit_value is None
            or entry.policy_reference != policy.strategy_policy_reference
            or fill.entry_reference != outcome.entry_reference
            or position.fill_reference != outcome.fill_reference
        ):
            raise PhaseCGateConflict("Strategy Outcome lineage replay mismatch")
        assessment = _load_entry_assessment(
            connection, entry.assessment_reference
        )
        if (
            assessment.model_reference != policy.entry_model_reference
            or assessment.decision is not EntryResearchDecision.SHADOW_ENTER
            or assessment.symbol != outcome.symbol
        ):
            raise PhaseCGateConflict("Entry assessment/outcome lineage mismatch")
        required_sources = {
            ("FORMAL_RESEARCH_PROTOCOL", str(formal.protocol_id), formal.protocol_hash),
            (oos[0].artifact_kind, str(oos[0].artifact_id), oos[0].content_hash),
        }
        actual_sources = {
            (item.artifact_kind, str(item.artifact_id), item.content_hash)
            for item in assessment.source_references
        }
        if not required_sources.issubset(actual_sources):
            provenance_rejected = True
        if len(liquidity_payloads) != 1:
            raise PhaseCGateConflict(
                "Strategy Outcome requires one liquidity observation"
            )
        provenance = {
            str(item[0]): ShadowParameterProvenance(str(item[1]))
            for item in _sequence(liquidity_payloads[0]["value_provenance"])
        }
        required_provenance = {
            "fillability",
            "slippage_bps",
            "impact_bps",
            "commission_bps",
            "exit_cost",
            "mfe",
            "mae",
        }
        if (
            not required_provenance.issubset(provenance)
            or any(provenance[name] not in allowed for name in required_provenance)
        ):
            provenance_rejected = True
        references.extend(
            (
                entry.assessment_reference,
                ValidationArtifactReference(
                    "STRATEGY_OUTCOME", outcome.outcome_id, outcome.outcome_hash
                ),
            )
        )
        resolved_outcomes.append(outcome)
        observed_rules.update(outcome.exit_rule_kinds)
    if provenance_rejected:
        return (
            PhaseCStageOutcome.REJECTED,
            ("FORMAL_ENTRY_OR_COST_PROVENANCE_REJECTED",),
            _ordered_references(references),
        )
    if len(resolved_outcomes) < policy.minimum_samples or any(
        item.mae is None for item in resolved_outcomes
    ):
        return (
            PhaseCStageOutcome.NOT_ESTIMABLE,
            ("ENTRY_HOLDING_EXIT_SAMPLE_FLOOR_NOT_ESTIMABLE",),
            _ordered_references(references),
        )
    count = Decimal(len(resolved_outcomes))
    hit_rate = Decimal(
        sum(item.net_return > 0 for item in resolved_outcomes)
    ) / count
    mean_net = sum(
        (item.net_return for item in resolved_outcomes), Decimal("0")
    ) / count
    mean_mae = sum(
        (item.mae for item in resolved_outcomes if item.mae is not None),
        Decimal("0"),
    ) / count
    if (
        hit_rate < policy.minimum_hit_rate
        or mean_net < policy.minimum_cost_adjusted_return
        or mean_mae < policy.maximum_mean_mae
        or not set(policy.required_exit_rule_coverage).issubset(observed_rules)
    ):
        return (
            PhaseCStageOutcome.REJECTED,
            ("ENTRY_HOLDING_EXIT_ECONOMIC_FLOOR_REJECTED",),
            _ordered_references(references),
        )
    approval = _approved_research_change(
        connection,
        ValidationArtifactReference(
            "ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY",
            policy.policy_id,
            policy.policy_hash,
        ),
    )
    if approval is None:
        return (
            PhaseCStageOutcome.BLOCKED,
            ("INDEPENDENT_GOVERNANCE_APPROVAL_MISSING",),
            _ordered_references(references),
        )
    references.append(approval)
    return PhaseCStageOutcome.SATISFIED, (), _ordered_references(references)


def _event_count(
    connection: Any, session_ids: list[str], event_kind: str
) -> int:
    if not session_ids:
        return 0
    row = connection.execute(
        """
        SELECT count(*) FROM strategy_shadow_event
        WHERE session_id = ANY(%s) AND event_kind = %s
        """,
        (session_ids, event_kind),
    ).fetchone()
    return int(row[0])


def _record_prospective_policy(
    connection: Any, policy: ProspectiveShadowQualificationPolicy
) -> None:
    owner = connection.execute(
        """
        SELECT policy_hash, policy_json
        FROM strategy_shadow_policy_authority
        WHERE policy_id = %s
        """,
        (str(policy.strategy_policy_reference.artifact_id),),
    ).fetchall()
    portfolio_owner = connection.execute(
        """
        SELECT policy_hash, policy_json FROM strategy_shadow_portfolio
        WHERE policy_id = %s
        """,
        (str(policy.portfolio_policy_reference.artifact_id),),
    ).fetchall()
    if len(owner) != 1 or str(owner[0][0]) != (
        policy.strategy_policy_reference.content_hash
    ):
        raise PhaseCGateConflict("Strategy Shadow Policy owner mismatch")
    if len(portfolio_owner) != 1 or str(portfolio_owner[0][0]) != (
        policy.portfolio_policy_reference.content_hash
    ):
        raise PhaseCGateConflict("Shadow Portfolio Policy owner mismatch")
    try:
        restore_strategy_shadow_artifact(
            artifact_kind="POLICY",
            artifact_id=policy.strategy_policy_reference.artifact_id,
            artifact_hash=str(owner[0][0]),
            payload=dict(_mapping(owner[0][1])),
        )
        ShadowPortfolioPolicy.from_canonical_dict(_mapping(portfolio_owner[0][1]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict(
            "Prospective Shadow Policy owner replay failed"
        ) from exc
    now = _postgres_now(connection)
    connection.execute(
        """
        INSERT INTO prospective_shadow_qualification_policy(
            policy_id, policy_hash, strategy_policy_id,
            strategy_policy_hash, portfolio_policy_id,
            portfolio_policy_hash, payload_json, locked_at, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (policy_id) DO NOTHING
        """,
        (
            str(policy.policy_id),
            policy.policy_hash,
            str(policy.strategy_policy_reference.artifact_id),
            policy.strategy_policy_reference.content_hash,
            str(policy.portfolio_policy_reference.artifact_id),
            policy.portfolio_policy_reference.content_hash,
            Jsonb(policy.to_canonical_dict()),
            policy.locked_at,
            now,
        ),
    )
    row = connection.execute(
        """
        SELECT policy_hash, payload_json
        FROM prospective_shadow_qualification_policy WHERE policy_id = %s
        """,
        (str(policy.policy_id),),
    ).fetchone()
    if row is None or (
        str(row[0]) != policy.policy_hash
        or row[1] != policy.to_canonical_dict()
    ):
        raise PhaseCGateConflict("Prospective Shadow Policy identity conflict")


def _resolve_admission_floors(
    connection: Any, *, formal_protocol_id: ArtifactId
) -> tuple[AdmissionFloorAssessment, ...]:
    results: dict[AdmissionFloor, AdmissionFloorAssessment] = {}
    oos = _latest_formal_oos_reference(
        connection, formal_protocol_id=formal_protocol_id
    )
    calibration = _latest_calibration_reference(
        connection, formal_protocol_id=formal_protocol_id
    )
    strategy = _latest_stage_reference(
        connection,
        stage=PhaseCStage.ENTRY_HOLDING_EXIT_QUALIFICATION,
        scope_id=str(formal_protocol_id),
        kind="ENTRY_HOLDING_EXIT_QUALIFICATION_DECISION",
    )
    shadow = _latest_shadow_reference_for_protocol(
        connection, formal_protocol_id=formal_protocol_id
    )
    pit_reference = _formal_pit_reference_from_oos(connection, oos[0])
    results[AdmissionFloor.FORMAL_PIT] = _floor(
        AdmissionFloor.FORMAL_PIT,
        pit_reference,
        "SATISFIED" if pit_reference is not None else "MISSING",
    )
    results[AdmissionFloor.FORMAL_OOS] = _floor(
        AdmissionFloor.FORMAL_OOS, oos[0], oos[1]
    )
    results[AdmissionFloor.ECONOMIC_VALIDATION] = _floor(
        AdmissionFloor.ECONOMIC_VALIDATION, oos[0], oos[1]
    )
    results[AdmissionFloor.CALIBRATION] = _floor(
        AdmissionFloor.CALIBRATION, calibration[0], calibration[1]
    )
    results[AdmissionFloor.ENTRY_QUALIFICATION] = _floor(
        AdmissionFloor.ENTRY_QUALIFICATION, strategy[0], strategy[1]
    )
    results[AdmissionFloor.HOLDING_EXIT_VALIDATION] = _floor(
        AdmissionFloor.HOLDING_EXIT_VALIDATION, strategy[0], strategy[1]
    )
    results[AdmissionFloor.SUSTAINED_STRATEGY_SHADOW] = _floor(
        AdmissionFloor.SUSTAINED_STRATEGY_SHADOW, shadow[0], shadow[1]
    )
    for floor, code in (
        (AdmissionFloor.COST_CAPACITY, "OWNER_RESOLVED_COST_CAPACITY_MISSING"),
        (AdmissionFloor.AUTH_RBAC, "EXTERNAL_AUTHENTICATION_NOT_BOUND"),
        (AdmissionFloor.OPERATOR_APPROVAL, "PRODUCTION_OPERATOR_APPROVAL_MISSING"),
        (AdmissionFloor.BROKER_READINESS, "BROKER_READINESS_EVIDENCE_MISSING"),
    ):
        results[floor] = AdmissionFloorAssessment(
            floor=floor,
            status=AdmissionFloorStatus.MISSING,
            evidence_reference=None,
            reason_codes=(code,),
        )
    return tuple(results[item] for item in sorted(AdmissionFloor, key=lambda x: x.value))


def _floor(
    floor: AdmissionFloor,
    reference: ValidationArtifactReference | None,
    outcome: str,
) -> AdmissionFloorAssessment:
    status = {
        "SATISFIED": AdmissionFloorStatus.SATISFIED,
        "REJECTED": AdmissionFloorStatus.REJECTED,
        "NOT_ESTIMABLE": AdmissionFloorStatus.BLOCKED,
        "BLOCKED": AdmissionFloorStatus.BLOCKED,
        "ACCUMULATING": AdmissionFloorStatus.BLOCKED,
        "MISSING": AdmissionFloorStatus.MISSING,
    }.get(outcome, AdmissionFloorStatus.MISSING)
    reasons = () if status is AdmissionFloorStatus.SATISFIED else (
        f"{floor.value}_{outcome or 'MISSING'}",
    )
    return AdmissionFloorAssessment(floor, status, reference, reasons)


def _formal_pit_reference_from_oos(
    connection: Any, oos_reference: ValidationArtifactReference | None
) -> ValidationArtifactReference | None:
    if oos_reference is None:
        return None
    oos_row = connection.execute(
        """
        SELECT decision_hash, payload_json
        FROM formal_oos_qualification_decision WHERE decision_id = %s
        """,
        (str(oos_reference.artifact_id),),
    ).fetchone()
    if oos_row is None:
        return None
    try:
        oos = FormalOOSQualificationDecision.from_canonical_dict(
            _mapping(oos_row[1])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Formal OOS owner replay failed") from exc
    if (
        oos.decision_id != oos_reference.artifact_id
        or oos.decision_hash != oos_reference.content_hash
        or oos.decision_hash != str(oos_row[0])
        or not oos.formal_oos_passed
    ):
        return None
    pit_ref = oos.formal_pit_reference
    row = connection.execute(
        """
        SELECT evidence_hash, payload_json
        FROM formal_pit_validation_evidence WHERE evidence_id = %s
        """,
        (str(pit_ref.artifact_id),),
    ).fetchone()
    if row is None:
        return None
    try:
        pit = FormalPITEvidenceArtifact.from_canonical_dict(_mapping(row[1]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Formal PIT owner replay failed") from exc
    if (
        pit.evidence_id != pit_ref.artifact_id
        or pit.evidence_hash != pit_ref.content_hash
        or pit.evidence_hash != str(row[0])
        or pit.outcome is not PITValidationOutcome.SATISFIED
    ):
        return None
    return pit_ref


def _latest_shadow_reference_for_protocol(
    connection: Any, *, formal_protocol_id: ArtifactId
) -> tuple[ValidationArtifactReference | None, str]:
    row = connection.execute(
        """
        SELECT d.decision_id, d.decision_hash, d.outcome, d.payload_json,
               p.policy_id, p.policy_hash
        FROM phase_c_stage_decision d
        JOIN prospective_shadow_qualification_policy p
          ON p.policy_id = d.policy_id
        JOIN formal_research_protocol f ON f.protocol_id = %s
        WHERE d.stage = 'PROSPECTIVE_STRATEGY_SHADOW'
          AND p.strategy_policy_id =
              f.payload_json->'strategy_policy_reference'->>'artifact_id'
          AND p.strategy_policy_hash =
              f.payload_json->'strategy_policy_reference'->>'content_hash'
        ORDER BY d.revision DESC LIMIT 1
        """,
        (str(formal_protocol_id),),
    ).fetchone()
    if row is None:
        return None, "MISSING"
    try:
        decision = PhaseCStageDecision.from_canonical_dict(_mapping(row[3]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Prospective Shadow decision replay failed") from exc
    expected_policy = ValidationArtifactReference(
        "PROSPECTIVE_SHADOW_QUALIFICATION_POLICY",
        ArtifactId(str(row[4])),
        str(row[5]),
    )
    if (
        decision.decision_id != ArtifactId(str(row[0]))
        or decision.decision_hash != str(row[1])
        or decision.outcome.value != str(row[2])
        or decision.stage is not PhaseCStage.PROSPECTIVE_STRATEGY_SHADOW
        or decision.scope_id != str(row[4])
        or decision.policy_reference != expected_policy
    ):
        raise PhaseCGateConflict("Prospective Shadow decision owner drift")
    return (
        ValidationArtifactReference(
            "PROSPECTIVE_STRATEGY_SHADOW_DECISION",
            decision.decision_id,
            decision.decision_hash,
        ),
        decision.outcome.value,
    )


def _latest_formal_oos_reference(
    connection: Any, *, formal_protocol_id: ArtifactId
) -> tuple[ValidationArtifactReference | None, str]:
    row = connection.execute(
        """
        SELECT decision_id, decision_hash, outcome, payload_json
        FROM formal_oos_qualification_decision
        WHERE formal_protocol_id = %s
        ORDER BY revision DESC LIMIT 1
        """,
        (str(formal_protocol_id),),
    ).fetchone()
    if row is None:
        return None, "MISSING"
    try:
        decision = FormalOOSQualificationDecision.from_canonical_dict(
            _mapping(row[3])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Formal OOS decision replay failed") from exc
    if (
        decision.decision_id != ArtifactId(str(row[0]))
        or decision.decision_hash != str(row[1])
        or decision.outcome.value != str(row[2])
        or decision.formal_protocol_reference.artifact_id != formal_protocol_id
    ):
        raise PhaseCGateConflict("Formal OOS decision owner drift")
    return (
        ValidationArtifactReference(
            "FORMAL_OOS_QUALIFICATION_DECISION",
            decision.decision_id,
            decision.decision_hash,
        ),
        decision.outcome.value,
    )


def _latest_calibration_reference(
    connection: Any, *, formal_protocol_id: ArtifactId
) -> tuple[ValidationArtifactReference | None, str]:
    row = connection.execute(
        """
        SELECT decision_id, decision_hash, outcome, payload_json
        FROM calibration_qualification_decision
        WHERE formal_protocol_id = %s
        ORDER BY revision DESC LIMIT 1
        """,
        (str(formal_protocol_id),),
    ).fetchone()
    if row is None:
        return None, "MISSING"
    try:
        decision = CalibrationQualificationDecision.from_canonical_dict(
            _mapping(row[3])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Calibration decision replay failed") from exc
    if (
        decision.decision_id != ArtifactId(str(row[0]))
        or decision.decision_hash != str(row[1])
        or decision.outcome.value != str(row[2])
        or decision.formal_protocol_reference.artifact_id != formal_protocol_id
    ):
        raise PhaseCGateConflict("Calibration decision owner drift")
    return (
        ValidationArtifactReference(
            "CALIBRATION_QUALIFICATION_DECISION",
            decision.decision_id,
            decision.decision_hash,
        ),
        decision.outcome.value,
    )


def _latest_stage_reference(
    connection: Any,
    *,
    stage: PhaseCStage,
    scope_id: str,
    kind: str,
) -> tuple[ValidationArtifactReference | None, str]:
    row = connection.execute(
        """
        SELECT decision_id, decision_hash, outcome, payload_json
        FROM phase_c_stage_decision
        WHERE stage = %s AND scope_id = %s
        ORDER BY revision DESC LIMIT 1
        """,
        (stage.value, scope_id),
    ).fetchone()
    if row is None:
        return None, "MISSING"
    try:
        decision = PhaseCStageDecision.from_canonical_dict(_mapping(row[3]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Phase C Stage decision replay failed") from exc
    if (
        decision.decision_id != ArtifactId(str(row[0]))
        or decision.decision_hash != str(row[1])
        or decision.outcome.value != str(row[2])
        or decision.stage is not stage
        or decision.scope_id != scope_id
    ):
        raise PhaseCGateConflict("Phase C Stage decision owner drift")
    return (
        ValidationArtifactReference(kind, decision.decision_id, decision.decision_hash),
        decision.outcome.value,
    )


def _latest_production_admission_reference(
    connection: Any, *, formal_protocol_id: ArtifactId
) -> tuple[ValidationArtifactReference | None, str]:
    row = connection.execute(
        """
        SELECT decision_id, decision_hash, status, payload_json
        FROM production_admission_decision_authority
        WHERE formal_protocol_id = %s
        ORDER BY revision DESC LIMIT 1
        """,
        (str(formal_protocol_id),),
    ).fetchone()
    if row is None:
        return None, "MISSING"
    payload = dict(_mapping(row[3]))
    payload.pop("owner_actor", None)
    payload.pop("owner_reason", None)
    try:
        decision = production_admission_from_canonical_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Production Admission replay failed") from exc
    if (
        decision.decision_id != ArtifactId(str(row[0]))
        or decision.decision_hash != str(row[1])
        or decision.status.value != str(row[2])
    ):
        raise PhaseCGateConflict("Production Admission owner drift")
    return (
        ValidationArtifactReference(
            "PRODUCTION_ADMISSION_DECISION",
            decision.decision_id,
            decision.decision_hash,
        ),
        decision.status.value,
    )


def _formal_protocol_reference(
    connection: Any, formal_protocol_id: ArtifactId
) -> ValidationArtifactReference:
    row = connection.execute(
        """
        SELECT protocol_hash FROM formal_research_protocol WHERE protocol_id = %s
        """,
        (str(formal_protocol_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(formal_protocol_id))
    return ValidationArtifactReference(
        "FORMAL_RESEARCH_PROTOCOL", formal_protocol_id, str(row[0])
    )


def _duplicate_command(
    connection: Any,
    *,
    idempotency_key: str,
    command_hash: str,
    result_kind: str,
) -> ArtifactId | None:
    row = connection.execute(
        """
        SELECT command_hash, result_kind, result_id
        FROM phase_c_gate_command WHERE idempotency_key = %s
        """,
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    if str(row[0]) != command_hash or str(row[1]) != result_kind:
        raise PhaseCGateConflict("Phase C gate idempotency conflict")
    return ArtifactId(str(row[2]))


def _record_command(
    connection: Any,
    *,
    idempotency_key: str,
    command_hash: str,
    result_kind: str,
    result_id: ArtifactId,
    created_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO phase_c_gate_command(
            idempotency_key, command_hash, result_kind, result_id, created_at
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (idempotency_key, command_hash, result_kind, str(result_id), created_at),
    )


def _ordered_references(
    values: list[ValidationArtifactReference],
) -> tuple[ValidationArtifactReference, ...]:
    return tuple(
        sorted(
            set(values),
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


def _load_formal_protocol(
    connection: Any, protocol_id: ArtifactId
) -> FormalResearchProtocol:
    try:
        return load_formal_protocol_owner(connection, protocol_id)
    except (FormalProtocolConflict, KeyError) as exc:
        raise PhaseCGateConflict("Formal Research Protocol replay failed") from exc


def _load_formal_evaluation_protocol(
    connection: Any, formal: FormalResearchProtocol
) -> FormalEvaluationProtocol:
    row = connection.execute(
        """
        SELECT artifact_hash, payload_json
        FROM research_validation_artifact
        WHERE artifact_id = %s AND artifact_kind = 'FORMAL_EVALUATION_PROTOCOL'
        """,
        (str(formal.evaluation_protocol_reference.artifact_id),),
    ).fetchone()
    if row is None or str(row[0]) != (
        formal.evaluation_protocol_reference.content_hash
    ):
        raise PhaseCGateConflict("Formal Evaluation Protocol owner mismatch")
    payload = {
        "protocol_id": str(formal.evaluation_protocol_reference.artifact_id),
        "protocol_hash": str(row[0]),
        **dict(_mapping(row[1])),
    }
    try:
        return FormalEvaluationProtocol.from_canonical_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Formal Evaluation Protocol replay failed") from exc


def _load_portfolio_policy(
    connection: Any, reference: ValidationArtifactReference
) -> ShadowPortfolioPolicy:
    row = connection.execute(
        """
        SELECT policy_hash, policy_json
        FROM strategy_shadow_portfolio WHERE policy_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchone()
    if row is None or str(row[0]) != reference.content_hash:
        raise PhaseCGateConflict("Shadow Portfolio Policy owner mismatch")
    try:
        return ShadowPortfolioPolicy.from_canonical_dict(_mapping(row[1]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Shadow Portfolio Policy replay failed") from exc


def _load_entry_assessment(
    connection: Any, reference: ValidationArtifactReference
) -> EntryResearchAssessment:
    row = connection.execute(
        """
        SELECT artifact_hash, artifact_kind, payload_json
        FROM research_validation_artifact WHERE artifact_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchone()
    if row is None or (
        str(row[0]) != reference.content_hash
        or str(row[1]) != "ENTRY_RESEARCH_ASSESSMENT"
    ):
        raise PhaseCGateConflict("Entry Research Assessment owner mismatch")
    try:
        return EntryResearchAssessment.from_canonical_dict(
            assessment_id=reference.artifact_id,
            assessment_hash=str(row[0]),
            value=dict(_mapping(row[2])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Entry Research Assessment replay failed") from exc


def _restore_strategy_session(connection: Any, row: Any) -> Any:
    event_rows = connection.execute(
        """
        SELECT payload_json FROM strategy_shadow_event
        WHERE session_id = %s ORDER BY sequence
        """,
        (str(row[0]),),
    ).fetchall()
    try:
        session = strategy_shadow_session_from_canonical_dict(
            {
                **dict(_mapping(row[7])),
                "events": [dict(_mapping(item[0])) for item in event_rows],
            }
        )
        replay_strategy_shadow(session)
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Strategy Shadow Session exact replay failed") from exc
    if (
        str(session.session_id) != str(row[0])
        or session.session_hash != str(row[1])
        or session.trading_date != row[2]
        or str(session.runtime_run_reference.artifact_id) != str(row[3])
        or str(session.runtime_tick_reference.artifact_id) != str(row[4])
        or str(session.research_shadow_reference.artifact_id) != str(row[5])
        or session.status.value != str(row[6])
    ):
        raise PhaseCGateConflict("Strategy Shadow Session owner projection drift")
    return session


def _approved_research_change(
    connection: Any, resource: ValidationArtifactReference
) -> ValidationArtifactReference | None:
    row = connection.execute(
        """
        WITH latest_status AS (
            SELECT DISTINCT ON (principal_id) principal_id, status
            FROM security_principal_status_event
            ORDER BY principal_id, sequence DESC
        ), latest_approver AS (
            SELECT DISTINCT ON (principal_id) principal_id, event_kind
            FROM security_role_event
            WHERE role = 'APPROVER'
            ORDER BY principal_id, sequence DESC
        )
        SELECT a.payload_json, a.approval_hash,
               d.payload_json, d.decision_hash
        FROM security_approval a
        JOIN security_approval_decision d ON d.approval_id = a.approval_id
        JOIN latest_status s ON s.principal_id = d.decided_by
        JOIN latest_approver r ON r.principal_id = d.decided_by
        WHERE a.action_kind = 'RESEARCH_CHANGE'
          AND a.resource_kind = %s AND a.resource_id = %s
          AND a.resource_hash = %s AND d.decision = 'APPROVED'
          AND s.status = 'ACTIVE' AND r.event_kind = 'GRANTED'
        ORDER BY d.decided_at DESC, d.decision_id DESC LIMIT 1
        """,
        (
            resource.artifact_kind,
            str(resource.artifact_id),
            resource.content_hash,
        ),
    ).fetchone()
    if row is None:
        return None
    try:
        approval = SecurityApproval.from_canonical_dict(_mapping(row[0]))
        decision = SecurityApprovalDecision.from_canonical_dict(_mapping(row[2]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseCGateConflict("Governance Approval replay failed") from exc
    if (
        approval.approval_hash != str(row[1])
        or approval.action_kind is not ApprovalAction.RESEARCH_CHANGE
        or approval.resource_reference != resource
        or decision.decision_hash != str(row[3])
        or decision.decision is not ApprovalDecisionKind.APPROVED
        or decision.approval_reference.artifact_id != approval.approval_id
        or decision.approval_reference.content_hash != approval.approval_hash
    ):
        raise PhaseCGateConflict("Governance Approval owner projection drift")
    return ValidationArtifactReference(
        "SECURITY_APPROVAL_DECISION",
        decision.decision_id,
        decision.decision_hash,
    )


def _postgres_now(connection: Any) -> datetime:
    return connection.execute(
        "SELECT date_trunc('second', clock_timestamp())"
    ).fetchone()[0]


def _runtime_authority_from_payload(
    value: Mapping[str, Any],
) -> RuntimeAuthorityEvidence:
    return RuntimeAuthorityEvidence(
        evidence_id=ArtifactId(str(value["evidence_id"])),
        evidence_hash=str(value["evidence_hash"]),
        run_id=ArtifactId(str(value["run_id"])),
        tick_id=ArtifactId(str(value["tick_id"])),
        clock_mode=ClockMode(str(value["clock_mode"])),
        runtime_origin=RuntimeOrigin(str(value["runtime_origin"])),
        clock_source=str(value["clock_source"]),
        origin_source=str(value["origin_source"]),
        observed_at=datetime.fromisoformat(str(value["observed_at"])),
        recorded_at=datetime.fromisoformat(str(value["recorded_at"])),
        code_revision=str(value["code_revision"]),
        schema_version=str(value["schema_version"]),
    )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PhaseCGateConflict("Phase C owner payload is not an object")
    return value


def _sequence(value: object) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise PhaseCGateConflict("Phase C owner payload is not an array")
    return tuple(value)


__all__ = ["PhaseCGateConflict", "PostgresPhaseCGateAuthority"]
