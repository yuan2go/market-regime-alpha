"""PostgreSQL owner/writers for Historical Sample and Formal OOS qualification."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    timestamp,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationObservation,
    EvaluationPartition,
    FormalEvaluationProtocol,
    FormalEvaluationResult,
    run_formal_evaluation,
)
from market_regime_alpha.application.research_evaluation.panel_v2 import (
    FrozenResearchPanelV2,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetOutcomeLabel,
    TargetedShadowOutcome,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
    OutcomeTargetBoundMultiTargetForecast,
    OutcomeTargetForecastStatus,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    FormalProtocolConflict,
    load_formal_protocol_owner,
)
from market_regime_alpha.application.research_validation.qualification import (
    FormalEvaluationObservationBinding,
    FormalOOSQualificationDecision,
    FormalOOSQualificationPolicy,
    HistoricalSampleQualificationDecision,
    LockedOOSEvidenceIdentity,
    QualificationOutcome,
    evaluate_metric_floor_payloads,
)
from market_regime_alpha.application.research_validation.samples import (
    HistoricalPathSampleRecord,
    HistoricalSampleDataset,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_authority import (
    FormalPITEvidenceArtifact,
    FormalPITValidationRequest,
    PITValidationOutcome,
)
from market_regime_alpha.data.postgres_provider_qualification import (
    ProviderFactQualificationDecision,
    ProviderFactQualificationStatus,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.native_repository import (
    acquire_scope_lock,
)


class ResearchQualificationConflict(ValueError):
    """A qualification owner, identity, or idempotency invariant failed."""


class PostgresResearchQualificationAuthority:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def record_oos_policy(
        self, policy: FormalOOSQualificationPolicy
    ) -> FormalOOSQualificationPolicy:
        self._factory.run_transaction(
            lambda connection: _record_oos_policy(
                connection,
                policy=policy,
                created_at=_postgres_now(connection),
            )
        )
        return policy

    def qualify_historical_sample(
        self,
        *,
        dataset_id: ArtifactId,
        formal_protocol_id: ArtifactId | None,
        formal_pit_evidence_id: ArtifactId | None,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> HistoricalSampleQualificationDecision:
        command = {
            "action": "QUALIFY_HISTORICAL_SAMPLE",
            "dataset_id": str(dataset_id),
            "formal_protocol_id": (
                None if formal_protocol_id is None else str(formal_protocol_id)
            ),
            "formal_pit_evidence_id": (
                None
                if formal_pit_evidence_id is None
                else str(formal_pit_evidence_id)
            ),
            "actor": actor,
            "reason": reason,
        }
        command_hash = canonical_hash(command)

        def operation(connection: Any) -> ArtifactId:
            acquire_scope_lock(
                connection,
                namespace="historical-sample-qualification",
                identity=str(dataset_id),
            )
            duplicate = _duplicate_command(
                connection,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
                action_kind="QUALIFY_HISTORICAL_SAMPLE",
            )
            if duplicate is not None:
                return duplicate
            now = _postgres_now(connection)
            dataset = _load_historical_dataset(connection, dataset_id)
            protocol = (
                None
                if formal_protocol_id is None
                else _load_formal_protocol(connection, formal_protocol_id)
            )
            pit = (
                None
                if formal_pit_evidence_id is None
                else _load_formal_pit(connection, formal_pit_evidence_id)
            )
            outcome, reasons, provider_decisions = _assess_historical_sample(
                connection,
                dataset=dataset,
                protocol=protocol,
                pit=pit,
                evaluated_at=now,
            )
            latest = connection.execute(
                """
                SELECT decision_id, revision
                FROM historical_sample_qualification_decision
                WHERE dataset_id = %s
                ORDER BY revision DESC
                LIMIT 1
                """,
                (str(dataset_id),),
            ).fetchone()
            revision = 1 if latest is None else int(latest[1]) + 1
            supersedes = None if latest is None else ArtifactId(str(latest[0]))
            decision = HistoricalSampleQualificationDecision.create(
                dataset_reference=ValidationArtifactReference(
                    "HISTORICAL_SAMPLE_DATASET",
                    dataset.dataset_id,
                    dataset.dataset_hash,
                ),
                formal_protocol_reference=(
                    None
                    if protocol is None
                    else ValidationArtifactReference(
                        "FORMAL_RESEARCH_PROTOCOL",
                        protocol.protocol_id,
                        protocol.protocol_hash,
                    )
                ),
                formal_pit_reference=(
                    None
                    if pit is None
                    else ValidationArtifactReference(
                        "FORMAL_PIT_EVIDENCE",
                        pit.evidence_id,
                        pit.evidence_hash,
                    )
                ),
                provider_fact_decision_references=provider_decisions,
                outcome=outcome,
                qualified=outcome is QualificationOutcome.SATISFIED,
                revision=revision,
                supersedes_decision_id=supersedes,
                evaluated_at=now,
                actor=actor,
                reason=reason,
                reason_codes=reasons,
            )
            connection.execute(
                """
                INSERT INTO historical_sample_qualification_decision(
                    decision_id, decision_hash, dataset_id,
                    formal_protocol_id, formal_pit_evidence_id, outcome,
                    qualified, revision, supersedes_decision_id,
                    payload_json, evaluated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(decision.decision_id),
                    decision.decision_hash,
                    str(dataset.dataset_id),
                    None if protocol is None else str(protocol.protocol_id),
                    None if pit is None else str(pit.evidence_id),
                    outcome.value,
                    decision.qualified,
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
                action_kind="QUALIFY_HISTORICAL_SAMPLE",
                decision_id=decision.decision_id,
                created_at=now,
            )
            return decision.decision_id

        decision_id = self._factory.run_transaction(operation)
        return self.get_historical_sample_decision(decision_id)

    def record_evaluation_candidate(
        self,
        *,
        formal_protocol_id: ArtifactId,
        panel_reference: ValidationArtifactReference,
        target_reference: ValidationArtifactReference,
        observation_bindings: tuple[FormalEvaluationObservationBinding, ...],
        formal_pit_evidence_id: ArtifactId,
    ) -> FormalEvaluationResult:
        if panel_reference.artifact_kind != "RESEARCH_PANEL_V2":
            raise ResearchQualificationConflict(
                "Formal Evaluation requires a PostgreSQL-owned Research Panel V2"
            )
        ordered_bindings = tuple(
            sorted(observation_bindings, key=lambda item: item.observation_id)
        )
        if not ordered_bindings or len(
            {item.observation_id for item in ordered_bindings}
        ) != len(ordered_bindings):
            raise ResearchQualificationConflict(
                "Formal Evaluation observation bindings must be non-empty and unique"
            )

        def operation(connection: Any) -> FormalEvaluationResult:
            owner_protocol = _load_formal_protocol(
                connection, formal_protocol_id
            )
            owner_evaluation = _load_evaluation_protocol(
                connection,
                owner_protocol.evaluation_protocol_reference.artifact_id,
            )
            owner_pit = _load_formal_pit(
                connection, formal_pit_evidence_id
            )
            if target_reference not in owner_protocol.target_references:
                raise ResearchQualificationConflict(
                    "Formal Evaluation Target is not frozen in the Formal Research Protocol"
                )
            panel = _load_panel_owner(connection, panel_reference)
            resolved = tuple(
                _resolve_evaluation_observation(
                    connection,
                    protocol=owner_protocol,
                    panel=panel,
                    target_reference=target_reference,
                    binding=binding,
                )
                for binding in ordered_bindings
            )
            observations = tuple(item[0] for item in resolved)
            created_at = _postgres_now(connection)
            if created_at < owner_protocol.locked_at:
                raise ResearchQualificationConflict(
                    "Formal Evaluation result predates the frozen Formal Research Protocol"
                )
            if any(item[2] > created_at for item in resolved):
                raise ResearchQualificationConflict(
                    "Formal Evaluation result predates an owner-resolved Target Label"
                )
            observation_set_payload = _observation_set_payload(
                formal_protocol=owner_protocol,
                panel_reference=panel_reference,
                target_reference=target_reference,
                bindings=ordered_bindings,
                created_at=created_at,
            )
            observation_set_hash = canonical_hash(observation_set_payload)
            observation_set_id = ArtifactId(
                f"formal-evaluation-observation-set:{observation_set_hash[7:]}"
            )
            observation_set_reference = ValidationArtifactReference(
                "FORMAL_EVALUATION_OBSERVATION_SET",
                observation_set_id,
                observation_set_hash,
            )
            panel_sources = _formal_evaluation_sources(
                owner_protocol,
                target_reference=target_reference,
                observation_set_reference=observation_set_reference,
            )
            result = run_formal_evaluation(
                protocol=owner_evaluation,
                panel_reference=panel_reference,
                observations=observations,
                formal_pit_evidence=owner_pit,
                created_at=created_at,
                panel_source_references=panel_sources,
                frozen_trading_dates=owner_protocol.frozen_trading_dates,
            )
            _record_observation_set(
                connection,
                observation_set_id=observation_set_id,
                observation_set_hash=observation_set_hash,
                observation_set_payload=observation_set_payload,
                formal_protocol=owner_protocol,
                panel_reference=panel_reference,
                target_reference=target_reference,
                bindings=ordered_bindings,
                resolved=resolved,
                created_at=created_at,
            )
            _consume_locked_oos_evidence(
                connection,
                formal_protocol=owner_protocol,
                evaluation_protocol=owner_evaluation,
                target_reference=target_reference,
                observation_set_id=observation_set_id,
                bindings=ordered_bindings,
                observations=observations,
            )
            connection.execute(
                """
                INSERT INTO research_validation_artifact(
                    artifact_id, artifact_hash, artifact_kind,
                    evidence_authority, qualified, production_authorized,
                    payload_json, created_at
                ) VALUES (%s, %s, 'FORMAL_EVALUATION_RESULT',
                          'ENGINEERING_ONLY', false, false, %s, %s)
                ON CONFLICT (artifact_id) DO NOTHING
                """,
                (
                    str(result.result_id),
                    result.result_hash,
                    Jsonb(result.identity_payload()),
                    result.created_at,
                ),
            )
            stored = connection.execute(
                """
                SELECT artifact_hash, payload_json
                FROM research_validation_artifact
                WHERE artifact_id = %s AND artifact_kind = 'FORMAL_EVALUATION_RESULT'
                """,
                (str(result.result_id),),
            ).fetchone()
            if stored is None or (
                str(stored[0]) != result.result_hash
                or stored[1] != result.identity_payload()
            ):
                raise ResearchQualificationConflict(
                    "Formal Evaluation candidate identity conflict"
                )
            return result

        return self._factory.run_transaction(operation)

    def qualify_formal_oos(
        self,
        *,
        policy: FormalOOSQualificationPolicy,
        formal_protocol_id: ArtifactId,
        evaluation_result_id: ArtifactId,
        historical_sample_decision_id: ArtifactId,
        formal_pit_evidence_id: ArtifactId,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> FormalOOSQualificationDecision:
        command = {
            "action": "QUALIFY_FORMAL_OOS",
            "policy_id": str(policy.policy_id),
            "formal_protocol_id": str(formal_protocol_id),
            "evaluation_result_id": str(evaluation_result_id),
            "historical_sample_decision_id": str(historical_sample_decision_id),
            "formal_pit_evidence_id": str(formal_pit_evidence_id),
            "actor": actor,
            "reason": reason,
        }
        command_hash = canonical_hash(command)

        def operation(connection: Any) -> ArtifactId:
            scope = f"{formal_protocol_id}:{evaluation_result_id}"
            acquire_scope_lock(
                connection,
                namespace="formal-oos-qualification",
                identity=scope,
            )
            duplicate = _duplicate_command(
                connection,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
                action_kind="QUALIFY_FORMAL_OOS",
            )
            if duplicate is not None:
                return duplicate
            now = _postgres_now(connection)
            _record_oos_policy(connection, policy=policy, created_at=now)
            protocol = _load_formal_protocol(connection, formal_protocol_id)
            pit = _load_formal_pit(connection, formal_pit_evidence_id)
            sample = _load_historical_decision(
                connection, historical_sample_decision_id
            )
            stored_result = _load_validation_artifact(
                connection,
                evaluation_result_id,
                expected_kind="FORMAL_EVALUATION_RESULT",
            )
            outcome, reasons = _assess_formal_oos(
                connection,
                policy=policy,
                protocol=protocol,
                pit=pit,
                sample=sample,
                result_id=evaluation_result_id,
                result_hash=str(stored_result[0]),
                result_payload=_mapping(stored_result[1]),
            )
            latest = connection.execute(
                """
                SELECT decision_id, revision
                FROM formal_oos_qualification_decision
                WHERE formal_protocol_id = %s AND evaluation_result_id = %s
                ORDER BY revision DESC
                LIMIT 1
                """,
                (str(formal_protocol_id), str(evaluation_result_id)),
            ).fetchone()
            revision = 1 if latest is None else int(latest[1]) + 1
            supersedes = None if latest is None else ArtifactId(str(latest[0]))
            decision = FormalOOSQualificationDecision.create(
                policy_reference=ValidationArtifactReference(
                    "FORMAL_OOS_QUALIFICATION_POLICY",
                    policy.policy_id,
                    policy.policy_hash,
                ),
                formal_protocol_reference=ValidationArtifactReference(
                    "FORMAL_RESEARCH_PROTOCOL",
                    protocol.protocol_id,
                    protocol.protocol_hash,
                ),
                evaluation_result_reference=ValidationArtifactReference(
                    "FORMAL_EVALUATION_RESULT",
                    evaluation_result_id,
                    str(stored_result[0]),
                ),
                historical_sample_decision_reference=ValidationArtifactReference(
                    "HISTORICAL_SAMPLE_QUALIFICATION_DECISION",
                    sample.decision_id,
                    sample.decision_hash,
                ),
                formal_pit_reference=ValidationArtifactReference(
                    "FORMAL_PIT_EVIDENCE", pit.evidence_id, pit.evidence_hash
                ),
                outcome=outcome,
                formal_evaluation_complete=outcome is not QualificationOutcome.BLOCKED,
                formal_oos_passed=outcome is QualificationOutcome.SATISFIED,
                revision=revision,
                supersedes_decision_id=supersedes,
                evaluated_at=now,
                actor=actor,
                reason=reason,
                reason_codes=reasons,
            )
            connection.execute(
                """
                INSERT INTO formal_oos_qualification_decision(
                    decision_id, decision_hash, policy_id,
                    formal_protocol_id, evaluation_result_id,
                    historical_sample_decision_id, formal_pit_evidence_id,
                    outcome, formal_evaluation_complete, formal_oos_passed,
                    revision, supersedes_decision_id, payload_json,
                    evaluated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s)
                """,
                (
                    str(decision.decision_id),
                    decision.decision_hash,
                    str(policy.policy_id),
                    str(protocol.protocol_id),
                    str(evaluation_result_id),
                    str(sample.decision_id),
                    str(pit.evidence_id),
                    outcome.value,
                    decision.formal_evaluation_complete,
                    decision.formal_oos_passed,
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
                action_kind="QUALIFY_FORMAL_OOS",
                decision_id=decision.decision_id,
                created_at=now,
            )
            return decision.decision_id

        decision_id = self._factory.run_transaction(operation)
        return self.get_formal_oos_decision(decision_id)

    def get_historical_sample_decision(
        self, decision_id: ArtifactId
    ) -> HistoricalSampleQualificationDecision:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, decision_hash
                FROM historical_sample_qualification_decision
                WHERE decision_id = %s
                """,
                (str(decision_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(decision_id))
        decision = HistoricalSampleQualificationDecision.from_canonical_dict(
            _mapping(row[0])
        )
        if decision.decision_hash != str(row[1]):
            raise ResearchQualificationConflict(
                "Historical Sample decision storage hash mismatch"
            )
        return decision

    def get_formal_oos_decision(
        self, decision_id: ArtifactId
    ) -> FormalOOSQualificationDecision:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, decision_hash
                FROM formal_oos_qualification_decision
                WHERE decision_id = %s
                """,
                (str(decision_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(decision_id))
        decision = FormalOOSQualificationDecision.from_canonical_dict(
            _mapping(row[0])
        )
        if decision.decision_hash != str(row[1]):
            raise ResearchQualificationConflict("Formal OOS storage hash mismatch")
        return decision


def _assess_historical_sample(
    connection: Any,
    *,
    dataset: HistoricalSampleDataset,
    protocol: FormalResearchProtocol | None,
    pit: FormalPITEvidenceArtifact | None,
    evaluated_at: datetime,
) -> tuple[
    QualificationOutcome,
    tuple[str, ...],
    tuple[ValidationArtifactReference, ...],
]:
    blocked: set[str] = set()
    rejected: set[str] = set()
    if protocol is None:
        blocked.add("FORMAL_RESEARCH_PROTOCOL_MISSING")
    if pit is None:
        blocked.add("FORMAL_PIT_EVIDENCE_MISSING")
    if blocked:
        return QualificationOutcome.BLOCKED, tuple(sorted(blocked)), ()
    assert protocol is not None and pit is not None
    pit_request = _load_formal_pit_request(connection, pit)
    if pit.outcome is not PITValidationOutcome.SATISFIED:
        blocked.add("FORMAL_PIT_NOT_SATISFIED")
    if pit.available_at > evaluated_at or pit.recorded_at > evaluated_at:
        rejected.add("FORMAL_PIT_NOT_AVAILABLE_AT_QUALIFICATION")
    if (
        protocol.dataset_reference.artifact_id != pit.lineage.dataset.artifact_id
        or protocol.dataset_reference.content_hash != pit.lineage.dataset.content_hash
    ):
        rejected.add("FORMAL_PROTOCOL_DATASET_PIT_LINEAGE_MISMATCH")
    if (
        protocol.historical_sample_dataset_reference.artifact_id
        != dataset.dataset_id
        or protocol.historical_sample_dataset_reference.content_hash
        != dataset.dataset_hash
    ):
        rejected.add("FORMAL_PROTOCOL_HISTORICAL_SAMPLE_DATASET_MISMATCH")
    if (
        protocol.universe_reference.artifact_id != pit.lineage.universe.artifact_id
        or protocol.universe_reference.content_hash != pit.lineage.universe.content_hash
    ):
        rejected.add("FORMAL_PROTOCOL_UNIVERSE_PIT_LINEAGE_MISMATCH")
    if (
        protocol.model_reference.artifact_id != pit.lineage.model_lineage_id
        or protocol.model_reference.content_hash != pit.lineage.model_lineage_hash
    ):
        rejected.add("FORMAL_PROTOCOL_MODEL_PIT_LINEAGE_MISMATCH")
    if dataset.target_reference not in protocol.target_references:
        rejected.add("HISTORICAL_SAMPLE_OUTCOME_TARGET_IDENTITY_MISMATCH")
    selected = {
        (str(item.fact_id), item.fact_hash) for item in pit.selected_fact_authorities
    }
    for record in dataset.records:
        if record.sample.symbol not in pit_request.symbols:
            rejected.add("HISTORICAL_SAMPLE_SYMBOL_OUTSIDE_FORMAL_PIT_SCOPE")
        if record.sample.available_at.value > evaluated_at:
            rejected.add("HISTORICAL_SAMPLE_NOT_AVAILABLE_AT_QUALIFICATION")
        if record.outcome_reference.artifact_kind != "TARGET_OUTCOME_LABEL":
            rejected.add("FORMAL_TARGET_OUTCOME_LABEL_REQUIRED")
        else:
            try:
                outcome, label = _load_target_label_owner(
                    connection,
                    reference=record.outcome_reference,
                    target_reference=record.target_reference,
                )
            except ResearchQualificationConflict:
                rejected.add("TARGET_OUTCOME_LABEL_OWNER_MISMATCH")
            else:
                rejected.update(
                    _historical_target_label_reason_codes(
                        protocol=protocol,
                        record=record,
                        outcome=outcome,
                        label=label,
                    )
                )
        pit_refs = tuple(
            item
            for item in record.pit_lineage
            if item.artifact_kind == "PIT_FACT_REVISION"
        )
        if not pit_refs:
            rejected.add("HISTORICAL_SAMPLE_PIT_FACT_LINEAGE_MISSING")
        elif any(
            (str(item.artifact_id), item.content_hash) not in selected
            for item in pit_refs
        ):
            rejected.add("HISTORICAL_SAMPLE_PIT_FACT_LINEAGE_MISMATCH")
        elif {
            (str(item.artifact_id), item.content_hash) for item in pit_refs
        } != selected:
            rejected.add("HISTORICAL_SAMPLE_PIT_FACT_LINEAGE_INCOMPLETE")
        rejected.update(
            _historical_pit_temporal_reason_codes(
                connection,
                protocol=protocol,
                record=record,
                pit_request=pit_request,
                pit=pit,
            )
        )
    provider_refs, provider_reasons = _resolve_provider_fact_decisions(
        connection, pit=pit, evaluated_at=evaluated_at
    )
    blocked.update(provider_reasons)
    if rejected:
        return QualificationOutcome.REJECTED, tuple(sorted(rejected | blocked)), provider_refs
    if blocked:
        return QualificationOutcome.BLOCKED, tuple(sorted(blocked)), provider_refs
    return QualificationOutcome.SATISFIED, (), provider_refs


def _historical_pit_temporal_reason_codes(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    record: HistoricalPathSampleRecord,
    pit_request: FormalPITValidationRequest,
    pit: FormalPITEvidenceArtifact,
) -> tuple[str, ...]:
    """Rebind one sample to the exact As-Of request and Fact owner rows."""

    reasons: set[str] = set()
    sample_time = record.sample.sample_decision_time.value
    if pit_request.decision_time != sample_time:
        reasons.add("HISTORICAL_SAMPLE_FORMAL_PIT_DECISION_TIME_MISMATCH")
    required = {
        (item.logical_key, item.fact_kind.value, item.subject)
        for item in pit_request.required_facts
    }
    selected_keys: set[tuple[str, str, str]] = set()
    calendar_facts = 0
    for selected in pit.selected_fact_authorities:
        row = connection.execute(
            """
            SELECT content_hash, logical_key, fact_kind, subject,
                   event_time, effective_from, effective_to,
                   available_at, recorded_at, artifact_id, artifact_hash
            FROM pit_fact_revision
            WHERE fact_id = %s
            """,
            (str(selected.fact_id),),
        ).fetchone()
        if row is None or str(row[0]) != selected.fact_hash:
            reasons.add("HISTORICAL_SAMPLE_PIT_FACT_OWNER_MISMATCH")
            continue
        fact_key = (str(row[1]), str(row[2]), str(row[3]))
        selected_keys.add(fact_key)
        if fact_key not in required:
            reasons.add("HISTORICAL_SAMPLE_PIT_FACT_REQUIREMENT_MISMATCH")
        if (
            row[4] > sample_time
            or row[5] > sample_time
            or (row[6] is not None and sample_time >= row[6])
            or row[7] > sample_time
            or row[8] > sample_time
        ):
            reasons.add("HISTORICAL_SAMPLE_PIT_FACT_NOT_AS_OF_SAMPLE")
        if str(row[2]) == "TRADING_CALENDAR":
            calendar_facts += 1
            if (
                str(row[9])
                != str(protocol.trading_calendar_reference.artifact_id)
                or str(row[10])
                != protocol.trading_calendar_reference.content_hash
            ):
                reasons.add("FORMAL_PIT_FROZEN_CALENDAR_LINEAGE_MISMATCH")
    if selected_keys != required:
        reasons.add("HISTORICAL_SAMPLE_PIT_FACT_REQUIREMENT_MISMATCH")
    if calendar_facts == 0:
        reasons.add("FORMAL_PIT_FROZEN_CALENDAR_LINEAGE_MISSING")
    return tuple(sorted(reasons))


def _resolve_provider_fact_decisions(
    connection: Any,
    *,
    pit: FormalPITEvidenceArtifact,
    evaluated_at: datetime,
) -> tuple[tuple[ValidationArtifactReference, ...], tuple[str, ...]]:
    references: list[ValidationArtifactReference] = []
    reasons: set[str] = set()
    for selected in pit.selected_fact_authorities:
        fact = connection.execute(
            """
            SELECT provider_id, provider_contract, fact_kind,
                   source_qualification_id
            FROM pit_fact_revision
            WHERE fact_id = %s AND content_hash = %s
            """,
            (str(selected.fact_id), selected.fact_hash),
        ).fetchone()
        if fact is None:
            reasons.add("PIT_SELECTED_FACT_OWNER_MISSING")
            continue
        decision = connection.execute(
            """
            SELECT decision_id, decision_hash, payload_json
            FROM provider_fact_qualification_decision
            WHERE provider_id = lower(%s) AND provider_contract = %s
              AND fact_kind = %s AND evaluated_at <= %s
            ORDER BY revision DESC
            LIMIT 1
            """,
            (str(fact[0]), str(fact[1]), str(fact[2]), evaluated_at),
        ).fetchone()
        if decision is None:
            reasons.add(f"PROVIDER_FACT_NOT_QUALIFIED_{fact[2]}")
            continue
        resolved_decision = ProviderFactQualificationDecision.from_canonical_dict(
            _mapping(decision[2])
        )
        if (
            resolved_decision.decision_id != ArtifactId(str(decision[0]))
            or resolved_decision.decision_hash != str(decision[1])
            or resolved_decision.status
            is not ProviderFactQualificationStatus.QUALIFIED
        ):
            reasons.add(f"PROVIDER_FACT_NOT_QUALIFIED_{fact[2]}")
            continue
        source_refs = tuple(
            resolved_decision.source_qualification_references
        )
        if not any(str(item.artifact_id) == str(fact[3]) for item in source_refs):
            reasons.add(f"PROVIDER_FACT_SOURCE_QUALIFICATION_MISMATCH_{fact[2]}")
            continue
        references.append(
            ValidationArtifactReference(
                "PROVIDER_FACT_QUALIFICATION_DECISION",
                ArtifactId(str(decision[0])),
                str(decision[1]),
            )
        )
    return _ordered_references(tuple(references)), tuple(sorted(reasons))


def _assess_formal_oos(
    connection: Any,
    *,
    policy: FormalOOSQualificationPolicy,
    protocol: FormalResearchProtocol,
    pit: FormalPITEvidenceArtifact,
    sample: HistoricalSampleQualificationDecision,
    result_id: ArtifactId,
    result_hash: str,
    result_payload: Mapping[str, Any],
) -> tuple[QualificationOutcome, tuple[str, ...]]:
    blocked: set[str] = set()
    rejected: set[str] = set()
    expected_policy = ValidationArtifactReference(
        "FORMAL_OOS_QUALIFICATION_POLICY", policy.policy_id, policy.policy_hash
    )
    if protocol.formal_oos_qualification_policy_reference != expected_policy:
        rejected.add("FORMAL_OOS_POLICY_NOT_FROZEN_IN_RESEARCH_PROTOCOL")
    if not sample.qualified:
        blocked.add("QUALIFIED_HISTORICAL_SAMPLE_REQUIRED")
    if sample.formal_protocol_reference is None or (
        sample.formal_protocol_reference.artifact_id != protocol.protocol_id
        or sample.formal_protocol_reference.content_hash != protocol.protocol_hash
    ):
        rejected.add("HISTORICAL_SAMPLE_FORMAL_PROTOCOL_LINEAGE_MISMATCH")
    if sample.formal_pit_reference is None or (
        sample.formal_pit_reference.artifact_id != pit.evidence_id
        or sample.formal_pit_reference.content_hash != pit.evidence_hash
    ):
        rejected.add("HISTORICAL_SAMPLE_FORMAL_PIT_LINEAGE_MISMATCH")
    protocol_ref = ValidationArtifactReference.from_canonical_dict(
        _mapping(result_payload["protocol_reference"])
    )
    pit_ref = (
        None
        if result_payload["pit_evidence_reference"] is None
        else ValidationArtifactReference.from_canonical_dict(
            _mapping(result_payload["pit_evidence_reference"])
        )
    )
    panel_ref = ValidationArtifactReference.from_canonical_dict(
        _mapping(result_payload["panel_reference"])
    )
    panel_sources = tuple(
        ValidationArtifactReference.from_canonical_dict(_mapping(item))
        for item in _sequence(result_payload["panel_source_references"])
    )
    if protocol_ref != protocol.evaluation_protocol_reference:
        rejected.add("FORMAL_EVALUATION_PROTOCOL_LINEAGE_MISMATCH")
    if pit_ref is None or (
        pit_ref.artifact_id != pit.evidence_id
        or pit_ref.content_hash != pit.evidence_hash
    ):
        rejected.add("FORMAL_EVALUATION_PIT_LINEAGE_MISMATCH")
    if protocol.dataset_reference not in panel_sources:
        rejected.add("FORMAL_EVALUATION_DATASET_LINEAGE_MISSING")
    if protocol.trading_calendar_reference not in panel_sources:
        rejected.add("FORMAL_EVALUATION_FROZEN_CALENDAR_LINEAGE_MISSING")
    if sample.dataset_reference not in panel_sources:
        rejected.add("FORMAL_EVALUATION_SAMPLE_DATASET_LINEAGE_MISSING")
    evaluation_protocol = _load_evaluation_protocol(
        connection, protocol.evaluation_protocol_reference.artifact_id
    )
    observations = _load_evaluation_observations(
        connection,
        protocol=protocol,
        result_payload=result_payload,
    )
    if not observations:
        blocked.add("OWNER_REPLAYABLE_EVALUATION_OBSERVATIONS_MISSING")
    if rejected:
        return QualificationOutcome.REJECTED, tuple(sorted(rejected | blocked))
    if blocked:
        return QualificationOutcome.BLOCKED, tuple(sorted(blocked))
    expected_folds = {
        item.fold
        for item in evaluation_protocol.windows
        if item.partition.value == "LOCKED_OOS"
    }
    metric_payloads = tuple(
        _mapping(item) for item in _sequence(result_payload["metrics"])
    )
    observed_folds = {
        int(item["fold"])
        for item in metric_payloads
        if str(item["partition"]) == "LOCKED_OOS"
    }
    if observed_folds != expected_folds:
        return QualificationOutcome.NOT_ESTIMABLE, (
            "LOCKED_OOS_FOLD_COVERAGE_INCOMPLETE",
        )
    replayed = run_formal_evaluation(
        protocol=evaluation_protocol,
        panel_reference=panel_ref,
        observations=observations,
        formal_pit_evidence=pit,
        created_at=datetime.fromisoformat(str(result_payload["created_at"])),
        panel_source_references=panel_sources,
        frozen_trading_dates=protocol.frozen_trading_dates,
    )
    if replayed.result_id != result_id or replayed.result_hash != result_hash:
        raise ResearchQualificationConflict("Formal Evaluation owner replay diverged")
    return evaluate_metric_floor_payloads(policy=policy, metrics=metric_payloads)


def _load_historical_dataset(
    connection: Any, dataset_id: ArtifactId
) -> HistoricalSampleDataset:
    row = _load_validation_artifact(
        connection, dataset_id, expected_kind="HISTORICAL_SAMPLE_DATASET"
    )
    return HistoricalSampleDataset.from_canonical_dict(
        {
            "dataset_id": str(dataset_id),
            "dataset_hash": str(row[0]),
            **_mapping(row[1]),
        }
    )


def _load_formal_protocol(
    connection: Any, protocol_id: ArtifactId
) -> FormalResearchProtocol:
    try:
        return load_formal_protocol_owner(connection, protocol_id)
    except FormalProtocolConflict as exc:
        raise ResearchQualificationConflict(
            "Formal Protocol owner replay failed"
        ) from exc


def _load_formal_pit(
    connection: Any, evidence_id: ArtifactId
) -> FormalPITEvidenceArtifact:
    row = connection.execute(
        """
        SELECT payload_json, evidence_hash
        FROM formal_pit_validation_evidence
        WHERE evidence_id = %s
        """,
        (str(evidence_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(evidence_id))
    evidence = FormalPITEvidenceArtifact.from_canonical_dict(_mapping(row[0]))
    if evidence.evidence_hash != str(row[1]):
        raise ResearchQualificationConflict("Formal PIT owner hash mismatch")
    return evidence


def _load_formal_pit_request(
    connection: Any,
    evidence: FormalPITEvidenceArtifact,
) -> FormalPITValidationRequest:
    row = connection.execute(
        """
        SELECT request_json
        FROM formal_pit_validation_evidence
        WHERE evidence_id = %s
        """,
        (str(evidence.evidence_id),),
    ).fetchone()
    if row is None or not isinstance(row[0], Mapping):
        raise ResearchQualificationConflict("Formal PIT request owner is missing")
    try:
        request = FormalPITValidationRequest.from_canonical_dict(_mapping(row[0]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchQualificationConflict("Formal PIT request replay failed") from exc
    if request.request_hash != evidence.request_hash:
        raise ResearchQualificationConflict("Formal PIT request identity mismatch")
    return request


def _load_target_label_owner(
    connection: Any,
    *,
    reference: ValidationArtifactReference,
    target_reference: ValidationArtifactReference,
) -> tuple[TargetedShadowOutcome, TargetOutcomeLabel]:
    rows = connection.execute(
        """
        SELECT outcome.settlement_hash, outcome.payload_json,
               label.label_hash, label.label_json
        FROM targeted_shadow_outcome_label AS label
        JOIN targeted_shadow_outcome AS outcome
          ON outcome.settlement_id = label.settlement_id
        WHERE label.label_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchall()
    exact: list[tuple[TargetedShadowOutcome, TargetOutcomeLabel]] = []
    for row in rows:
        if (
            str(row[2]) != reference.content_hash
            or not isinstance(row[1], Mapping)
            or not isinstance(row[3], Mapping)
        ):
            continue
        try:
            outcome = TargetedShadowOutcome.from_canonical_dict(_mapping(row[1]))
            label = TargetOutcomeLabel.from_canonical_dict(_mapping(row[3]))
        except (KeyError, TypeError, ValueError):
            continue
        if (
            outcome.settlement_hash == str(row[0])
            and label.label_id == reference.artifact_id
            and label.label_hash == reference.content_hash
            and label.target.artifact_id == target_reference.artifact_id
            and label.target.content_hash == target_reference.content_hash
            and label in outcome.labels
        ):
            exact.append((outcome, label))
    if len(exact) != 1:
        raise ResearchQualificationConflict("Target Outcome Label owner mismatch")
    return exact[0]


def _decimal_from_float(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _historical_target_label_reason_codes(
    *,
    protocol: FormalResearchProtocol,
    record: HistoricalPathSampleRecord,
    outcome: TargetedShadowOutcome,
    label: TargetOutcomeLabel,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    sample = record.sample
    if (
        outcome.source_dataset.artifact_id
        != protocol.dataset_reference.artifact_id
        or outcome.source_dataset.content_hash
        != protocol.dataset_reference.content_hash
        or outcome.target_protocol_id
        != protocol.outcome_target_protocol_reference.artifact_id
        or outcome.target_protocol_hash
        != protocol.outcome_target_protocol_reference.content_hash
    ):
        reasons.add("TARGET_OUTCOME_DATASET_OR_PROTOCOL_LINEAGE_MISMATCH")
    if (
        label.symbol != sample.symbol
        or label.target.artifact_id != record.target_reference.artifact_id
        or label.target.content_hash != record.target_reference.content_hash
        or label.label_interval_start != sample.sample_decision_time.value
        or label.outcome_available_at > sample.available_at.value
        or sample.source_artifact_id != outcome.settlement_id
        or sample.source_content_hash != outcome.settlement_hash
        or _decimal_from_float(sample.realized_return) != label.checkpoint_return
        or _decimal_from_float(sample.realized_mfe) != label.mfe
        or _decimal_from_float(sample.realized_mae) != label.mae
    ):
        reasons.add("HISTORICAL_SAMPLE_TARGET_LABEL_LINEAGE_MISMATCH")
    return tuple(sorted(reasons))


def _load_historical_decision(
    connection: Any, decision_id: ArtifactId
) -> HistoricalSampleQualificationDecision:
    row = connection.execute(
        """
        SELECT payload_json, decision_hash
        FROM historical_sample_qualification_decision
        WHERE decision_id = %s
        """,
        (str(decision_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(decision_id))
    decision = HistoricalSampleQualificationDecision.from_canonical_dict(
        _mapping(row[0])
    )
    if decision.decision_hash != str(row[1]):
        raise ResearchQualificationConflict("Historical decision owner hash mismatch")
    return decision


def _load_validation_artifact(
    connection: Any,
    artifact_id: ArtifactId,
    *,
    expected_kind: str,
) -> tuple[Any, ...]:
    row = connection.execute(
        """
        SELECT artifact_hash, payload_json, evidence_authority,
               qualified, production_authorized
        FROM research_validation_artifact
        WHERE artifact_id = %s AND artifact_kind = %s
        """,
        (str(artifact_id), expected_kind),
    ).fetchone()
    if row is None:
        raise KeyError(str(artifact_id))
    if canonical_hash(dict(_mapping(row[1]))) != str(row[0]):
        raise ResearchQualificationConflict("Research Validation owner hash mismatch")
    if bool(row[3]) or bool(row[4]):
        raise ResearchQualificationConflict("Migration 046 authority ceiling drift")
    return tuple(row)


def _load_evaluation_protocol(
    connection: Any, protocol_id: ArtifactId
) -> FormalEvaluationProtocol:
    row = _load_validation_artifact(
        connection, protocol_id, expected_kind="FORMAL_EVALUATION_PROTOCOL"
    )
    return FormalEvaluationProtocol.from_canonical_dict(
        {
            "protocol_id": str(protocol_id),
            "protocol_hash": str(row[0]),
            **dict(_mapping(row[1])),
        }
    )


def _load_evaluation_observations(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    result_payload: Mapping[str, Any],
) -> tuple[EvaluationObservation, ...]:
    panel_reference = ValidationArtifactReference.from_canonical_dict(
        _mapping(result_payload["panel_reference"])
    )
    source_references = tuple(
        ValidationArtifactReference.from_canonical_dict(_mapping(item))
        for item in _sequence(result_payload["panel_source_references"])
    )
    set_references = tuple(
        item
        for item in source_references
        if item.artifact_kind == "FORMAL_EVALUATION_OBSERVATION_SET"
    )
    if len(set_references) != 1:
        raise ResearchQualificationConflict(
            "Formal Evaluation requires exactly one observation-set owner"
        )
    set_reference = set_references[0]
    row = connection.execute(
        """
        SELECT observation_set_hash, formal_protocol_id, panel_id,
               target_protocol_id, target_id, target_hash,
               observation_count, payload_json, created_at
        FROM formal_evaluation_observation_set
        WHERE observation_set_id = %s
        """,
        (str(set_reference.artifact_id),),
    ).fetchone()
    if row is None or not isinstance(row[7], Mapping):
        raise ResearchQualificationConflict(
            "Formal Evaluation observation-set owner is missing"
        )
    payload = _mapping(row[7])
    formal_protocol_reference = ValidationArtifactReference.from_canonical_dict(
        _mapping(payload["formal_protocol_reference"])
    )
    stored_panel_reference = ValidationArtifactReference.from_canonical_dict(
        _mapping(payload["panel_reference"])
    )
    target_reference = ValidationArtifactReference.from_canonical_dict(
        _mapping(payload["target_reference"])
    )
    expected_protocol_reference = ValidationArtifactReference(
        "FORMAL_RESEARCH_PROTOCOL", protocol.protocol_id, protocol.protocol_hash
    )
    if (
        str(row[0]) != set_reference.content_hash
        or canonical_hash(payload) != set_reference.content_hash
        or str(row[1]) != str(protocol.protocol_id)
        or formal_protocol_reference != expected_protocol_reference
        or str(row[2]) != str(panel_reference.artifact_id)
        or stored_panel_reference != panel_reference
        or str(row[3]) != str(protocol.outcome_target_protocol_reference.artifact_id)
        or str(row[4]) != str(target_reference.artifact_id)
        or str(row[5]) != target_reference.content_hash
        or target_reference not in protocol.target_references
        or timestamp(row[8]) != str(payload["created_at"])
        or str(result_payload["created_at"]) != str(payload["created_at"])
    ):
        raise ResearchQualificationConflict(
            "Formal Evaluation observation-set owner lineage mismatch"
        )
    expected_sources = _formal_evaluation_sources(
        protocol,
        target_reference=target_reference,
        observation_set_reference=set_reference,
    )
    if source_references != expected_sources:
        raise ResearchQualificationConflict(
            "Formal Evaluation result does not freeze exact result-affecting lineage"
        )
    binding_payloads = tuple(
        _mapping(item) for item in _sequence(payload["observation_bindings"])
    )
    bindings = tuple(
        FormalEvaluationObservationBinding.from_canonical_dict(item)
        for item in binding_payloads
    )
    if (
        bindings != tuple(sorted(bindings, key=lambda item: item.observation_id))
        or len(bindings) != int(row[6])
        or len({item.observation_id for item in bindings}) != len(bindings)
    ):
        raise ResearchQualificationConflict(
            "Formal Evaluation observation-set binding identity mismatch"
        )
    rows = connection.execute(
        """
        SELECT observation_id, forecast_id, forecast_hash,
               settlement_id, label_id, label_hash,
               panel_id, slice_id, row_id, row_hash,
               session_date, label_end_date, payload_json
        FROM formal_evaluation_observation_binding
        WHERE observation_set_id = %s
        ORDER BY observation_id
        """,
        (str(set_reference.artifact_id),),
    ).fetchall()
    if tuple(_mapping(item[12]) for item in rows) != binding_payloads:
        raise ResearchQualificationConflict(
            "Formal Evaluation observation bindings diverge from set identity"
        )
    panel = _load_panel_owner(connection, panel_reference)
    evaluation_protocol = _load_evaluation_protocol(
        connection, protocol.evaluation_protocol_reference.artifact_id
    )
    observations: list[EvaluationObservation] = []
    for binding, stored in zip(bindings, rows, strict=True):
        observation, settlement_id, _ = _resolve_evaluation_observation(
            connection,
            protocol=protocol,
            panel=panel,
            target_reference=target_reference,
            binding=binding,
        )
        expected_projection = (
            binding.observation_id,
            str(binding.forecast_reference.artifact_id),
            binding.forecast_reference.content_hash,
            settlement_id,
            str(binding.label_reference.artifact_id),
            binding.label_reference.content_hash,
            str(panel_reference.artifact_id),
            str(binding.panel_slice_reference.artifact_id),
            str(binding.panel_row_reference.artifact_id),
            binding.panel_row_reference.content_hash,
            observation.session_date,
            observation.label_end_date,
        )
        actual_projection = tuple(stored[:12])
        if actual_projection != expected_projection:
            raise ResearchQualificationConflict(
                "Formal Evaluation observation binding projection mismatch"
            )
        consumption = _locked_oos_consumption_payload(
            formal_protocol=protocol,
            evaluation_protocol=evaluation_protocol,
            target_reference=target_reference,
            observation_set_id=set_reference.artifact_id,
            binding=binding,
            observation=observation,
        )
        if consumption is not None:
            identity_hash, consumption_payload = consumption
            _require_locked_oos_consumption(
                connection,
                identity_hash=identity_hash,
                payload=consumption_payload,
                observation_set_id=set_reference.artifact_id,
            )
        observations.append(observation)
    return tuple(observations)


def _load_panel_owner(
    connection: Any,
    reference: ValidationArtifactReference,
) -> FrozenResearchPanelV2:
    row = connection.execute(
        """
        SELECT panel_hash, payload_json
        FROM research_evaluation_panel_v2
        WHERE panel_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchone()
    if row is None or not isinstance(row[1], Mapping):
        raise ResearchQualificationConflict("Research Panel owner is missing")
    try:
        panel = FrozenResearchPanelV2.from_canonical_dict(_mapping(row[1]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchQualificationConflict("Research Panel owner replay failed") from exc
    if (
        reference.artifact_kind != "RESEARCH_PANEL_V2"
        or panel.panel_id != reference.artifact_id
        or panel.panel_hash != reference.content_hash
        or str(row[0]) != panel.panel_hash
    ):
        raise ResearchQualificationConflict("Research Panel owner identity mismatch")
    return panel


def _resolve_evaluation_observation(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    panel: FrozenResearchPanelV2,
    target_reference: ValidationArtifactReference,
    binding: FormalEvaluationObservationBinding,
) -> tuple[EvaluationObservation, str, datetime]:
    forecast_row = connection.execute(
        """
        SELECT forecast_hash, payload_json
        FROM outcome_target_bound_forecast
        WHERE forecast_id = %s
        """,
        (str(binding.forecast_reference.artifact_id),),
    ).fetchone()
    if forecast_row is None or not isinstance(forecast_row[1], Mapping):
        raise ResearchQualificationConflict("Target-bound Forecast owner is missing")
    try:
        forecast = OutcomeTargetBoundMultiTargetForecast.from_canonical_dict(
            dict(_mapping(forecast_row[1]))
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchQualificationConflict("Target-bound Forecast replay failed") from exc
    if (
        forecast.forecast_id != binding.forecast_reference.artifact_id
        or forecast.forecast_hash != binding.forecast_reference.content_hash
        or str(forecast_row[0]) != forecast.forecast_hash
        or forecast.target_protocol_reference
        != protocol.outcome_target_protocol_reference
        or forecast.model_reference != protocol.model_reference
    ):
        raise ResearchQualificationConflict("Target-bound Forecast owner mismatch")
    required_forecast_sources = {
        protocol.universe_reference,
        protocol.dataset_reference,
        protocol.feature_reference,
        protocol.factor_reference,
        protocol.threshold_policy_reference,
    }
    if not required_forecast_sources.issubset(forecast.source_references):
        raise ResearchQualificationConflict(
            "Target-bound Forecast omits frozen result-affecting source lineage"
        )
    matching_estimates = tuple(
        item
        for item in forecast.estimates
        if item.target_id == target_reference.artifact_id
        and item.target_hash == target_reference.content_hash
    )
    if (
        len(matching_estimates) != 1
        or matching_estimates[0].status
        is not OutcomeTargetForecastStatus.AVAILABLE_FOR_RESEARCH
        or matching_estimates[0].score is None
    ):
        raise ResearchQualificationConflict(
            "Formal Evaluation Forecast estimate is not owner-estimable for Target"
        )
    label_rows = connection.execute(
        """
        SELECT l.settlement_id, l.label_hash, l.target_protocol_id,
               l.target_id, l.symbol, l.label_json,
               o.settlement_hash, o.shadow_decision_id, d.decision_hash
        FROM targeted_shadow_outcome_label AS l
        JOIN targeted_shadow_outcome AS o
          ON o.settlement_id = l.settlement_id
        JOIN shadow_research_decision AS d
          ON d.decision_id = o.shadow_decision_id
        WHERE l.label_id = %s
        """,
        (str(binding.label_reference.artifact_id),),
    ).fetchall()
    exact_label_rows = tuple(
        item
        for item in label_rows
        if str(item[1]) == binding.label_reference.content_hash
        and str(item[2]) == str(protocol.outcome_target_protocol_reference.artifact_id)
        and str(item[3]) == str(target_reference.artifact_id)
        and str(item[4]) == forecast.symbol
    )
    if len(exact_label_rows) != 1:
        raise ResearchQualificationConflict("Target Outcome Label owner mismatch")
    label_row = exact_label_rows[0]
    try:
        label = TargetOutcomeLabel.from_canonical_dict(_mapping(label_row[5]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchQualificationConflict("Target Outcome Label replay failed") from exc
    if (
        label.label_id != binding.label_reference.artifact_id
        or label.label_hash != binding.label_reference.content_hash
        or label.target.artifact_id != target_reference.artifact_id
        or label.target.content_hash != target_reference.content_hash
        or label.availability_status is not OutcomeAvailabilityStatus.COMPLETE
        or label.checkpoint_return is None
        or forecast.decision_time != label.label_interval_start
        or forecast.created_at != forecast.decision_time
        or forecast.created_at >= label.label_interval_end
    ):
        raise ResearchQualificationConflict(
            "Formal Evaluation Forecast/Outcome temporal or Target lineage mismatch"
        )
    matching_slices = tuple(
        item
        for item in panel.slices
        if item.slice_id == binding.panel_slice_reference.artifact_id
        and item.slice_hash == binding.panel_slice_reference.content_hash
    )
    if len(matching_slices) != 1:
        raise ResearchQualificationConflict("Research Panel slice owner mismatch")
    panel_slice = matching_slices[0]
    matching_rows = tuple(
        item
        for item in panel_slice.rows
        if item.row_id == binding.panel_row_reference.artifact_id
        and item.row_hash == binding.panel_row_reference.content_hash
        and item.symbol == forecast.symbol
    )
    if len(matching_rows) != 1:
        raise ResearchQualificationConflict("Research Panel row owner mismatch")
    panel_row = matching_rows[0]
    if (
        panel.target_protocol_id
        != protocol.outcome_target_protocol_reference.artifact_id
        or panel.target_protocol_hash
        != protocol.outcome_target_protocol_reference.content_hash
        or panel_slice.target_protocol.artifact_id
        != protocol.outcome_target_protocol_reference.artifact_id
        or panel_slice.target_protocol.content_hash
        != protocol.outcome_target_protocol_reference.content_hash
        or str(panel_slice.targeted_outcome.artifact_id) != str(label_row[0])
        or panel_slice.targeted_outcome.content_hash != str(label_row[6])
        or not any(
            item.reference_kind == "TARGET_OUTCOME_LABEL"
            and item.artifact_id == label.label_id
            and item.content_hash == label.label_hash
            for item in panel_row.target_labels
        )
        or not any(
            item.artifact_kind == "SHADOW_DECISION"
            and str(item.artifact_id) == str(label_row[7])
            and item.content_hash == str(label_row[8])
            for item in forecast.source_references
        )
    ):
        raise ResearchQualificationConflict(
            "Research Panel, Forecast, Decision, and Outcome lineage mismatch"
        )
    regime = _state_slice(
        connection,
        table="market_regime_state",
        state_id=panel_slice.market_state.artifact_id,
        state_hash=panel_slice.market_state.content_hash,
    )
    theme = _state_slice(
        connection,
        table="theme_rotation_state",
        state_id=panel_slice.theme_state.artifact_id,
        state_hash=panel_slice.theme_state.content_hash,
    )
    observation = EvaluationObservation(
        observation_id=binding.observation_id,
        session_date=panel_slice.trading_date,
        label_end_date=label.label_interval_end.date(),
        symbol=forecast.symbol,
        score=matching_estimates[0].score,
        realized_return=label.checkpoint_return,
        mfe=label.mfe,
        mae=label.mae,
        regime=regime,
        liquidity_slice="UNKNOWN",
        market_cap_slice="UNKNOWN",
        theme_slice=theme,
    )
    return observation, str(label_row[0]), label.outcome_available_at


def _state_slice(
    connection: Any,
    *,
    table: str,
    state_id: ArtifactId,
    state_hash: str,
) -> str:
    if table not in {"market_regime_state", "theme_rotation_state"}:
        raise AssertionError("unsupported state slice owner")
    row = connection.execute(
        f"SELECT state_hash, effective_state FROM {table} WHERE state_id = %s",
        (str(state_id),),
    ).fetchone()
    if row is None or str(row[0]) != state_hash or not str(row[1]).strip():
        raise ResearchQualificationConflict("Formal Evaluation state slice owner mismatch")
    return str(row[1])


def _consume_locked_oos_evidence(
    connection: Any,
    *,
    formal_protocol: FormalResearchProtocol,
    evaluation_protocol: FormalEvaluationProtocol,
    target_reference: ValidationArtifactReference,
    observation_set_id: ArtifactId,
    bindings: tuple[FormalEvaluationObservationBinding, ...],
    observations: tuple[EvaluationObservation, ...],
) -> None:
    for binding, observation in zip(bindings, observations, strict=True):
        locked_windows = tuple(
            item
            for item in evaluation_protocol.windows
            if item.partition is EvaluationPartition.LOCKED_OOS
            and item.start_date <= observation.session_date <= item.end_date
        )
        if not locked_windows:
            continue
        consumption = _locked_oos_consumption_payload(
            formal_protocol=formal_protocol,
            evaluation_protocol=evaluation_protocol,
            target_reference=target_reference,
            observation_set_id=observation_set_id,
            binding=binding,
            observation=observation,
        )
        if consumption is None:
            raise AssertionError("Locked OOS window consumption was not constructed")
        identity_hash, payload = consumption
        acquire_scope_lock(
            connection,
            namespace="locked-oos-evidence-consumption",
            identity=identity_hash,
        )
        prior_rows = connection.execute(
            """
            SELECT DISTINCT observation_set.formal_protocol_id,
                            binding.observation_set_id
            FROM formal_evaluation_observation_binding AS binding
            JOIN formal_evaluation_observation_set AS observation_set
              ON observation_set.observation_set_id = binding.observation_set_id
            WHERE binding.label_id = %s
              AND binding.observation_set_id <> %s
            """,
            (
                str(binding.label_reference.artifact_id),
                str(observation_set_id),
            ),
        ).fetchall()
        if prior_rows:
            raise ResearchQualificationConflict(
                "Locked OOS evidence was touched by prior Formal Evaluation"
            )
        consumed_at = _postgres_now(connection)
        connection.execute(
            """
            INSERT INTO locked_oos_evidence_consumption(
                evidence_identity_hash, dataset_id, dataset_hash,
                universe_id, universe_hash,
                target_protocol_id, target_protocol_hash,
                target_id, target_hash, label_id, label_hash,
                subject, session_date, label_end_date, partition_kind,
                first_formal_protocol_id, first_formal_protocol_hash,
                first_model_id, first_model_hash,
                first_forecast_id, first_forecast_hash,
                observation_set_id, payload_json, consumed_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, 'LOCKED_OOS', %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT DO NOTHING
            """,
            (
                identity_hash,
                str(formal_protocol.dataset_reference.artifact_id),
                formal_protocol.dataset_reference.content_hash,
                str(formal_protocol.universe_reference.artifact_id),
                formal_protocol.universe_reference.content_hash,
                str(formal_protocol.outcome_target_protocol_reference.artifact_id),
                formal_protocol.outcome_target_protocol_reference.content_hash,
                str(target_reference.artifact_id),
                target_reference.content_hash,
                str(binding.label_reference.artifact_id),
                binding.label_reference.content_hash,
                observation.symbol,
                observation.session_date,
                observation.label_end_date,
                str(formal_protocol.protocol_id),
                formal_protocol.protocol_hash,
                str(formal_protocol.model_reference.artifact_id),
                formal_protocol.model_reference.content_hash,
                str(binding.forecast_reference.artifact_id),
                binding.forecast_reference.content_hash,
                str(observation_set_id),
                Jsonb(payload),
                consumed_at,
            ),
        )
        _require_locked_oos_consumption(
            connection,
            identity_hash=identity_hash,
            payload=payload,
            observation_set_id=observation_set_id,
        )


def _locked_oos_evidence_identity_payload(
    *,
    formal_protocol: FormalResearchProtocol,
    target_reference: ValidationArtifactReference,
    binding: FormalEvaluationObservationBinding,
    observation: EvaluationObservation,
) -> dict[str, Any]:
    del binding
    return LockedOOSEvidenceIdentity(
        dataset_reference=formal_protocol.dataset_reference,
        universe_reference=formal_protocol.universe_reference,
        target_protocol_reference=(
            formal_protocol.outcome_target_protocol_reference
        ),
        target_reference=target_reference,
        subject=observation.symbol,
        session_date=observation.session_date,
        label_end_date=observation.label_end_date,
    ).to_canonical_dict()


def _locked_oos_consumption_payload(
    *,
    formal_protocol: FormalResearchProtocol,
    evaluation_protocol: FormalEvaluationProtocol,
    target_reference: ValidationArtifactReference,
    observation_set_id: ArtifactId,
    binding: FormalEvaluationObservationBinding,
    observation: EvaluationObservation,
) -> tuple[str, dict[str, Any]] | None:
    locked_windows = tuple(
        item
        for item in evaluation_protocol.windows
        if item.partition is EvaluationPartition.LOCKED_OOS
        and item.start_date <= observation.session_date <= item.end_date
    )
    if not locked_windows:
        return None
    identity_payload = _locked_oos_evidence_identity_payload(
        formal_protocol=formal_protocol,
        target_reference=target_reference,
        binding=binding,
        observation=observation,
    )
    identity = LockedOOSEvidenceIdentity.from_canonical_dict(identity_payload)
    identity_hash = identity.identity_hash
    return identity_hash, {
        "schema_version": "locked-oos-evidence-consumption/v1",
        "evidence_identity": identity_payload,
        "first_consumption": {
            "formal_protocol_reference": ValidationArtifactReference(
                "FORMAL_RESEARCH_PROTOCOL",
                formal_protocol.protocol_id,
                formal_protocol.protocol_hash,
            ).to_canonical_dict(),
            "model_reference": formal_protocol.model_reference.to_canonical_dict(),
            "forecast_reference": binding.forecast_reference.to_canonical_dict(),
            "label_reference": binding.label_reference.to_canonical_dict(),
            "observation_set_id": str(observation_set_id),
            "evaluation_window_ids": [item.window_id for item in locked_windows],
        },
    }


def _require_locked_oos_consumption(
    connection: Any,
    *,
    identity_hash: str,
    payload: Mapping[str, Any],
    observation_set_id: ArtifactId,
) -> None:
    row = connection.execute(
        """
        SELECT evidence_identity_hash, observation_set_id, payload_json
        FROM locked_oos_evidence_consumption
        WHERE evidence_identity_hash = %s
        """,
        (identity_hash,),
    ).fetchone()
    if row is None or (
        str(row[0]) != identity_hash
        or str(row[1]) != str(observation_set_id)
        or row[2] != dict(payload)
    ):
        raise ResearchQualificationConflict(
            "Locked OOS evidence was already formally consumed"
        )


def _formal_evaluation_sources(
    protocol: FormalResearchProtocol,
    *,
    target_reference: ValidationArtifactReference,
    observation_set_reference: ValidationArtifactReference,
) -> tuple[ValidationArtifactReference, ...]:
    return _ordered_references(
        (
            ValidationArtifactReference(
                "FORMAL_RESEARCH_PROTOCOL", protocol.protocol_id, protocol.protocol_hash
            ),
            protocol.outcome_target_protocol_reference,
            target_reference,
            protocol.evaluation_protocol_reference,
            *tuple(protocol.component_references().values()),
            observation_set_reference,
        )
    )


def _observation_set_payload(
    *,
    formal_protocol: FormalResearchProtocol,
    panel_reference: ValidationArtifactReference,
    target_reference: ValidationArtifactReference,
    bindings: tuple[FormalEvaluationObservationBinding, ...],
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "formal-evaluation-observation-set/v1",
        "formal_protocol_reference": ValidationArtifactReference(
            "FORMAL_RESEARCH_PROTOCOL",
            formal_protocol.protocol_id,
            formal_protocol.protocol_hash,
        ).to_canonical_dict(),
        "panel_reference": panel_reference.to_canonical_dict(),
        "target_protocol_reference": formal_protocol.outcome_target_protocol_reference.to_canonical_dict(),
        "target_reference": target_reference.to_canonical_dict(),
        "observation_bindings": [item.to_canonical_dict() for item in bindings],
        "created_at": timestamp(created_at),
        "values_resolved_by": "POSTGRESQL_IMMUTABLE_OWNER_REPLAY",
    }


def _record_observation_set(
    connection: Any,
    *,
    observation_set_id: ArtifactId,
    observation_set_hash: str,
    observation_set_payload: Mapping[str, Any],
    formal_protocol: FormalResearchProtocol,
    panel_reference: ValidationArtifactReference,
    target_reference: ValidationArtifactReference,
    bindings: tuple[FormalEvaluationObservationBinding, ...],
    resolved: tuple[tuple[EvaluationObservation, str, datetime], ...],
    created_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO formal_evaluation_observation_set(
            observation_set_id, observation_set_hash, formal_protocol_id,
            panel_id, target_protocol_id, target_id, target_hash,
            observation_count, payload_json, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (observation_set_id) DO NOTHING
        """,
        (
            str(observation_set_id),
            observation_set_hash,
            str(formal_protocol.protocol_id),
            str(panel_reference.artifact_id),
            str(formal_protocol.outcome_target_protocol_reference.artifact_id),
            str(target_reference.artifact_id),
            target_reference.content_hash,
            len(bindings),
            Jsonb(dict(observation_set_payload)),
            created_at,
        ),
    )
    for binding, (observation, settlement_id, _) in zip(
        bindings, resolved, strict=True
    ):
        connection.execute(
            """
            INSERT INTO formal_evaluation_observation_binding(
                observation_set_id, observation_id, forecast_id,
                forecast_hash, settlement_id, label_id, label_hash,
                panel_id, slice_id, row_id, row_hash,
                session_date, label_end_date, payload_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s)
            ON CONFLICT (observation_set_id, observation_id) DO NOTHING
            """,
            (
                str(observation_set_id),
                binding.observation_id,
                str(binding.forecast_reference.artifact_id),
                binding.forecast_reference.content_hash,
                settlement_id,
                str(binding.label_reference.artifact_id),
                binding.label_reference.content_hash,
                str(panel_reference.artifact_id),
                str(binding.panel_slice_reference.artifact_id),
                str(binding.panel_row_reference.artifact_id),
                binding.panel_row_reference.content_hash,
                observation.session_date,
                observation.label_end_date,
                Jsonb(binding.to_canonical_dict()),
            ),
        )
    stored_set = connection.execute(
        """
        SELECT observation_set_hash, observation_count, payload_json
        FROM formal_evaluation_observation_set
        WHERE observation_set_id = %s
        """,
        (str(observation_set_id),),
    ).fetchone()
    stored_bindings = connection.execute(
        """
        SELECT payload_json
        FROM formal_evaluation_observation_binding
        WHERE observation_set_id = %s
        ORDER BY observation_id
        """,
        (str(observation_set_id),),
    ).fetchall()
    expected_binding_payloads = tuple(item.to_canonical_dict() for item in bindings)
    if stored_set is None or (
        str(stored_set[0]) != observation_set_hash
        or int(stored_set[1]) != len(bindings)
        or stored_set[2] != dict(observation_set_payload)
        or tuple(item[0] for item in stored_bindings) != expected_binding_payloads
    ):
        raise ResearchQualificationConflict(
            "Formal Evaluation observation-set identity conflict"
        )


def _record_oos_policy(
    connection: Any,
    *,
    policy: FormalOOSQualificationPolicy,
    created_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO formal_oos_qualification_policy(
            policy_id, policy_hash, payload_json, locked_at, created_at
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (policy_id) DO NOTHING
        """,
        (
            str(policy.policy_id),
            policy.policy_hash,
            Jsonb(policy.to_canonical_dict()),
            policy.locked_at,
            created_at,
        ),
    )
    row = connection.execute(
        """
        SELECT policy_hash, payload_json, locked_at
        FROM formal_oos_qualification_policy WHERE policy_id = %s
        """,
        (str(policy.policy_id),),
    ).fetchone()
    if row is None or (
        str(row[0]) != policy.policy_hash
        or row[1] != policy.to_canonical_dict()
        or row[2] != policy.locked_at
    ):
        raise ResearchQualificationConflict("Formal OOS Policy identity conflict")


def _duplicate_command(
    connection: Any,
    *,
    idempotency_key: str,
    command_hash: str,
    action_kind: str,
) -> ArtifactId | None:
    row = connection.execute(
        """
        SELECT command_hash, action_kind, decision_id
        FROM research_qualification_command
        WHERE idempotency_key = %s
        """,
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    if str(row[0]) != command_hash or str(row[1]) != action_kind:
        raise ResearchQualificationConflict("Research qualification idempotency conflict")
    return ArtifactId(str(row[2]))


def _record_command(
    connection: Any,
    *,
    idempotency_key: str,
    command_hash: str,
    action_kind: str,
    decision_id: ArtifactId,
    created_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO research_qualification_command(
            idempotency_key, command_hash, action_kind,
            decision_id, created_at
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (idempotency_key, command_hash, action_kind, str(decision_id), created_at),
    )


def _postgres_now(connection: Any) -> datetime:
    return connection.execute(
        "SELECT date_trunc('second', clock_timestamp())"
    ).fetchone()[0]


def _ordered_references(
    values: tuple[ValidationArtifactReference, ...],
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


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ResearchQualificationConflict("Qualification owner payload is not an object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ResearchQualificationConflict("Qualification owner payload is not an array")
    return tuple(value)


__all__ = [
    "PostgresResearchQualificationAuthority",
    "ResearchQualificationConflict",
]
