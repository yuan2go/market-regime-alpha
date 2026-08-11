"""PostgreSQL owner/writers for Historical Sample and Formal OOS qualification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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
from market_regime_alpha.application.research_validation.formal_forecast_computation import (
    FormalForecastComputationReceipt,
)
from market_regime_alpha.application.research_validation.formal_hypothesis_family import (
    FamilyEvaluationInput,
    FamilyEvaluationObservationBindings,
    FormalHypothesisFamilyEvaluationResult,
    FrozenHypothesisFamily,
    LockedOOSTargetObservationConsumption,
    RawOOSEvidenceIdentity,
    run_formal_hypothesis_family_evaluation,
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
    load_formal_protocol_pre_oos_owner,
    load_frozen_hypothesis_family_owner,
)
from market_regime_alpha.application.research_validation.qualification import (
    FormalEvaluationObservationBinding,
    FormalOOSQualificationDecision,
    FormalOOSQualificationPolicy,
    HistoricalSampleQualificationDecision,
    LockedOOSEvidenceIdentity,
    QualificationOutcome,
    evaluate_metric_floor_payloads,
    evaluate_pre_oos_metric_readiness,
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
from market_regime_alpha.data.pit_artifact_authority import (
    PITUniverseMembershipAuthorityProjection,
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


@dataclass(frozen=True, slots=True)
class _LockedOOSRosterPreparation:
    roster_id: ArtifactId
    roster_hash: str
    frozen_at: datetime


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
        formal_pit_evidence_ids: tuple[ArtifactId, ...] = (),
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> HistoricalSampleQualificationDecision:
        pit_ids = tuple(sorted(set(formal_pit_evidence_ids), key=str))
        if formal_pit_evidence_id is not None:
            if pit_ids and formal_pit_evidence_id not in pit_ids:
                raise ValueError(
                    "Historical qualification primary PIT is outside PIT set"
                )
            if not pit_ids:
                pit_ids = (formal_pit_evidence_id,)
        command = {
            "action": "QUALIFY_HISTORICAL_SAMPLE",
            "dataset_id": str(dataset_id),
            "formal_protocol_id": (
                None if formal_protocol_id is None else str(formal_protocol_id)
            ),
            "formal_pit_evidence_ids": [str(item) for item in pit_ids],
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
            pits = tuple(_load_formal_pit(connection, item) for item in pit_ids)
            outcome, reasons, provider_decisions, forecast_receipts = (
                _assess_historical_sample(
                    connection,
                    dataset=dataset,
                    protocol=protocol,
                    pits=pits,
                    evaluated_at=now,
                )
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
                    if not pits
                    else ValidationArtifactReference(
                        "FORMAL_PIT_EVIDENCE",
                        pits[0].evidence_id,
                        pits[0].evidence_hash,
                    )
                ),
                formal_pit_references=tuple(
                    ValidationArtifactReference(
                        "FORMAL_PIT_EVIDENCE", item.evidence_id, item.evidence_hash
                    )
                    for item in pits
                ),
                provider_fact_decision_references=provider_decisions,
                formal_forecast_receipt_references=forecast_receipts,
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
                    None if not pits else str(pits[0].evidence_id),
                    outcome.value,
                    decision.qualified,
                    revision,
                    None if supersedes is None else str(supersedes),
                    Jsonb(decision.to_canonical_dict()),
                    now,
                ),
            )
            for ordinal, pit in enumerate(pits, start=1):
                connection.execute(
                    """
                    INSERT INTO historical_sample_qualification_pit_evidence(
                        decision_id, ordinal, formal_pit_evidence_id,
                        formal_pit_evidence_hash
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        str(decision.decision_id),
                        ordinal,
                        str(pit.evidence_id),
                        pit.evidence_hash,
                    ),
                )
            for ordinal, receipt in enumerate(forecast_receipts, start=1):
                connection.execute(
                    """
                    INSERT INTO historical_sample_qualification_forecast_receipt(
                        decision_id, ordinal, receipt_id, receipt_hash
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        str(decision.decision_id),
                        ordinal,
                        str(receipt.artifact_id),
                        receipt.content_hash,
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
            owner_protocol = _load_formal_protocol(connection, formal_protocol_id)
            owner_evaluation = _load_evaluation_protocol(
                connection,
                owner_protocol.evaluation_protocol_reference.artifact_id,
            )
            if target_reference not in owner_protocol.target_references:
                raise ResearchQualificationConflict(
                    "Formal Evaluation Target is not frozen in the Formal Research Protocol"
                )
            preflight_forecasts = tuple(
                _resolve_forecast_evaluation_input(
                    connection,
                    protocol=owner_protocol,
                    target_reference=target_reference,
                    binding=binding,
                    require_formal_forecast=False,
                    formal_pit_evidence_ids=(),
                )[0]
                for binding in ordered_bindings
            )
            if any(
                window.partition is EvaluationPartition.LOCKED_OOS
                and window.start_date
                <= forecast.decision_time.date()
                <= window.end_date
                for forecast in preflight_forecasts
                for window in owner_evaluation.windows
            ):
                raise ResearchQualificationConflict(
                    "LEGACY_SINGLE_TARGET_LOCKED_OOS_REPLAY_ONLY_USE_FAMILY_AUTHORITY"
                )
            owner_pit = _load_formal_pit(connection, formal_pit_evidence_id)
            panel = _load_panel_owner(
                connection,
                panel_reference,
                protocol=owner_protocol,
            )
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

    def record_family_evaluation_candidate(
        self,
        *,
        formal_protocol_id: ArtifactId,
        observation_groups: tuple[FamilyEvaluationObservationBindings, ...],
        historical_sample_decision_ids: tuple[ArtifactId, ...],
        formal_pit_evidence_id: ArtifactId,
        actor: str,
        reason: str,
        idempotency_key: str,
        formal_pit_evidence_ids: tuple[ArtifactId, ...] = (),
    ) -> FormalHypothesisFamilyEvaluationResult:
        """Resolve and evaluate the complete pre-registered Target family."""

        if not actor.strip() or not reason.strip() or not idempotency_key.strip():
            raise ValueError(
                "Formal Family Evaluation actor, reason and idempotency key are required"
            )
        sample_ids = tuple(sorted(set(historical_sample_decision_ids), key=str))
        if not sample_ids:
            raise ValueError("Formal Family Evaluation requires qualified C3 decisions")

        pit_ids = tuple(sorted(set(formal_pit_evidence_ids), key=str))
        if pit_ids and formal_pit_evidence_id not in pit_ids:
            raise ValueError("Family Evaluation primary PIT is outside PIT set")
        if not pit_ids:
            pit_ids = (formal_pit_evidence_id,)
        ordered_groups = tuple(
            sorted(
                observation_groups,
                key=lambda item: (
                    item.target_reference.artifact_kind,
                    str(item.target_reference.artifact_id),
                    item.target_reference.content_hash,
                ),
            )
        )
        command_payload = {
            "schema_version": "formal-family-evaluation-command/v1",
            "formal_protocol_id": str(formal_protocol_id),
            "historical_sample_decision_ids": [str(item) for item in sample_ids],
            "formal_pit_evidence_ids": [str(item) for item in pit_ids],
            "observation_groups": [
                {
                    "target_reference": item.target_reference.to_canonical_dict(),
                    "panel_reference": item.panel_reference.to_canonical_dict(),
                    "observation_bindings": [
                        binding.to_canonical_dict()
                        for binding in item.observation_bindings
                    ],
                }
                for item in ordered_groups
            ],
            "actor": actor,
            "reason": reason,
        }
        command_hash = canonical_hash(command_payload)
        with self._factory.connection(read_only=True) as connection:
            existing_result = _existing_family_operator_result(
                connection,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
            )
        if existing_result is not None:
            return existing_result
        prepared = self._factory.run_transaction(
            lambda connection: _prepare_locked_oos_roster(
                connection,
                formal_protocol_id=formal_protocol_id,
                groups=ordered_groups,
                sample_ids=sample_ids,
                pit_ids=pit_ids,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
            )
        )

        def operation(connection: Any) -> FormalHypothesisFamilyEvaluationResult:
            acquire_scope_lock(
                connection,
                namespace="formal-family-evaluation-idempotency",
                identity=idempotency_key,
            )
            duplicate = connection.execute(
                """
                SELECT command_hash, action_kind, result_artifact_id
                FROM phase_c_formal_operator_command
                WHERE idempotency_key = %s
                """,
                (idempotency_key,),
            ).fetchone()
            if duplicate is not None:
                if (
                    str(duplicate[0]) != command_hash
                    or str(duplicate[1]) != "EVALUATE_FORMAL_FAMILY"
                ):
                    raise ResearchQualificationConflict(
                        "Formal Family Evaluation idempotency conflict"
                    )
                return _load_family_evaluation_result(
                    connection, ArtifactId(str(duplicate[2]))
                )
            protocol = _load_formal_protocol(connection, formal_protocol_id)
            evaluation = _load_evaluation_protocol(
                connection,
                protocol.evaluation_protocol_reference.artifact_id,
            )
            family = load_frozen_hypothesis_family_owner(
                connection,
                formal_protocol_id=formal_protocol_id,
            )
            if tuple(item.target_reference for item in ordered_groups) != (
                family.target_references
            ):
                raise ResearchQualificationConflict(
                    "Formal Family Evaluation requires every frozen Target exactly once"
                )
            created_at = prepared.frozen_at
            samples = tuple(
                _load_historical_decision(connection, item) for item in sample_ids
            )
            if any(
                not sample.qualified
                or sample.outcome is not QualificationOutcome.SATISFIED
                or sample.evaluated_at > created_at
                for sample in samples
            ):
                raise ResearchQualificationConflict(
                    "C3_QUALIFIED_HISTORICAL_SAMPLE_REQUIRED_BEFORE_LOCKED_OOS"
                )
            pits = tuple(_load_formal_pit(connection, item) for item in pit_ids)
            _require_family_historical_prerequisites(
                connection,
                protocol=protocol,
                family=family,
                pits=pits,
                samples=samples,
                evaluated_at=created_at,
            )
            _require_locked_oos_roster(
                connection,
                preparation=prepared,
                protocol=protocol,
                family=family,
                groups=ordered_groups,
                pits=pits,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
            )
            inputs: list[FamilyEvaluationInput] = []
            used_pit_ids: set[ArtifactId] = set()
            observation_sets: list[
                tuple[
                    ValidationArtifactReference,
                    FamilyEvaluationObservationBindings,
                    tuple[EvaluationObservation, ...],
                ]
            ] = []
            for group in ordered_groups:
                panel = _load_panel_owner(
                    connection,
                    group.panel_reference,
                    protocol=protocol,
                )
                resolved = tuple(
                    _resolve_evaluation_observation(
                        connection,
                        protocol=protocol,
                        panel=panel,
                        target_reference=group.target_reference,
                        binding=binding,
                        require_formal_forecast=True,
                        formal_pit_evidence_ids=pit_ids,
                    )
                    for binding in group.observation_bindings
                )
                observations = tuple(item[0] for item in resolved)
                used_pit_ids.update(item[3] for item in resolved if item[3] is not None)
                if any(item[2] > created_at for item in resolved):
                    raise ResearchQualificationConflict(
                        "Family Evaluation predates an owner-resolved Target Label"
                    )
                set_payload = _observation_set_payload(
                    formal_protocol=protocol,
                    panel_reference=group.panel_reference,
                    target_reference=group.target_reference,
                    bindings=group.observation_bindings,
                    created_at=created_at,
                )
                set_hash = canonical_hash(set_payload)
                set_id = ArtifactId(f"formal-evaluation-observation-set:{set_hash[7:]}")
                set_reference = ValidationArtifactReference(
                    "FORMAL_EVALUATION_OBSERVATION_SET",
                    set_id,
                    set_hash,
                )
                _record_observation_set(
                    connection,
                    observation_set_id=set_id,
                    observation_set_hash=set_hash,
                    observation_set_payload=set_payload,
                    formal_protocol=protocol,
                    panel_reference=group.panel_reference,
                    target_reference=group.target_reference,
                    bindings=group.observation_bindings,
                    resolved=resolved,
                    created_at=created_at,
                )
                panel_sources = _formal_evaluation_sources(
                    protocol,
                    target_reference=group.target_reference,
                    observation_set_reference=set_reference,
                )
                inputs.append(
                    FamilyEvaluationInput(
                        target_reference=group.target_reference,
                        panel_reference=group.panel_reference,
                        observations=observations,
                        panel_source_references=panel_sources,
                    )
                )
                observation_sets.append((set_reference, group, observations))
            if used_pit_ids != set(pit_ids):
                raise ResearchQualificationConflict(
                    "Formal Family Evaluation PIT lineage is not exactly consumed"
                )
            _consume_family_locked_oos(
                connection,
                protocol=protocol,
                evaluation_protocol=evaluation,
                family=family,
                observation_sets=tuple(observation_sets),
                consumed_at=created_at,
            )
            result = run_formal_hypothesis_family_evaluation(
                family=family,
                protocol=evaluation,
                inputs=tuple(inputs),
                formal_pit_evidence=pits[0],
                formal_pit_evidences=pits,
                created_at=created_at,
                frozen_trading_dates=protocol.frozen_trading_dates,
            )
            _record_family_evaluation_result(
                connection,
                result=result,
                protocol=protocol,
                pits=pits,
                samples=samples,
                observation_sets=tuple(observation_sets),
            )
            connection.execute(
                """
                INSERT INTO phase_c_formal_operator_command(
                    idempotency_key, command_hash, action_kind,
                    result_artifact_id, result_artifact_hash,
                    actor, reason, payload_json, created_at
                ) VALUES (
                    %s, %s, 'EVALUATE_FORMAL_FAMILY', %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    idempotency_key,
                    command_hash,
                    str(result.result_id),
                    result.result_hash,
                    actor,
                    reason,
                    Jsonb(command_payload),
                    created_at,
                ),
            )
            return result

        return self._factory.run_transaction(operation)

    def get_family_evaluation_candidate(
        self, result_id: ArtifactId
    ) -> FormalHypothesisFamilyEvaluationResult:
        with self._factory.connection(read_only=True) as connection:
            return _load_family_evaluation_result(connection, result_id)

    def replay_family_evaluation_candidate(
        self, result_id: ArtifactId
    ) -> FormalHypothesisFamilyEvaluationResult:
        with self._factory.connection(read_only=True) as connection:
            return _replay_family_evaluation_result(connection, result_id)

    def qualify_formal_oos(
        self,
        *,
        policy: FormalOOSQualificationPolicy,
        formal_protocol_id: ArtifactId,
        evaluation_result_id: ArtifactId,
        historical_sample_decision_id: ArtifactId,
        historical_sample_decision_ids: tuple[ArtifactId, ...] = (),
        formal_pit_evidence_id: ArtifactId,
        actor: str,
        reason: str,
        idempotency_key: str,
        formal_pit_evidence_ids: tuple[ArtifactId, ...] = (),
    ) -> FormalOOSQualificationDecision:
        sample_ids = tuple(sorted(set(historical_sample_decision_ids), key=str))
        if sample_ids and historical_sample_decision_id not in sample_ids:
            raise ValueError("Formal OOS primary Historical decision is outside family")
        if not sample_ids:
            sample_ids = (historical_sample_decision_id,)
        pit_ids = tuple(sorted(set(formal_pit_evidence_ids), key=str))
        if pit_ids and formal_pit_evidence_id not in pit_ids:
            raise ValueError("Formal OOS primary PIT is outside PIT set")
        if not pit_ids:
            pit_ids = (formal_pit_evidence_id,)
        command = {
            "action": "QUALIFY_FORMAL_OOS",
            "policy_id": str(policy.policy_id),
            "formal_protocol_id": str(formal_protocol_id),
            "evaluation_result_id": str(evaluation_result_id),
            "historical_sample_decision_ids": [str(item) for item in sample_ids],
            "formal_pit_evidence_ids": [str(item) for item in pit_ids],
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
            samples = tuple(
                _load_historical_decision(connection, item) for item in sample_ids
            )
            stored_result = _load_validation_artifact(
                connection,
                evaluation_result_id,
                expected_kind="FORMAL_HYPOTHESIS_FAMILY_EVALUATION_RESULT",
            )
            result = FormalHypothesisFamilyEvaluationResult.from_canonical_dict(
                {
                    "result_id": str(evaluation_result_id),
                    "result_hash": str(stored_result[0]),
                    **dict(_mapping(stored_result[1])),
                }
            )
            expected_pit_ids = tuple(
                item.artifact_id for item in result.pit_evidence_references
            )
            if pit_ids != expected_pit_ids:
                raise ResearchQualificationConflict(
                    "Formal OOS PIT scope differs from Family Evaluation owner lineage"
                )
            pits = tuple(_load_formal_pit(connection, item) for item in pit_ids)
            outcome, reasons = _assess_formal_oos_family(
                connection,
                policy=policy,
                protocol=protocol,
                pits=pits,
                samples=samples,
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
                    "FORMAL_HYPOTHESIS_FAMILY_EVALUATION_RESULT",
                    evaluation_result_id,
                    str(stored_result[0]),
                ),
                historical_sample_decision_reference=ValidationArtifactReference(
                    "HISTORICAL_SAMPLE_QUALIFICATION_DECISION",
                    samples[0].decision_id,
                    samples[0].decision_hash,
                ),
                historical_sample_decision_references=tuple(
                    ValidationArtifactReference(
                        "HISTORICAL_SAMPLE_QUALIFICATION_DECISION",
                        sample.decision_id,
                        sample.decision_hash,
                    )
                    for sample in samples
                ),
                formal_pit_reference=ValidationArtifactReference(
                    "FORMAL_PIT_EVIDENCE", pits[0].evidence_id, pits[0].evidence_hash
                ),
                formal_pit_references=tuple(
                    ValidationArtifactReference(
                        "FORMAL_PIT_EVIDENCE", pit.evidence_id, pit.evidence_hash
                    )
                    for pit in pits
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
                    str(samples[0].decision_id),
                    str(pits[0].evidence_id),
                    outcome.value,
                    decision.formal_evaluation_complete,
                    decision.formal_oos_passed,
                    revision,
                    None if supersedes is None else str(supersedes),
                    Jsonb(decision.to_canonical_dict()),
                    now,
                ),
            )
            for ordinal, sample in enumerate(samples, start=1):
                connection.execute(
                    """
                    INSERT INTO formal_oos_qualification_historical_decision(
                        formal_oos_decision_id, ordinal,
                        historical_decision_id, historical_decision_hash
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        str(decision.decision_id),
                        ordinal,
                        str(sample.decision_id),
                        sample.decision_hash,
                    ),
                )
            for ordinal, pit in enumerate(pits, start=1):
                connection.execute(
                    """
                    INSERT INTO formal_oos_qualification_pit_evidence(
                        formal_oos_decision_id, ordinal,
                        formal_pit_evidence_id, formal_pit_evidence_hash
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        str(decision.decision_id),
                        ordinal,
                        str(pit.evidence_id),
                        pit.evidence_hash,
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
            pit_rows = connection.execute(
                """
                SELECT formal_pit_evidence_id, formal_pit_evidence_hash
                FROM historical_sample_qualification_pit_evidence
                WHERE decision_id = %s ORDER BY ordinal
                """,
                (str(decision_id),),
            ).fetchall()
            receipt_rows = connection.execute(
                """
                SELECT receipt_id, receipt_hash
                FROM historical_sample_qualification_forecast_receipt
                WHERE decision_id = %s ORDER BY ordinal
                """,
                (str(decision_id),),
            ).fetchall()
        if row is None:
            raise KeyError(str(decision_id))
        decision = HistoricalSampleQualificationDecision.from_canonical_dict(
            _mapping(row[0])
        )
        if decision.decision_hash != str(row[1]):
            raise ResearchQualificationConflict(
                "Historical Sample decision storage hash mismatch"
            )
        expected_pits = tuple(
            (str(item.artifact_id), item.content_hash)
            for item in decision.formal_pit_references
        )
        if tuple((str(item[0]), str(item[1])) for item in pit_rows) != expected_pits:
            raise ResearchQualificationConflict(
                "Historical Sample decision PIT binding storage mismatch"
            )
        expected_receipts = tuple(
            (str(item.artifact_id), item.content_hash)
            for item in decision.formal_forecast_receipt_references
        )
        if (
            tuple((str(item[0]), str(item[1])) for item in receipt_rows)
            != expected_receipts
        ):
            raise ResearchQualificationConflict(
                "Historical Sample decision Forecast receipt binding storage mismatch"
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
            historical_rows = connection.execute(
                """
                SELECT historical_decision_id, historical_decision_hash
                FROM formal_oos_qualification_historical_decision
                WHERE formal_oos_decision_id = %s ORDER BY ordinal
                """,
                (str(decision_id),),
            ).fetchall()
            pit_rows = connection.execute(
                """
                SELECT formal_pit_evidence_id, formal_pit_evidence_hash
                FROM formal_oos_qualification_pit_evidence
                WHERE formal_oos_decision_id = %s ORDER BY ordinal
                """,
                (str(decision_id),),
            ).fetchall()
        if row is None:
            raise KeyError(str(decision_id))
        decision = FormalOOSQualificationDecision.from_canonical_dict(_mapping(row[0]))
        if decision.decision_hash != str(row[1]):
            raise ResearchQualificationConflict("Formal OOS storage hash mismatch")
        expected_historical = tuple(
            (str(item.artifact_id), item.content_hash)
            for item in decision.historical_sample_decision_references
        )
        if (
            tuple((str(item[0]), str(item[1])) for item in historical_rows)
            != expected_historical
        ):
            raise ResearchQualificationConflict(
                "Formal OOS Historical decision binding storage mismatch"
            )
        expected_pits = tuple(
            (str(item.artifact_id), item.content_hash)
            for item in decision.formal_pit_references
        )
        if tuple((str(item[0]), str(item[1])) for item in pit_rows) != expected_pits:
            raise ResearchQualificationConflict(
                "Formal OOS PIT Evidence binding storage mismatch"
            )
        return decision


def _assess_historical_sample(
    connection: Any,
    *,
    dataset: HistoricalSampleDataset,
    protocol: FormalResearchProtocol | None,
    pits: tuple[FormalPITEvidenceArtifact, ...],
    evaluated_at: datetime,
) -> tuple[
    QualificationOutcome,
    tuple[str, ...],
    tuple[ValidationArtifactReference, ...],
    tuple[ValidationArtifactReference, ...],
]:
    blocked: set[str] = set()
    rejected: set[str] = set()
    if protocol is None:
        blocked.add("FORMAL_RESEARCH_PROTOCOL_MISSING")
    if not pits:
        blocked.add("FORMAL_PIT_EVIDENCE_MISSING")
    if blocked:
        return QualificationOutcome.BLOCKED, tuple(sorted(blocked)), (), ()
    assert protocol is not None and pits
    pit_requests = tuple(_load_formal_pit_request(connection, pit) for pit in pits)
    if any(pit.outcome is not PITValidationOutcome.SATISFIED for pit in pits):
        blocked.add("FORMAL_PIT_NOT_SATISFIED")
    if any(
        pit.available_at > evaluated_at or pit.recorded_at > evaluated_at
        for pit in pits
    ):
        rejected.add("FORMAL_PIT_NOT_AVAILABLE_AT_QUALIFICATION")
    if any(
        protocol.dataset_reference.artifact_id != pit.lineage.dataset.artifact_id
        or protocol.dataset_reference.content_hash != pit.lineage.dataset.content_hash
        for pit in pits
    ):
        rejected.add("FORMAL_PROTOCOL_DATASET_PIT_LINEAGE_MISMATCH")
    if (
        ValidationArtifactReference(
            "HISTORICAL_SAMPLE_DATASET", dataset.dataset_id, dataset.dataset_hash
        )
        not in protocol.historical_sample_dataset_references
    ):
        rejected.add("FORMAL_PROTOCOL_HISTORICAL_SAMPLE_DATASET_MISMATCH")
    if any(
        protocol.universe_reference.artifact_id != pit.lineage.universe.artifact_id
        or protocol.universe_reference.content_hash != pit.lineage.universe.content_hash
        for pit in pits
    ):
        rejected.add("FORMAL_PROTOCOL_UNIVERSE_PIT_LINEAGE_MISMATCH")
    if any(
        protocol.model_reference.artifact_id != pit.lineage.model_lineage_id
        or protocol.model_reference.content_hash != pit.lineage.model_lineage_hash
        for pit in pits
    ):
        rejected.add("FORMAL_PROTOCOL_MODEL_PIT_LINEAGE_MISMATCH")
    if dataset.target_reference not in protocol.target_references:
        rejected.add("HISTORICAL_SAMPLE_OUTCOME_TARGET_IDENTITY_MISMATCH")
    forecast_receipts: set[ValidationArtifactReference] = set()
    for record in dataset.records:
        matching = tuple(
            (pit, request)
            for pit, request in zip(pits, pit_requests, strict=True)
            if request.decision_time == record.sample.sample_decision_time.value
            and record.sample.symbol in request.symbols
        )
        if len(matching) != 1:
            rejected.add("HISTORICAL_SAMPLE_FORMAL_PIT_BINDING_NOT_EXACT")
            continue
        pit, pit_request = matching[0]
        selected = {
            (str(item.fact_id), item.fact_hash)
            for item in pit.selected_fact_authorities
        }
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
                    expected_symbol=record.sample.symbol,
                    expected_decision_time=(record.sample.sample_decision_time.value),
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
        receipt_reasons, receipt_reference = _historical_forecast_receipt_resolution(
            connection,
            protocol=protocol,
            record=record,
            pit=pit,
        )
        rejected.update(receipt_reasons)
        if receipt_reference is not None:
            forecast_receipts.add(receipt_reference)
    provider_references: set[ValidationArtifactReference] = set()
    for pit in pits:
        provider_refs, provider_reasons = _resolve_provider_fact_decisions(
            connection, pit=pit, evaluated_at=evaluated_at
        )
        provider_references.update(provider_refs)
        blocked.update(provider_reasons)
    provider_refs = tuple(
        sorted(
            provider_references,
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )
    receipt_refs = _ordered_references(tuple(forecast_receipts))
    if rejected:
        return (
            QualificationOutcome.REJECTED,
            tuple(sorted(rejected | blocked)),
            provider_refs,
            receipt_refs,
        )
    if blocked:
        return (
            QualificationOutcome.BLOCKED,
            tuple(sorted(blocked)),
            provider_refs,
            receipt_refs,
        )
    return QualificationOutcome.SATISFIED, (), provider_refs, receipt_refs


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
                str(row[9]) != str(protocol.trading_calendar_reference.artifact_id)
                or str(row[10]) != protocol.trading_calendar_reference.content_hash
            ):
                reasons.add("FORMAL_PIT_FROZEN_CALENDAR_LINEAGE_MISMATCH")
    if selected_keys != required:
        reasons.add("HISTORICAL_SAMPLE_PIT_FACT_REQUIREMENT_MISMATCH")
    if calendar_facts == 0:
        reasons.add("FORMAL_PIT_FROZEN_CALENDAR_LINEAGE_MISSING")
    return tuple(sorted(reasons))


def _historical_forecast_receipt_resolution(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    record: HistoricalPathSampleRecord,
    pit: FormalPITEvidenceArtifact,
) -> tuple[tuple[str, ...], ValidationArtifactReference | None]:
    rows = connection.execute(
        """
        SELECT receipt.receipt_id, receipt.receipt_hash,
               receipt.formal_protocol_id, receipt.formal_pit_evidence_id,
               receipt.forecast_id, receipt.decision_time,
               receipt.materialized_at, receipt.payload_json,
               forecast.forecast_hash, forecast.forecast_authority
        FROM formal_forecast_computation_receipt AS receipt
        JOIN outcome_target_bound_forecast AS forecast
          ON forecast.forecast_id = receipt.forecast_id
        WHERE receipt.formal_protocol_id = %s
          AND receipt.formal_pit_evidence_id = %s
          AND receipt.decision_time = %s
          AND forecast.symbol = %s
        """,
        (
            str(protocol.protocol_id),
            str(pit.evidence_id),
            record.sample.sample_decision_time.value,
            record.sample.symbol,
        ),
    ).fetchall()
    if len(rows) != 1 or not isinstance(rows[0][7], Mapping):
        return (
            ("HISTORICAL_SAMPLE_FORMAL_FORECAST_RECEIPT_BINDING_NOT_EXACT",),
            None,
        )
    row = rows[0]
    try:
        receipt = FormalForecastComputationReceipt.from_canonical_dict(dict(row[7]))
    except (KeyError, TypeError, ValueError):
        return (("HISTORICAL_SAMPLE_FORMAL_FORECAST_RECEIPT_REPLAY_FAILED",), None)
    reference = ValidationArtifactReference(
        "FORMAL_FORECAST_COMPUTATION_RECEIPT",
        ArtifactId(str(row[0])),
        str(row[1]),
    )
    if (
        receipt.receipt_id != reference.artifact_id
        or receipt.receipt_hash != reference.content_hash
        or str(row[2]) != str(protocol.protocol_id)
        or str(row[3]) != str(pit.evidence_id)
        or str(row[4]) != str(receipt.forecast_reference.artifact_id)
        or row[5] != record.sample.sample_decision_time.value
        or row[6] != receipt.materialized_at
        or str(row[8]) != receipt.forecast_reference.content_hash
        or str(row[9]) != "FORMAL_OWNER_COMPUTED"
        or receipt.request.symbol != record.sample.symbol
        or receipt.decision_time != record.sample.sample_decision_time.value
    ):
        return (("HISTORICAL_SAMPLE_FORMAL_FORECAST_RECEIPT_LINEAGE_MISMATCH",), None)
    return (), reference


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
            or resolved_decision.status is not ProviderFactQualificationStatus.QUALIFIED
        ):
            reasons.add(f"PROVIDER_FACT_NOT_QUALIFIED_{fact[2]}")
            continue
        source_refs = tuple(resolved_decision.source_qualification_references)
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
    if (
        sample.formal_protocol_reference is None
        or sample.formal_protocol_reference.artifact_id != protocol.protocol_id
        or sample.formal_protocol_reference.content_hash != protocol.protocol_hash
    ):
        rejected.add("HISTORICAL_SAMPLE_FORMAL_PROTOCOL_LINEAGE_MISMATCH")
    if sample.formal_pit_reference is None or (
        sample.formal_pit_reference.artifact_id != pit.evidence_id
        or sample.formal_pit_reference.content_hash != pit.evidence_hash
    ):
        rejected.add("HISTORICAL_SAMPLE_FORMAL_PIT_LINEAGE_MISSING")
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


def _assess_formal_oos_family(
    connection: Any,
    *,
    policy: FormalOOSQualificationPolicy,
    protocol: FormalResearchProtocol,
    pits: tuple[FormalPITEvidenceArtifact, ...],
    samples: tuple[HistoricalSampleQualificationDecision, ...],
    result_id: ArtifactId,
    result_hash: str,
    result_payload: Mapping[str, Any],
) -> tuple[QualificationOutcome, tuple[str, ...]]:
    blocked: set[str] = set()
    rejected: set[str] = set()
    if protocol.formal_oos_qualification_policy_reference != (
        ValidationArtifactReference(
            "FORMAL_OOS_QUALIFICATION_POLICY",
            policy.policy_id,
            policy.policy_hash,
        )
    ):
        rejected.add("FORMAL_OOS_POLICY_NOT_FROZEN_IN_RESEARCH_PROTOCOL")
    if not samples or any(not sample.qualified for sample in samples):
        blocked.add("QUALIFIED_HISTORICAL_SAMPLE_REQUIRED")
    if any(
        sample.formal_protocol_reference is None
        or sample.formal_protocol_reference.artifact_id != protocol.protocol_id
        or sample.formal_protocol_reference.content_hash != protocol.protocol_hash
        for sample in samples
    ):
        rejected.add("HISTORICAL_SAMPLE_FORMAL_PROTOCOL_LINEAGE_MISMATCH")
    if any(not sample.formal_pit_references for sample in samples):
        rejected.add("HISTORICAL_SAMPLE_FORMAL_PIT_LINEAGE_MISMATCH")
    try:
        result = FormalHypothesisFamilyEvaluationResult.from_canonical_dict(
            {
                "result_id": str(result_id),
                "result_hash": result_hash,
                **dict(result_payload),
            }
        )
        family = load_frozen_hypothesis_family_owner(
            connection, formal_protocol_id=protocol.protocol_id
        )
    except (KeyError, TypeError, ValueError, FormalProtocolConflict) as exc:
        raise ResearchQualificationConflict(
            "Formal Family Evaluation owner replay failed"
        ) from exc
    if result.family_reference != family.reference:
        rejected.add("FORMAL_HYPOTHESIS_FAMILY_LINEAGE_MISMATCH")
    if result.evaluation_protocol_reference != protocol.evaluation_protocol_reference:
        rejected.add("FORMAL_EVALUATION_PROTOCOL_LINEAGE_MISMATCH")
    expected_pit_references = _ordered_references(
        tuple(
            ValidationArtifactReference(
                "FORMAL_PIT_EVIDENCE", pit.evidence_id, pit.evidence_hash
            )
            for pit in pits
        )
    )
    if result.pit_evidence_references != expected_pit_references:
        rejected.add("FORMAL_EVALUATION_PIT_LINEAGE_MISMATCH")
    evaluation_historical_rows = connection.execute(
        """
        SELECT historical_decision_id, historical_decision_hash
        FROM formal_hypothesis_family_evaluation_historical_decision
        WHERE result_id = %s ORDER BY ordinal
        """,
        (str(result_id),),
    ).fetchall()
    if tuple(
        (str(item[0]), str(item[1])) for item in evaluation_historical_rows
    ) != tuple((str(sample.decision_id), sample.decision_hash) for sample in samples):
        rejected.add("FORMAL_EVALUATION_C3_PREREQUISITE_LINEAGE_MISMATCH")
    historical_pit_references = _ordered_references(
        tuple(
            reference
            for sample in samples
            for reference in sample.formal_pit_references
        )
    )
    if historical_pit_references != expected_pit_references:
        rejected.add("HISTORICAL_SAMPLE_FORMAL_PIT_LINEAGE_MISMATCH")
    historical_targets: dict[str, HistoricalSampleQualificationDecision] = {}
    for sample in samples:
        dataset = _load_historical_dataset(
            connection, sample.dataset_reference.artifact_id
        )
        if (
            dataset.dataset_hash != sample.dataset_reference.content_hash
            or str(dataset.target_reference.artifact_id) in historical_targets
        ):
            rejected.add("HISTORICAL_SAMPLE_FAMILY_DATASET_IDENTITY_MISMATCH")
            continue
        historical_targets[str(dataset.target_reference.artifact_id)] = sample
    if set(historical_targets) != {
        str(item.artifact_id) for item in family.target_references
    }:
        blocked.add("HISTORICAL_SAMPLE_FAMILY_TARGET_COVERAGE_INCOMPLETE")
    if any(
        sample.dataset_reference not in protocol.historical_sample_dataset_references
        for sample in samples
    ):
        rejected.add("FORMAL_EVALUATION_SAMPLE_DATASET_LINEAGE_MISSING")
    if not blocked:
        rejected.update(
            _historical_family_observation_coverage_reasons(
                connection,
                result_id=result_id,
                family=family,
                historical_targets=historical_targets,
            )
        )
    replayed = _replay_family_evaluation_result(connection, result_id)
    if replayed != result:
        rejected.add("FORMAL_FAMILY_EVALUATION_REPLAY_MISMATCH")
    evaluation_protocol = _load_evaluation_protocol(
        connection, protocol.evaluation_protocol_reference.artifact_id
    )
    expected_folds_by_partition = {
        partition.value: tuple(
            sorted(
                {
                    item.fold
                    for item in evaluation_protocol.windows
                    if item.partition is partition
                }
            )
        )
        for partition in EvaluationPartition
    }
    metrics_by_target: dict[str, list[Mapping[str, Any]]] = {
        str(item.artifact_id): [] for item in family.target_references
    }
    for item in _sequence(result_payload["metrics"]):
        family_metric = _mapping(item)
        target = ValidationArtifactReference.from_canonical_dict(
            _mapping(family_metric["target_reference"])
        )
        if target not in family.target_references:
            rejected.add("FORMAL_FAMILY_METRIC_TARGET_NOT_FROZEN")
            continue
        metrics_by_target[str(target.artifact_id)].append(
            _mapping(family_metric["metric"])
        )
    for target_id, target_metrics in metrics_by_target.items():
        for partition, expected_folds in expected_folds_by_partition.items():
            observed_folds = {
                int(item["fold"])
                for item in target_metrics
                if str(item["partition"]) == partition
            }
            if observed_folds != set(expected_folds):
                blocked.add(f"{partition}_FOLD_COVERAGE_INCOMPLETE:{target_id}")
    if rejected:
        return QualificationOutcome.REJECTED, tuple(sorted(rejected | blocked))
    if blocked:
        return QualificationOutcome.BLOCKED, tuple(sorted(blocked))
    pre_oos_reasons: set[str] = set()
    for target_id, target_metrics in metrics_by_target.items():
        pre_oos_outcome, target_reasons = evaluate_pre_oos_metric_readiness(
            policy=policy,
            metrics=tuple(target_metrics),
            required_partition_folds={
                partition: expected_folds_by_partition[partition]
                for partition in ("TRAIN", "VALIDATION")
            },
        )
        if pre_oos_outcome is not QualificationOutcome.SATISFIED:
            pre_oos_reasons.update(f"{reason}:{target_id}" for reason in target_reasons)
    if pre_oos_reasons:
        return QualificationOutcome.NOT_ESTIMABLE, tuple(sorted(pre_oos_reasons))
    all_metric_payloads = tuple(
        item for target_metrics in metrics_by_target.values() for item in target_metrics
    )
    return evaluate_metric_floor_payloads(
        policy=policy,
        metrics=all_metric_payloads,
    )


def _historical_family_observation_coverage_reasons(
    connection: Any,
    *,
    result_id: ArtifactId,
    family: FrozenHypothesisFamily,
    historical_targets: Mapping[str, HistoricalSampleQualificationDecision],
) -> tuple[str, ...]:
    """Reject Train/Validation cherry-picking between qualified C3 and C4."""

    reasons: set[str] = set()
    result_rows = connection.execute(
        """
        SELECT target_id, target_hash, observation_set_id
        FROM formal_hypothesis_family_evaluation_target
        WHERE result_id = %s ORDER BY target_id
        """,
        (str(result_id),),
    ).fetchall()
    result_sets = {
        str(row[0]): (str(row[1]), ArtifactId(str(row[2]))) for row in result_rows
    }
    pre_oos_windows = tuple(
        item
        for item in family.windows
        if item.partition in {EvaluationPartition.TRAIN, EvaluationPartition.VALIDATION}
    )
    for target in family.target_references:
        target_id = str(target.artifact_id)
        decision = historical_targets[target_id]
        dataset = _load_historical_dataset(
            connection, decision.dataset_reference.artifact_id
        )
        receipt_by_scope: dict[
            tuple[str, datetime],
            tuple[ValidationArtifactReference, FormalForecastComputationReceipt],
        ] = {}
        for receipt_ref in decision.formal_forecast_receipt_references:
            row = connection.execute(
                """
                SELECT receipt_hash, forecast_id, decision_time, payload_json
                FROM formal_forecast_computation_receipt WHERE receipt_id = %s
                """,
                (str(receipt_ref.artifact_id),),
            ).fetchone()
            if (
                row is None
                or str(row[0]) != receipt_ref.content_hash
                or not isinstance(row[3], Mapping)
            ):
                reasons.add(f"HISTORICAL_PRE_OOS_FORECAST_RECEIPT_MISMATCH:{target_id}")
                continue
            try:
                receipt = FormalForecastComputationReceipt.from_canonical_dict(
                    dict(row[3])
                )
            except (KeyError, TypeError, ValueError):
                reasons.add(f"HISTORICAL_PRE_OOS_FORECAST_RECEIPT_MISMATCH:{target_id}")
                continue
            scope = (receipt.request.symbol, receipt.decision_time)
            if (
                receipt.receipt_id != receipt_ref.artifact_id
                or receipt.receipt_hash != receipt_ref.content_hash
                or str(receipt.forecast_reference.artifact_id) != str(row[1])
                or receipt.decision_time != row[2]
                or scope in receipt_by_scope
            ):
                reasons.add(f"HISTORICAL_PRE_OOS_FORECAST_RECEIPT_MISMATCH:{target_id}")
                continue
            receipt_by_scope[scope] = (receipt_ref, receipt)
        record_scopes = {
            (record.sample.symbol, record.sample.sample_decision_time.value)
            for record in dataset.records
        }
        if set(receipt_by_scope) != record_scopes:
            reasons.add(
                f"HISTORICAL_FORECAST_RECEIPT_RECORD_COVERAGE_MISMATCH:{target_id}"
            )
        expected: set[tuple[str, str, str, str]] = set()
        for record in dataset.records:
            session_date = record.sample.sample_decision_time.value.date()
            if not any(
                window.start_date <= session_date <= window.end_date
                for window in pre_oos_windows
            ):
                continue
            resolved_receipt = receipt_by_scope.get(
                (record.sample.symbol, record.sample.sample_decision_time.value)
            )
            if resolved_receipt is None or (
                record.outcome_reference.artifact_kind != "TARGET_OUTCOME_LABEL"
            ):
                reasons.add(f"HISTORICAL_PRE_OOS_BINDING_NOT_EXACT:{target_id}")
                continue
            receipt_ref, receipt = resolved_receipt
            expected.add(
                (
                    str(receipt.forecast_reference.artifact_id),
                    receipt.forecast_reference.content_hash,
                    str(record.outcome_reference.artifact_id),
                    record.outcome_reference.content_hash,
                )
            )
        result_owner = result_sets.get(target_id)
        if result_owner is None or result_owner[0] != target.content_hash:
            reasons.add(f"FORMAL_FAMILY_TARGET_OBSERVATION_SET_MISSING:{target_id}")
            continue
        observed_rows = connection.execute(
            """
            SELECT forecast_id, forecast_hash, label_id, label_hash,
                   session_date
            FROM formal_evaluation_observation_binding
            WHERE observation_set_id = %s
            """,
            (str(result_owner[1]),),
        ).fetchall()
        observed = {
            (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            for row in observed_rows
            if any(
                window.start_date <= row[4] <= window.end_date
                for window in pre_oos_windows
            )
        }
        if observed != expected:
            reasons.add(f"HISTORICAL_PRE_OOS_RECORD_SET_MISMATCH:{target_id}")
    return tuple(sorted(reasons))


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


def _load_formal_protocol_pre_oos(
    connection: Any, protocol_id: ArtifactId
) -> FormalResearchProtocol:
    try:
        return load_formal_protocol_pre_oos_owner(connection, protocol_id)
    except FormalProtocolConflict as exc:
        raise ResearchQualificationConflict(
            "Formal Protocol pre-OOS owner replay failed"
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
    expected_symbol: str,
    expected_decision_time: datetime,
) -> tuple[TargetedShadowOutcome, TargetOutcomeLabel]:
    metadata_rows = connection.execute(
        """
        SELECT label_hash, target_id, symbol, label_interval_start,
               availability_status
        FROM targeted_shadow_outcome_label
        WHERE label_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchall()
    exact_metadata = tuple(
        row
        for row in metadata_rows
        if str(row[0]) == reference.content_hash
        and str(row[1]) == str(target_reference.artifact_id)
        and str(row[2]) == expected_symbol
        and row[3] == expected_decision_time
        and str(row[4]) == OutcomeAvailabilityStatus.COMPLETE.value
    )
    if len(exact_metadata) != 1:
        raise ResearchQualificationConflict(
            "Target Outcome Label metadata owner mismatch"
        )
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
        outcome.source_dataset.artifact_id != protocol.dataset_reference.artifact_id
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
    panel = _load_panel_owner(connection, panel_reference, protocol=protocol)
    evaluation_protocol = _load_evaluation_protocol(
        connection, protocol.evaluation_protocol_reference.artifact_id
    )
    observations: list[EvaluationObservation] = []
    for binding, stored in zip(bindings, rows, strict=True):
        observation, settlement_id, _, _receipt_pit_id = (
            _resolve_evaluation_observation(
                connection,
                protocol=protocol,
                panel=panel,
                target_reference=target_reference,
                binding=binding,
            )
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
    *,
    protocol: FormalResearchProtocol,
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
        raise ResearchQualificationConflict(
            "Research Panel owner replay failed"
        ) from exc
    if (
        reference.artifact_kind != "RESEARCH_PANEL_V2"
        or panel.panel_id != reference.artifact_id
        or panel.panel_hash != reference.content_hash
        or str(row[0]) != panel.panel_hash
    ):
        raise ResearchQualificationConflict("Research Panel owner identity mismatch")
    if any(
        item.dataset.artifact_id != protocol.dataset_reference.artifact_id
        or item.dataset.content_hash != protocol.dataset_reference.content_hash
        for item in panel.slices
    ):
        raise ResearchQualificationConflict(
            "RESEARCH_PANEL_DATASET_OWNER_LINEAGE_MISMATCH"
        )
    return panel


def _resolve_evaluation_observation(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    panel: FrozenResearchPanelV2,
    target_reference: ValidationArtifactReference,
    binding: FormalEvaluationObservationBinding,
    require_formal_forecast: bool = False,
    formal_pit_evidence_ids: tuple[ArtifactId, ...] = (),
) -> tuple[EvaluationObservation, str, datetime, ArtifactId | None]:
    forecast, score, receipt_pit_id = _resolve_forecast_evaluation_input(
        connection,
        protocol=protocol,
        target_reference=target_reference,
        binding=binding,
        require_formal_forecast=require_formal_forecast,
        formal_pit_evidence_ids=formal_pit_evidence_ids,
    )

    label_row = _load_evaluation_label_metadata(
        connection,
        protocol=protocol,
        target_reference=target_reference,
        binding=binding,
        forecast=forecast,
    )
    label_payload = connection.execute(
        """
        SELECT label_json
        FROM targeted_shadow_outcome_label
        WHERE settlement_id = %s AND label_id = %s AND label_hash = %s
        """,
        (
            str(label_row[0]),
            str(binding.label_reference.artifact_id),
            binding.label_reference.content_hash,
        ),
    ).fetchone()
    if label_payload is None or not isinstance(label_payload[0], Mapping):
        raise ResearchQualificationConflict("Target Outcome Label payload is missing")
    try:
        label = TargetOutcomeLabel.from_canonical_dict(_mapping(label_payload[0]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchQualificationConflict(
            "Target Outcome Label replay failed"
        ) from exc
    if (
        label.label_id != binding.label_reference.artifact_id
        or label.label_hash != binding.label_reference.content_hash
        or label.target.artifact_id != target_reference.artifact_id
        or label.target.content_hash != target_reference.content_hash
        or label.availability_status is not OutcomeAvailabilityStatus.COMPLETE
        or label.checkpoint_return is None
        or forecast.decision_time != label.label_interval_start
        or (
            not require_formal_forecast
            and (
                forecast.created_at != forecast.decision_time
                or forecast.created_at >= label.label_interval_end
            )
        )
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
    if panel_slice.trading_date != forecast.decision_time.date():
        raise ResearchQualificationConflict(
            "Research Panel trading date does not equal Forecast DecisionTime date"
        )
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
        or panel_slice.targeted_outcome.content_hash != str(label_row[8])
        or not any(
            item.reference_kind == "TARGET_OUTCOME_LABEL"
            and item.artifact_id == label.label_id
            and item.content_hash == label.label_hash
            for item in panel_row.target_labels
        )
        or (
            not require_formal_forecast
            and not any(
                item.artifact_kind == "SHADOW_DECISION"
                and str(item.artifact_id) == str(label_row[9])
                and item.content_hash == str(label_row[10])
                for item in forecast.source_references
            )
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
        score=score,
        realized_return=label.checkpoint_return,
        mfe=label.mfe,
        mae=label.mae,
        regime=regime,
        liquidity_slice="UNKNOWN",
        market_cap_slice="UNKNOWN",
        theme_slice=theme,
    )
    return observation, str(label_row[0]), label.outcome_available_at, receipt_pit_id


def _load_evaluation_label_metadata(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    target_reference: ValidationArtifactReference,
    binding: FormalEvaluationObservationBinding,
    forecast: OutcomeTargetBoundMultiTargetForecast,
) -> tuple[Any, ...]:
    """Reject label substitution before reading any realized value payload."""

    label_rows = connection.execute(
        """
        SELECT l.settlement_id, l.label_hash, l.target_protocol_id,
               l.target_id, l.symbol, l.label_interval_start,
               l.label_interval_end, l.availability_status,
               o.settlement_hash, o.shadow_decision_id, d.decision_hash,
               definition.target_hash, target_protocol.protocol_hash,
               o.source_dataset_id, factual.source_dataset_id,
               factual.source_dataset_hash
        FROM targeted_shadow_outcome_label AS l
        JOIN targeted_shadow_outcome AS o
          ON o.settlement_id = l.settlement_id
        JOIN shadow_research_decision AS d
          ON d.decision_id = o.shadow_decision_id
        JOIN prospective_outcome_settlement AS factual
          ON factual.settlement_id = o.factual_outcome_v1_id
        JOIN outcome_target_definition AS definition
          ON definition.protocol_id = l.target_protocol_id
         AND definition.target_id = l.target_id
        JOIN outcome_target_protocol AS target_protocol
          ON target_protocol.protocol_id = l.target_protocol_id
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
        and str(item[11]) == target_reference.content_hash
        and str(item[12])
        == protocol.outcome_target_protocol_reference.content_hash
        and str(item[13]) == str(protocol.dataset_reference.artifact_id)
        and str(item[14]) == str(protocol.dataset_reference.artifact_id)
        and str(item[15]) == protocol.dataset_reference.content_hash
    )
    if len(exact_label_rows) != 1:
        raise ResearchQualificationConflict("Target Outcome Label owner mismatch")
    label_row = exact_label_rows[0]
    if (
        label_row[5] != forecast.decision_time
        or label_row[6] <= label_row[5]
        or str(label_row[7]) != OutcomeAvailabilityStatus.COMPLETE.value
    ):
        raise ResearchQualificationConflict(
            "Formal Evaluation Label metadata/Forecast temporal mismatch"
        )
    return tuple(label_row)


def _resolve_forecast_evaluation_input(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    target_reference: ValidationArtifactReference,
    binding: FormalEvaluationObservationBinding,
    require_formal_forecast: bool,
    formal_pit_evidence_ids: tuple[ArtifactId, ...],
) -> tuple[OutcomeTargetBoundMultiTargetForecast, Decimal, ArtifactId | None]:
    """Resolve a Forecast without touching its future Target Label owner."""

    forecast_row = connection.execute(
        """
        SELECT forecast_hash, payload_json, forecast_authority
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
        raise ResearchQualificationConflict(
            "Target-bound Forecast replay failed"
        ) from exc
    if (
        forecast.forecast_id != binding.forecast_reference.artifact_id
        or forecast.forecast_hash != binding.forecast_reference.content_hash
        or str(forecast_row[0]) != forecast.forecast_hash
        or forecast.target_protocol_reference
        != protocol.outcome_target_protocol_reference
        or forecast.model_reference != protocol.model_reference
    ):
        raise ResearchQualificationConflict("Target-bound Forecast owner mismatch")
    if require_formal_forecast:
        receipt = connection.execute(
            """
            SELECT receipt_id, receipt_hash, formal_protocol_id,
                   formal_pit_evidence_id,
                   model_id, model_hash, decision_time, materialized_at,
                   payload_json
            FROM formal_forecast_computation_receipt
            WHERE forecast_id = %s
            """,
            (str(forecast.forecast_id),),
        ).fetchone()
        restored_receipt: FormalForecastComputationReceipt | None = None
        if receipt is not None and isinstance(receipt[8], Mapping):
            try:
                restored_receipt = FormalForecastComputationReceipt.from_canonical_dict(
                    dict(receipt[8])
                )
            except (KeyError, TypeError, ValueError):
                restored_receipt = None
        receipt_pit_id = None if receipt is None else ArtifactId(str(receipt[3]))
        if (
            str(forecast_row[2]) != "FORMAL_OWNER_COMPUTED"
            or not formal_pit_evidence_ids
            or receipt is None
            or restored_receipt is None
            or restored_receipt.receipt_id != ArtifactId(str(receipt[0]))
            or restored_receipt.receipt_hash != str(receipt[1])
            or str(receipt[2]) != str(protocol.protocol_id)
            or receipt_pit_id not in formal_pit_evidence_ids
            or str(receipt[4]) != str(protocol.model_reference.artifact_id)
            or str(receipt[5]) != protocol.model_reference.content_hash
            or receipt[6] != forecast.decision_time
            or receipt[7] != forecast.created_at
            or restored_receipt.formal_protocol_reference
            != ValidationArtifactReference(
                "FORMAL_RESEARCH_PROTOCOL",
                protocol.protocol_id,
                protocol.protocol_hash,
            )
            or restored_receipt.formal_pit_evidence_reference.artifact_id
            != receipt_pit_id
            or restored_receipt.model_reference != protocol.model_reference
            or restored_receipt.request.formal_protocol_id != protocol.protocol_id
            or restored_receipt.request.formal_pit_evidence_id != receipt_pit_id
            or restored_receipt.request.symbol != forecast.symbol
            or restored_receipt.decision_time != forecast.decision_time
            or restored_receipt.materialized_at != forecast.created_at
            or restored_receipt.forecast_reference
            != ValidationArtifactReference(
                "OUTCOME_TARGET_BOUND_FORECAST",
                forecast.forecast_id,
                forecast.forecast_hash,
            )
        ):
            raise ResearchQualificationConflict(
                "Formal Family Evaluation requires owner-computed Forecast receipt"
            )
    else:
        receipt_pit_id = None
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
    score = matching_estimates[0].score
    assert score is not None
    return forecast, score, receipt_pit_id


def _require_family_historical_prerequisites(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    family: FrozenHypothesisFamily,
    pits: tuple[FormalPITEvidenceArtifact, ...],
    samples: tuple[HistoricalSampleQualificationDecision, ...],
    evaluated_at: datetime,
) -> None:
    """Resolve C3 owner receipts before any Locked OOS value is read."""

    expected_protocol = ValidationArtifactReference(
        "FORMAL_RESEARCH_PROTOCOL", protocol.protocol_id, protocol.protocol_hash
    )
    expected_pits = _ordered_references(
        tuple(
            ValidationArtifactReference(
                "FORMAL_PIT_EVIDENCE", pit.evidence_id, pit.evidence_hash
            )
            for pit in pits
        )
    )
    by_target: dict[str, HistoricalSampleQualificationDecision] = {}
    for sample in samples:
        if (
            not sample.qualified
            or sample.outcome is not QualificationOutcome.SATISFIED
            or sample.formal_protocol_reference != expected_protocol
            or sample.formal_pit_references != expected_pits
            or sample.evaluated_at > evaluated_at
            or not sample.formal_forecast_receipt_references
        ):
            raise ResearchQualificationConflict(
                "C3_QUALIFIED_HISTORICAL_SAMPLE_REQUIRED_BEFORE_LOCKED_OOS"
            )
        dataset_hash, dataset_target = _load_historical_dataset_metadata(
            connection, sample.dataset_reference.artifact_id
        )
        target_id = str(dataset_target.artifact_id)
        if (
            dataset_hash != sample.dataset_reference.content_hash
            or dataset_target not in family.target_references
            or sample.dataset_reference
            not in protocol.historical_sample_dataset_references
            or target_id in by_target
        ):
            raise ResearchQualificationConflict(
                "C3_HISTORICAL_FAMILY_DATASET_LINEAGE_MISMATCH"
            )
        _verify_historical_decision_side_bindings(connection, sample)
        for receipt_reference in sample.formal_forecast_receipt_references:
            receipt_row = connection.execute(
                """
                SELECT receipt_hash, formal_protocol_id,
                       formal_pit_evidence_id, payload_json
                FROM formal_forecast_computation_receipt
                WHERE receipt_id = %s
                """,
                (str(receipt_reference.artifact_id),),
            ).fetchone()
            if receipt_row is None or not isinstance(receipt_row[3], Mapping):
                raise ResearchQualificationConflict(
                    "C3_FORMAL_FORECAST_RECEIPT_OWNER_MISSING"
                )
            try:
                receipt = FormalForecastComputationReceipt.from_canonical_dict(
                    dict(receipt_row[3])
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ResearchQualificationConflict(
                    "C3_FORMAL_FORECAST_RECEIPT_REPLAY_FAILED"
                ) from exc
            if (
                receipt.receipt_id != receipt_reference.artifact_id
                or receipt.receipt_hash != receipt_reference.content_hash
                or str(receipt_row[0]) != receipt_reference.content_hash
                or str(receipt_row[1]) != str(protocol.protocol_id)
                or ArtifactId(str(receipt_row[2]))
                not in {pit.evidence_id for pit in pits}
                or receipt.formal_protocol_reference != expected_protocol
                or receipt.formal_pit_evidence_reference.artifact_id
                != ArtifactId(str(receipt_row[2]))
            ):
                raise ResearchQualificationConflict(
                    "C3_FORMAL_FORECAST_RECEIPT_LINEAGE_MISMATCH"
                )
        by_target[target_id] = sample
    if set(by_target) != {str(item.artifact_id) for item in family.target_references}:
        raise ResearchQualificationConflict(
            "C3_HISTORICAL_FAMILY_TARGET_COVERAGE_INCOMPLETE"
        )


def _load_historical_dataset_metadata(
    connection: Any,
    dataset_id: ArtifactId,
) -> tuple[str, ValidationArtifactReference]:
    row = connection.execute(
        """
        SELECT artifact_hash, artifact_kind,
               payload_json->'target_reference',
               qualified, production_authorized
        FROM research_validation_artifact
        WHERE artifact_id = %s
        """,
        (str(dataset_id),),
    ).fetchone()
    if (
        row is None
        or str(row[1]) != "HISTORICAL_SAMPLE_DATASET"
        or not isinstance(row[2], Mapping)
        or bool(row[3])
        or bool(row[4])
    ):
        raise ResearchQualificationConflict(
            "C3_HISTORICAL_DATASET_METADATA_OWNER_MISSING"
        )
    try:
        target = ValidationArtifactReference.from_canonical_dict(_mapping(row[2]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchQualificationConflict(
            "C3_HISTORICAL_DATASET_METADATA_REPLAY_FAILED"
        ) from exc
    if target.artifact_kind != "OUTCOME_TARGET":
        raise ResearchQualificationConflict(
            "C3_HISTORICAL_DATASET_METADATA_TARGET_MISMATCH"
        )
    return str(row[0]), target


def _verify_historical_decision_side_bindings(
    connection: Any,
    sample: HistoricalSampleQualificationDecision,
) -> None:
    pit_rows = connection.execute(
        """
        SELECT formal_pit_evidence_id, formal_pit_evidence_hash
        FROM historical_sample_qualification_pit_evidence
        WHERE decision_id = %s ORDER BY ordinal
        """,
        (str(sample.decision_id),),
    ).fetchall()
    receipt_rows = connection.execute(
        """
        SELECT receipt_id, receipt_hash
        FROM historical_sample_qualification_forecast_receipt
        WHERE decision_id = %s ORDER BY ordinal
        """,
        (str(sample.decision_id),),
    ).fetchall()
    expected_pits = tuple(
        (str(item.artifact_id), item.content_hash)
        for item in sample.formal_pit_references
    )
    expected_receipts = tuple(
        (str(item.artifact_id), item.content_hash)
        for item in sample.formal_forecast_receipt_references
    )
    if (
        tuple((str(item[0]), str(item[1])) for item in pit_rows) != expected_pits
        or tuple((str(item[0]), str(item[1])) for item in receipt_rows)
        != expected_receipts
    ):
        raise ResearchQualificationConflict(
            "C3_HISTORICAL_DECISION_BINDING_STORAGE_MISMATCH"
        )


def _existing_family_operator_result(
    connection: Any,
    *,
    idempotency_key: str,
    command_hash: str,
) -> FormalHypothesisFamilyEvaluationResult | None:
    row = connection.execute(
        """
        SELECT command_hash, action_kind, result_artifact_id
        FROM phase_c_formal_operator_command
        WHERE idempotency_key = %s
        """,
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    if (
        str(row[0]) != command_hash
        or str(row[1]) != "EVALUATE_FORMAL_FAMILY"
    ):
        raise ResearchQualificationConflict(
            "Formal Family Evaluation idempotency conflict"
        )
    return _load_family_evaluation_result(connection, ArtifactId(str(row[2])))


def _load_protocol_universe_membership_projection(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
) -> PITUniverseMembershipAuthorityProjection:
    row = connection.execute(
        """
        SELECT projection.projection_id, projection.projection_hash,
               projection.artifact_resolution_id,
               projection.artifact_resolution_hash,
               projection.universe_id, projection.universe_hash,
               projection.decision_date, projection.effective_at,
               projection.available_at, projection.member_count,
               projection.included_member_count, projection.members_hash,
               projection.payload_json, projection.resolved_at,
               owner.owner_kind, owner.owner_artifact_id,
               owner.owner_artifact_hash, owner.artifact_id,
               owner.artifact_hash, owner.owner_recorded_at
        FROM formal_research_protocol_component_owner_resolution AS owner
        JOIN pit_universe_membership_projection AS projection
          ON projection.artifact_resolution_id = owner.owner_artifact_id
         AND projection.artifact_resolution_hash = owner.owner_artifact_hash
        WHERE owner.protocol_id = %s
          AND owner.component_role = 'universe_reference'
        """,
        (str(protocol.protocol_id),),
    ).fetchone()
    if row is None or not isinstance(row[12], Mapping):
        raise ResearchQualificationConflict(
            "LOCKED_OOS_CANONICAL_UNIVERSE_MEMBERSHIP_PROJECTION_MISSING"
        )
    try:
        projection = PITUniverseMembershipAuthorityProjection.from_canonical_dict(
            _mapping(row[12])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchQualificationConflict(
            "LOCKED_OOS_CANONICAL_UNIVERSE_MEMBERSHIP_PROJECTION_REPLAY_FAILED"
        ) from exc
    expected_storage = (
        str(projection.projection_id),
        projection.projection_hash,
        str(projection.artifact_resolution_id),
        projection.artifact_resolution_hash,
        str(projection.universe_reference.artifact_id),
        projection.universe_reference.content_hash,
        projection.decision_date,
        projection.effective_at,
        projection.available_at,
        len(projection.members),
        len(projection.included_symbols),
        projection.members_hash,
        projection.resolved_at,
    )
    actual_storage = tuple(row[:12]) + (row[13],)
    if (
        actual_storage != expected_storage
        or str(row[14]) != "PIT_ARTIFACT_AUTHORITY"
        or str(row[15]) != str(projection.artifact_resolution_id)
        or str(row[16]) != projection.artifact_resolution_hash
        or str(row[17]) != str(protocol.universe_reference.artifact_id)
        or str(row[18]) != protocol.universe_reference.content_hash
        or projection.universe_reference.reference_kind
        != protocol.universe_reference.artifact_kind
        or projection.universe_reference.artifact_id
        != protocol.universe_reference.artifact_id
        or projection.universe_reference.content_hash
        != protocol.universe_reference.content_hash
        or row[19] != projection.resolved_at
        or projection.resolved_at > protocol.locked_at
        or not projection.included_symbols
    ):
        raise ResearchQualificationConflict(
            "LOCKED_OOS_CANONICAL_UNIVERSE_MEMBERSHIP_PROJECTION_MISMATCH"
        )
    member_rows = connection.execute(
        """
        SELECT symbol, included, record_hash, payload_json
        FROM pit_universe_membership_projection_member
        WHERE projection_id = %s ORDER BY symbol
        """,
        (str(projection.projection_id),),
    ).fetchall()
    expected_members = tuple(
        (
            member.symbol,
            member.included,
            member.record_hash,
            member.to_canonical_dict(),
        )
        for member in projection.members
    )
    actual_members = tuple(
        (
            str(item[0]),
            bool(item[1]),
            str(item[2]),
            dict(_mapping(item[3])),
        )
        for item in member_rows
    )
    if actual_members != expected_members:
        raise ResearchQualificationConflict(
            "LOCKED_OOS_CANONICAL_UNIVERSE_MEMBER_SET_MISMATCH"
        )
    return projection


def _prepare_locked_oos_roster(
    connection: Any,
    *,
    formal_protocol_id: ArtifactId,
    groups: tuple[FamilyEvaluationObservationBindings, ...],
    sample_ids: tuple[ArtifactId, ...],
    pit_ids: tuple[ArtifactId, ...],
    idempotency_key: str,
    command_hash: str,
) -> _LockedOOSRosterPreparation:
    """Durably claim the complete label-blind Locked scope before value reads."""

    acquire_scope_lock(
        connection,
        namespace="formal-family-evaluation-idempotency",
        identity=idempotency_key,
    )
    existing_operator = connection.execute(
        """
        SELECT command_hash, action_kind
        FROM phase_c_formal_operator_command
        WHERE idempotency_key = %s
        """,
        (idempotency_key,),
    ).fetchone()
    if existing_operator is not None and (
        str(existing_operator[0]) != command_hash
        or str(existing_operator[1]) != "EVALUATE_FORMAL_FAMILY"
    ):
        raise ResearchQualificationConflict(
            "Formal Family Evaluation idempotency conflict"
        )
    acquire_scope_lock(
        connection,
        namespace="formal-locked-oos-roster",
        identity=formal_protocol_id,
    )
    existing_rows = connection.execute(
        """
        SELECT roster_id, roster_hash, frozen_at, formal_protocol_id,
               idempotency_key, command_hash
        FROM formal_locked_oos_roster
        WHERE formal_protocol_id = %s OR idempotency_key = %s
        """,
        (str(formal_protocol_id), idempotency_key),
    ).fetchall()
    if len(existing_rows) > 1:
        raise ResearchQualificationConflict("LOCKED_OOS_ROSTER_SCOPE_CONFLICT")
    existing = None if not existing_rows else existing_rows[0]
    protocol = _load_formal_protocol_pre_oos(connection, formal_protocol_id)
    family = load_frozen_hypothesis_family_owner(
        connection,
        formal_protocol_id=formal_protocol_id,
    )
    if existing is not None:
        if (
            str(existing[3]) != str(formal_protocol_id)
            or str(existing[4]) != idempotency_key
            or str(existing[5]) != command_hash
        ):
            raise ResearchQualificationConflict("LOCKED_OOS_ROSTER_SCOPE_CONFLICT")
        pits = tuple(_load_formal_pit(connection, item) for item in pit_ids)
        preparation = _LockedOOSRosterPreparation(
            ArtifactId(str(existing[0])), str(existing[1]), existing[2]
        )
        _require_locked_oos_roster(
            connection,
            preparation=preparation,
            protocol=protocol,
            family=family,
            groups=groups,
            pits=pits,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
        return preparation
    if tuple(item.target_reference for item in groups) != family.target_references:
        raise ResearchQualificationConflict(
            "Formal Family Evaluation requires every frozen Target exactly once"
        )
    frozen_at = _postgres_now(connection)
    samples = tuple(_load_historical_decision(connection, item) for item in sample_ids)
    if any(
        not sample.qualified
        or sample.outcome is not QualificationOutcome.SATISFIED
        or sample.evaluated_at > frozen_at
        for sample in samples
    ):
        raise ResearchQualificationConflict(
            "C3_QUALIFIED_HISTORICAL_SAMPLE_REQUIRED_BEFORE_LOCKED_OOS"
        )
    pits = tuple(_load_formal_pit(connection, item) for item in pit_ids)
    _require_family_historical_prerequisites(
        connection,
        protocol=protocol,
        family=family,
        pits=pits,
        samples=samples,
        evaluated_at=frozen_at,
    )
    evaluation = _load_evaluation_protocol(
        connection,
        protocol.evaluation_protocol_reference.artifact_id,
    )
    pre_oos = run_formal_hypothesis_family_evaluation(
        family=family,
        protocol=evaluation,
        inputs=_resolve_pre_oos_family_inputs(
            connection,
            protocol=protocol,
            evaluation=evaluation,
            family=family,
            groups=groups,
            pits=pits,
            created_at=frozen_at,
        ),
        formal_pit_evidence=pits[0],
        formal_pit_evidences=pits,
        created_at=frozen_at,
        frozen_trading_dates=protocol.frozen_trading_dates,
    )
    _require_pre_oos_readiness(
        policy=_load_oos_policy(
            connection,
            protocol.formal_oos_qualification_policy_reference,
        ),
        evaluation=evaluation,
        family=family,
        result=pre_oos,
    )
    set_references = {
        str(group.target_reference.artifact_id): _observation_set_reference(
            protocol=protocol,
            group=group,
            created_at=frozen_at,
        )
        for group in groups
    }
    universe_projection = _load_protocol_universe_membership_projection(
        connection,
        protocol=protocol,
    )
    members = _resolve_locked_oos_roster_members(
        connection,
        protocol=protocol,
        evaluation=evaluation,
        family=family,
        groups=groups,
        pits=pits,
        set_references=set_references,
        universe_projection=universe_projection,
        frozen_at=frozen_at,
    )
    locked_dates = tuple(
        item.isoformat()
        for item in _locked_oos_dates_from_family(protocol, family)
    )
    roster_payload = {
        "schema_version": "formal-locked-oos-roster/v1",
        "family_reference": family.reference.to_canonical_dict(),
        "formal_protocol_reference": ValidationArtifactReference(
            "FORMAL_RESEARCH_PROTOCOL",
            protocol.protocol_id,
            protocol.protocol_hash,
        ).to_canonical_dict(),
        "formal_pit_evidence_references": [
            ValidationArtifactReference(
                "FORMAL_PIT_EVIDENCE", pit.evidence_id, pit.evidence_hash
            ).to_canonical_dict()
            for pit in pits
        ],
        "universe_membership_projection_reference": (
            _universe_membership_projection_reference(
                universe_projection
            ).to_canonical_dict()
        ),
        "universe_members_hash": universe_projection.members_hash,
        "command_hash": command_hash,
        "idempotency_key": idempotency_key,
        "locked_dates": list(locked_dates),
        "members": list(members),
        "frozen_at": timestamp(frozen_at),
        "outcome_values_read": False,
    }
    roster_hash = canonical_hash(roster_payload)
    preparation = _LockedOOSRosterPreparation(
        ArtifactId(f"formal-locked-oos-roster:{roster_hash[7:]}"),
        roster_hash,
        frozen_at,
    )
    for group in groups:
        set_reference = set_references[str(group.target_reference.artifact_id)]
        _record_observation_set_header(
            connection,
            set_reference=set_reference,
            payload=_observation_set_payload(
                formal_protocol=protocol,
                panel_reference=group.panel_reference,
                target_reference=group.target_reference,
                bindings=group.observation_bindings,
                created_at=frozen_at,
            ),
            formal_protocol=protocol,
            group=group,
            created_at=frozen_at,
        )
    connection.execute(
        """
        INSERT INTO formal_locked_oos_roster(
            roster_id, roster_hash, family_id, family_hash,
            formal_protocol_id, formal_protocol_hash, idempotency_key,
            command_hash,
            locked_date_count, subject_date_count, target_observation_count,
            payload_json, frozen_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        """,
        (
            str(preparation.roster_id),
            preparation.roster_hash,
            str(family.family_id),
            family.family_hash,
            str(protocol.protocol_id),
            protocol.protocol_hash,
            idempotency_key,
            command_hash,
            len(locked_dates),
            len(
                {
                    (str(item["subject"]), str(item["decision_time"]))
                    for item in members
                }
            ),
            len(members),
            Jsonb(roster_payload),
            frozen_at,
        ),
    )
    _insert_locked_oos_roster_universe_binding(
        connection,
        preparation=preparation,
        projection=universe_projection,
    )
    for member in members:
        _insert_locked_oos_roster_member(
            connection,
            preparation=preparation,
            member=member,
        )
        _claim_locked_oos_roster_member(
            connection,
            protocol=protocol,
            family=family,
            member=member,
            consumed_at=frozen_at,
        )
    _require_locked_oos_roster(
        connection,
        preparation=preparation,
        protocol=protocol,
        family=family,
        groups=groups,
        pits=pits,
        idempotency_key=idempotency_key,
        command_hash=command_hash,
    )
    return preparation


def _observation_set_reference(
    *,
    protocol: FormalResearchProtocol,
    group: FamilyEvaluationObservationBindings,
    created_at: datetime,
) -> ValidationArtifactReference:
    payload = _observation_set_payload(
        formal_protocol=protocol,
        panel_reference=group.panel_reference,
        target_reference=group.target_reference,
        bindings=group.observation_bindings,
        created_at=created_at,
    )
    digest = canonical_hash(payload)
    return ValidationArtifactReference(
        "FORMAL_EVALUATION_OBSERVATION_SET",
        ArtifactId(f"formal-evaluation-observation-set:{digest[7:]}"),
        digest,
    )


def _locked_oos_dates(
    protocol: FormalResearchProtocol,
    evaluation: FormalEvaluationProtocol,
) -> tuple[date, ...]:
    return tuple(
        item
        for item in protocol.frozen_trading_dates
        if any(
            window.partition is EvaluationPartition.LOCKED_OOS
            and window.start_date <= item <= window.end_date
            for window in evaluation.windows
        )
    )


def _locked_oos_dates_from_family(
    protocol: FormalResearchProtocol,
    family: FrozenHypothesisFamily,
) -> tuple[date, ...]:
    return tuple(
        item
        for item in protocol.frozen_trading_dates
        if any(
            window.partition is EvaluationPartition.LOCKED_OOS
            and window.start_date <= item <= window.end_date
            for window in family.windows
        )
    )


def _universe_membership_projection_reference(
    projection: PITUniverseMembershipAuthorityProjection,
) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        "PIT_UNIVERSE_MEMBERSHIP_PROJECTION",
        projection.projection_id,
        projection.projection_hash,
    )


def _insert_locked_oos_roster_universe_binding(
    connection: Any,
    *,
    preparation: _LockedOOSRosterPreparation,
    projection: PITUniverseMembershipAuthorityProjection,
) -> None:
    payload = {
        "schema_version": "formal-locked-oos-roster-universe-binding-v1",
        "roster_reference": ValidationArtifactReference(
            "FORMAL_LOCKED_OOS_ROSTER",
            preparation.roster_id,
            preparation.roster_hash,
        ).to_canonical_dict(),
        "universe_membership_projection_reference": (
            _universe_membership_projection_reference(projection).to_canonical_dict()
        ),
        "universe_reference": ValidationArtifactReference(
            projection.universe_reference.reference_kind,
            projection.universe_reference.artifact_id,
            projection.universe_reference.content_hash,
        ).to_canonical_dict(),
        "members_hash": projection.members_hash,
        "included_symbols": list(projection.included_symbols),
        "bound_at": timestamp(preparation.frozen_at),
    }
    connection.execute(
        """
        INSERT INTO formal_locked_oos_roster_universe_binding(
            roster_id, projection_id, projection_hash,
            universe_id, universe_hash, members_hash,
            included_member_count, payload_json, bound_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(preparation.roster_id),
            str(projection.projection_id),
            projection.projection_hash,
            str(projection.universe_reference.artifact_id),
            projection.universe_reference.content_hash,
            projection.members_hash,
            len(projection.included_symbols),
            Jsonb(payload),
            preparation.frozen_at,
        ),
    )


def _require_locked_oos_roster_universe_binding(
    connection: Any,
    *,
    preparation: _LockedOOSRosterPreparation,
    projection: PITUniverseMembershipAuthorityProjection,
) -> None:
    row = connection.execute(
        """
        SELECT roster_id, projection_id, projection_hash,
               universe_id, universe_hash, members_hash,
               included_member_count, payload_json, bound_at
        FROM formal_locked_oos_roster_universe_binding
        WHERE roster_id = %s
        """,
        (str(preparation.roster_id),),
    ).fetchone()
    if row is None or not isinstance(row[7], Mapping):
        raise ResearchQualificationConflict(
            "LOCKED_OOS_ROSTER_UNIVERSE_BINDING_MISSING"
        )
    expected_payload = {
        "schema_version": "formal-locked-oos-roster-universe-binding-v1",
        "roster_reference": ValidationArtifactReference(
            "FORMAL_LOCKED_OOS_ROSTER",
            preparation.roster_id,
            preparation.roster_hash,
        ).to_canonical_dict(),
        "universe_membership_projection_reference": (
            _universe_membership_projection_reference(projection).to_canonical_dict()
        ),
        "universe_reference": ValidationArtifactReference(
            projection.universe_reference.reference_kind,
            projection.universe_reference.artifact_id,
            projection.universe_reference.content_hash,
        ).to_canonical_dict(),
        "members_hash": projection.members_hash,
        "included_symbols": list(projection.included_symbols),
        "bound_at": timestamp(preparation.frozen_at),
    }
    if tuple(row[:7]) + (dict(row[7]), row[8]) != (
        str(preparation.roster_id),
        str(projection.projection_id),
        projection.projection_hash,
        str(projection.universe_reference.artifact_id),
        projection.universe_reference.content_hash,
        projection.members_hash,
        len(projection.included_symbols),
        expected_payload,
        preparation.frozen_at,
    ):
        raise ResearchQualificationConflict(
            "LOCKED_OOS_ROSTER_UNIVERSE_BINDING_MISMATCH"
        )


def _resolve_locked_oos_roster_members(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    evaluation: FormalEvaluationProtocol,
    family: FrozenHypothesisFamily,
    groups: tuple[FamilyEvaluationObservationBindings, ...],
    pits: tuple[FormalPITEvidenceArtifact, ...],
    set_references: Mapping[str, ValidationArtifactReference],
    universe_projection: PITUniverseMembershipAuthorityProjection,
    frozen_at: datetime,
) -> tuple[dict[str, Any], ...]:
    """Build an expected roster from PIT request/Forecast/Label metadata only."""

    locked_dates = set(_locked_oos_dates(protocol, evaluation))
    if not locked_dates:
        raise ResearchQualificationConflict("LOCKED_OOS_FROZEN_DATE_ROSTER_EMPTY")
    expected: list[dict[str, Any]] = []
    covered_dates: set[date] = set()
    covered_scopes: set[tuple[date, str]] = set()
    member_record_hashes = {
        member.symbol: member.record_hash
        for member in universe_projection.members
        if member.included
    }
    for pit in pits:
        request = _load_formal_pit_request(connection, pit)
        decision_date = request.decision_time.date()
        if decision_date not in locked_dates:
            continue
        _require_locked_oos_pit_universe_scope(
            request=request,
            projection=universe_projection,
        )
        covered_dates.add(decision_date)
        duplicate_scopes = {
            (decision_date, symbol) for symbol in request.symbols
        } & covered_scopes
        if duplicate_scopes:
            raise ResearchQualificationConflict(
                "LOCKED_OOS_PIT_SUBJECT_SCOPE_OVERLAPS"
            )
        covered_scopes.update((decision_date, symbol) for symbol in request.symbols)
        receipt_rows = connection.execute(
            """
            SELECT receipt_id, receipt_hash, forecast_id,
                   decision_time, materialized_at, payload_json
            FROM formal_forecast_computation_receipt
            WHERE formal_protocol_id = %s AND formal_pit_evidence_id = %s
            ORDER BY receipt_id
            """,
            (str(protocol.protocol_id), str(pit.evidence_id)),
        ).fetchall()
        receipts: dict[str, FormalForecastComputationReceipt] = {}
        for row in receipt_rows:
            if not isinstance(row[5], Mapping):
                raise ResearchQualificationConflict(
                    "LOCKED_OOS_FORECAST_RECEIPT_OWNER_MISSING"
                )
            try:
                receipt = FormalForecastComputationReceipt.from_canonical_dict(
                    dict(row[5])
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ResearchQualificationConflict(
                    "LOCKED_OOS_FORECAST_RECEIPT_REPLAY_FAILED"
                ) from exc
            if (
                receipt.receipt_id != ArtifactId(str(row[0]))
                or receipt.receipt_hash != str(row[1])
                or receipt.forecast_reference.artifact_id != ArtifactId(str(row[2]))
                or receipt.decision_time != row[3]
                or receipt.materialized_at != row[4]
                or receipt.request.symbol in receipts
                or receipt.request.formal_protocol_id != protocol.protocol_id
                or receipt.request.formal_pit_evidence_id != pit.evidence_id
                or receipt.formal_protocol_reference
                != ValidationArtifactReference(
                    "FORMAL_RESEARCH_PROTOCOL",
                    protocol.protocol_id,
                    protocol.protocol_hash,
                )
                or receipt.formal_pit_evidence_reference
                != ValidationArtifactReference(
                    "FORMAL_PIT_EVIDENCE", pit.evidence_id, pit.evidence_hash
                )
                or receipt.decision_time != request.decision_time
                or receipt.materialized_at > frozen_at
            ):
                raise ResearchQualificationConflict(
                    "LOCKED_OOS_FORECAST_RECEIPT_LINEAGE_MISMATCH"
                )
            receipts[receipt.request.symbol] = receipt
        if set(receipts) != set(request.symbols):
            raise ResearchQualificationConflict(
                "LOCKED_OOS_FORECAST_RECEIPT_SCOPE_INCOMPLETE"
            )
        for symbol in request.symbols:
            receipt = receipts[symbol]
            for target in family.target_references:
                label_rows = connection.execute(
                    """
                    SELECT label.settlement_id, label.label_id,
                           label.label_hash, label.label_interval_start,
                           label.label_interval_end, label.availability_status,
                           definition.target_hash, target_protocol.protocol_hash,
                           outcome.source_dataset_id,
                           factual.source_dataset_id,
                           factual.source_dataset_hash,
                           outcome.outcome_available_at, outcome.created_at
                    FROM targeted_shadow_outcome_label AS label
                    JOIN targeted_shadow_outcome AS outcome
                      ON outcome.settlement_id = label.settlement_id
                    JOIN prospective_outcome_settlement AS factual
                      ON factual.settlement_id = outcome.factual_outcome_v1_id
                    JOIN outcome_target_definition AS definition
                      ON definition.protocol_id = label.target_protocol_id
                     AND definition.target_id = label.target_id
                    JOIN outcome_target_protocol AS target_protocol
                      ON target_protocol.protocol_id = label.target_protocol_id
                    WHERE label.target_protocol_id = %s
                      AND label.target_id = %s AND label.symbol = %s
                      AND label.label_interval_start = %s
                    ORDER BY label.settlement_id, label.label_id
                    """,
                    (
                        str(protocol.outcome_target_protocol_reference.artifact_id),
                        str(target.artifact_id),
                        symbol,
                        request.decision_time,
                    ),
                ).fetchall()
                if (
                    len(label_rows) != 1
                    or str(label_rows[0][5])
                    != OutcomeAvailabilityStatus.COMPLETE.value
                    or str(label_rows[0][6]) != target.content_hash
                    or str(label_rows[0][7])
                    != protocol.outcome_target_protocol_reference.content_hash
                    or str(label_rows[0][8])
                    != str(protocol.dataset_reference.artifact_id)
                    or str(label_rows[0][9])
                    != str(protocol.dataset_reference.artifact_id)
                    or str(label_rows[0][10])
                    != protocol.dataset_reference.content_hash
                    or label_rows[0][3] != request.decision_time
                    or label_rows[0][4] <= label_rows[0][3]
                    or label_rows[0][4] > label_rows[0][11]
                    or label_rows[0][11] > frozen_at
                    or label_rows[0][12] > frozen_at
                ):
                    raise ResearchQualificationConflict(
                        "LOCKED_OOS_LABEL_METADATA_SCOPE_INCOMPLETE"
                    )
                label_row = label_rows[0]
                raw = RawOOSEvidenceIdentity(
                    subject=symbol,
                    decision_session_date=decision_date,
                    outcome_session_date=label_row[4].date(),
                )
                member = {
                    "schema_version": "formal-locked-oos-roster-member/v1",
                    "target_protocol_reference": (
                        protocol.outcome_target_protocol_reference.to_canonical_dict()
                    ),
                    "target_reference": target.to_canonical_dict(),
                    "subject": symbol,
                    "decision_time": timestamp(request.decision_time),
                    "outcome_time": timestamp(label_row[4]),
                    "formal_pit_evidence_reference": ValidationArtifactReference(
                        "FORMAL_PIT_EVIDENCE", pit.evidence_id, pit.evidence_hash
                    ).to_canonical_dict(),
                    "universe_membership_projection_reference": (
                        _universe_membership_projection_reference(
                            universe_projection
                        ).to_canonical_dict()
                    ),
                    "universe_member_record_hash": member_record_hashes[symbol],
                    "forecast_reference": receipt.forecast_reference.to_canonical_dict(),
                    "settlement_id": str(label_row[0]),
                    "label_reference": ValidationArtifactReference(
                        "TARGET_OUTCOME_LABEL",
                        ArtifactId(str(label_row[1])),
                        str(label_row[2]),
                    ).to_canonical_dict(),
                    "observation_set_reference": set_references[
                        str(target.artifact_id)
                    ].to_canonical_dict(),
                    "raw_evidence_identity_hash": raw.identity_hash,
                }
                expected.append(member)
    if covered_dates != locked_dates:
        raise ResearchQualificationConflict("LOCKED_OOS_PIT_DATE_ROSTER_INCOMPLETE")
    ordered = tuple(
        sorted(
            expected,
            key=lambda item: (
                str(item["decision_time"]),
                str(item["subject"]),
                str(_mapping(item["target_reference"])["artifact_id"]),
            ),
        )
    )
    expected_keys = {_locked_oos_member_binding_key(item) for item in ordered}
    actual_keys: set[tuple[str, ...]] = set()
    actual_locked_count = 0
    pit_ids = tuple(pit.evidence_id for pit in pits)
    for group in groups:
        for binding in group.observation_bindings:
            forecast, _score, _pit_id = _resolve_forecast_evaluation_input(
                connection,
                protocol=protocol,
                target_reference=group.target_reference,
                binding=binding,
                require_formal_forecast=True,
                formal_pit_evidence_ids=pit_ids,
            )
            if forecast.decision_time.date() not in locked_dates:
                continue
            actual_locked_count += 1
            actual_keys.add(
                (
                    str(group.target_reference.artifact_id),
                    group.target_reference.content_hash,
                    str(binding.forecast_reference.artifact_id),
                    binding.forecast_reference.content_hash,
                    str(binding.label_reference.artifact_id),
                    binding.label_reference.content_hash,
                )
            )
    if (
        actual_keys != expected_keys
        or len(actual_keys) != len(ordered)
        or actual_locked_count != len(ordered)
    ):
        raise ResearchQualificationConflict(
            "LOCKED_OOS_SUBMITTED_BINDINGS_DO_NOT_EQUAL_FROZEN_ROSTER"
        )
    return ordered


def _require_locked_oos_pit_universe_scope(
    *,
    request: FormalPITValidationRequest,
    projection: PITUniverseMembershipAuthorityProjection,
) -> None:
    if (
        request.lineage.universe.reference_kind
        != projection.universe_reference.reference_kind
        or request.lineage.universe.artifact_id
        != projection.universe_reference.artifact_id
        or request.lineage.universe.content_hash
        != projection.universe_reference.content_hash
        or tuple(request.symbols) != projection.included_symbols
        or projection.effective_at > request.decision_time
        or projection.available_at > request.decision_time
    ):
        raise ResearchQualificationConflict(
            "LOCKED_OOS_PIT_SCOPE_DOES_NOT_EQUAL_CANONICAL_UNIVERSE"
        )


def _locked_oos_member_binding_key(
    member: Mapping[str, Any],
) -> tuple[str, ...]:
    target = _mapping(member["target_reference"])
    forecast = _mapping(member["forecast_reference"])
    label = _mapping(member["label_reference"])
    return (
        str(target["artifact_id"]),
        str(target["content_hash"]),
        str(forecast["artifact_id"]),
        str(forecast["content_hash"]),
        str(label["artifact_id"]),
        str(label["content_hash"]),
    )


def _locked_oos_member_storage_projection(
    member: Mapping[str, Any],
) -> tuple[object, ...]:
    if member.get("schema_version") != "formal-locked-oos-roster-member/v1":
        raise ResearchQualificationConflict("LOCKED_OOS_ROSTER_MEMBER_SCHEMA_DRIFT")
    target_protocol = ValidationArtifactReference.from_canonical_dict(
        _mapping(member["target_protocol_reference"])
    )
    target = ValidationArtifactReference.from_canonical_dict(
        _mapping(member["target_reference"])
    )
    pit = ValidationArtifactReference.from_canonical_dict(
        _mapping(member["formal_pit_evidence_reference"])
    )
    universe_projection = ValidationArtifactReference.from_canonical_dict(
        _mapping(member["universe_membership_projection_reference"])
    )
    forecast = ValidationArtifactReference.from_canonical_dict(
        _mapping(member["forecast_reference"])
    )
    label = ValidationArtifactReference.from_canonical_dict(
        _mapping(member["label_reference"])
    )
    observation_set = ValidationArtifactReference.from_canonical_dict(
        _mapping(member["observation_set_reference"])
    )
    decision_time = _parse_timestamp(str(member["decision_time"]))
    outcome_time = _parse_timestamp(str(member["outcome_time"]))
    raw = RawOOSEvidenceIdentity(
        subject=str(member["subject"]),
        decision_session_date=decision_time.date(),
        outcome_session_date=outcome_time.date(),
    )
    if (
        target_protocol.artifact_kind != "OUTCOME_TARGET_PROTOCOL"
        or target.artifact_kind != "OUTCOME_TARGET"
        or pit.artifact_kind != "FORMAL_PIT_EVIDENCE"
        or universe_projection.artifact_kind
        != "PIT_UNIVERSE_MEMBERSHIP_PROJECTION"
        or not isinstance(member.get("universe_member_record_hash"), str)
        or not str(member["universe_member_record_hash"]).startswith("sha256:")
        or forecast.artifact_kind != "OUTCOME_TARGET_BOUND_FORECAST"
        or label.artifact_kind != "TARGET_OUTCOME_LABEL"
        or observation_set.artifact_kind != "FORMAL_EVALUATION_OBSERVATION_SET"
        or member.get("raw_evidence_identity_hash") != raw.identity_hash
    ):
        raise ResearchQualificationConflict("LOCKED_OOS_ROSTER_MEMBER_LINEAGE_DRIFT")
    return (
        canonical_hash(dict(member)),
        str(target_protocol.artifact_id),
        target_protocol.content_hash,
        str(target.artifact_id),
        target.content_hash,
        str(member["subject"]),
        decision_time,
        outcome_time,
        str(pit.artifact_id),
        pit.content_hash,
        str(forecast.artifact_id),
        forecast.content_hash,
        str(member["settlement_id"]),
        str(label.artifact_id),
        label.content_hash,
        str(observation_set.artifact_id),
    )


def _insert_locked_oos_roster_member(
    connection: Any,
    *,
    preparation: _LockedOOSRosterPreparation,
    member: Mapping[str, Any],
) -> None:
    target_protocol = _mapping(member["target_protocol_reference"])
    target = _mapping(member["target_reference"])
    pit = _mapping(member["formal_pit_evidence_reference"])
    forecast = _mapping(member["forecast_reference"])
    label = _mapping(member["label_reference"])
    observation_set = _mapping(member["observation_set_reference"])
    connection.execute(
        """
        INSERT INTO formal_locked_oos_roster_member(
            roster_id, member_hash, target_protocol_id, target_protocol_hash,
            target_id, target_hash, subject,
            decision_time, outcome_time, formal_pit_evidence_id,
            formal_pit_evidence_hash, forecast_id, forecast_hash,
            settlement_id, label_id, label_hash, observation_set_id,
            payload_json
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            str(preparation.roster_id),
            canonical_hash(dict(member)),
            str(target_protocol["artifact_id"]),
            str(target_protocol["content_hash"]),
            str(target["artifact_id"]),
            str(target["content_hash"]),
            str(member["subject"]),
            _parse_timestamp(str(member["decision_time"])),
            _parse_timestamp(str(member["outcome_time"])),
            str(pit["artifact_id"]),
            str(pit["content_hash"]),
            str(forecast["artifact_id"]),
            str(forecast["content_hash"]),
            str(member["settlement_id"]),
            str(label["artifact_id"]),
            str(label["content_hash"]),
            str(observation_set["artifact_id"]),
            Jsonb(dict(member)),
        ),
    )


def _require_locked_oos_roster(
    connection: Any,
    *,
    preparation: _LockedOOSRosterPreparation,
    protocol: FormalResearchProtocol,
    family: FrozenHypothesisFamily,
    groups: tuple[FamilyEvaluationObservationBindings, ...],
    pits: tuple[FormalPITEvidenceArtifact, ...],
    idempotency_key: str,
    command_hash: str,
) -> None:
    row = connection.execute(
        """
        SELECT roster_hash, family_id, family_hash, formal_protocol_id,
               formal_protocol_hash, idempotency_key, command_hash,
               locked_date_count, subject_date_count,
               target_observation_count, payload_json, frozen_at
        FROM formal_locked_oos_roster WHERE roster_id = %s
        """,
        (str(preparation.roster_id),),
    ).fetchone()
    if row is None or not isinstance(row[10], Mapping):
        raise ResearchQualificationConflict("LOCKED_OOS_ROSTER_OWNER_MISSING")
    payload = dict(row[10])
    try:
        pit_references = tuple(
            ValidationArtifactReference.from_canonical_dict(_mapping(item))
            for item in _sequence(payload.get("formal_pit_evidence_references", ()))
        )
        payload_family = ValidationArtifactReference.from_canonical_dict(
            _mapping(payload.get("family_reference"))
        )
        payload_protocol = ValidationArtifactReference.from_canonical_dict(
            _mapping(payload.get("formal_protocol_reference"))
        )
        payload_universe_projection = (
            ValidationArtifactReference.from_canonical_dict(
                _mapping(payload.get("universe_membership_projection_reference"))
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchQualificationConflict(
            "LOCKED_OOS_ROSTER_PAYLOAD_REPLAY_FAILED"
        ) from exc
    expected_pits = tuple(
        ValidationArtifactReference(
            "FORMAL_PIT_EVIDENCE", pit.evidence_id, pit.evidence_hash
        )
        for pit in pits
    )
    members = tuple(
        dict(_mapping(item)) for item in _sequence(payload.get("members", ()))
    )
    universe_projection = _load_protocol_universe_membership_projection(
        connection,
        protocol=protocol,
    )
    expected_universe_projection = _universe_membership_projection_reference(
        universe_projection
    )
    universe_member_hashes = {
        item.symbol: item.record_hash
        for item in universe_projection.members
        if item.included
    }
    _require_locked_oos_roster_universe_binding(
        connection,
        preparation=preparation,
        projection=universe_projection,
    )
    expected_sets = {
        group.target_reference: _observation_set_reference(
            protocol=protocol,
            group=group,
            created_at=preparation.frozen_at,
        )
        for group in groups
    }
    try:
        member_lineage = tuple(
            (
                ValidationArtifactReference.from_canonical_dict(
                    _mapping(member["target_protocol_reference"])
                ),
                ValidationArtifactReference.from_canonical_dict(
                    _mapping(member["target_reference"])
                ),
                ValidationArtifactReference.from_canonical_dict(
                    _mapping(member["formal_pit_evidence_reference"])
                ),
                ValidationArtifactReference.from_canonical_dict(
                    _mapping(member["observation_set_reference"])
                ),
                ValidationArtifactReference.from_canonical_dict(
                    _mapping(member["universe_membership_projection_reference"])
                ),
                str(member["universe_member_record_hash"]),
                str(member["subject"]),
                _parse_timestamp(str(member["decision_time"])),
            )
            for member in members
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchQualificationConflict(
            "LOCKED_OOS_ROSTER_MEMBER_REPLAY_FAILED"
        ) from exc
    actual_group_keys = {
        (
            str(group.target_reference.artifact_id),
            group.target_reference.content_hash,
            str(binding.forecast_reference.artifact_id),
            binding.forecast_reference.content_hash,
            str(binding.label_reference.artifact_id),
            binding.label_reference.content_hash,
        )
        for group in groups
        for binding in group.observation_bindings
        if any(
            key[:4]
            == (
                str(group.target_reference.artifact_id),
                group.target_reference.content_hash,
                str(binding.forecast_reference.artifact_id),
                binding.forecast_reference.content_hash,
            )
            for key in (_locked_oos_member_binding_key(item) for item in members)
        )
    }
    member_keys = {_locked_oos_member_binding_key(item) for item in members}
    locked_dates = tuple(
        item.isoformat()
        for item in _locked_oos_dates_from_family(protocol, family)
    )
    subject_date_count = len(
        {
            (str(item.get("subject")), str(item.get("decision_time")))
            for item in members
        }
    )
    expected_pit_set = set(expected_pits)
    locked_date_set = {date.fromisoformat(item) for item in locked_dates}
    if any(
        target_protocol != protocol.outcome_target_protocol_reference
        or target not in family.target_references
        or pit not in expected_pit_set
        or expected_sets.get(target) != observation_set
        or member_universe_projection != expected_universe_projection
        or universe_member_hashes.get(subject) != member_record_hash
        or decision_time.date() not in locked_date_set
        for (
            target_protocol,
            target,
            pit,
            observation_set,
            member_universe_projection,
            member_record_hash,
            subject,
            decision_time,
        ) in member_lineage
    ):
        raise ResearchQualificationConflict("LOCKED_OOS_ROSTER_MEMBER_LINEAGE_DRIFT")
    if (
        str(row[0]) != preparation.roster_hash
        or str(row[1]) != str(family.family_id)
        or str(row[2]) != family.family_hash
        or str(row[3]) != str(protocol.protocol_id)
        or str(row[4]) != protocol.protocol_hash
        or str(row[5]) != idempotency_key
        or str(row[6]) != command_hash
        or int(row[7]) != len(locked_dates)
        or int(row[8]) != subject_date_count
        or int(row[9]) != len(members)
        or row[11] != preparation.frozen_at
        or canonical_hash(payload) != preparation.roster_hash
        or payload.get("schema_version") != "formal-locked-oos-roster/v1"
        or payload_family != family.reference
        or payload_protocol
        != ValidationArtifactReference(
            "FORMAL_RESEARCH_PROTOCOL", protocol.protocol_id, protocol.protocol_hash
        )
        or payload_universe_projection != expected_universe_projection
        or payload.get("universe_members_hash") != universe_projection.members_hash
        or tuple(str(item) for item in _sequence(payload.get("locked_dates", ())))
        != locked_dates
        or payload.get("command_hash") != command_hash
        or payload.get("idempotency_key") != idempotency_key
        or payload.get("frozen_at") != timestamp(preparation.frozen_at)
        or payload.get("outcome_values_read") is not False
        or pit_references != expected_pits
        or actual_group_keys != member_keys
    ):
        raise ResearchQualificationConflict("LOCKED_OOS_ROSTER_IDENTITY_CONFLICT")
    stored_members = connection.execute(
        """
        SELECT member_hash, target_protocol_id, target_protocol_hash,
               target_id, target_hash, subject, decision_time, outcome_time,
               formal_pit_evidence_id, formal_pit_evidence_hash,
               forecast_id, forecast_hash, settlement_id, label_id,
               label_hash, observation_set_id, payload_json
        FROM formal_locked_oos_roster_member
        WHERE roster_id = %s
        ORDER BY decision_time, subject, target_id
        """,
        (str(preparation.roster_id),),
    ).fetchall()
    if (
        len(stored_members) != len(members)
        or any(
            not isinstance(row_value[16], Mapping)
            or _locked_oos_member_storage_projection(dict(row_value[16]))
            != tuple(row_value[:16])
            for row_value in stored_members
        )
        or tuple(dict(item[16]) for item in stored_members) != members
    ):
        raise ResearchQualificationConflict("LOCKED_OOS_ROSTER_MEMBER_DRIFT")
    for member in members:
        _require_locked_oos_member_claim(
            connection,
            protocol=protocol,
            family=family,
            member=member,
            consumed_at=preparation.frozen_at,
        )


def _claim_locked_oos_roster_member(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    family: FrozenHypothesisFamily,
    member: Mapping[str, Any],
    consumed_at: datetime,
) -> None:
    target = ValidationArtifactReference.from_canonical_dict(
        _mapping(member["target_reference"])
    )
    forecast = ValidationArtifactReference.from_canonical_dict(
        _mapping(member["forecast_reference"])
    )
    label = ValidationArtifactReference.from_canonical_dict(
        _mapping(member["label_reference"])
    )
    observation_set = ValidationArtifactReference.from_canonical_dict(
        _mapping(member["observation_set_reference"])
    )
    raw = RawOOSEvidenceIdentity(
        subject=str(member["subject"]),
        decision_session_date=_parse_timestamp(
            str(member["decision_time"])
        ).date(),
        outcome_session_date=_parse_timestamp(str(member["outcome_time"])).date(),
    )
    _claim_raw_oos_unlock(
        connection,
        protocol=protocol,
        family=family,
        raw=raw,
        unlocked_at=consumed_at,
    )
    consumption = LockedOOSTargetObservationConsumption.create(
        raw_evidence_identity_hash=raw.identity_hash,
        family_reference=family.reference,
        target_reference=target,
        forecast_reference=forecast,
        label_reference=label,
        observation_set_reference=observation_set,
        consumed_at=consumed_at,
    )
    _insert_target_oos_consumption(connection, consumption)


def _require_locked_oos_member_claim(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    family: FrozenHypothesisFamily,
    member: Mapping[str, Any],
    consumed_at: datetime,
) -> None:
    raw = RawOOSEvidenceIdentity(
        subject=str(member["subject"]),
        decision_session_date=_parse_timestamp(
            str(member["decision_time"])
        ).date(),
        outcome_session_date=_parse_timestamp(str(member["outcome_time"])).date(),
    )
    _require_raw_oos_unlock(
        connection,
        raw=raw,
        family=family,
        protocol=protocol,
        payload=_raw_oos_unlock_payload(raw=raw, family=family, protocol=protocol),
    )
    _require_target_oos_consumption(
        connection,
        LockedOOSTargetObservationConsumption.create(
            raw_evidence_identity_hash=raw.identity_hash,
            family_reference=family.reference,
            target_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(member["target_reference"])
            ),
            forecast_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(member["forecast_reference"])
            ),
            label_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(member["label_reference"])
            ),
            observation_set_reference=(
                ValidationArtifactReference.from_canonical_dict(
                    _mapping(member["observation_set_reference"])
                )
            ),
            consumed_at=consumed_at,
        ),
    )


def _resolve_pre_oos_family_inputs(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    evaluation: FormalEvaluationProtocol,
    family: FrozenHypothesisFamily,
    groups: tuple[FamilyEvaluationObservationBindings, ...],
    pits: tuple[FormalPITEvidenceArtifact, ...],
    created_at: datetime,
) -> tuple[FamilyEvaluationInput, ...]:
    """Resolve Train/Validation only; Locked labels remain unread."""

    pit_ids = tuple(item.evidence_id for item in pits)
    planned: list[
        tuple[
            FamilyEvaluationObservationBindings,
            FrozenResearchPanelV2,
            tuple[FormalEvaluationObservationBinding, ...],
        ]
    ] = []
    used_pit_ids: set[ArtifactId] = set()
    for group in groups:
        panel = _load_panel_owner(
            connection,
            group.panel_reference,
            protocol=protocol,
        )
        safe_bindings: list[FormalEvaluationObservationBinding] = []
        for binding in group.observation_bindings:
            forecast, _score, receipt_pit_id = _resolve_forecast_evaluation_input(
                connection,
                protocol=protocol,
                target_reference=group.target_reference,
                binding=binding,
                require_formal_forecast=True,
                formal_pit_evidence_ids=pit_ids,
            )
            if forecast.created_at > created_at or receipt_pit_id is None:
                raise ResearchQualificationConflict(
                    "FORMAL_FORECAST_NOT_AVAILABLE_AT_PRE_OOS_GATE"
                )
            used_pit_ids.add(receipt_pit_id)
            matching_partitions = {
                window.partition
                for window in evaluation.windows
                if window.start_date <= forecast.decision_time.date() <= window.end_date
            }
            if not matching_partitions:
                raise ResearchQualificationConflict(
                    "FORMAL_EVALUATION_OBSERVATION_OUTSIDE_FROZEN_WINDOWS"
                )
            if EvaluationPartition.LOCKED_OOS in matching_partitions:
                if len(matching_partitions) != 1:
                    raise ResearchQualificationConflict(
                        "PRE_OOS_PARTITION_DATE_OVERLAP"
                    )
                continue
            safe_bindings.append(binding)
        planned.append((group, panel, tuple(safe_bindings)))
    if used_pit_ids != set(pit_ids):
        raise ResearchQualificationConflict(
            "FORMAL_FAMILY_EVALUATION_PIT_LINEAGE_NOT_EXACTLY_CONSUMED"
        )
    inputs: list[FamilyEvaluationInput] = []
    for group, panel, safe_group_bindings in planned:
        resolved = tuple(
            _resolve_evaluation_observation(
                connection,
                protocol=protocol,
                panel=panel,
                target_reference=group.target_reference,
                binding=binding,
                require_formal_forecast=True,
                formal_pit_evidence_ids=pit_ids,
            )
            for binding in safe_group_bindings
        )
        if any(item[2] > created_at for item in resolved):
            raise ResearchQualificationConflict(
                "Pre-OOS Evaluation predates an owner-resolved Target Label"
            )
        set_payload = _observation_set_payload(
            formal_protocol=protocol,
            panel_reference=group.panel_reference,
            target_reference=group.target_reference,
            bindings=group.observation_bindings,
            created_at=created_at,
        )
        set_hash = canonical_hash(set_payload)
        set_reference = ValidationArtifactReference(
            "FORMAL_EVALUATION_OBSERVATION_SET",
            ArtifactId(f"formal-evaluation-observation-set:{set_hash[7:]}"),
            set_hash,
        )
        inputs.append(
            FamilyEvaluationInput(
                target_reference=group.target_reference,
                panel_reference=group.panel_reference,
                observations=tuple(item[0] for item in resolved),
                panel_source_references=_formal_evaluation_sources(
                    protocol,
                    target_reference=group.target_reference,
                    observation_set_reference=set_reference,
                ),
            )
        )
    ordered = tuple(
        sorted(inputs, key=lambda item: str(item.target_reference.artifact_id))
    )
    if tuple(item.target_reference for item in ordered) != family.target_references:
        raise ResearchQualificationConflict("PRE_OOS_FROZEN_TARGET_FAMILY_MISMATCH")
    return ordered


def _require_pre_oos_readiness(
    *,
    policy: FormalOOSQualificationPolicy,
    evaluation: FormalEvaluationProtocol,
    family: FrozenHypothesisFamily,
    result: FormalHypothesisFamilyEvaluationResult,
) -> None:
    required_folds = {
        partition.value: tuple(
            sorted(
                {
                    item.fold
                    for item in evaluation.windows
                    if item.partition is partition
                }
            )
        )
        for partition in (EvaluationPartition.TRAIN, EvaluationPartition.VALIDATION)
    }
    metrics_by_target: dict[str, list[Mapping[str, Any]]] = {
        str(item.artifact_id): [] for item in family.target_references
    }
    for family_metric in result.metrics:
        metrics_by_target[str(family_metric.target_reference.artifact_id)].append(
            _mapping(family_metric.to_canonical_dict()["metric"])
        )
    reasons: set[str] = set()
    for target_id, metrics in metrics_by_target.items():
        outcome, target_reasons = evaluate_pre_oos_metric_readiness(
            policy=policy,
            metrics=tuple(metrics),
            required_partition_folds=required_folds,
        )
        if outcome is not QualificationOutcome.SATISFIED:
            reasons.update(f"{item}:{target_id}" for item in target_reasons)
    if reasons:
        raise ResearchQualificationConflict(
            "PRE_OOS_GATE_NOT_SATISFIED:" + ",".join(sorted(reasons))
        )


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
        raise ResearchQualificationConflict(
            "Formal Evaluation state slice owner mismatch"
        )
    return str(row[1])


def _claim_raw_oos_unlock(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    family: FrozenHypothesisFamily,
    raw: RawOOSEvidenceIdentity,
    unlocked_at: datetime,
) -> None:
    acquire_scope_lock(
        connection,
        namespace="locked-oos-raw-evidence-unlock",
        identity=raw.identity_hash,
    )
    legacy = connection.execute(
        """
        SELECT evidence_identity_hash
        FROM locked_oos_evidence_consumption
        WHERE subject = %s AND session_date = %s
          AND label_end_date = %s AND partition_kind = 'LOCKED_OOS'
        LIMIT 1
        """,
        (raw.subject, raw.decision_session_date, raw.outcome_session_date),
    ).fetchone()
    if legacy is not None:
        raise ResearchQualificationConflict(
            "Raw Locked OOS Evidence was already unlocked by legacy Formal Evaluation"
        )
    payload = _raw_oos_unlock_payload(raw=raw, family=family, protocol=protocol)
    connection.execute(
        """
        INSERT INTO locked_oos_raw_evidence_unlock(
            raw_evidence_identity_hash, subject,
            decision_session_date, outcome_session_date,
            partition_kind, first_family_id, first_family_hash,
            first_formal_protocol_id, first_formal_protocol_hash,
            first_dataset_id, first_dataset_hash,
            first_universe_id, first_universe_hash,
            first_model_id, first_model_hash,
            payload_json, unlocked_at
        ) VALUES (
            %s, %s, %s, %s, 'LOCKED_OOS', %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s
        ) ON CONFLICT DO NOTHING
        """,
        (
            raw.identity_hash,
            raw.subject,
            raw.decision_session_date,
            raw.outcome_session_date,
            str(family.family_id),
            family.family_hash,
            str(protocol.protocol_id),
            protocol.protocol_hash,
            str(protocol.dataset_reference.artifact_id),
            protocol.dataset_reference.content_hash,
            str(protocol.universe_reference.artifact_id),
            protocol.universe_reference.content_hash,
            str(protocol.model_reference.artifact_id),
            protocol.model_reference.content_hash,
            Jsonb(payload),
            unlocked_at,
        ),
    )
    _require_raw_oos_unlock(
        connection,
        raw=raw,
        family=family,
        protocol=protocol,
        payload=payload,
    )


def _insert_target_oos_consumption(
    connection: Any,
    consumption: LockedOOSTargetObservationConsumption,
) -> None:
    connection.execute(
        """
        INSERT INTO locked_oos_target_observation_consumption(
            consumption_id, consumption_hash,
            raw_evidence_identity_hash, family_id, family_hash,
            target_id, target_hash, forecast_id, forecast_hash,
            label_id, label_hash, observation_set_id,
            payload_json, consumed_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        ) ON CONFLICT DO NOTHING
        """,
        (
            str(consumption.consumption_id),
            consumption.consumption_hash,
            consumption.raw_evidence_identity_hash,
            str(consumption.family_reference.artifact_id),
            consumption.family_reference.content_hash,
            str(consumption.target_reference.artifact_id),
            consumption.target_reference.content_hash,
            str(consumption.forecast_reference.artifact_id),
            consumption.forecast_reference.content_hash,
            str(consumption.label_reference.artifact_id),
            consumption.label_reference.content_hash,
            str(consumption.observation_set_reference.artifact_id),
            Jsonb(consumption.to_canonical_dict()),
            consumption.consumed_at,
        ),
    )
    _require_target_oos_consumption(connection, consumption)


def _consume_family_locked_oos(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    evaluation_protocol: FormalEvaluationProtocol,
    family: FrozenHypothesisFamily,
    observation_sets: tuple[
        tuple[
            ValidationArtifactReference,
            FamilyEvaluationObservationBindings,
            tuple[EvaluationObservation, ...],
        ],
        ...,
    ],
    consumed_at: datetime,
) -> None:
    expected_family = ValidationArtifactReference(
        "FORMAL_RESEARCH_PROTOCOL",
        protocol.protocol_id,
        protocol.protocol_hash,
    )
    if family.formal_protocol_reference != expected_family:
        raise ResearchQualificationConflict(
            "Frozen Hypothesis Family Formal Protocol mismatch"
        )
    for set_reference, group, observations in observation_sets:
        for binding, observation in zip(
            group.observation_bindings, observations, strict=True
        ):
            locked = any(
                item.partition is EvaluationPartition.LOCKED_OOS
                and item.start_date <= observation.session_date <= item.end_date
                for item in evaluation_protocol.windows
            )
            if not locked:
                continue
            raw = RawOOSEvidenceIdentity(
                subject=observation.symbol,
                decision_session_date=observation.session_date,
                outcome_session_date=observation.label_end_date,
            )
            _claim_raw_oos_unlock(
                connection,
                protocol=protocol,
                family=family,
                raw=raw,
                unlocked_at=consumed_at,
            )
            consumption = LockedOOSTargetObservationConsumption.create(
                raw_evidence_identity_hash=raw.identity_hash,
                family_reference=family.reference,
                target_reference=group.target_reference,
                forecast_reference=binding.forecast_reference,
                label_reference=binding.label_reference,
                observation_set_reference=set_reference,
                consumed_at=consumed_at,
            )
            _insert_target_oos_consumption(connection, consumption)


def _raw_oos_unlock_payload(
    *,
    raw: RawOOSEvidenceIdentity,
    family: FrozenHypothesisFamily,
    protocol: FormalResearchProtocol,
) -> dict[str, Any]:
    return {
        "schema_version": "locked-oos-raw-unlock/v1",
        "raw_evidence_identity": raw.to_canonical_dict(),
        "first_family_reference": family.reference.to_canonical_dict(),
        "first_formal_protocol_reference": ValidationArtifactReference(
            "FORMAL_RESEARCH_PROTOCOL", protocol.protocol_id, protocol.protocol_hash
        ).to_canonical_dict(),
        "first_dataset_reference": protocol.dataset_reference.to_canonical_dict(),
        "first_universe_reference": protocol.universe_reference.to_canonical_dict(),
        "first_model_reference": protocol.model_reference.to_canonical_dict(),
    }


def _require_raw_oos_unlock(
    connection: Any,
    *,
    raw: RawOOSEvidenceIdentity,
    family: FrozenHypothesisFamily,
    protocol: FormalResearchProtocol,
    payload: Mapping[str, Any],
) -> None:
    row = connection.execute(
        """
        SELECT first_family_id, first_family_hash,
               first_formal_protocol_id, first_formal_protocol_hash,
               first_dataset_id, first_dataset_hash,
               first_universe_id, first_universe_hash,
               first_model_id, first_model_hash, payload_json
        FROM locked_oos_raw_evidence_unlock
        WHERE raw_evidence_identity_hash = %s
        """,
        (raw.identity_hash,),
    ).fetchone()
    expected = (
        str(family.family_id),
        family.family_hash,
        str(protocol.protocol_id),
        protocol.protocol_hash,
        str(protocol.dataset_reference.artifact_id),
        protocol.dataset_reference.content_hash,
        str(protocol.universe_reference.artifact_id),
        protocol.universe_reference.content_hash,
        str(protocol.model_reference.artifact_id),
        protocol.model_reference.content_hash,
        dict(payload),
    )
    if row is None or tuple(row) != expected:
        raise ResearchQualificationConflict(
            "Raw Locked OOS Evidence was already unlocked by another frozen family"
        )


def _require_target_oos_consumption(
    connection: Any,
    consumption: LockedOOSTargetObservationConsumption,
) -> None:
    row = connection.execute(
        """
        SELECT consumption_hash, family_id, family_hash, target_id,
               target_hash, forecast_id, forecast_hash, label_id,
               label_hash, observation_set_id, payload_json, consumed_at
        FROM locked_oos_target_observation_consumption
        WHERE raw_evidence_identity_hash = %s AND target_id = %s
        """,
        (
            consumption.raw_evidence_identity_hash,
            str(consumption.target_reference.artifact_id),
        ),
    ).fetchone()
    expected = (
        consumption.consumption_hash,
        str(consumption.family_reference.artifact_id),
        consumption.family_reference.content_hash,
        str(consumption.target_reference.artifact_id),
        consumption.target_reference.content_hash,
        str(consumption.forecast_reference.artifact_id),
        consumption.forecast_reference.content_hash,
        str(consumption.label_reference.artifact_id),
        consumption.label_reference.content_hash,
        str(consumption.observation_set_reference.artifact_id),
        consumption.to_canonical_dict(),
        consumption.consumed_at,
    )
    if row is None or tuple(row) != expected:
        raise ResearchQualificationConflict(
            "Locked OOS Target observation was already consumed differently"
        )


def _record_family_evaluation_result(
    connection: Any,
    *,
    result: FormalHypothesisFamilyEvaluationResult,
    protocol: FormalResearchProtocol,
    pits: tuple[FormalPITEvidenceArtifact, ...],
    samples: tuple[HistoricalSampleQualificationDecision, ...],
    observation_sets: tuple[
        tuple[
            ValidationArtifactReference,
            FamilyEvaluationObservationBindings,
            tuple[EvaluationObservation, ...],
        ],
        ...,
    ],
) -> None:
    payload = result.identity_payload()
    connection.execute(
        """
        INSERT INTO research_validation_artifact(
            artifact_id, artifact_hash, artifact_kind, evidence_authority,
            qualified, production_authorized, payload_json, created_at
        ) VALUES (
            %s, %s, 'FORMAL_HYPOTHESIS_FAMILY_EVALUATION_RESULT',
            'ENGINEERING_ONLY', false, false, %s, %s
        ) ON CONFLICT (artifact_id) DO NOTHING
        """,
        (
            str(result.result_id),
            result.result_hash,
            Jsonb(payload),
            result.created_at,
        ),
    )
    connection.execute(
        """
        INSERT INTO formal_hypothesis_family_evaluation(
            result_id, result_hash, family_id, family_hash,
            formal_protocol_id, formal_pit_evidence_id,
            target_count, payload_json, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (result_id) DO NOTHING
        """,
        (
            str(result.result_id),
            result.result_hash,
            str(result.family_reference.artifact_id),
            result.family_reference.content_hash,
            str(protocol.protocol_id),
            str(pits[0].evidence_id),
            len(observation_sets),
            Jsonb(payload),
            result.created_at,
        ),
    )
    for ordinal, pit in enumerate(pits, start=1):
        connection.execute(
            """
            INSERT INTO formal_hypothesis_family_evaluation_pit_evidence(
                result_id, ordinal, formal_pit_evidence_id,
                formal_pit_evidence_hash
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (result_id, formal_pit_evidence_id) DO NOTHING
            """,
            (
                str(result.result_id),
                ordinal,
                str(pit.evidence_id),
                pit.evidence_hash,
            ),
        )
    for ordinal, sample in enumerate(samples, start=1):
        connection.execute(
            """
            INSERT INTO formal_hypothesis_family_evaluation_historical_decision(
                result_id, ordinal, historical_decision_id,
                historical_decision_hash
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (result_id, historical_decision_id) DO NOTHING
            """,
            (
                str(result.result_id),
                ordinal,
                str(sample.decision_id),
                sample.decision_hash,
            ),
        )
    for set_reference, group, _observations in observation_sets:
        connection.execute(
            """
            INSERT INTO formal_hypothesis_family_evaluation_target(
                result_id, family_id, target_id, target_hash,
                observation_set_id
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (result_id, target_id) DO NOTHING
            """,
            (
                str(result.result_id),
                str(result.family_reference.artifact_id),
                str(group.target_reference.artifact_id),
                group.target_reference.content_hash,
                str(set_reference.artifact_id),
            ),
        )
    restored = _load_family_evaluation_result(connection, result.result_id)
    if restored != result:
        raise ResearchQualificationConflict(
            "Formal Family Evaluation result identity conflict"
        )


def _load_family_evaluation_result(
    connection: Any,
    result_id: ArtifactId,
) -> FormalHypothesisFamilyEvaluationResult:
    row = connection.execute(
        """
        SELECT result_hash, family_id, family_hash, formal_protocol_id,
               formal_pit_evidence_id, target_count, payload_json, created_at
        FROM formal_hypothesis_family_evaluation WHERE result_id = %s
        """,
        (str(result_id),),
    ).fetchone()
    if row is None or not isinstance(row[6], Mapping):
        raise KeyError(str(result_id))
    try:
        result = FormalHypothesisFamilyEvaluationResult.from_canonical_dict(
            {
                "result_id": str(result_id),
                "result_hash": str(row[0]),
                **dict(row[6]),
            }
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchQualificationConflict(
            "Formal Family Evaluation result replay failed"
        ) from exc
    targets = connection.execute(
        """
        SELECT target_id, target_hash, observation_set_id
        FROM formal_hypothesis_family_evaluation_target
        WHERE result_id = %s ORDER BY target_id
        """,
        (str(result_id),),
    ).fetchall()
    pit_rows = connection.execute(
        """
        SELECT formal_pit_evidence_id, formal_pit_evidence_hash
        FROM formal_hypothesis_family_evaluation_pit_evidence
        WHERE result_id = %s ORDER BY ordinal
        """,
        (str(result_id),),
    ).fetchall()
    historical_rows = connection.execute(
        """
        SELECT historical_decision_id, historical_decision_hash
        FROM formal_hypothesis_family_evaluation_historical_decision
        WHERE result_id = %s ORDER BY ordinal
        """,
        (str(result_id),),
    ).fetchall()
    metric_targets = {
        (str(item.target_reference.artifact_id), item.target_reference.content_hash)
        for item in result.metrics
    }
    if (
        result.family_reference.artifact_id != ArtifactId(str(row[1]))
        or result.family_reference.content_hash != str(row[2])
        or result.pit_evidence_reference is None
        or result.pit_evidence_reference.artifact_id != ArtifactId(str(row[4]))
        or tuple((str(item[0]), str(item[1])) for item in pit_rows)
        != tuple(
            (str(item.artifact_id), item.content_hash)
            for item in result.pit_evidence_references
        )
        or not historical_rows
        or any(
            _load_historical_decision(
                connection, ArtifactId(str(item[0]))
            ).decision_hash
            != str(item[1])
            for item in historical_rows
        )
        or len(targets) != int(row[5])
        or {(str(item[0]), str(item[1])) for item in targets} != metric_targets
        or result.created_at != row[7]
    ):
        raise ResearchQualificationConflict(
            "Formal Family Evaluation result storage drift"
        )
    _load_validation_artifact(
        connection,
        result_id,
        expected_kind="FORMAL_HYPOTHESIS_FAMILY_EVALUATION_RESULT",
    )
    return result


def _replay_family_evaluation_result(
    connection: Any,
    result_id: ArtifactId,
) -> FormalHypothesisFamilyEvaluationResult:
    original = _load_family_evaluation_result(connection, result_id)
    owner = connection.execute(
        """
        SELECT formal_protocol_id, formal_pit_evidence_id
        FROM formal_hypothesis_family_evaluation WHERE result_id = %s
        """,
        (str(result_id),),
    ).fetchone()
    if owner is None:
        raise ResearchQualificationConflict("Formal Family owner is missing")
    protocol = _load_formal_protocol(connection, ArtifactId(str(owner[0])))
    pit_rows = connection.execute(
        """
        SELECT formal_pit_evidence_id
        FROM formal_hypothesis_family_evaluation_pit_evidence
        WHERE result_id = %s ORDER BY ordinal
        """,
        (str(result_id),),
    ).fetchall()
    if not pit_rows or str(pit_rows[0][0]) != str(owner[1]):
        raise ResearchQualificationConflict("Formal Family PIT owner set is missing")
    pits = tuple(
        _load_formal_pit(connection, ArtifactId(str(item[0]))) for item in pit_rows
    )
    historical_rows = connection.execute(
        """
        SELECT historical_decision_id, historical_decision_hash
        FROM formal_hypothesis_family_evaluation_historical_decision
        WHERE result_id = %s ORDER BY ordinal
        """,
        (str(result_id),),
    ).fetchall()
    samples = tuple(
        _load_historical_decision(connection, ArtifactId(str(item[0])))
        for item in historical_rows
    )
    if tuple(sample.decision_hash for sample in samples) != tuple(
        str(item[1]) for item in historical_rows
    ):
        raise ResearchQualificationConflict(
            "Formal Family Historical prerequisite owner drift"
        )
    family = load_frozen_hypothesis_family_owner(
        connection, formal_protocol_id=protocol.protocol_id
    )
    _require_family_historical_prerequisites(
        connection,
        protocol=protocol,
        family=family,
        pits=pits,
        samples=samples,
        evaluated_at=original.created_at,
    )
    evaluation = _load_evaluation_protocol(
        connection, protocol.evaluation_protocol_reference.artifact_id
    )
    target_rows = connection.execute(
        """
        SELECT target_id, target_hash, observation_set_id
        FROM formal_hypothesis_family_evaluation_target
        WHERE result_id = %s ORDER BY target_id
        """,
        (str(result_id),),
    ).fetchall()
    inputs = tuple(
        _load_family_observation_input(
            connection,
            protocol=protocol,
            family=family,
            formal_pit_evidence_ids=tuple(item.evidence_id for item in pits),
            target_reference=ValidationArtifactReference(
                "OUTCOME_TARGET", ArtifactId(str(row[0])), str(row[1])
            ),
            observation_set_id=ArtifactId(str(row[2])),
            result_created_at=original.created_at,
        )
        for row in target_rows
    )
    replayed = run_formal_hypothesis_family_evaluation(
        family=family,
        protocol=evaluation,
        inputs=inputs,
        formal_pit_evidence=pits[0],
        formal_pit_evidences=pits,
        created_at=original.created_at,
        frozen_trading_dates=protocol.frozen_trading_dates,
    )
    if replayed != original:
        raise ResearchQualificationConflict(
            "Formal Family Evaluation deterministic replay failed"
        )
    return replayed


def _load_family_observation_input(
    connection: Any,
    *,
    protocol: FormalResearchProtocol,
    family: FrozenHypothesisFamily,
    formal_pit_evidence_ids: tuple[ArtifactId, ...],
    target_reference: ValidationArtifactReference,
    observation_set_id: ArtifactId,
    result_created_at: datetime,
) -> FamilyEvaluationInput:
    row = connection.execute(
        """
        SELECT observation_set_hash, formal_protocol_id, panel_id,
               target_protocol_id, target_id, target_hash,
               observation_count, payload_json, created_at
        FROM formal_evaluation_observation_set
        WHERE observation_set_id = %s
        """,
        (str(observation_set_id),),
    ).fetchone()
    if row is None or not isinstance(row[7], Mapping):
        raise ResearchQualificationConflict(
            "Family Evaluation observation-set owner is missing"
        )
    payload = _mapping(row[7])
    panel_reference = ValidationArtifactReference.from_canonical_dict(
        _mapping(payload["panel_reference"])
    )
    stored_target = ValidationArtifactReference.from_canonical_dict(
        _mapping(payload["target_reference"])
    )
    set_reference = ValidationArtifactReference(
        "FORMAL_EVALUATION_OBSERVATION_SET",
        observation_set_id,
        str(row[0]),
    )
    if (
        canonical_hash(dict(payload)) != str(row[0])
        or str(row[1]) != str(protocol.protocol_id)
        or str(row[2]) != str(panel_reference.artifact_id)
        or str(row[3]) != str(protocol.outcome_target_protocol_reference.artifact_id)
        or str(row[4]) != str(target_reference.artifact_id)
        or str(row[5]) != target_reference.content_hash
        or stored_target != target_reference
        or target_reference not in family.target_references
        or row[8] != result_created_at
    ):
        raise ResearchQualificationConflict(
            "Family Evaluation observation-set lineage mismatch"
        )
    bindings = tuple(
        FormalEvaluationObservationBinding.from_canonical_dict(_mapping(item))
        for item in _sequence(payload["observation_bindings"])
    )
    if (
        bindings != tuple(sorted(bindings, key=lambda item: item.observation_id))
        or len(bindings) != int(row[6])
        or len({item.observation_id for item in bindings}) != len(bindings)
    ):
        raise ResearchQualificationConflict(
            "Family Evaluation observation-set binding identity mismatch"
        )
    panel = _load_panel_owner(connection, panel_reference, protocol=protocol)
    observations = tuple(
        _resolve_evaluation_observation(
            connection,
            protocol=protocol,
            panel=panel,
            target_reference=target_reference,
            binding=binding,
            require_formal_forecast=True,
            formal_pit_evidence_ids=formal_pit_evidence_ids,
        )[0]
        for binding in bindings
    )
    for binding, observation in zip(bindings, observations, strict=True):
        if not any(
            item.partition is EvaluationPartition.LOCKED_OOS
            and item.start_date <= observation.session_date <= item.end_date
            for item in family.windows
        ):
            continue
        raw = RawOOSEvidenceIdentity(
            subject=observation.symbol,
            decision_session_date=observation.session_date,
            outcome_session_date=observation.label_end_date,
        )
        consumed = connection.execute(
            """
            SELECT consumption_hash, payload_json
            FROM locked_oos_target_observation_consumption
            WHERE raw_evidence_identity_hash = %s AND target_id = %s
            """,
            (raw.identity_hash, str(target_reference.artifact_id)),
        ).fetchone()
        if consumed is None or not isinstance(consumed[1], Mapping):
            raise ResearchQualificationConflict(
                "Family Evaluation Target OOS consumption is missing"
            )
        consumption_payload = _mapping(consumed[1])
        if (
            str(consumed[0]) != str(consumption_payload["consumption_hash"])
            or str(_mapping(consumption_payload["family_reference"])["artifact_id"])
            != str(family.family_id)
            or str(_mapping(consumption_payload["forecast_reference"])["artifact_id"])
            != str(binding.forecast_reference.artifact_id)
            or str(_mapping(consumption_payload["label_reference"])["artifact_id"])
            != str(binding.label_reference.artifact_id)
            or str(
                _mapping(consumption_payload["observation_set_reference"])[
                    "artifact_id"
                ]
            )
            != str(observation_set_id)
        ):
            raise ResearchQualificationConflict(
                "Family Evaluation Target OOS consumption replay mismatch"
            )
    return FamilyEvaluationInput(
        target_reference=target_reference,
        panel_reference=panel_reference,
        observations=observations,
        panel_source_references=_formal_evaluation_sources(
            protocol,
            target_reference=target_reference,
            observation_set_reference=set_reference,
        ),
    )


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
        raw = RawOOSEvidenceIdentity(
            subject=observation.symbol,
            decision_session_date=observation.session_date,
            outcome_session_date=observation.label_end_date,
        )
        acquire_scope_lock(
            connection,
            namespace="locked-oos-raw-evidence-unlock",
            identity=raw.identity_hash,
        )
        family_unlock = connection.execute(
            """
            SELECT first_family_id
            FROM locked_oos_raw_evidence_unlock
            WHERE raw_evidence_identity_hash = %s
            """,
            (raw.identity_hash,),
        ).fetchone()
        if family_unlock is not None:
            raise ResearchQualificationConflict(
                "Locked OOS evidence was already formally consumed by a frozen family"
            )
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
        target_protocol_reference=(formal_protocol.outcome_target_protocol_reference),
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
            *protocol.historical_sample_dataset_references,
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


def _record_observation_set_header(
    connection: Any,
    *,
    set_reference: ValidationArtifactReference,
    payload: Mapping[str, Any],
    formal_protocol: FormalResearchProtocol,
    group: FamilyEvaluationObservationBindings,
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
            str(set_reference.artifact_id),
            set_reference.content_hash,
            str(formal_protocol.protocol_id),
            str(group.panel_reference.artifact_id),
            str(formal_protocol.outcome_target_protocol_reference.artifact_id),
            str(group.target_reference.artifact_id),
            group.target_reference.content_hash,
            len(group.observation_bindings),
            Jsonb(dict(payload)),
            created_at,
        ),
    )
    stored = connection.execute(
        """
        SELECT observation_set_hash, formal_protocol_id, panel_id,
               target_protocol_id, target_id, target_hash,
               observation_count, payload_json, created_at
        FROM formal_evaluation_observation_set
        WHERE observation_set_id = %s
        """,
        (str(set_reference.artifact_id),),
    ).fetchone()
    expected = (
        set_reference.content_hash,
        str(formal_protocol.protocol_id),
        str(group.panel_reference.artifact_id),
        str(formal_protocol.outcome_target_protocol_reference.artifact_id),
        str(group.target_reference.artifact_id),
        group.target_reference.content_hash,
        len(group.observation_bindings),
        dict(payload),
        created_at,
    )
    if stored is None or tuple(stored) != expected:
        raise ResearchQualificationConflict(
            "Formal Evaluation observation-set header identity conflict"
        )


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
    resolved: tuple[
        tuple[EvaluationObservation, str, datetime, ArtifactId | None], ...
    ],
    created_at: datetime,
) -> None:
    _record_observation_set_header(
        connection,
        set_reference=ValidationArtifactReference(
            "FORMAL_EVALUATION_OBSERVATION_SET",
            observation_set_id,
            observation_set_hash,
        ),
        payload=observation_set_payload,
        formal_protocol=formal_protocol,
        group=FamilyEvaluationObservationBindings(
            target_reference=target_reference,
            panel_reference=panel_reference,
            observation_bindings=bindings,
        ),
        created_at=created_at,
    )
    for binding, (observation, settlement_id, _, _pit_id) in zip(
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


def _load_oos_policy(
    connection: Any,
    reference: ValidationArtifactReference,
) -> FormalOOSQualificationPolicy:
    row = connection.execute(
        """
        SELECT policy_hash, payload_json, locked_at
        FROM formal_oos_qualification_policy WHERE policy_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchone()
    if row is None or not isinstance(row[1], Mapping):
        raise ResearchQualificationConflict("Formal OOS Policy owner is missing")
    try:
        policy = FormalOOSQualificationPolicy.from_canonical_dict(_mapping(row[1]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchQualificationConflict(
            "Formal OOS Policy owner replay failed"
        ) from exc
    if (
        reference.artifact_kind != "FORMAL_OOS_QUALIFICATION_POLICY"
        or policy.policy_id != reference.artifact_id
        or policy.policy_hash != reference.content_hash
        or str(row[0]) != policy.policy_hash
        or row[2] != policy.locked_at
    ):
        raise ResearchQualificationConflict("Formal OOS Policy owner mismatch")
    return policy


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
        raise ResearchQualificationConflict(
            "Research qualification idempotency conflict"
        )
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
        raise ResearchQualificationConflict(
            "Qualification owner payload is not an object"
        )
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ResearchQualificationConflict(
            "Qualification owner payload is not an array"
        )
    return tuple(value)


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchQualificationConflict(
            "Qualification owner timestamp is invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResearchQualificationConflict(
            "Qualification owner timestamp must be timezone-aware"
        )
    return parsed


__all__ = [
    "PostgresResearchQualificationAuthority",
    "ResearchQualificationConflict",
]
