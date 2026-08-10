"""Append-only PostgreSQL index for prospective-evidence attestations."""

from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.application.shadow_research.attestation import (
    ProspectiveEvidenceAttestation,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class ProspectiveAttestationConflict(ValueError):
    """Attestation identity or owner lineage conflict."""


class ProspectiveAttestationIntegrityError(ValueError):
    """Stored attestation failed canonical restoration."""


class PostgresProspectiveAttestationRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def record(self, attestation: ProspectiveEvidenceAttestation) -> ProspectiveEvidenceAttestation:
        def operation(connection: Any) -> None:
            decision = connection.execute(
                "SELECT decision_hash FROM shadow_research_decision WHERE decision_id = %s",
                (str(attestation.shadow_decision.artifact_id),),
            ).fetchone()
            outcome = connection.execute(
                "SELECT settlement_hash, shadow_decision_id FROM prospective_outcome_settlement WHERE settlement_id = %s",
                (str(attestation.outcome_settlement.artifact_id),),
            ).fetchone()
            if decision is None or str(decision[0]) != attestation.shadow_decision.content_hash:
                raise ProspectiveAttestationConflict("Attestation Decision lineage mismatch")
            if outcome is None or (
                str(outcome[0]) != attestation.outcome_settlement.content_hash
                or str(outcome[1]) != str(attestation.shadow_decision.artifact_id)
            ):
                raise ProspectiveAttestationConflict("Attestation Outcome lineage mismatch")
            if attestation.runtime_authority_evidence is None:
                raise ProspectiveAttestationConflict("Attestation Runtime Authority evidence missing")
            runtime_authority = connection.execute(
                """
                SELECT evidence_hash, run_id, tick_id, clock_mode,
                       runtime_origin, code_revision
                FROM continuous_runtime_authority_evidence
                WHERE evidence_id = %s
                """,
                (str(attestation.runtime_authority_evidence.artifact_id),),
            ).fetchone()
            if runtime_authority is None or (
                str(runtime_authority[0]) != attestation.runtime_authority_evidence.content_hash
                or str(runtime_authority[1]) != str(attestation.run_id)
                or str(runtime_authority[2]) != str(attestation.tick_id)
                or str(runtime_authority[3]) != attestation.clock_mode.value
                or str(runtime_authority[4]) != attestation.runtime_origin.value
                or str(runtime_authority[5]) != attestation.code_revision
            ):
                raise ProspectiveAttestationConflict("Attestation Runtime Authority lineage mismatch")
            connection.execute(
                """
                INSERT INTO prospective_evidence_attestation(
                    attestation_id, attestation_hash, shadow_decision_id,
                    outcome_settlement_id, run_id, tick_id, status, clock_mode,
                    runtime_origin, prospective_proven, decision_frozen_at,
                    outcome_available_at, runtime_authority_evidence_id,
                    payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, false, %s, %s, %s, %s, %s)
                ON CONFLICT (attestation_id) DO NOTHING
                """,
                (
                    str(attestation.attestation_id),
                    attestation.attestation_hash,
                    str(attestation.shadow_decision.artifact_id),
                    str(attestation.outcome_settlement.artifact_id),
                    str(attestation.run_id),
                    str(attestation.tick_id),
                    attestation.status.value,
                    attestation.clock_mode.value,
                    attestation.runtime_origin.value,
                    attestation.decision_frozen_at,
                    attestation.outcome_available_at,
                    (None if attestation.runtime_authority_evidence is None else str(attestation.runtime_authority_evidence.artifact_id)),
                    Jsonb(attestation.to_canonical_dict()),
                    attestation.created_at,
                ),
            )
            stored = connection.execute(
                "SELECT attestation_hash FROM prospective_evidence_attestation WHERE attestation_id = %s",
                (str(attestation.attestation_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != attestation.attestation_hash:
                raise ProspectiveAttestationConflict("Attestation identity conflict")

        self._factory.run_transaction(operation)
        return self.get(attestation.attestation_id)

    def get(self, attestation_id: ArtifactId) -> ProspectiveEvidenceAttestation:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT payload_json, attestation_hash, prospective_proven FROM prospective_evidence_attestation WHERE attestation_id = %s",
                (str(attestation_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(attestation_id))
        if bool(row[2]):
            raise ProspectiveAttestationIntegrityError("Attestation illegally grants prospective PASS")
        try:
            value = ProspectiveEvidenceAttestation.from_canonical_dict(_object(row[0]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProspectiveAttestationIntegrityError("Attestation restoration failed") from exc
        if value.attestation_hash != str(row[1]) or value.prospective_proven:
            raise ProspectiveAttestationIntegrityError("Attestation authority drift")
        return value


def _object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ProspectiveAttestationIntegrityError("Attestation payload is not an object")
    return value


__all__ = [
    "PostgresProspectiveAttestationRepository",
    "ProspectiveAttestationConflict",
    "ProspectiveAttestationIntegrityError",
]
