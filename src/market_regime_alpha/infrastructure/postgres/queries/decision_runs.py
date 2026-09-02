"""Immutable Decision Run loader used by exact replay and verification."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from market_regime_alpha.decision_support.domain import (
    DecisionRuntimeMode,
    OpenDecisionRunRequest,
    PreparedDecisionInputs,
    PreparedDecisionReference,
    PreparedResearchQualification,
    ProviderProductDecisionSnapshot,
    RequestedDecisionTarget,
    RequestedResearchQualification,
    RuntimeDecisionSnapshot,
    TargetDecisionSnapshot,
    build_decision_authority,
)
from market_regime_alpha.decision_support.domain.vocabulary import (
    DecisionReferenceAvailabilityStatus,
    DecisionReferenceFinalityStatus,
    DecisionReferenceSourceKind,
    DecisionReferenceValueStatus,
    QualificationInputRole,
    ResearchPurpose,
)
from market_regime_alpha.decision_support.errors import (
    DecisionAuthorityIntegrityError,
)
from market_regime_alpha.decision_support.ports import DecisionRunSnapshot
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.decision_inputs import (
    _load_candidate_set,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError


class PostgresDecisionRunQueryProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def load(self, decision_run_id: UUID) -> DecisionRunSnapshot:
        with self._pool.connection(read_only=True) as connection:
            return _load_snapshot(connection, decision_run_id)

    def find_by_candidate_set(
        self,
        candidate_set_id: UUID,
    ) -> DecisionRunSnapshot | None:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT decision_run_id
                FROM mra.decision_run
                WHERE candidate_set_id = %s
                """,
                (candidate_set_id,),
            ).fetchone()
            if row is None:
                return None
            return _load_snapshot(connection, UUID(str(row[0])))


def _load_snapshot(connection: Any, decision_run_id: UUID) -> DecisionRunSnapshot:
    root = connection.execute(
        """
        SELECT decision_run_id, status, candidate_set_id,
               candidate_set_content_sha256, dataset_id,
               candidate_policy_id, candidate_count, selected_count,
               ranked_not_selected_count, unrankable_count,
               candidate_roster_sha256, research_purpose,
               research_qualification_roster_id,
               research_qualification_count,
               research_qualification_roster_sha256, target_count,
               target_roster_sha256, commitment_count, reference_count,
               commitment_roster_sha256, runtime_mode, decision_time,
               commitment_recorded_at, request_received_at,
               runtime_run_id, runtime_step_id, runtime_attempt_id,
               runtime_fence_token, runtime_step_key, runtime_step_kind,
               code_sha, config_artifact_id, config_hash,
               request_kind, request_scope_id, request_identity,
               request_sha256, command_receipt_id,
               created_by_actor_type, created_by_actor_id,
               creation_reason_code, definition_summary_sha256
        FROM mra.decision_run
        WHERE decision_run_id = %s
        """,
        (decision_run_id,),
    ).fetchone()
    if root is None:
        raise RuntimeNotFoundError(f"DecisionRun {decision_run_id} does not exist")
    target_rows = connection.execute(
        """
        SELECT decision_run_target_id, ordinal, target_definition_id,
               target_code, target_version, target_definition_sha256,
               target_checkpoint_id, target_checkpoint_sha256,
               target_checkpoint_ordinal, target_checkpoint_role,
               timeframe, price_basis, value_field, reference_rule,
               availability_rule, finality_rule,
               reference_provider_product_id, reference_provider_id,
               reference_provider_product_code,
               reference_provider_product_revision,
               decision_visibility_policy, source_availability_policy,
               commitment_recorded_at, content_sha256, created_at
        FROM mra.decision_run_target
        WHERE decision_run_id = %s
        ORDER BY ordinal
        """,
        (decision_run_id,),
    ).fetchall()
    commitment_rows = connection.execute(
        """
        SELECT commitment.commitment_id,
               commitment.decision_run_target_id,
               commitment.candidate_id,
               commitment.content_sha256,
               reference.decision_reference_observation_id,
               reference.target_definition_id,
               reference.target_checkpoint_id,
               reference.reference_provider_product_id,
               reference.reference_provider_id, reference.capture_id,
               reference.instrument_id, reference.session_id,
               reference.event_start, reference.event_end,
               reference.observation_time, reference.source_recorded_at,
               reference.known_at, reference.timeframe,
               reference.price_basis, reference.source_kind,
               reference.value_status, reference.availability_status,
               reference.finality_status, reference.value_field,
               reference.decimal_value, reference.bar_revision_id,
               reference.bar_revision, reference.source_gap_id,
               reference.source_gap_kind, reference.source_gap_reason_code,
               reference.content_sha256,
               commitment.candidate_set_id,
               commitment.instrument_id,
               commitment.candidate_disposition,
               commitment.target_definition_id,
               commitment.decision_time, commitment.runtime_mode,
               commitment.commitment_recorded_at,
               commitment.decision_reference_sha256,
               commitment.created_at, reference.created_at
        FROM mra.decision_target_commitment AS commitment
        JOIN mra.decision_run_target AS target
          ON target.decision_run_target_id =
             commitment.decision_run_target_id
        JOIN mra.decision_reference_observation AS reference
          ON reference.decision_reference_observation_id =
             commitment.decision_reference_observation_id
        WHERE commitment.decision_run_id = %s
        ORDER BY target.ordinal, commitment.candidate_id
        """,
        (decision_run_id,),
    ).fetchall()
    qualification_rows = connection.execute(
        """
        SELECT member.research_qualification_member_id,
               member.research_qualification_roster_id,
               member.decision_run_id, member.ordinal, member.role,
               member.research_qualification_decision_id,
               member.decision_code, member.revision,
               member.supersedes_decision_id,
               member.research_assessment_id,
               member.research_qualification_policy_id,
               member.experiment_id, member.target_definition_id,
               member.qualification_purpose,
               member.source_generation_max_decision_time,
               member.effective_at, member.known_at,
               member.qualification_content_sha256,
               member.decision_time, member.content_sha256,
               member.created_at
        FROM mra.decision_run_research_qualification_member AS member
        WHERE member.decision_run_id = %s
        ORDER BY member.ordinal
        """,
        (decision_run_id,),
    ).fetchall()
    try:
        candidate_set = _load_candidate_set(
            connection,
            UUID(str(root[2])),
            lock=False,
        )
        targets = tuple(_target_snapshot(row) for row in target_rows)
        references = tuple(_reference(row) for row in commitment_rows)
        runtime = RuntimeDecisionSnapshot(
            run_id=UUID(str(root[24])),
            step_id=UUID(str(root[25])),
            attempt_id=UUID(str(root[26])),
            fence_token=int(root[27]),
            step_key=str(root[28]),
            step_kind=str(root[29]),
            runtime_mode=DecisionRuntimeMode(str(root[20])),
            decision_time=root[21],
            code_sha=str(root[30]),
            config_artifact_id=UUID(str(root[31])),
            config_hash=str(root[32]),
        )
        research_purpose = ResearchPurpose(str(root[11]))
        research_qualifications = tuple(
            PreparedResearchQualification(
                research_qualification_decision_id=UUID(str(row[5])),
                role=QualificationInputRole(str(row[4])),
                decision_code=str(row[6]),
                revision=int(row[7]),
                supersedes_decision_id=(
                    UUID(str(row[8])) if row[8] is not None else None
                ),
                research_assessment_id=UUID(str(row[9])),
                research_qualification_policy_id=UUID(str(row[10])),
                experiment_id=UUID(str(row[11])),
                target_definition_id=UUID(str(row[12])),
                qualification_purpose=ResearchPurpose(str(row[13])),
                source_generation_max_decision_time=row[14],
                effective_at=row[15],
                known_at=row[16],
                content_sha256=str(row[17]),
            )
            for row in qualification_rows
        )
        target_ids = {
            UUID(str(row[2])): UUID(str(row[0])) for row in target_rows
        }
        commitment_ids = {
            (UUID(str(row[2])), UUID(str(row[5]))): UUID(str(row[0]))
            for row in commitment_rows
        }
        observation_ids = {
            UUID(str(row[0])): UUID(str(row[4])) for row in commitment_rows
        }
        qualification_member_ids = {
            UUID(str(row[5])): UUID(str(row[0])) for row in qualification_rows
        }
        authority = build_decision_authority(
            decision_run_id=UUID(str(root[0])),
            command_receipt_id=UUID(str(root[37])),
            candidate_set=candidate_set,
            targets=targets,
            references=references,
            runtime=runtime,
            research_purpose=research_purpose,
            research_qualifications=research_qualifications,
            request_identity=str(root[35]),
            request_sha256=str(root[36]),
            request_received_at=root[23],
            commitment_recorded_at=root[22],
            actor_type=str(root[38]),
            actor_id=str(root[39]),
            reason_code=str(root[40]),
            qualification_roster_id=UUID(str(root[12])),
            qualification_member_id_factory=lambda item, ordinal: (
                qualification_member_ids[item.research_qualification_decision_id]
            ),
            target_id_factory=lambda target, ordinal: target_ids[
                target.target_definition_id
            ],
            commitment_id_factory=lambda candidate, target: commitment_ids[
                (candidate.candidate_id, target.target_definition_id)
            ],
            observation_id_factory=lambda commitment_id: observation_ids[
                commitment_id
            ],
        )
        prepared = PreparedDecisionInputs(
            candidate_set=candidate_set,
            targets=targets,
            references=references,
            runtime=runtime,
            research_qualifications=research_qualifications,
        )
        request = OpenDecisionRunRequest(
            candidate_set_id=candidate_set.candidate_set_id,
            targets=tuple(
                RequestedDecisionTarget(
                    target_definition_id=target.target_definition_id,
                    reference_provider_product_id=(
                        target.reference_provider_product.provider_product_id
                    ),
                )
                for target in targets
            ),
            research_purpose=research_purpose,
            research_qualifications=tuple(
                RequestedResearchQualification(
                    research_qualification_decision_id=(
                        item.research_qualification_decision_id
                    ),
                    role=item.role,
                )
                for item in research_qualifications
            ),
        )
        computed_request_hash = prepared.semantic_request_sha256(
            request=request,
            actor_type=str(root[38]),
            actor_id=str(root[39]),
            reason_code=str(root[40]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DecisionAuthorityIntegrityError(
            "Decision Run rows cannot reconstruct the typed Authority"
        ) from exc

    _validate_root(root, authority, computed_request_hash)
    _validate_children(target_rows, commitment_rows, qualification_rows, authority)
    receipt = connection.execute(
        """
        SELECT status, result_aggregate_kind, result_aggregate_id,
               result_aggregate_version, result_hash, command_kind,
               scope_id, idempotency_key, request_hash,
               runtime_step_id, runtime_attempt_id, fence_token
        FROM mra.command_receipt
        WHERE receipt_id = %s
        """,
        (authority.command_receipt_id,),
    ).fetchone()
    if (
        receipt is None
        or str(receipt[0]) != "SUCCEEDED"
        or str(receipt[1]) != "DECISION_RUN"
        or str(receipt[2]) != str(authority.decision_run_id)
        or int(receipt[3]) != 1
        or str(receipt[5]) != "OPEN_DECISION_RUN"
        or str(receipt[6]) != str(candidate_set.candidate_set_id)
        or str(receipt[7]) != authority.request_identity
        or str(receipt[8]) != authority.request_sha256
        or UUID(str(receipt[9])) != runtime.step_id
        or UUID(str(receipt[10])) != runtime.attempt_id
        or int(receipt[11]) != runtime.fence_token
    ):
        raise DecisionAuthorityIntegrityError(
            "Decision Run command receipt does not match its Authority"
        )
    return DecisionRunSnapshot(
        authority=authority,
        receipt_id=authority.command_receipt_id,
        result_hash=str(receipt[4]),
    )


def _target_snapshot(row: tuple[Any, ...]) -> TargetDecisionSnapshot:
    if str(row[9]) != "DECISION_REFERENCE":
        raise ValueError("Decision Target checkpoint role changed")
    if row[22] != row[24]:
        raise ValueError("Decision Target creation timestamp changed")
    return TargetDecisionSnapshot(
        target_definition_id=UUID(str(row[2])),
        target_code=str(row[3]),
        version=int(row[4]),
        content_sha256=str(row[5]),
        target_checkpoint_id=UUID(str(row[6])),
        checkpoint_content_sha256=str(row[7]),
        checkpoint_ordinal=int(row[8]),
        timeframe=str(row[10]),
        price_basis=str(row[11]),
        value_field=str(row[12]),
        reference_rule=str(row[13]),
        availability_rule=str(row[14]),
        finality_rule=str(row[15]),
        reference_provider_product=ProviderProductDecisionSnapshot(
            provider_product_id=UUID(str(row[16])),
            provider_id=UUID(str(row[17])),
            product_code=str(row[18]),
            revision=int(row[19]),
            decision_visibility_policy=str(row[20]),
            source_availability_policy=str(row[21]),
        ),
    )


def _reference(row: tuple[Any, ...]) -> PreparedDecisionReference:
    return PreparedDecisionReference(
        candidate_id=UUID(str(row[2])),
        target_definition_id=UUID(str(row[5])),
        target_checkpoint_id=UUID(str(row[6])),
        provider_product_id=UUID(str(row[7])),
        provider_id=UUID(str(row[8])),
        capture_id=UUID(str(row[9])),
        instrument_id=UUID(str(row[10])),
        session_id=UUID(str(row[11])),
        event_start=row[12],
        event_end=row[13],
        observation_time=row[14],
        recorded_at=row[15],
        known_at=row[16],
        timeframe=str(row[17]),
        price_basis=str(row[18]),
        source_kind=DecisionReferenceSourceKind(str(row[19])),
        value_status=DecisionReferenceValueStatus(str(row[20])),
        availability_status=DecisionReferenceAvailabilityStatus(str(row[21])),
        finality_status=DecisionReferenceFinalityStatus(str(row[22])),
        value_field=str(row[23]),
        decimal_value=row[24],
        bar_revision_id=UUID(str(row[25])) if row[25] is not None else None,
        bar_revision=int(row[26]) if row[26] is not None else None,
        source_gap_id=UUID(str(row[27])) if row[27] is not None else None,
        source_gap_kind=str(row[28]) if row[28] is not None else None,
        source_gap_reason_code=str(row[29]) if row[29] is not None else None,
    )


def _validate_root(root: tuple[Any, ...], authority: Any, request_hash: str) -> None:
    candidate = authority.candidate_set
    actual = (
        str(root[1]), UUID(str(root[2])), str(root[3]), UUID(str(root[4])),
        UUID(str(root[5])), int(root[6]), int(root[7]), int(root[8]),
        int(root[9]), str(root[10]), str(root[11]), UUID(str(root[12])),
        int(root[13]), str(root[14]), int(root[15]), str(root[16]),
        int(root[17]), int(root[18]), str(root[19]), str(root[33]),
        str(root[34]), str(root[41]),
    )
    expected = (
        authority.status.value, candidate.candidate_set_id,
        candidate.content_sha256, candidate.dataset_id,
        candidate.candidate_policy_id, authority.candidate_count,
        candidate.selected_count, candidate.ranked_not_selected_count,
        candidate.unrankable_count, authority.candidate_roster_sha256,
        authority.research_purpose.value,
        authority.research_qualification_roster.roster_id,
        authority.research_qualification_count,
        authority.research_qualification_roster_sha256,
        authority.target_count, authority.target_roster_sha256,
        authority.commitment_count, authority.reference_count,
        authority.commitment_roster_sha256, "OPEN_DECISION_RUN",
        str(candidate.candidate_set_id), authority.definition_summary_sha256,
    )
    if (
        actual != expected
        or request_hash != authority.request_sha256
        or str(root[36]) != request_hash
    ):
        raise DecisionAuthorityIntegrityError(
            "Decision Run root facts do not reconstruct canonically"
        )


def _validate_children(
    target_rows: tuple[tuple[Any, ...], ...],
    commitment_rows: tuple[tuple[Any, ...], ...],
    qualification_rows: tuple[tuple[Any, ...], ...],
    authority: Any,
) -> None:
    if tuple(str(row[23]) for row in target_rows) != tuple(
        item.content_sha256 for item in authority.targets
    ):
        raise DecisionAuthorityIntegrityError("Decision Target hash changed")
    by_id = {item.commitment_id: item for item in authority.commitments}
    if len(by_id) != len(commitment_rows):
        raise DecisionAuthorityIntegrityError("Decision commitment roster changed")
    for row in commitment_rows:
        commitment = by_id.get(UUID(str(row[0])))
        if (
            commitment is None
            or str(row[3]) != commitment.content_sha256
            or str(row[30]) != commitment.reference.content_sha256
            or str(row[38]) != commitment.reference.content_sha256
            or row[37] != row[39]
            or row[37] != row[40]
            or row[37] != commitment.commitment_recorded_at
        ):
            raise DecisionAuthorityIntegrityError(
                "Decision commitment/reference immutable facts changed"
            )
    qualification_members = authority.research_qualification_roster.members
    if len(qualification_rows) != len(qualification_members):
        raise DecisionAuthorityIntegrityError(
            "Decision Research Qualification roster changed"
        )
    for row, member in zip(qualification_rows, qualification_members, strict=True):
        if (
            UUID(str(row[0])) != member.member_id
            or UUID(str(row[1])) != member.roster_id
            or UUID(str(row[2])) != member.decision_run_id
            or int(row[3]) != member.ordinal
            or str(row[19]) != member.content_sha256
            or row[18] != authority.runtime.decision_time
            or row[20] != authority.commitment_recorded_at
        ):
            raise DecisionAuthorityIntegrityError(
                "Decision Research Qualification immutable facts changed"
            )


__all__ = ["PostgresDecisionRunQueryProvider"]
