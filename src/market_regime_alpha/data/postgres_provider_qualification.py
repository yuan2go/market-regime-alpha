"""Owner-resolved Provider × Contract × Fact Kind qualification authority."""

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
from market_regime_alpha.data.pit_contracts import (
    PITFactKind,
    PITProviderEvidenceKind,
    PITSourceAuthorityStatus,
    PITSourceEvidenceLevel,
    ProviderQualificationPolicyV2,
)
from market_regime_alpha.data.pit_source_authority import PITSourceQualification
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.native_repository import (
    acquire_scope_lock,
)


class ProviderFactQualificationStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    INCOMPLETE = "INCOMPLETE"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class ProviderFactQualificationDecision:
    decision_id: ArtifactId
    decision_hash: str
    policy_reference: ValidationArtifactReference
    provider_id: str
    provider_contract: str
    fact_kind: PITFactKind
    status: ProviderFactQualificationStatus
    source_qualification_references: tuple[ValidationArtifactReference, ...]
    evidence_kinds: tuple[PITProviderEvidenceKind, ...]
    evidence_references: tuple[ValidationArtifactReference, ...]
    revision: int
    supersedes_decision_id: ArtifactId | None
    evaluated_at: datetime
    actor: str
    reason: str
    reason_codes: tuple[str, ...]
    schema_version: str = "provider-fact-qualification-decision/v1"

    def __post_init__(self) -> None:
        require_sha256("decision_hash", self.decision_hash)
        if self.schema_version != "provider-fact-qualification-decision/v1":
            raise ValueError("unsupported Provider Fact Qualification schema")
        if self.policy_reference.artifact_kind != "PROVIDER_QUALIFICATION_POLICY_V2":
            raise ValueError("Provider Fact decision requires Policy V2")
        if not self.provider_id.strip() or not self.provider_contract.strip():
            raise ValueError("Provider Fact decision scope must be non-empty")
        if self.revision <= 0 or (self.revision == 1) != (
            self.supersedes_decision_id is None
        ):
            raise ValueError("Provider Fact decision revision/supersession mismatch")
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("Provider Fact decision time must be timezone-aware")
        if not self.actor.strip() or not self.reason.strip():
            raise ValueError("Provider Fact decision actor/reason must be non-empty")
        if self.source_qualification_references != _ordered_references(
            self.source_qualification_references
        ):
            raise ValueError("Source Qualification references must be unique and sorted")
        if self.evidence_references != _ordered_references(self.evidence_references):
            raise ValueError("Provider evidence references must be unique and sorted")
        if self.evidence_kinds != tuple(
            sorted(set(self.evidence_kinds), key=lambda item: item.value)
        ):
            raise ValueError("Provider evidence kinds must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Provider Fact decision reasons must be unique and sorted")
        if self.status is ProviderFactQualificationStatus.QUALIFIED:
            if not self.source_qualification_references or self.reason_codes:
                raise ValueError("qualified Provider Fact requires source evidence and no rejection")
        elif not self.reason_codes:
            raise ValueError("non-qualified Provider Fact decision requires reasons")
        if canonical_hash(self.identity_payload()) != self.decision_hash:
            raise ValueError("Provider Fact decision hash mismatch")
        if self.decision_id != ArtifactId(
            f"provider-fact-qualification:{self.decision_hash[7:]}"
        ):
            raise ValueError("Provider Fact decision identity mismatch")

    @property
    def qualified(self) -> bool:
        return self.status is ProviderFactQualificationStatus.QUALIFIED

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_reference": self.policy_reference.to_canonical_dict(),
            "provider_id": self.provider_id,
            "provider_contract": self.provider_contract,
            "fact_kind": self.fact_kind.value,
            "status": self.status.value,
            "source_qualification_references": [
                item.to_canonical_dict()
                for item in self.source_qualification_references
            ],
            "evidence_kinds": [item.value for item in self.evidence_kinds],
            "evidence_references": [
                item.to_canonical_dict() for item in self.evidence_references
            ],
            "revision": self.revision,
            "supersedes_decision_id": (
                None
                if self.supersedes_decision_id is None
                else str(self.supersedes_decision_id)
            ),
            "evaluated_at": timestamp(self.evaluated_at),
            "actor": self.actor,
            "reason": self.reason,
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            "decision_hash": self.decision_hash,
            **self.identity_payload(),
        }

    @classmethod
    def create(cls, **values: Any) -> ProviderFactQualificationDecision:
        normalized = dict(values)
        normalized["source_qualification_references"] = _ordered_references(
            tuple(values["source_qualification_references"])
        )
        normalized["evidence_references"] = _ordered_references(
            tuple(values["evidence_references"])
        )
        normalized["evidence_kinds"] = tuple(
            sorted(set(values["evidence_kinds"]), key=lambda item: item.value)
        )
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        payload = _decision_payload(**normalized)
        decision_id, decision_hash = content_identity(
            "provider-fact-qualification", payload
        )
        return cls(decision_id, decision_hash, **normalized)

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> ProviderFactQualificationDecision:
        supersedes = value["supersedes_decision_id"]
        return cls(
            decision_id=ArtifactId(str(value["decision_id"])),
            decision_hash=str(value["decision_hash"]),
            policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["policy_reference"])
            ),
            provider_id=str(value["provider_id"]),
            provider_contract=str(value["provider_contract"]),
            fact_kind=PITFactKind(str(value["fact_kind"])),
            status=ProviderFactQualificationStatus(str(value["status"])),
            source_qualification_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(value["source_qualification_references"])
            ),
            evidence_kinds=tuple(
                PITProviderEvidenceKind(str(item))
                for item in _sequence(value["evidence_kinds"])
            ),
            evidence_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(value["evidence_references"])
            ),
            revision=int(value["revision"]),
            supersedes_decision_id=(
                None if supersedes is None else ArtifactId(str(supersedes))
            ),
            evaluated_at=datetime.fromisoformat(str(value["evaluated_at"])),
            actor=str(value["actor"]),
            reason=str(value["reason"]),
            reason_codes=tuple(str(item) for item in _sequence(value["reason_codes"])),
            schema_version=str(value["schema_version"]),
        )


class PostgresProviderFactQualificationAuthority:
    """Resolve C1 decisions from existing PostgreSQL PIT source owners."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def assess(
        self,
        *,
        policy: ProviderQualificationPolicyV2,
        provider_id: str,
        provider_contract: str,
        fact_kind: PITFactKind,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> ProviderFactQualificationDecision:
        command = {
            "policy_id": str(policy.policy_id),
            "policy_hash": policy.policy_hash,
            "provider_id": provider_id.casefold(),
            "provider_contract": provider_contract,
            "fact_kind": fact_kind.value,
            "actor": actor,
            "reason": reason,
        }
        command_hash = canonical_hash(command)

        def operation(connection: Any) -> ArtifactId:
            scope = f"{provider_id.casefold()}:{provider_contract}:{fact_kind.value}"
            acquire_scope_lock(
                connection,
                namespace="provider-fact-qualification",
                identity=scope,
            )
            duplicate = connection.execute(
                """
                SELECT command_hash, decision_id
                FROM provider_fact_qualification_command
                WHERE idempotency_key = %s
                """,
                (idempotency_key,),
            ).fetchone()
            if duplicate is not None:
                if str(duplicate[0]) != command_hash:
                    raise ValueError("Provider Fact qualification idempotency conflict")
                return ArtifactId(str(duplicate[1]))
            now = connection.execute(
                "SELECT date_trunc('second', clock_timestamp())"
            ).fetchone()[0]
            self._record_policy(connection, policy, recorded_at=now)
            latest_decision = _latest_decision(
                connection,
                provider_id=provider_id,
                provider_contract=provider_contract,
                fact_kind=fact_kind,
            )
            if latest_decision is not None and (
                latest_decision.status is ProviderFactQualificationStatus.REVOKED
            ):
                connection.execute(
                    """
                    INSERT INTO provider_fact_qualification_command(
                        idempotency_key, command_hash, decision_id, created_at
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        idempotency_key,
                        command_hash,
                        str(latest_decision.decision_id),
                        now,
                    ),
                )
                return latest_decision.decision_id
            source_qualifications = self._active_source_qualifications(
                connection,
                provider_id=provider_id,
                provider_contract=provider_contract,
                fact_kind=fact_kind,
                evaluated_at=now,
            )
            status, reasons = _resolve_status(
                policy=policy,
                provider_id=provider_id,
                provider_contract=provider_contract,
                fact_kind=fact_kind,
                source_qualifications=source_qualifications,
            )
            source_references = tuple(
                ValidationArtifactReference(
                    "PIT_SOURCE_QUALIFICATION",
                    item.qualification_id,
                    item.qualification_hash,
                )
                for item in source_qualifications
            )
            evidence = tuple(
                item
                for qualification in source_qualifications
                for item in qualification.provider_evidence
            )
            evidence_kinds = tuple(item.evidence_kind for item in evidence)
            evidence_references = tuple(
                ValidationArtifactReference(
                    "PIT_PROVIDER_EVIDENCE",
                    item.reference.artifact_id,
                    item.reference.content_hash,
                )
                for item in evidence
            )
            latest = connection.execute(
                """
                SELECT decision_id, revision
                FROM provider_fact_qualification_decision
                WHERE provider_id = %s AND provider_contract = %s
                  AND fact_kind = %s
                ORDER BY revision DESC
                LIMIT 1
                """,
                (provider_id.casefold(), provider_contract, fact_kind.value),
            ).fetchone()
            revision = 1 if latest is None else int(latest[1]) + 1
            supersedes = None if latest is None else ArtifactId(str(latest[0]))
            decision = ProviderFactQualificationDecision.create(
                policy_reference=ValidationArtifactReference(
                    "PROVIDER_QUALIFICATION_POLICY_V2",
                    policy.policy_id,
                    policy.policy_hash,
                ),
                provider_id=provider_id.casefold(),
                provider_contract=provider_contract,
                fact_kind=fact_kind,
                status=status,
                source_qualification_references=source_references,
                evidence_kinds=evidence_kinds,
                evidence_references=evidence_references,
                revision=revision,
                supersedes_decision_id=supersedes,
                evaluated_at=now,
                actor=actor,
                reason=reason,
                reason_codes=reasons,
            )
            connection.execute(
                """
                INSERT INTO provider_fact_qualification_decision(
                    decision_id, decision_hash, policy_id, provider_id,
                    provider_contract, fact_kind, status, revision,
                    supersedes_decision_id, payload_json, evaluated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(decision.decision_id),
                    decision.decision_hash,
                    str(policy.policy_id),
                    decision.provider_id,
                    provider_contract,
                    fact_kind.value,
                    status.value,
                    revision,
                    None if supersedes is None else str(supersedes),
                    Jsonb(decision.to_canonical_dict()),
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO provider_fact_qualification_command(
                    idempotency_key, command_hash, decision_id, created_at
                ) VALUES (%s, %s, %s, %s)
                """,
                (idempotency_key, command_hash, str(decision.decision_id), now),
            )
            return decision.decision_id

        decision_id = self._factory.run_transaction(operation)
        return self.get(decision_id)

    def revoke(
        self,
        *,
        provider_id: str,
        provider_contract: str,
        fact_kind: PITFactKind,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> ProviderFactQualificationDecision:
        command = {
            "action": "REVOKE_PROVIDER_FACT",
            "provider_id": provider_id.casefold(),
            "provider_contract": provider_contract,
            "fact_kind": fact_kind.value,
            "actor": actor,
            "reason": reason,
        }
        command_hash = canonical_hash(command)

        def operation(connection: Any) -> ArtifactId:
            scope = f"{provider_id.casefold()}:{provider_contract}:{fact_kind.value}"
            acquire_scope_lock(
                connection,
                namespace="provider-fact-qualification",
                identity=scope,
            )
            duplicate = connection.execute(
                """
                SELECT command_hash, decision_id
                FROM provider_fact_qualification_command
                WHERE idempotency_key = %s
                """,
                (idempotency_key,),
            ).fetchone()
            if duplicate is not None:
                if str(duplicate[0]) != command_hash:
                    raise ValueError("Provider Fact qualification idempotency conflict")
                return ArtifactId(str(duplicate[1]))
            previous = _latest_decision(
                connection,
                provider_id=provider_id,
                provider_contract=provider_contract,
                fact_kind=fact_kind,
            )
            if previous is None:
                raise ValueError("Provider Fact cannot be revoked before assessment")
            now = connection.execute(
                "SELECT date_trunc('second', clock_timestamp())"
            ).fetchone()[0]
            if previous.status is ProviderFactQualificationStatus.REVOKED:
                decision = previous
            else:
                decision = ProviderFactQualificationDecision.create(
                    policy_reference=previous.policy_reference,
                    provider_id=previous.provider_id,
                    provider_contract=previous.provider_contract,
                    fact_kind=previous.fact_kind,
                    status=ProviderFactQualificationStatus.REVOKED,
                    source_qualification_references=(
                        previous.source_qualification_references
                    ),
                    evidence_kinds=previous.evidence_kinds,
                    evidence_references=previous.evidence_references,
                    revision=previous.revision + 1,
                    supersedes_decision_id=previous.decision_id,
                    evaluated_at=now,
                    actor=actor,
                    reason=reason,
                    reason_codes=("OPERATOR_REVOKED",),
                )
                connection.execute(
                    """
                    INSERT INTO provider_fact_qualification_decision(
                        decision_id, decision_hash, policy_id, provider_id,
                        provider_contract, fact_kind, status, revision,
                        supersedes_decision_id, payload_json, evaluated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(decision.decision_id),
                        decision.decision_hash,
                        str(decision.policy_reference.artifact_id),
                        decision.provider_id,
                        decision.provider_contract,
                        decision.fact_kind.value,
                        decision.status.value,
                        decision.revision,
                        str(previous.decision_id),
                        Jsonb(decision.to_canonical_dict()),
                        now,
                    ),
                )
            connection.execute(
                """
                INSERT INTO provider_fact_qualification_command(
                    idempotency_key, command_hash, decision_id, created_at
                ) VALUES (%s, %s, %s, %s)
                """,
                (idempotency_key, command_hash, str(decision.decision_id), now),
            )
            return decision.decision_id

        decision_id = self._factory.run_transaction(operation)
        return self.get(decision_id)

    def get(self, decision_id: ArtifactId) -> ProviderFactQualificationDecision:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, decision_hash, policy_id,
                       provider_id, provider_contract, fact_kind,
                       status, revision, supersedes_decision_id
                FROM provider_fact_qualification_decision
                WHERE decision_id = %s
                """,
                (str(decision_id),),
            ).fetchone()
        if row is None or not isinstance(row[0], Mapping):
            raise KeyError(str(decision_id))
        decision = ProviderFactQualificationDecision.from_canonical_dict(row[0])
        if (
            decision.decision_hash != str(row[1])
            or str(decision.policy_reference.artifact_id) != str(row[2])
            or decision.provider_id != str(row[3])
            or decision.provider_contract != str(row[4])
            or decision.fact_kind.value != str(row[5])
            or decision.status.value != str(row[6])
            or decision.revision != int(row[7])
            or (
                None
                if decision.supersedes_decision_id is None
                else str(decision.supersedes_decision_id)
            )
            != (None if row[8] is None else str(row[8]))
        ):
            raise ValueError("Provider Fact decision storage hash mismatch")
        return decision

    @staticmethod
    def _record_policy(
        connection: Any,
        policy: ProviderQualificationPolicyV2,
        *,
        recorded_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO provider_fact_qualification_policy(
                policy_id, policy_hash, policy_json, created_at
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (policy_id) DO NOTHING
            """,
            (
                str(policy.policy_id),
                policy.policy_hash,
                Jsonb(policy.to_canonical_dict()),
                recorded_at,
            ),
        )
        row = connection.execute(
            """
            SELECT policy_hash, policy_json
            FROM provider_fact_qualification_policy
            WHERE policy_id = %s
            """,
            (str(policy.policy_id),),
        ).fetchone()
        if row is None or (
            str(row[0]) != policy.policy_hash
            or row[1] != policy.to_canonical_dict()
        ):
            raise ValueError("Provider Qualification Policy identity conflict")

    @staticmethod
    def _active_source_qualifications(
        connection: Any,
        *,
        provider_id: str,
        provider_contract: str,
        fact_kind: PITFactKind,
        evaluated_at: datetime,
    ) -> tuple[PITSourceQualification, ...]:
        rows = connection.execute(
            """
            SELECT current.payload_json
            FROM pit_source_qualification AS current
            WHERE lower(current.provider_id) = %s
              AND current.provider_contract = %s
              AND %s = ANY(current.qualified_fact_kinds)
              AND current.effective_at <= %s
              AND current.recorded_at <= %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM pit_source_qualification AS later
                  WHERE later.supersedes_qualification_id = current.qualification_id
                    AND later.effective_at <= %s
                    AND later.recorded_at <= %s
              )
            ORDER BY current.source_manifest_id, current.qualification_id
            """,
            (
                provider_id.casefold(),
                provider_contract,
                fact_kind.value,
                evaluated_at,
                evaluated_at,
                evaluated_at,
                evaluated_at,
            ),
        ).fetchall()
        return tuple(
            PITSourceQualification.from_canonical_dict(_mapping(row[0]))
            for row in rows
        )


def _latest_decision(
    connection: Any,
    *,
    provider_id: str,
    provider_contract: str,
    fact_kind: PITFactKind,
) -> ProviderFactQualificationDecision | None:
    row = connection.execute(
        """
        SELECT decision_id, decision_hash, payload_json,
               provider_id, provider_contract, fact_kind,
               status, revision
        FROM provider_fact_qualification_decision
        WHERE provider_id = %s AND provider_contract = %s
          AND fact_kind = %s
        ORDER BY revision DESC
        LIMIT 1
        """,
        (provider_id.casefold(), provider_contract, fact_kind.value),
    ).fetchone()
    if row is None or not isinstance(row[2], Mapping):
        return None
    decision = ProviderFactQualificationDecision.from_canonical_dict(row[2])
    if (
        decision.decision_id != ArtifactId(str(row[0]))
        or decision.decision_hash != str(row[1])
        or decision.provider_id != str(row[3])
        or decision.provider_contract != str(row[4])
        or decision.fact_kind.value != str(row[5])
        or decision.status.value != str(row[6])
        or decision.revision != int(row[7])
    ):
        raise ValueError("Provider Fact latest decision owner mismatch")
    return decision


def _resolve_status(
    *,
    policy: ProviderQualificationPolicyV2,
    provider_id: str,
    provider_contract: str,
    fact_kind: PITFactKind,
    source_qualifications: tuple[PITSourceQualification, ...],
) -> tuple[ProviderFactQualificationStatus, tuple[str, ...]]:
    maximum = policy.maximum_level(
        provider_id,
        provider_contract=provider_contract,
        fact_kind=fact_kind,
    )
    if maximum is not PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER:
        return ProviderFactQualificationStatus.REJECTED, (
            "FORMAL_PROVIDER_EVIDENCE_CEILING_NOT_MET",
        )
    if not source_qualifications:
        return ProviderFactQualificationStatus.INCOMPLETE, (
            "ACTIVE_SOURCE_QUALIFICATION_MISSING",
        )
    if any(
        item.status is PITSourceAuthorityStatus.SUSPENDED
        for item in source_qualifications
    ):
        return ProviderFactQualificationStatus.SUSPENDED, (
            "SOURCE_QUALIFICATION_SUSPENDED",
        )
    reasons: set[str] = set()
    if any(
        item.evidence_level is not PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER
        for item in source_qualifications
    ):
        reasons.add("FORMAL_PROVIDER_EVIDENCE_LEVEL_MISSING")
    if any(fact_kind not in item.qualified_fact_kinds for item in source_qualifications):
        reasons.add("FACT_KIND_NOT_QUALIFIED")
    for item in source_qualifications:
        kinds = {evidence.evidence_kind for evidence in item.provider_evidence}
        missing = set(policy.formal_required_evidence).difference(kinds)
        reasons.update(f"PROVIDER_EVIDENCE_MISSING_{kind.value}" for kind in missing)
    if reasons:
        return ProviderFactQualificationStatus.INCOMPLETE, tuple(sorted(reasons))
    return ProviderFactQualificationStatus.QUALIFIED, ()


def _decision_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "provider-fact-qualification-decision/v1",
        "policy_reference": values["policy_reference"].to_canonical_dict(),
        "provider_id": values["provider_id"],
        "provider_contract": values["provider_contract"],
        "fact_kind": values["fact_kind"].value,
        "status": values["status"].value,
        "source_qualification_references": [
            item.to_canonical_dict()
            for item in values["source_qualification_references"]
        ],
        "evidence_kinds": [item.value for item in values["evidence_kinds"]],
        "evidence_references": [
            item.to_canonical_dict() for item in values["evidence_references"]
        ],
        "revision": values["revision"],
        "supersedes_decision_id": (
            None
            if values["supersedes_decision_id"] is None
            else str(values["supersedes_decision_id"])
        ),
        "evaluated_at": timestamp(values["evaluated_at"]),
        "actor": values["actor"],
        "reason": values["reason"],
        "reason_codes": list(values["reason_codes"]),
    }


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
        raise ValueError("Provider qualification payload is not an object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Provider qualification payload is not an array")
    return tuple(value)


__all__ = [
    "PostgresProviderFactQualificationAuthority",
    "ProviderFactQualificationDecision",
    "ProviderFactQualificationStatus",
]
