from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    ModelLifecycleStatus,
)
from market_regime_alpha.platform.durable_governance import PersistentModelRegistry
from market_regime_alpha.platform.postgres_runtime_governance import (
    PostgresModelGovernanceRepository,
)
from market_regime_alpha.platform.repositories import VersionConflictError
from market_regime_alpha.platform.runtime_governance import (
    ArtifactLineageReference,
    AssignmentLane,
    AssignmentStatus,
    ModelSelectionRequest,
    QualificationEvidenceKind,
    QualificationEvidenceOutcome,
    QualificationStatus,
    RuntimePurpose,
    SelectionStatus,
)
from tests.platform.test_platform_kernel import _model_definition
from tests.platform.test_runtime_governance import (
    NOW,
    _evidence,
    _lineage,
    _research_policy,
    _runtime_lineage,
)


def _governed_model(
    repository: PostgresModelGovernanceRepository,
    *,
    suffix: str = "a",
):
    definition = (
        _model_definition()
        if suffix == "a"
        else replace(
            _model_definition(),
            model_id=ModelId(f"candidate-governed-{suffix}-v1"),
            name=f"Governed candidate {suffix}",
        )
    )
    registry = PersistentModelRegistry(repository)
    registered = registry.register(
        definition, idempotency_key=f"register-{suffix}"
    )
    research = registry.transition(
        definition.model_id,
        expected_version=registered.version,
        idempotency_key=f"research-{suffix}",
        to_status=ModelLifecycleStatus.RESEARCH,
        changed_at=NOW,
        reason="explicit research lifecycle",
        evidence_refs=(f"lifecycle-evidence-{suffix}",),
        evidence_level=EvidenceLevel.EXPLORATORY,
    )
    lineage = repository.record_version_lineage(
        _lineage(definition),
        actor="governance-operator",
        reason="bind immutable model lineage",
        idempotency_key=f"lineage-{suffix}",
    )
    policy = _research_policy()
    repository.record_policy(
        policy,
        actor="governance-operator",
        reason="explicit research policy",
        created_at=NOW,
        idempotency_key="research-policy-v1",
    )
    for kind in policy.required_evidence_kinds:
        repository.record_evidence(
            _evidence(lineage, kind),
            idempotency_key=f"evidence-{suffix}-{kind.value}",
        )
    qualification = repository.qualify(
        model_id=definition.model_id,
        policy_id=policy.policy_id,
        actor="governance-reviewer",
        reason="explicit research qualification",
        approval_ref=f"approval:research-{suffix}",
        decided_at=NOW,
        expected_registry_version=research.version,
        idempotency_key=f"qualify-{suffix}",
    )
    assert qualification.status is QualificationStatus.QUALIFIED
    return definition, lineage, policy, research


def _request(
    lineage,
    *,
    key: str,
    purpose=RuntimePurpose.RESEARCH,
    selected_at=NOW,
):
    return ModelSelectionRequest.create(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=purpose,
        runtime_lineage=_runtime_lineage(lineage),
        selected_at=selected_at,
        idempotency_key=key,
    )


def test_postgres_selection_is_idempotent_and_historical_replay_is_revision_bound(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresModelGovernanceRepository(postgres_factory)
    definition, lineage, policy, research = _governed_model(repository)
    champion = repository.assign(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        lane=AssignmentLane.CHAMPION,
        model_id=definition.model_id,
        policy_id=policy.policy_id,
        expected_governance_revision=repository.current_revision(),
        effective_at=NOW,
        actor="governance-operator",
        reason="explicit Research Champion",
        approval_ref="approval:research-champion",
        idempotency_key="assign-champion",
    )
    request = _request(lineage, key="select-once")

    selected = repository.select(request)
    assert repository.select(request) == selected
    assert selected.status is SelectionStatus.SELECTED
    assert selected.selected_model_id == definition.model_id
    assert selected.selected_registry_version == research.version

    suspended = repository.transition_assignment(
        champion.assignment_id,
        expected_version=champion.version,
        status=AssignmentStatus.SUSPENDED,
        effective_at=NOW,
        actor="governance-operator",
        reason="explicit suspension",
        approval_ref="approval:suspend-champion",
        idempotency_key="suspend-champion",
    )
    assert suspended.status is AssignmentStatus.SUSPENDED
    rejected = repository.select(_request(lineage, key="select-after-suspend"))
    assert rejected.status is SelectionStatus.REJECTED
    assert "CHAMPION_AUTHORITY_MISSING" in rejected.reason_codes
    assert repository.get_selection_receipt(rejected.receipt_id) == rejected
    assert repository.replay_selection(selected.receipt_id) == selected


def test_version_lineage_semantic_duplicate_cannot_create_orphan_action(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresModelGovernanceRepository(postgres_factory)
    _, lineage, _, _ = _governed_model(repository)

    with pytest.raises(ValueError, match="original idempotency key"):
        repository.record_version_lineage(
            lineage,
            actor="different-operator",
            reason="attempt duplicate semantic lineage",
            idempotency_key="lineage-semantic-duplicate",
        )

    with postgres_factory.connection(read_only=True) as connection:
        action_count = connection.execute(
            "SELECT count(*) FROM model_governance_action "
            "WHERE action_type = 'MODEL_VERSION_LINEAGE'"
        ).fetchone()[0]
        event_count = connection.execute(
            "SELECT count(*) FROM model_version_lineage"
        ).fetchone()[0]
    assert action_count == event_count == 1


def test_registry_demotion_invalidates_new_selection_without_rewriting_history(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresModelGovernanceRepository(postgres_factory)
    definition, lineage, policy, research = _governed_model(repository)
    repository.assign(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        lane=AssignmentLane.CHAMPION,
        model_id=definition.model_id,
        policy_id=policy.policy_id,
        expected_governance_revision=repository.current_revision(),
        effective_at=NOW,
        actor="governance-operator",
        reason="explicit Research Champion",
        approval_ref="approval:research-champion",
        idempotency_key="assign-before-demotion",
    )
    historical = repository.select(_request(lineage, key="before-demotion"))
    suspended = PersistentModelRegistry(repository).transition(
        definition.model_id,
        expected_version=research.version,
        idempotency_key="suspend-model-lifecycle",
        to_status=ModelLifecycleStatus.SUSPENDED,
        changed_at=NOW,
        reason="model governance suspension",
    )

    current = repository.select(_request(lineage, key="after-demotion"))
    assert current.status is SelectionStatus.REJECTED
    assert "QUALIFICATION_REGISTRY_VERSION_STALE" in current.reason_codes
    PersistentModelRegistry(repository).transition(
        definition.model_id,
        expected_version=suspended.version,
        idempotency_key="retire-model-lifecycle",
        to_status=ModelLifecycleStatus.RETIRED,
        changed_at=NOW + timedelta(seconds=1),
        reason="model governance retirement",
    )
    assert repository.replay_selection(historical.receipt_id) == historical
    assert repository.replay_selection(current.receipt_id) == current


def test_challenger_is_audited_but_never_selected_for_authoritative_output(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresModelGovernanceRepository(postgres_factory)
    champion_definition, champion_lineage, policy, _ = _governed_model(repository)
    challenger_definition, _, _, _ = _governed_model(repository, suffix="b")
    champion = repository.assign(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        lane=AssignmentLane.CHAMPION,
        model_id=champion_definition.model_id,
        policy_id=policy.policy_id,
        expected_governance_revision=repository.current_revision(),
        effective_at=NOW,
        actor="operator",
        reason="Champion",
        approval_ref="approval:champion",
        idempotency_key="champion-a",
    )
    challenger = repository.assign(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        lane=AssignmentLane.CHALLENGER,
        model_id=challenger_definition.model_id,
        policy_id=policy.policy_id,
        expected_governance_revision=repository.current_revision(),
        effective_at=NOW,
        actor="operator",
        reason="Challenger comparison only",
        approval_ref="approval:challenger",
        idempotency_key="challenger-b",
    )

    selected = repository.select(_request(champion_lineage, key="with-challenger"))
    assert selected.selected_model_id == champion.model_id
    assert selected.challenger_model_ids == (challenger.model_id,)


def test_assignment_cas_serializes_concurrent_champion_writers(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresModelGovernanceRepository(postgres_factory)
    definition, _, policy, _ = _governed_model(repository)
    expected = repository.current_revision()

    def assign(key: str):
        return PostgresModelGovernanceRepository(postgres_factory).assign(
            runtime_scope="DAILY_LOOP",
            model_slot="DAILY_B0",
            purpose=RuntimePurpose.RESEARCH,
            lane=AssignmentLane.CHAMPION,
            model_id=definition.model_id,
            policy_id=policy.policy_id,
            expected_governance_revision=expected,
            effective_at=NOW,
            actor="operator",
            reason="concurrent writer",
            approval_ref="approval:concurrency",
            idempotency_key=key,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(executor.submit(assign, key) for key in ("writer-a", "writer-b"))
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result())
        except VersionConflictError:
            outcomes.append("CONFLICT")
    assert sum(item == "CONFLICT" for item in outcomes) == 1
    assert len(repository.list_assignments(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
    )) == 1


def test_champion_replacement_is_explicit_and_old_selection_remains_replayable(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresModelGovernanceRepository(postgres_factory)
    first_definition, first_lineage, policy, _ = _governed_model(repository)
    second_definition, second_lineage, _, _ = _governed_model(
        repository, suffix="replacement"
    )
    first = repository.assign(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        lane=AssignmentLane.CHAMPION,
        model_id=first_definition.model_id,
        policy_id=policy.policy_id,
        expected_governance_revision=repository.current_revision(),
        effective_at=NOW,
        actor="operator",
        reason="first Champion",
        approval_ref="approval:first",
        idempotency_key="replacement-first-champion",
    )
    historical = repository.select(
        _request(first_lineage, key="replacement-before")
    )
    challenger = repository.assign(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        lane=AssignmentLane.CHALLENGER,
        model_id=second_definition.model_id,
        policy_id=policy.policy_id,
        expected_governance_revision=repository.current_revision(),
        effective_at=NOW,
        actor="operator",
        reason="explicit Challenger before promotion",
        approval_ref="approval:replacement-challenger",
        idempotency_key="replacement-second-challenger",
    )
    expected_revision = repository.current_revision()
    replacement = repository.replace_champion(
        first.assignment_id,
        new_model_id=second_definition.model_id,
        policy_id=policy.policy_id,
        expected_version=first.version,
        expected_governance_revision=expected_revision,
        effective_at=NOW,
        actor="operator",
        reason="explicit Champion replacement",
        approval_ref="approval:replacement",
        idempotency_key="replace-first-champion",
    )
    assert repository.replace_champion(
        first.assignment_id,
        new_model_id=second_definition.model_id,
        policy_id=policy.policy_id,
        expected_version=first.version,
        expected_governance_revision=expected_revision,
        effective_at=NOW,
        actor="operator",
        reason="explicit Champion replacement",
        approval_ref="approval:replacement",
        idempotency_key="replace-first-champion",
    ) == replacement

    selected = repository.select(
        _request(second_lineage, key="replacement-after")
    )
    assert selected.selected_model_id == replacement.model_id
    assert selected.challenger_model_ids == ()
    assignment_events = repository.inspect_model(
        second_definition.model_id
    )["assignment_events"]
    assert any(
        item["supersedes_assignment_id"] == str(challenger.assignment_id)
        and item["status"] == "REPLACED"
        for item in assignment_events
    )
    assert repository.replay_selection(historical.receipt_id) == historical


def test_production_selection_without_production_qualification_is_persistently_rejected(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresModelGovernanceRepository(postgres_factory)
    _, lineage, _, _ = _governed_model(repository)

    rejected = repository.select(
        _request(
            lineage,
            key="forged-production-selection",
            purpose=RuntimePurpose.PRODUCTION_DECISION,
        )
    )
    assert rejected.status is SelectionStatus.REJECTED
    assert rejected.production_authorized is False
    assert repository.replay_selection(rejected.receipt_id) == rejected


def test_selection_rejects_runtime_lineage_conflict_and_persists_reason(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresModelGovernanceRepository(postgres_factory)
    definition, lineage, policy, _ = _governed_model(repository)
    repository.assign(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        lane=AssignmentLane.CHAMPION,
        model_id=definition.model_id,
        policy_id=policy.policy_id,
        expected_governance_revision=repository.current_revision(),
        effective_at=NOW,
        actor="operator",
        reason="Champion",
        approval_ref="approval:champion",
        idempotency_key="lineage-champion",
    )
    bad_runtime = _runtime_lineage(lineage, configuration_hash="sha256:" + "f" * 64)
    request = ModelSelectionRequest.create(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        runtime_lineage=bad_runtime,
        selected_at=NOW,
        idempotency_key="bad-runtime-lineage",
    )

    rejected = repository.select(request)
    assert rejected.status is SelectionStatus.REJECTED
    assert "RUNTIME_LINEAGE_MISMATCH" in rejected.reason_codes
    assert repository.get_selection_receipt(rejected.receipt_id) == rejected


def test_later_revoked_evidence_invalidates_qualification_until_requalified(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresModelGovernanceRepository(postgres_factory)
    definition, lineage, policy, _ = _governed_model(repository)
    repository.assign(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        lane=AssignmentLane.CHAMPION,
        model_id=definition.model_id,
        policy_id=policy.policy_id,
        expected_governance_revision=repository.current_revision(),
        effective_at=NOW,
        actor="operator",
        reason="Champion before evidence revocation",
        approval_ref="approval:champion-before-revocation",
        idempotency_key="champion-before-revocation",
    )
    assert repository.select(
        _request(lineage, key="before-evidence-revocation")
    ).status is SelectionStatus.SELECTED
    revoked_at = NOW + timedelta(seconds=1)
    repository.record_evidence(
        _evidence(
            lineage,
            policy.required_evidence_kinds[0],
            outcome=QualificationEvidenceOutcome.REVOKED,
            at=revoked_at,
        ),
        idempotency_key="revoke-required-evidence",
    )

    rejected = repository.select(
        _request(
            lineage,
            key="after-evidence-revocation",
            selected_at=revoked_at,
        )
    )

    assert rejected.status is SelectionStatus.REJECTED
    assert "QUALIFICATION_EVIDENCE_STALE" in rejected.reason_codes


def test_global_revision_cas_serializes_writers_in_different_scopes(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresModelGovernanceRepository(postgres_factory)
    definition, _, policy, _ = _governed_model(repository)
    expected_revision = repository.current_revision()

    def assign(slot: str):
        return repository.assign(
            runtime_scope="GLOBAL_CAS_TEST",
            model_slot=slot,
            purpose=RuntimePurpose.RESEARCH,
            lane=AssignmentLane.CHAMPION,
            model_id=definition.model_id,
            policy_id=policy.policy_id,
            expected_governance_revision=expected_revision,
            effective_at=NOW,
            actor="concurrent-operator",
            reason=f"global revision writer {slot}",
            approval_ref=f"approval:{slot}",
            idempotency_key=f"global-cas-{slot}",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(assign, slot) for slot in ("SLOT_A", "SLOT_B")]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except VersionConflictError as error:
                outcomes.append(error)

    assert sum(not isinstance(item, Exception) for item in outcomes) == 1
    assert sum(isinstance(item, VersionConflictError) for item in outcomes) == 1


def test_selection_enforces_runtime_data_eligibility_against_policy(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresModelGovernanceRepository(postgres_factory)
    definition, lineage, policy, _ = _governed_model(repository)
    repository.assign(
        runtime_scope="DAILY_LOOP",
        model_slot="DAILY_B0",
        purpose=RuntimePurpose.RESEARCH,
        lane=AssignmentLane.CHAMPION,
        model_id=definition.model_id,
        policy_id=policy.policy_id,
        expected_governance_revision=repository.current_revision(),
        effective_at=NOW,
        actor="operator",
        reason="Exploratory-only Champion",
        approval_ref="approval:exploratory-only",
        idempotency_key="exploratory-only-champion",
    )
    formal_runtime = _runtime_lineage(
        lineage,
        data_eligibility=DataEligibility.FORMAL_RESEARCH,
    )

    rejected = repository.select(
        ModelSelectionRequest.create(
            runtime_scope="DAILY_LOOP",
            model_slot="DAILY_B0",
            purpose=RuntimePurpose.RESEARCH,
            runtime_lineage=formal_runtime,
            selected_at=NOW,
            idempotency_key="formal-runtime-under-exploratory-policy",
        )
    )

    assert rejected.status is SelectionStatus.REJECTED
    assert "RUNTIME_DATA_ELIGIBILITY_NOT_ALLOWED" in rejected.reason_codes


def test_evidence_protocol_must_be_declared_by_model_lineage(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    repository = PostgresModelGovernanceRepository(postgres_factory)
    definition = _model_definition()
    registry = PersistentModelRegistry(repository)
    registry.register(definition, idempotency_key="protocol-register")
    lineage = repository.record_version_lineage(
        _lineage(definition),
        actor="operator",
        reason="protocol-bound lineage",
        idempotency_key="protocol-lineage",
    )
    wrong_protocol = ArtifactLineageReference(
        "VALIDATION_PROTOCOL",
        ArtifactId("unrelated-validation-protocol"),
        "sha256:" + "9" * 64,
    )

    with pytest.raises(ValueError, match="validation protocol mismatch"):
        repository.record_evidence(
            _evidence(
                lineage,
                QualificationEvidenceKind.DATASET_INTEGRITY,
                validation_protocol_ref=wrong_protocol,
            ),
            idempotency_key="wrong-evidence-protocol",
        )
