"""Append-only engineering RBAC and two-person approval governance.

This module deliberately owns no authentication, Production Admission, Order,
Fill, Position, Broker, or qualification permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class PrincipalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class SecurityRole(str, Enum):
    RESEARCHER = "RESEARCHER"
    OPERATOR = "OPERATOR"
    APPROVER = "APPROVER"
    ADMIN = "ADMIN"


class SecurityPermission(str, Enum):
    READ_RESEARCH = "READ_RESEARCH"
    RUN_RESEARCH = "RUN_RESEARCH"
    RECORD_RESEARCH_EVIDENCE = "RECORD_RESEARCH_EVIDENCE"
    RUN_SHADOW = "RUN_SHADOW"
    RECOVER_RUNTIME = "RECOVER_RUNTIME"
    REPORT_RUNTIME = "REPORT_RUNTIME"
    APPROVE_ENGINEERING_CHANGE = "APPROVE_ENGINEERING_CHANGE"
    MANAGE_PRINCIPALS = "MANAGE_PRINCIPALS"
    MANAGE_ROLES = "MANAGE_ROLES"
    READ_SECURITY_AUDIT = "READ_SECURITY_AUDIT"


class RoleEventKind(str, Enum):
    GRANTED = "GRANTED"
    REVOKED = "REVOKED"


class ApprovalAction(str, Enum):
    RESEARCH_CHANGE = "RESEARCH_CHANGE"
    SHADOW_OPERATION = "SHADOW_OPERATION"
    RECOVERY_OPERATION = "RECOVERY_OPERATION"


class ApprovalDecisionKind(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


_ROLE_PERMISSIONS: dict[SecurityRole, frozenset[SecurityPermission]] = {
    SecurityRole.RESEARCHER: frozenset(
        {
            SecurityPermission.READ_RESEARCH,
            SecurityPermission.RUN_RESEARCH,
            SecurityPermission.RECORD_RESEARCH_EVIDENCE,
        }
    ),
    SecurityRole.OPERATOR: frozenset(
        {
            SecurityPermission.READ_RESEARCH,
            SecurityPermission.RUN_SHADOW,
            SecurityPermission.RECOVER_RUNTIME,
            SecurityPermission.REPORT_RUNTIME,
        }
    ),
    SecurityRole.APPROVER: frozenset(
        {
            SecurityPermission.READ_RESEARCH,
            SecurityPermission.APPROVE_ENGINEERING_CHANGE,
            SecurityPermission.READ_SECURITY_AUDIT,
        }
    ),
    SecurityRole.ADMIN: frozenset(SecurityPermission),
}

_ACTION_PERMISSION = {
    ApprovalAction.RESEARCH_CHANGE: SecurityPermission.RUN_RESEARCH,
    ApprovalAction.SHADOW_OPERATION: SecurityPermission.RUN_SHADOW,
    ApprovalAction.RECOVERY_OPERATION: SecurityPermission.RECOVER_RUNTIME,
}

# Serialize the two global governance invariants (single bootstrap and at least
# one active Admin) without introducing a mutable singleton owner row.
_SECURITY_GOVERNANCE_ADVISORY_LOCK = 5_114_731_902_026_081_106

_LIMITATIONS = (
    "AUTHENTICATION_PROVIDER_NOT_BOUND",
    "BROKER_PERMISSION_ABSENT",
    "PRODUCTION_ADMISSION_PERMISSION_ABSENT",
)


@dataclass(frozen=True, slots=True)
class SecurityPrincipal:
    principal_id: ArtifactId
    principal_hash: str
    external_subject: str
    display_name: str
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "security-principal/v1"

    def __post_init__(self) -> None:
        require_sha256("principal_hash", self.principal_hash)
        if canonical_hash(self.identity_payload()) != self.principal_hash:
            raise ValueError("Security Principal hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        external_subject: str,
        display_name: str,
        created_at: datetime,
    ) -> SecurityPrincipal:
        if not external_subject.strip() or not display_name.strip():
            raise ValueError("Security Principal subject/name must be non-empty")
        values = {
            "schema_version": "security-principal/v1",
            "external_subject": external_subject,
            "display_name": display_name,
            "created_at": timestamp(created_at),
            "limitations": list(_LIMITATIONS),
        }
        principal_id, digest = content_identity("security-principal", values)
        return cls(
            principal_id,
            digest,
            external_subject,
            display_name,
            created_at,
            _LIMITATIONS,
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "external_subject": self.external_subject,
            "display_name": self.display_name,
            "created_at": timestamp(self.created_at),
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "principal_id": str(self.principal_id),
            "principal_hash": self.principal_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> SecurityPrincipal:
        return cls(
            principal_id=ArtifactId(str(value["principal_id"])),
            principal_hash=str(value["principal_hash"]),
            external_subject=str(value["external_subject"]),
            display_name=str(value["display_name"]),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            limitations=tuple(str(item) for item in _sequence(value["limitations"])),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class SecurityRoleEvent:
    event_id: ArtifactId
    event_hash: str
    principal_id: ArtifactId
    role: SecurityRole
    event_kind: RoleEventKind
    sequence: int
    previous_event_id: ArtifactId | None
    changed_by: ArtifactId
    reason: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        require_sha256("role event hash", self.event_hash)
        if canonical_hash(self.identity_payload()) != self.event_hash:
            raise ValueError("Security Role Event hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "principal_id": str(self.principal_id),
            "role": self.role.value,
            "event_kind": self.event_kind.value,
            "sequence": self.sequence,
            "previous_event_id": (
                None if self.previous_event_id is None else str(self.previous_event_id)
            ),
            "changed_by": str(self.changed_by),
            "reason": self.reason,
            "occurred_at": timestamp(self.occurred_at),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_hash": self.event_hash,
            **self.identity_payload(),
        }


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    principal_id: ArtifactId
    status: PrincipalStatus
    roles: tuple[SecurityRole, ...]
    permission: SecurityPermission
    allowed: bool
    reason_codes: tuple[str, ...]
    authentication_established: bool = False
    production_authorized: bool = False

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "principal_id": str(self.principal_id),
            "status": self.status.value,
            "roles": [item.value for item in self.roles],
            "permission": self.permission.value,
            "allowed": self.allowed,
            "reason_codes": list(self.reason_codes),
            "authentication_established": False,
            "production_authorized": False,
        }


@dataclass(frozen=True, slots=True)
class SecurityApproval:
    approval_id: ArtifactId
    approval_hash: str
    action_kind: ApprovalAction
    resource_reference: ValidationArtifactReference
    requested_by: ArtifactId
    reason: str
    requested_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "security-approval/v1"

    def __post_init__(self) -> None:
        require_sha256("approval_hash", self.approval_hash)
        if canonical_hash(self.identity_payload()) != self.approval_hash:
            raise ValueError("Security Approval hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "action_kind": self.action_kind.value,
            "resource_reference": self.resource_reference.to_canonical_dict(),
            "requested_by": str(self.requested_by),
            "reason": self.reason,
            "requested_at": timestamp(self.requested_at),
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "approval_id": str(self.approval_id),
            "approval_hash": self.approval_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> SecurityApproval:
        approval = cls(
            approval_id=ArtifactId(str(value["approval_id"])),
            approval_hash=str(value["approval_hash"]),
            action_kind=ApprovalAction(str(value["action_kind"])),
            resource_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["resource_reference"])
            ),
            requested_by=ArtifactId(str(value["requested_by"])),
            reason=str(value["reason"]),
            requested_at=datetime.fromisoformat(str(value["requested_at"])),
            limitations=tuple(str(item) for item in _sequence(value["limitations"])),
            schema_version=str(value["schema_version"]),
        )
        return approval


@dataclass(frozen=True, slots=True)
class SecurityApprovalDecision:
    decision_id: ArtifactId
    decision_hash: str
    approval_reference: ValidationArtifactReference
    decision: ApprovalDecisionKind
    decided_by: ArtifactId
    reason: str
    decided_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "security-approval-decision/v1"

    def __post_init__(self) -> None:
        require_sha256("decision_hash", self.decision_hash)
        if canonical_hash(self.identity_payload()) != self.decision_hash:
            raise ValueError("Security Approval Decision hash mismatch")

    @property
    def production_authorized(self) -> bool:
        return False

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "approval_reference": self.approval_reference.to_canonical_dict(),
            "decision": self.decision.value,
            "decided_by": str(self.decided_by),
            "reason": self.reason,
            "decided_at": timestamp(self.decided_at),
            "production_authorized": False,
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            "decision_hash": self.decision_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> SecurityApprovalDecision:
        if value["production_authorized"] is not False:
            raise ValueError("Security Approval cannot authorize Production")
        result = cls(
            decision_id=ArtifactId(str(value["decision_id"])),
            decision_hash=str(value["decision_hash"]),
            approval_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["approval_reference"])
            ),
            decision=ApprovalDecisionKind(str(value["decision"])),
            decided_by=ArtifactId(str(value["decided_by"])),
            reason=str(value["reason"]),
            decided_at=datetime.fromisoformat(str(value["decided_at"])),
            limitations=tuple(str(item) for item in _sequence(value["limitations"])),
            schema_version=str(value["schema_version"]),
        )
        return result


class PostgresAccessGovernance:
    """Sole writer for the lightweight engineering access-control facts."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def bootstrap_admin(
        self,
        *,
        external_subject: str,
        display_name: str,
        reason: str,
        occurred_at: datetime,
        idempotency_key: str,
    ) -> SecurityPrincipal:
        principal = SecurityPrincipal.create(
            external_subject=external_subject,
            display_name=display_name,
            created_at=occurred_at,
        )
        command_payload = {
            "operation": "BOOTSTRAP_ADMIN",
            "principal": principal.to_canonical_dict(),
            "reason": reason,
            "occurred_at": timestamp(occurred_at),
        }
        command_hash = canonical_hash(command_payload)

        def operation(connection: Any) -> str:
            _lock_security_governance(connection)
            existing = _existing_command(connection, idempotency_key, command_hash)
            if existing is not None:
                return existing
            count = int(
                connection.execute("SELECT count(*) FROM security_principal").fetchone()[0]
            )
            if count != 0:
                raise PermissionError("Security bootstrap is closed after first Principal")
            self._insert_principal(connection, principal)
            self._insert_status(
                connection,
                principal_id=principal.principal_id,
                status=PrincipalStatus.ACTIVE,
                actor=principal.principal_id,
                reason=reason,
                occurred_at=occurred_at,
            )
            self._insert_role_event(
                connection,
                principal_id=principal.principal_id,
                role=SecurityRole.ADMIN,
                event_kind=RoleEventKind.GRANTED,
                actor=principal.principal_id,
                reason=reason,
                occurred_at=occurred_at,
            )
            self._audit(
                connection,
                event_kind="BOOTSTRAP_ADMIN",
                actor=principal.principal_id,
                target_kind="SECURITY_PRINCIPAL",
                target_id=principal.principal_id,
                details=(("bootstrap_only", "true"),),
                occurred_at=occurred_at,
            )
            _record_command(
                connection,
                idempotency_key,
                command_hash,
                "SECURITY_PRINCIPAL",
                principal.principal_id,
                occurred_at,
            )
            return str(principal.principal_id)

        principal_id = ArtifactId(self._factory.run_transaction(operation))
        return self.get_principal(principal_id)

    def create_principal(
        self,
        *,
        actor: ArtifactId,
        external_subject: str,
        display_name: str,
        reason: str,
        occurred_at: datetime,
        idempotency_key: str,
    ) -> SecurityPrincipal:
        principal = SecurityPrincipal.create(
            external_subject=external_subject,
            display_name=display_name,
            created_at=occurred_at,
        )
        payload = {
            "operation": "CREATE_PRINCIPAL",
            "actor": str(actor),
            "principal": principal.to_canonical_dict(),
            "reason": reason,
        }
        digest = canonical_hash(payload)

        def operation(connection: Any) -> str:
            _lock_security_governance(connection)
            existing = _existing_command(connection, idempotency_key, digest)
            if existing is not None:
                return existing
            _require_permission(
                connection, actor, SecurityPermission.MANAGE_PRINCIPALS
            )
            self._insert_principal(connection, principal)
            self._insert_status(
                connection,
                principal_id=principal.principal_id,
                status=PrincipalStatus.ACTIVE,
                actor=actor,
                reason=reason,
                occurred_at=occurred_at,
            )
            self._audit(
                connection,
                event_kind="PRINCIPAL_CREATED",
                actor=actor,
                target_kind="SECURITY_PRINCIPAL",
                target_id=principal.principal_id,
                details=(),
                occurred_at=occurred_at,
            )
            _record_command(
                connection,
                idempotency_key,
                digest,
                "SECURITY_PRINCIPAL",
                principal.principal_id,
                occurred_at,
            )
            return str(principal.principal_id)

        principal_id = ArtifactId(self._factory.run_transaction(operation))
        return self.get_principal(principal_id)

    def change_role(
        self,
        *,
        actor: ArtifactId,
        principal_id: ArtifactId,
        role: SecurityRole,
        event_kind: RoleEventKind,
        reason: str,
        occurred_at: datetime,
        idempotency_key: str,
    ) -> SecurityRoleEvent:
        payload = {
            "operation": "CHANGE_ROLE",
            "actor": str(actor),
            "principal_id": str(principal_id),
            "role": role.value,
            "event_kind": event_kind.value,
            "reason": reason,
            "occurred_at": timestamp(occurred_at),
        }
        digest = canonical_hash(payload)

        def operation(connection: Any) -> str:
            _lock_security_governance(connection)
            existing = _existing_command(connection, idempotency_key, digest)
            if existing is not None:
                return existing
            _require_permission(connection, actor, SecurityPermission.MANAGE_ROLES)
            if _principal_status(connection, principal_id) is not PrincipalStatus.ACTIVE:
                raise PermissionError("Role target Principal is not active")
            if (
                role is SecurityRole.ADMIN
                and event_kind is RoleEventKind.REVOKED
                and _active_admin_count(connection) <= 1
            ):
                raise PermissionError("Security Governance must retain one active Admin")
            event = self._insert_role_event(
                connection,
                principal_id=principal_id,
                role=role,
                event_kind=event_kind,
                actor=actor,
                reason=reason,
                occurred_at=occurred_at,
            )
            self._audit(
                connection,
                event_kind=f"ROLE_{event_kind.value}",
                actor=actor,
                target_kind="SECURITY_PRINCIPAL",
                target_id=principal_id,
                details=(("role", role.value),),
                occurred_at=occurred_at,
            )
            _record_command(
                connection,
                idempotency_key,
                digest,
                "SECURITY_ROLE_EVENT",
                event.event_id,
                occurred_at,
            )
            return str(event.event_id)

        event_id = ArtifactId(self._factory.run_transaction(operation))
        return self.get_role_event(event_id)

    def set_principal_status(
        self,
        *,
        actor: ArtifactId,
        principal_id: ArtifactId,
        status: PrincipalStatus,
        reason: str,
        occurred_at: datetime,
        idempotency_key: str,
    ) -> PrincipalStatus:
        payload = {
            "operation": "SET_PRINCIPAL_STATUS",
            "actor": str(actor),
            "principal_id": str(principal_id),
            "status": status.value,
            "reason": reason,
            "occurred_at": timestamp(occurred_at),
        }
        digest = canonical_hash(payload)

        def operation(connection: Any) -> str:
            _lock_security_governance(connection)
            existing = _existing_command(connection, idempotency_key, digest)
            if existing is not None:
                return existing
            _require_permission(
                connection, actor, SecurityPermission.MANAGE_PRINCIPALS
            )
            if actor == principal_id and status is PrincipalStatus.DISABLED:
                raise PermissionError("Admin cannot disable its own Principal")
            if (
                status is PrincipalStatus.DISABLED
                and SecurityRole.ADMIN in _current_roles(connection, principal_id)
                and _active_admin_count(connection) <= 1
            ):
                raise PermissionError("Security Governance must retain one active Admin")
            event_id = self._insert_status(
                connection,
                principal_id=principal_id,
                status=status,
                actor=actor,
                reason=reason,
                occurred_at=occurred_at,
            )
            self._audit(
                connection,
                event_kind="PRINCIPAL_STATUS_CHANGED",
                actor=actor,
                target_kind="SECURITY_PRINCIPAL",
                target_id=principal_id,
                details=(("status", status.value),),
                occurred_at=occurred_at,
            )
            _record_command(
                connection,
                idempotency_key,
                digest,
                "SECURITY_PRINCIPAL_STATUS_EVENT",
                event_id,
                occurred_at,
            )
            return str(event_id)

        self._factory.run_transaction(operation)
        return self.authorization(
            principal_id, SecurityPermission.READ_RESEARCH
        ).status

    def authorization(
        self, principal_id: ArtifactId, permission: SecurityPermission
    ) -> AuthorizationDecision:
        with self._factory.connection(read_only=True) as connection:
            status = _principal_status(connection, principal_id)
            roles = _current_roles(connection, principal_id)
        allowed = status is PrincipalStatus.ACTIVE and any(
            permission in _ROLE_PERMISSIONS[role] for role in roles
        )
        reasons: set[str] = set()
        if status is not PrincipalStatus.ACTIVE:
            reasons.add("PRINCIPAL_NOT_ACTIVE")
        if not any(permission in _ROLE_PERMISSIONS[role] for role in roles):
            reasons.add("PERMISSION_NOT_GRANTED")
        if allowed:
            reasons.add("ENGINEERING_PERMISSION_GRANTED")
        return AuthorizationDecision(
            principal_id=principal_id,
            status=status,
            roles=roles,
            permission=permission,
            allowed=allowed,
            reason_codes=tuple(sorted(reasons)),
        )

    def authorize_operation(
        self,
        *,
        principal_id: ArtifactId,
        permission: SecurityPermission,
        resource_reference: ValidationArtifactReference,
        approval_decision_id: ArtifactId | None,
        occurred_at: datetime,
    ) -> AuthorizationDecision:
        """Authorize and audit one operator invocation against an exact resource.

        Non-Admin Shadow and recovery mutations require an independently approved
        engineering resource.  This never grants Production or Broker authority.
        """

        def operation(connection: Any) -> AuthorizationDecision:
            status = _principal_status(connection, principal_id)
            roles = _current_roles(connection, principal_id)
            allowed = status is PrincipalStatus.ACTIVE and any(
                permission in _ROLE_PERMISSIONS[role] for role in roles
            )
            reasons: set[str] = set()
            if status is not PrincipalStatus.ACTIVE:
                reasons.add("PRINCIPAL_NOT_ACTIVE")
            if not any(permission in _ROLE_PERMISSIONS[role] for role in roles):
                reasons.add("PERMISSION_NOT_GRANTED")
            approval_required = (
                permission
                in {SecurityPermission.RUN_SHADOW, SecurityPermission.RECOVER_RUNTIME}
                and SecurityRole.ADMIN not in roles
            )
            if approval_required:
                approval_reason = _validate_operation_approval(
                    connection,
                    principal_id=principal_id,
                    permission=permission,
                    resource_reference=resource_reference,
                    approval_decision_id=approval_decision_id,
                )
                if approval_reason is not None:
                    allowed = False
                    reasons.add(approval_reason)
                else:
                    reasons.add("INDEPENDENT_ENGINEERING_APPROVAL_VERIFIED")
            elif SecurityRole.ADMIN in roles:
                reasons.add("ADMIN_ENGINEERING_APPROVAL_EXEMPTION")
            if allowed:
                reasons.add("ENGINEERING_PERMISSION_GRANTED")
            self._audit(
                connection,
                event_kind=(
                    "OPERATOR_INVOCATION_AUTHORIZED"
                    if allowed
                    else "OPERATOR_INVOCATION_DENIED"
                ),
                actor=principal_id,
                target_kind=resource_reference.artifact_kind,
                target_id=resource_reference.artifact_id,
                details=tuple(
                    sorted(
                        {
                            ("allowed", str(allowed).lower()),
                            ("permission", permission.value),
                            ("resource_hash", resource_reference.content_hash),
                            *(
                                ()
                                if approval_decision_id is None
                                else (("approval_decision_id", str(approval_decision_id)),)
                            ),
                            *(("reason_code", item) for item in reasons),
                        }
                    )
                ),
                occurred_at=occurred_at,
            )
            return AuthorizationDecision(
                principal_id=principal_id,
                status=status,
                roles=roles,
                permission=permission,
                allowed=allowed,
                reason_codes=tuple(sorted(reasons)),
            )

        return self._factory.run_transaction(operation)

    def audit_denied_operation(
        self,
        *,
        principal_id: ArtifactId,
        resource_reference: ValidationArtifactReference,
        reason_code: str,
        occurred_at: datetime,
    ) -> None:
        def operation(connection: Any) -> None:
            _principal_status(connection, principal_id)
            self._audit(
                connection,
                event_kind="OPERATOR_INVOCATION_DENIED",
                actor=principal_id,
                target_kind=resource_reference.artifact_kind,
                target_id=resource_reference.artifact_id,
                details=(
                    ("allowed", "false"),
                    ("reason_code", reason_code),
                    ("resource_hash", resource_reference.content_hash),
                ),
                occurred_at=occurred_at,
            )

        self._factory.run_transaction(operation)

    def request_approval(
        self,
        *,
        requester: ArtifactId,
        action_kind: ApprovalAction,
        resource_reference: ValidationArtifactReference,
        reason: str,
        requested_at: datetime,
        idempotency_key: str,
    ) -> SecurityApproval:
        limitations = tuple(sorted({*_LIMITATIONS, "ENGINEERING_APPROVAL_ONLY"}))
        values = {
            "schema_version": "security-approval/v1",
            "action_kind": action_kind.value,
            "resource_reference": resource_reference.to_canonical_dict(),
            "requested_by": str(requester),
            "reason": reason,
            "requested_at": timestamp(requested_at),
            "limitations": list(limitations),
        }
        approval_id, approval_hash = content_identity("security-approval", values)
        approval = SecurityApproval(
            approval_id,
            approval_hash,
            action_kind,
            resource_reference,
            requester,
            reason,
            requested_at,
            limitations,
        )
        digest = canonical_hash(
            {"operation": "REQUEST_APPROVAL", "approval": approval.to_canonical_dict()}
        )

        def operation(connection: Any) -> str:
            existing = _existing_command(connection, idempotency_key, digest)
            if existing is not None:
                return existing
            _require_permission(connection, requester, _ACTION_PERMISSION[action_kind])
            connection.execute(
                """
                INSERT INTO security_approval(
                    approval_id, approval_hash, action_kind, resource_kind,
                    resource_id, resource_hash, requested_by, reason,
                    payload_json, requested_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(approval.approval_id),
                    approval.approval_hash,
                    approval.action_kind.value,
                    approval.resource_reference.artifact_kind,
                    str(approval.resource_reference.artifact_id),
                    approval.resource_reference.content_hash,
                    str(approval.requested_by),
                    approval.reason,
                    Jsonb(approval.to_canonical_dict()),
                    approval.requested_at,
                ),
            )
            self._audit(
                connection,
                event_kind="APPROVAL_REQUESTED",
                actor=requester,
                target_kind="SECURITY_APPROVAL",
                target_id=approval.approval_id,
                details=(("action_kind", action_kind.value),),
                occurred_at=requested_at,
            )
            _record_command(
                connection,
                idempotency_key,
                digest,
                "SECURITY_APPROVAL",
                approval.approval_id,
                requested_at,
            )
            return str(approval.approval_id)

        stored_id = ArtifactId(self._factory.run_transaction(operation))
        return self.get_approval(stored_id)

    def decide_approval(
        self,
        *,
        approval_id: ArtifactId,
        approver: ArtifactId,
        decision: ApprovalDecisionKind,
        reason: str,
        decided_at: datetime,
        idempotency_key: str,
    ) -> SecurityApprovalDecision:
        approval = self.get_approval(approval_id)
        limitations = tuple(
            sorted({*_LIMITATIONS, "ENGINEERING_APPROVAL_ONLY", "PRODUCTION_AUTHORIZED_FALSE"})
        )
        approval_reference = ValidationArtifactReference(
            "SECURITY_APPROVAL", approval.approval_id, approval.approval_hash
        )
        values = {
            "schema_version": "security-approval-decision/v1",
            "approval_reference": approval_reference.to_canonical_dict(),
            "decision": decision.value,
            "decided_by": str(approver),
            "reason": reason,
            "decided_at": timestamp(decided_at),
            "production_authorized": False,
            "limitations": list(limitations),
        }
        decision_id, decision_hash = content_identity(
            "security-approval-decision", values
        )
        result = SecurityApprovalDecision(
            decision_id,
            decision_hash,
            approval_reference,
            decision,
            approver,
            reason,
            decided_at,
            limitations,
        )
        digest = canonical_hash(
            {"operation": "DECIDE_APPROVAL", "decision": result.to_canonical_dict()}
        )

        def operation(connection: Any) -> str:
            existing = _existing_command(connection, idempotency_key, digest)
            if existing is not None:
                return existing
            _require_permission(
                connection,
                approver,
                SecurityPermission.APPROVE_ENGINEERING_CHANGE,
            )
            locked = connection.execute(
                """
                SELECT requested_by FROM security_approval
                WHERE approval_id = %s FOR UPDATE
                """,
                (str(approval_id),),
            ).fetchone()
            if locked is None:
                raise KeyError(str(approval_id))
            if str(locked[0]) == str(approver):
                raise PermissionError("Approval requires requester/approver separation")
            connection.execute(
                """
                INSERT INTO security_approval_decision(
                    decision_id, decision_hash, approval_id, decision,
                    decided_by, reason, production_authorized,
                    payload_json, decided_at
                ) VALUES (%s, %s, %s, %s, %s, %s, false, %s, %s)
                """,
                (
                    str(result.decision_id),
                    result.decision_hash,
                    str(approval_id),
                    result.decision.value,
                    str(approver),
                    result.reason,
                    Jsonb(result.to_canonical_dict()),
                    result.decided_at,
                ),
            )
            self._audit(
                connection,
                event_kind="APPROVAL_DECIDED",
                actor=approver,
                target_kind="SECURITY_APPROVAL",
                target_id=approval_id,
                details=(("decision", decision.value),),
                occurred_at=decided_at,
            )
            _record_command(
                connection,
                idempotency_key,
                digest,
                "SECURITY_APPROVAL_DECISION",
                result.decision_id,
                decided_at,
            )
            return str(result.decision_id)

        stored_id = ArtifactId(self._factory.run_transaction(operation))
        return self.get_approval_decision(stored_id)

    def get_principal(self, principal_id: ArtifactId) -> SecurityPrincipal:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT payload_json FROM security_principal WHERE principal_id = %s",
                (str(principal_id),),
            ).fetchone()
        if row is None or not isinstance(row[0], dict):
            raise KeyError(str(principal_id))
        return SecurityPrincipal.from_canonical_dict(row[0])

    def get_role_event(self, event_id: ArtifactId) -> SecurityRoleEvent:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT event_id, event_hash, principal_id, role, event_kind,
                       sequence, previous_event_id, changed_by, reason, occurred_at
                FROM security_role_event WHERE event_id = %s
                """,
                (str(event_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(event_id))
        return _role_event_from_row(row)

    def get_approval(self, approval_id: ArtifactId) -> SecurityApproval:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT payload_json FROM security_approval WHERE approval_id = %s",
                (str(approval_id),),
            ).fetchone()
        if row is None or not isinstance(row[0], dict):
            raise KeyError(str(approval_id))
        return SecurityApproval.from_canonical_dict(row[0])

    def get_approval_decision(
        self, decision_id: ArtifactId
    ) -> SecurityApprovalDecision:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM security_approval_decision
                WHERE decision_id = %s
                """,
                (str(decision_id),),
            ).fetchone()
        if row is None or not isinstance(row[0], dict):
            raise KeyError(str(decision_id))
        return SecurityApprovalDecision.from_canonical_dict(row[0])

    def audit_events(
        self, *, reader: ArtifactId
    ) -> tuple[dict[str, Any], ...]:
        decision = self.authorization(reader, SecurityPermission.READ_SECURITY_AUDIT)
        if not decision.allowed:
            raise PermissionError("Security audit permission denied")
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM security_audit_event
                ORDER BY occurred_at, audit_id
                """
            ).fetchall()
        if any(not isinstance(row[0], dict) for row in rows):
            raise ValueError("Security Audit durable payload is invalid")
        return tuple(dict(row[0]) for row in rows)

    @staticmethod
    def _insert_principal(connection: Any, principal: SecurityPrincipal) -> None:
        connection.execute(
            """
            INSERT INTO security_principal(
                principal_id, principal_hash, external_subject,
                display_name, payload_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                str(principal.principal_id),
                principal.principal_hash,
                principal.external_subject,
                principal.display_name,
                Jsonb(principal.to_canonical_dict()),
                principal.created_at,
            ),
        )

    def _insert_status(
        self,
        connection: Any,
        *,
        principal_id: ArtifactId,
        status: PrincipalStatus,
        actor: ArtifactId,
        reason: str,
        occurred_at: datetime,
    ) -> ArtifactId:
        connection.execute(
            "SELECT principal_id FROM security_principal WHERE principal_id = %s FOR UPDATE",
            (str(principal_id),),
        )
        latest = connection.execute(
            """
            SELECT sequence, status FROM security_principal_status_event
            WHERE principal_id = %s ORDER BY sequence DESC LIMIT 1
            """,
            (str(principal_id),),
        ).fetchone()
        if latest is not None and str(latest[1]) == status.value:
            raise ValueError("Security Principal already has requested status")
        sequence = 1 if latest is None else int(latest[0]) + 1
        payload = {
            "principal_id": str(principal_id),
            "sequence": sequence,
            "status": status.value,
            "changed_by": str(actor),
            "reason": reason,
            "occurred_at": timestamp(occurred_at),
        }
        event_id, event_hash = content_identity("security-principal-status", payload)
        connection.execute(
            """
            INSERT INTO security_principal_status_event(
                event_id, event_hash, principal_id, sequence, status,
                changed_by, reason, payload_json, occurred_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(event_id),
                event_hash,
                str(principal_id),
                sequence,
                status.value,
                str(actor),
                reason,
                Jsonb(payload),
                occurred_at,
            ),
        )
        return event_id

    def _insert_role_event(
        self,
        connection: Any,
        *,
        principal_id: ArtifactId,
        role: SecurityRole,
        event_kind: RoleEventKind,
        actor: ArtifactId,
        reason: str,
        occurred_at: datetime,
    ) -> SecurityRoleEvent:
        connection.execute(
            "SELECT principal_id FROM security_principal WHERE principal_id = %s FOR UPDATE",
            (str(principal_id),),
        )
        latest = connection.execute(
            """
            SELECT event_id, event_kind, sequence FROM security_role_event
            WHERE principal_id = %s AND role = %s
            ORDER BY sequence DESC LIMIT 1
            """,
            (str(principal_id), role.value),
        ).fetchone()
        if latest is None and event_kind is RoleEventKind.REVOKED:
            raise ValueError("Security Role cannot be revoked before grant")
        if latest is not None and str(latest[1]) == event_kind.value:
            raise ValueError("Security Role already has requested state")
        sequence = 1 if latest is None else int(latest[2]) + 1
        previous = None if latest is None else ArtifactId(str(latest[0]))
        payload = {
            "principal_id": str(principal_id),
            "role": role.value,
            "event_kind": event_kind.value,
            "sequence": sequence,
            "previous_event_id": None if previous is None else str(previous),
            "changed_by": str(actor),
            "reason": reason,
            "occurred_at": timestamp(occurred_at),
        }
        event_id, event_hash = content_identity("security-role-event", payload)
        connection.execute(
            """
            INSERT INTO security_role_event(
                event_id, event_hash, principal_id, role, event_kind,
                sequence, previous_event_id, changed_by, reason,
                payload_json, occurred_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(event_id),
                event_hash,
                str(principal_id),
                role.value,
                event_kind.value,
                sequence,
                None if previous is None else str(previous),
                str(actor),
                reason,
                Jsonb(payload),
                occurred_at,
            ),
        )
        return SecurityRoleEvent(
            event_id,
            event_hash,
            principal_id,
            role,
            event_kind,
            sequence,
            previous,
            actor,
            reason,
            occurred_at,
        )

    def _audit(
        self,
        connection: Any,
        *,
        event_kind: str,
        actor: ArtifactId,
        target_kind: str,
        target_id: ArtifactId,
        details: tuple[tuple[str, str], ...],
        occurred_at: datetime,
    ) -> None:
        payload = {
            "schema_version": "security-audit-event/v1",
            "event_kind": event_kind,
            "actor_principal_id": str(actor),
            "target_kind": target_kind,
            "target_id": str(target_id),
            "details": [list(item) for item in sorted(set(details))],
            "occurred_at": timestamp(occurred_at),
            "production_authorized": False,
        }
        audit_id, audit_hash = content_identity("security-audit-event", payload)
        connection.execute(
            """
            INSERT INTO security_audit_event(
                audit_id, audit_hash, event_kind, actor_principal_id,
                target_kind, target_id, payload_json, occurred_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (audit_id) DO NOTHING
            """,
            (
                str(audit_id),
                audit_hash,
                event_kind,
                str(actor),
                target_kind,
                str(target_id),
                Jsonb(payload),
                occurred_at,
            ),
        )


def _principal_status(connection: Any, principal_id: ArtifactId) -> PrincipalStatus:
    row = connection.execute(
        """
        SELECT status FROM security_principal_status_event
        WHERE principal_id = %s ORDER BY sequence DESC LIMIT 1
        """,
        (str(principal_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(principal_id))
    return PrincipalStatus(str(row[0]))


def _lock_security_governance(connection: Any) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(%s)",
        (_SECURITY_GOVERNANCE_ADVISORY_LOCK,),
    )


def _current_roles(
    connection: Any, principal_id: ArtifactId
) -> tuple[SecurityRole, ...]:
    rows = connection.execute(
        """
        SELECT DISTINCT ON (role) role, event_kind
        FROM security_role_event WHERE principal_id = %s
        ORDER BY role, sequence DESC
        """,
        (str(principal_id),),
    ).fetchall()
    return tuple(
        sorted(
            (
                SecurityRole(str(row[0]))
                for row in rows
                if str(row[1]) == RoleEventKind.GRANTED.value
            ),
            key=lambda item: item.value,
        )
    )


def _validate_operation_approval(
    connection: Any,
    *,
    principal_id: ArtifactId,
    permission: SecurityPermission,
    resource_reference: ValidationArtifactReference,
    approval_decision_id: ArtifactId | None,
) -> str | None:
    if approval_decision_id is None:
        return "INDEPENDENT_ENGINEERING_APPROVAL_REQUIRED"
    expected_action = {
        SecurityPermission.RUN_SHADOW: ApprovalAction.SHADOW_OPERATION,
        SecurityPermission.RECOVER_RUNTIME: ApprovalAction.RECOVERY_OPERATION,
    }.get(permission)
    if expected_action is None:
        return "APPROVAL_ACTION_NOT_DEFINED"
    row = connection.execute(
        """
        SELECT decision.decision, decision.decided_by,
               approval.action_kind, approval.resource_kind,
               approval.resource_id, approval.resource_hash,
               approval.requested_by
        FROM security_approval_decision AS decision
        JOIN security_approval AS approval
          ON approval.approval_id = decision.approval_id
        WHERE decision.decision_id = %s
        """,
        (str(approval_decision_id),),
    ).fetchone()
    if row is None:
        return "APPROVAL_DECISION_NOT_FOUND"
    if str(row[0]) != ApprovalDecisionKind.APPROVED.value:
        return "APPROVAL_NOT_APPROVED"
    if str(row[1]) == str(principal_id) or str(row[6]) != str(principal_id):
        return "APPROVAL_PRINCIPAL_SEPARATION_MISMATCH"
    if str(row[2]) != expected_action.value:
        return "APPROVAL_ACTION_MISMATCH"
    if (
        str(row[3]) != resource_reference.artifact_kind
        or str(row[4]) != str(resource_reference.artifact_id)
        or str(row[5]) != resource_reference.content_hash
    ):
        return "APPROVAL_RESOURCE_MISMATCH"
    return None


def _active_admin_count(connection: Any) -> int:
    row = connection.execute(
        """
        WITH latest_status AS (
            SELECT DISTINCT ON (principal_id) principal_id, status
            FROM security_principal_status_event
            ORDER BY principal_id, sequence DESC
        ), latest_admin_role AS (
            SELECT DISTINCT ON (principal_id) principal_id, event_kind
            FROM security_role_event
            WHERE role = 'ADMIN'
            ORDER BY principal_id, sequence DESC
        )
        SELECT count(*)
        FROM latest_status AS status
        JOIN latest_admin_role AS role USING (principal_id)
        WHERE status.status = 'ACTIVE' AND role.event_kind = 'GRANTED'
        """
    ).fetchone()
    return 0 if row is None else int(row[0])


def _require_permission(
    connection: Any,
    principal_id: ArtifactId,
    permission: SecurityPermission,
) -> None:
    status = _principal_status(connection, principal_id)
    roles = _current_roles(connection, principal_id)
    if status is not PrincipalStatus.ACTIVE or not any(
        permission in _ROLE_PERMISSIONS[role] for role in roles
    ):
        raise PermissionError(f"Security permission denied: {permission.value}")


def _existing_command(
    connection: Any, idempotency_key: str, command_hash: str
) -> str | None:
    if not idempotency_key.strip():
        raise ValueError("Security idempotency key must be non-empty")
    row = connection.execute(
        """
        SELECT command_hash, result_id FROM security_governance_command
        WHERE idempotency_key = %s FOR UPDATE
        """,
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    if str(row[0]) != command_hash:
        raise ValueError("Security Governance idempotency conflict")
    return str(row[1])


def _record_command(
    connection: Any,
    idempotency_key: str,
    command_hash: str,
    result_kind: str,
    result_id: ArtifactId,
    created_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO security_governance_command(
            idempotency_key, command_hash, result_kind, result_id, created_at
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (
            idempotency_key,
            command_hash,
            result_kind,
            str(result_id),
            created_at,
        ),
    )


def _role_event_from_row(row: Any) -> SecurityRoleEvent:
    return SecurityRoleEvent(
        event_id=ArtifactId(str(row[0])),
        event_hash=str(row[1]),
        principal_id=ArtifactId(str(row[2])),
        role=SecurityRole(str(row[3])),
        event_kind=RoleEventKind(str(row[4])),
        sequence=int(row[5]),
        previous_event_id=None if row[6] is None else ArtifactId(str(row[6])),
        changed_by=ArtifactId(str(row[7])),
        reason=str(row[8]),
        occurred_at=row[9],
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Security Governance payload must contain objects")
    return value


def _sequence(value: Any) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Security Governance payload must contain arrays")
    return tuple(value)


__all__ = [
    "ApprovalAction",
    "ApprovalDecisionKind",
    "AuthorizationDecision",
    "PostgresAccessGovernance",
    "PrincipalStatus",
    "RoleEventKind",
    "SecurityPermission",
    "SecurityPrincipal",
    "SecurityRole",
]
