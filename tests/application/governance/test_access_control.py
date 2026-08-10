from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

from market_regime_alpha.application.governance.access_control import (
    ApprovalAction,
    ApprovalDecisionKind,
    PostgresAccessGovernance,
    PrincipalStatus,
    RoleEventKind,
    SecurityPermission,
    SecurityPrincipal,
    SecurityRole,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.admission import (
    AdmissionFloor,
    AdmissionFloorStatus,
    ProductionAdmissionStatus,
    current_engineering_blocked_admission,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory


NOW = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)


def test_engineering_rbac_approval_audit_and_revocation_are_fail_closed(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    governance = PostgresAccessGovernance(postgres_factory)
    admin = governance.bootstrap_admin(
        external_subject="local:phase-b-admin",
        display_name="Phase B Admin",
        reason="one-time engineering bootstrap",
        occurred_at=NOW,
        idempotency_key="bootstrap-admin-v1",
    )
    assert governance.bootstrap_admin(
        external_subject="local:phase-b-admin",
        display_name="Phase B Admin",
        reason="one-time engineering bootstrap",
        occurred_at=NOW,
        idempotency_key="bootstrap-admin-v1",
    ) == admin
    assert governance.authorization(
        admin.principal_id, SecurityPermission.MANAGE_ROLES
    ).allowed
    with pytest.raises(PermissionError, match="retain one active Admin"):
        governance.change_role(
            actor=admin.principal_id,
            principal_id=admin.principal_id,
            role=SecurityRole.ADMIN,
            event_kind=RoleEventKind.REVOKED,
            reason="would lock out governance",
            occurred_at=NOW,
            idempotency_key="revoke-last-admin",
        )

    researcher = governance.create_principal(
        actor=admin.principal_id,
        external_subject="local:researcher",
        display_name="Researcher",
        reason="research engineering",
        occurred_at=NOW + timedelta(seconds=1),
        idempotency_key="create-researcher",
    )
    approver = governance.create_principal(
        actor=admin.principal_id,
        external_subject="local:approver",
        display_name="Approver",
        reason="approval separation",
        occurred_at=NOW + timedelta(seconds=2),
        idempotency_key="create-approver",
    )
    governance.change_role(
        actor=admin.principal_id,
        principal_id=researcher.principal_id,
        role=SecurityRole.RESEARCHER,
        event_kind=RoleEventKind.GRANTED,
        reason="research role",
        occurred_at=NOW + timedelta(seconds=3),
        idempotency_key="grant-researcher",
    )
    governance.change_role(
        actor=admin.principal_id,
        principal_id=approver.principal_id,
        role=SecurityRole.APPROVER,
        event_kind=RoleEventKind.GRANTED,
        reason="approval role",
        occurred_at=NOW + timedelta(seconds=4),
        idempotency_key="grant-approver",
    )
    assert governance.authorization(
        researcher.principal_id, SecurityPermission.RUN_RESEARCH
    ).allowed
    assert not governance.authorization(
        researcher.principal_id, SecurityPermission.RUN_SHADOW
    ).allowed

    resource = ValidationArtifactReference(
        "FACTOR_RESEARCH_CATALOG",
        ArtifactId("factor-catalog-1"),
        canonical_hash({"factor": "catalog"}),
    )
    approval = governance.request_approval(
        requester=researcher.principal_id,
        action_kind=ApprovalAction.RESEARCH_CHANGE,
        resource_reference=resource,
        reason="review one research change",
        requested_at=NOW + timedelta(seconds=5),
        idempotency_key="request-research-change",
    )
    with pytest.raises(PermissionError, match="permission denied"):
        governance.decide_approval(
            approval_id=approval.approval_id,
            approver=researcher.principal_id,
            decision=ApprovalDecisionKind.APPROVED,
            reason="self approval forbidden",
            decided_at=NOW + timedelta(seconds=6),
            idempotency_key="self-approval",
        )
    decision = governance.decide_approval(
        approval_id=approval.approval_id,
        approver=approver.principal_id,
        decision=ApprovalDecisionKind.APPROVED,
        reason="engineering review complete",
        decided_at=NOW + timedelta(seconds=7),
        idempotency_key="approve-research-change",
    )
    assert decision.production_authorized is False
    assert "PRODUCTION_AUTHORIZED_FALSE" in decision.limitations
    admission = current_engineering_blocked_admission(
        governance_version="phase-b-access-v1",
        evidence={
            AdmissionFloor.AUTH_RBAC: ValidationArtifactReference(
                "SECURITY_APPROVAL_DECISION",
                decision.decision_id,
                decision.decision_hash,
            )
        },
        evaluated_at=NOW + timedelta(seconds=7),
    )
    assert admission.status is ProductionAdmissionStatus.BLOCKED
    assert next(
        item for item in admission.assessments if item.floor is AdmissionFloor.AUTH_RBAC
    ).status is AdmissionFloorStatus.MISSING
    assert len(governance.audit_events(reader=approver.principal_id)) == 7

    revoked = governance.change_role(
        actor=admin.principal_id,
        principal_id=researcher.principal_id,
        role=SecurityRole.RESEARCHER,
        event_kind=RoleEventKind.REVOKED,
        reason="revoke research access",
        occurred_at=NOW + timedelta(seconds=8),
        idempotency_key="revoke-researcher",
    )
    assert revoked.sequence == 2
    assert not governance.authorization(
        researcher.principal_id, SecurityPermission.RUN_RESEARCH
    ).allowed
    assert governance.set_principal_status(
        actor=admin.principal_id,
        principal_id=researcher.principal_id,
        status=PrincipalStatus.DISABLED,
        reason="disable external subject",
        occurred_at=NOW + timedelta(seconds=9),
        idempotency_key="disable-researcher",
    ) is PrincipalStatus.DISABLED


def test_security_bootstrap_and_commands_are_single_use(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    governance = PostgresAccessGovernance(postgres_factory)
    governance.bootstrap_admin(
        external_subject="local:admin",
        display_name="Admin",
        reason="bootstrap",
        occurred_at=NOW,
        idempotency_key="bootstrap",
    )
    with pytest.raises(PermissionError, match="bootstrap is closed"):
        governance.bootstrap_admin(
            external_subject="local:second-admin",
            display_name="Second Admin",
            reason="not allowed",
            occurred_at=NOW,
            idempotency_key="bootstrap-second",
        )
    with pytest.raises(ValueError, match="idempotency conflict"):
        governance.bootstrap_admin(
            external_subject="local:different",
            display_name="Different",
            reason="conflict",
            occurred_at=NOW,
            idempotency_key="bootstrap",
        )


def test_security_global_invariants_are_serialized(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresAccessGovernance(postgres_factory)
    bootstrap_barrier = Barrier(2)

    def bootstrap(index: int) -> SecurityPrincipal:
        bootstrap_barrier.wait()
        return PostgresAccessGovernance(
            postgres_factory, apply_migrations=False
        ).bootstrap_admin(
            external_subject=f"local:concurrent-admin-{index}",
            display_name=f"Concurrent Admin {index}",
            reason="concurrent bootstrap",
            occurred_at=NOW + timedelta(seconds=index),
            idempotency_key=f"concurrent-bootstrap-{index}",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(bootstrap, index) for index in (1, 2)]
        results: list[SecurityPrincipal] = []
        errors: list[BaseException] = []
        for future in futures:
            try:
                results.append(future.result())
            except BaseException as exc:  # noqa: BLE001 - assert concurrent outcome.
                errors.append(exc)

    assert len(results) == 1, (results, errors)
    assert len(errors) == 1
    assert isinstance(errors[0], PermissionError)
    first = results[0]
    first_id = first.principal_id
    governance = PostgresAccessGovernance(postgres_factory, apply_migrations=False)
    second = governance.create_principal(
        actor=first_id,
        external_subject="local:second-admin",
        display_name="Second Admin",
        reason="last-admin concurrency test",
        occurred_at=NOW + timedelta(seconds=3),
        idempotency_key="create-second-admin",
    )
    governance.change_role(
        actor=first_id,
        principal_id=second.principal_id,
        role=SecurityRole.ADMIN,
        event_kind=RoleEventKind.GRANTED,
        reason="last-admin concurrency test",
        occurred_at=NOW + timedelta(seconds=4),
        idempotency_key="grant-second-admin",
    )
    revoke_barrier = Barrier(2)

    def revoke(*, actor: ArtifactId, target: ArtifactId, key: str) -> object:
        revoke_barrier.wait()
        return PostgresAccessGovernance(
            postgres_factory, apply_migrations=False
        ).change_role(
            actor=actor,
            principal_id=target,
            role=SecurityRole.ADMIN,
            event_kind=RoleEventKind.REVOKED,
            reason="concurrent last-admin revocation",
            occurred_at=NOW + timedelta(seconds=5),
            idempotency_key=key,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(
                revoke,
                actor=first_id,
                target=second.principal_id,
                key="revoke-second-concurrently",
            ),
            executor.submit(
                revoke,
                actor=second.principal_id,
                target=first_id,
                key="revoke-first-concurrently",
            ),
        )
        revoked = 0
        denied = 0
        for future in futures:
            try:
                future.result()
                revoked += 1
            except PermissionError:
                denied += 1

    assert (revoked, denied) == (1, 1)
    assert sum(
        governance.authorization(principal_id, SecurityPermission.MANAGE_ROLES).allowed
        for principal_id in (first_id, second.principal_id)
    ) == 1
