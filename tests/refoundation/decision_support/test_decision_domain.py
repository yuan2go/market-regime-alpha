from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.decision_support.domain import (
    CandidateDecisionFact,
    CandidateDisposition,
    CandidateSetDecisionSnapshot,
    DecisionReferenceAvailabilityStatus,
    DecisionReferenceFinalityStatus,
    DecisionReferenceSourceKind,
    DecisionReferenceValueStatus,
    DecisionRuntimeMode,
    PreparedDecisionReference,
    ProviderProductDecisionSnapshot,
    RequestedDecisionTarget,
    RuntimeDecisionSnapshot,
    TargetDecisionSnapshot,
    build_decision_authority,
)


def _uuid(suffix: int) -> UUID:
    return UUID(f"00000000-0000-4000-8000-{suffix:012d}")


DECISION_TIME = datetime(2026, 8, 28, 6, 55, tzinfo=UTC)


def _candidate_snapshot() -> CandidateSetDecisionSnapshot:
    candidates = (
        CandidateDecisionFact(
            candidate_id=_uuid(1),
            candidate_set_id=_uuid(10),
            instrument_id=_uuid(101),
            disposition=CandidateDisposition.SELECTED,
        ),
        CandidateDecisionFact(
            candidate_id=_uuid(2),
            candidate_set_id=_uuid(10),
            instrument_id=_uuid(102),
            disposition=CandidateDisposition.RANKED_NOT_SELECTED,
        ),
        CandidateDecisionFact(
            candidate_id=_uuid(3),
            candidate_set_id=_uuid(10),
            instrument_id=_uuid(103),
            disposition=CandidateDisposition.UNRANKABLE,
        ),
    )
    return CandidateSetDecisionSnapshot(
        candidate_set_id=_uuid(10),
        content_sha256="a" * 64,
        dataset_id=_uuid(11),
        candidate_policy_id=_uuid(12),
        decision_time=DECISION_TIME,
        population_count=3,
        selected_count=1,
        ranked_not_selected_count=1,
        unrankable_count=1,
        candidates=candidates,
    )


def _target_snapshot() -> TargetDecisionSnapshot:
    return TargetDecisionSnapshot(
        target_definition_id=_uuid(20),
        target_code="mr1_next_session_return",
        version=1,
        content_sha256="b" * 64,
        target_checkpoint_id=_uuid(21),
        checkpoint_content_sha256="c" * 64,
        checkpoint_ordinal=1,
        timeframe="MINUTE_5",
        price_basis="RAW_UNADJUSTED",
        value_field="CLOSE",
        reference_rule="EXACT_SESSION_BAR",
        availability_rule="EXACT_REVISION_OR_SOURCE_GAP",
        finality_rule="RECORD_UNKNOWN",
        reference_provider_product=ProviderProductDecisionSnapshot(
            provider_product_id=_uuid(22),
            provider_id=_uuid(23),
            product_code="fixture.market_bar",
            revision=1,
            decision_visibility_policy="KNOWN_AT",
            source_availability_policy="RECORDED_SOURCE_GAPS",
        ),
    )


def _runtime() -> RuntimeDecisionSnapshot:
    return RuntimeDecisionSnapshot(
        run_id=_uuid(30),
        step_id=_uuid(31),
        attempt_id=_uuid(32),
        fence_token=1,
        step_key="open-decision-run",
        step_kind="OPEN_DECISION_RUN",
        runtime_mode=DecisionRuntimeMode.HISTORICAL,
        decision_time=DECISION_TIME,
        code_sha="d" * 40,
        config_artifact_id=_uuid(33),
        config_hash="e" * 64,
    )


def _references() -> tuple[PreparedDecisionReference, ...]:
    return tuple(
        PreparedDecisionReference(
            candidate_id=_uuid(index),
            target_definition_id=_uuid(20),
            target_checkpoint_id=_uuid(21),
            provider_product_id=_uuid(22),
            provider_id=_uuid(23),
            capture_id=_uuid(40 + index),
            instrument_id=_uuid(100 + index),
            session_id=_uuid(50),
            event_start=datetime(2026, 8, 28, 6, 50, tzinfo=UTC),
            event_end=DECISION_TIME,
            observation_time=DECISION_TIME,
            recorded_at=datetime(2026, 8, 28, 6, 54, tzinfo=UTC),
            known_at=DECISION_TIME,
            timeframe="MINUTE_5",
            price_basis="RAW_UNADJUSTED",
            source_kind=DecisionReferenceSourceKind.BAR_REVISION,
            value_status=DecisionReferenceValueStatus.PRESENT,
            availability_status=DecisionReferenceAvailabilityStatus.AVAILABLE,
            finality_status=DecisionReferenceFinalityStatus.UNKNOWN,
            value_field="CLOSE",
            decimal_value=Decimal(f"{10 + index}.25"),
            bar_revision_id=_uuid(60 + index),
            bar_revision=1,
            source_gap_id=None,
            source_gap_kind=None,
            source_gap_reason_code=None,
        )
        for index in range(1, 4)
    )


def test_decision_authority_freezes_all_candidate_dispositions_and_complete_cross_product() -> None:
    authority = build_decision_authority(
        decision_run_id=_uuid(70),
        command_receipt_id=_uuid(700),
        candidate_set=_candidate_snapshot(),
        targets=(_target_snapshot(),),
        references=_references(),
        runtime=_runtime(),
        request_identity="open-decision-run-1",
        request_sha256="f" * 64,
        request_received_at=datetime(2026, 8, 28, 6, 56, tzinfo=UTC),
        commitment_recorded_at=datetime(2026, 8, 28, 6, 57, tzinfo=UTC),
        actor_type="WORKER",
        actor_id="decision-test",
        reason_code="OPEN_DECISION_RUN",
        commitment_id_factory=lambda candidate, target: UUID(
            int=candidate.candidate_id.int ^ target.target_definition_id.int
        ),
        observation_id_factory=lambda commitment_id: UUID(int=commitment_id.int ^ 99),
    )

    assert authority.candidate_count == 3
    assert authority.target_count == 1
    assert authority.commitment_count == 3
    assert authority.reference_count == 3
    assert {item.candidate_disposition for item in authority.commitments} == {
        CandidateDisposition.SELECTED,
        CandidateDisposition.RANKED_NOT_SELECTED,
        CandidateDisposition.UNRANKABLE,
    }
    assert all(item.reference.commitment_id == item.commitment_id for item in authority.commitments)
    assert len(authority.candidate_roster_sha256) == 64
    assert len(authority.target_roster_sha256) == 64
    assert len(authority.commitment_roster_sha256) == 64
    assert len(authority.definition_summary_sha256) == 64


def test_empty_candidate_set_still_closes_non_empty_target_roster() -> None:
    empty = replace(
        _candidate_snapshot(),
        population_count=0,
        selected_count=0,
        ranked_not_selected_count=0,
        unrankable_count=0,
        candidates=(),
    )
    authority = build_decision_authority(
        decision_run_id=_uuid(71),
        command_receipt_id=_uuid(710),
        candidate_set=empty,
        targets=(_target_snapshot(),),
        references=(),
        runtime=_runtime(),
        request_identity="open-empty",
        request_sha256="1" * 64,
        request_received_at=DECISION_TIME,
        commitment_recorded_at=DECISION_TIME,
        actor_type="WORKER",
        actor_id="decision-test",
        reason_code="OPEN_DECISION_RUN",
        commitment_id_factory=lambda candidate, target: _uuid(72),
        observation_id_factory=lambda commitment_id: _uuid(73),
    )
    assert authority.candidate_count == 0
    assert authority.target_count == 1
    assert authority.commitment_count == 0
    assert authority.reference_count == 0


def test_request_and_snapshot_reject_empty_or_duplicate_target_rosters() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        RequestedDecisionTarget.roster(())
    target = RequestedDecisionTarget(
        target_definition_id=_uuid(20),
        reference_provider_product_id=_uuid(22),
    )
    with pytest.raises(ValueError, match="duplicate"):
        RequestedDecisionTarget.roster((target, target))


def test_reference_state_axes_are_independent_but_source_shape_is_closed() -> None:
    reference = _references()[0]
    gap = replace(
        reference,
        source_kind=DecisionReferenceSourceKind.SOURCE_GAP,
        value_status=DecisionReferenceValueStatus.UNAVAILABLE,
        availability_status=DecisionReferenceAvailabilityStatus.UNAVAILABLE,
        decimal_value=None,
        bar_revision_id=None,
        bar_revision=None,
        source_gap_id=_uuid(90),
        source_gap_kind="MISSING",
        source_gap_reason_code="EXACT_BAR_MISSING",
    )
    assert gap.finality_status is DecisionReferenceFinalityStatus.UNKNOWN
    with pytest.raises(ValueError, match="BAR_REVISION"):
        replace(reference, bar_revision_id=None)
    late = replace(
            reference,
            known_at=datetime(2026, 8, 28, 6, 56, tzinfo=UTC),
    )
    late_references = (late, *_references()[1:])
    with pytest.raises(ValueError, match="known_at"):
        build_decision_authority(
            decision_run_id=_uuid(91),
            command_receipt_id=_uuid(910),
            candidate_set=_candidate_snapshot(),
            targets=(_target_snapshot(),),
            references=late_references,
            runtime=_runtime(),
            request_identity="late-reference",
            request_sha256="3" * 64,
            request_received_at=DECISION_TIME,
            commitment_recorded_at=DECISION_TIME,
            actor_type="WORKER",
            actor_id="decision-test",
            reason_code="OPEN_DECISION_RUN",
            commitment_id_factory=lambda candidate, target: UUID(
                int=candidate.candidate_id.int ^ target.target_definition_id.int
            ),
            observation_id_factory=lambda commitment_id: UUID(
                int=commitment_id.int ^ 99
            ),
        )


def test_runtime_and_candidate_decision_time_must_match() -> None:
    with pytest.raises(ValueError, match="DecisionTime"):
        build_decision_authority(
            decision_run_id=_uuid(74),
            command_receipt_id=_uuid(740),
            candidate_set=_candidate_snapshot(),
            targets=(_target_snapshot(),),
            references=_references(),
            runtime=replace(
                _runtime(),
                decision_time=datetime(2026, 8, 28, 6, 56, tzinfo=UTC),
            ),
            request_identity="open-mismatch",
            request_sha256="2" * 64,
            request_received_at=DECISION_TIME,
            commitment_recorded_at=DECISION_TIME,
            actor_type="WORKER",
            actor_id="decision-test",
            reason_code="OPEN_DECISION_RUN",
            commitment_id_factory=lambda candidate, target: _uuid(75),
            observation_id_factory=lambda commitment_id: _uuid(76),
        )
