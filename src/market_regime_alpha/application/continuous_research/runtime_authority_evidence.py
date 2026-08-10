"""Durable clock/origin evidence owned by the Continuous Runtime invocation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.application.shadow_research.attestation import ClockMode, RuntimeOrigin
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash, require_sha256, require_text
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityEvidence:
    evidence_id: ArtifactId
    evidence_hash: str
    run_id: ArtifactId
    tick_id: ArtifactId
    clock_mode: ClockMode
    runtime_origin: RuntimeOrigin
    clock_source: str
    origin_source: str
    observed_at: datetime
    recorded_at: datetime
    code_revision: str
    schema_version: str = "runtime-authority-evidence/v1"

    @classmethod
    def create(
        cls,
        *,
        run_id: ArtifactId,
        tick_id: ArtifactId,
        clock_mode: ClockMode,
        runtime_origin: RuntimeOrigin,
        clock_source: str,
        origin_source: str,
        observed_at: datetime,
        recorded_at: datetime,
        code_revision: str,
    ) -> RuntimeAuthorityEvidence:
        require_text("clock_source", clock_source)
        require_text("origin_source", origin_source)
        require_text("code_revision", code_revision)
        if recorded_at < observed_at:
            raise ValueError("Runtime Authority evidence recorded before observation")
        payload = _payload(
            run_id, tick_id, clock_mode, runtime_origin, clock_source, origin_source, observed_at, recorded_at, code_revision
        )
        digest = canonical_hash(payload)
        return cls(
            ArtifactId(f"runtime-authority-evidence:{digest[7:]}"),
            digest,
            run_id,
            tick_id,
            clock_mode,
            runtime_origin,
            clock_source,
            origin_source,
            observed_at,
            recorded_at,
            code_revision,
        )

    def __post_init__(self) -> None:
        require_sha256("evidence_hash", self.evidence_hash)
        if canonical_hash(self.identity_payload()) != self.evidence_hash:
            raise ValueError("Runtime Authority evidence hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _payload(
            self.run_id,
            self.tick_id,
            self.clock_mode,
            self.runtime_origin,
            self.clock_source,
            self.origin_source,
            self.observed_at,
            self.recorded_at,
            self.code_revision,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"evidence_id": str(self.evidence_id), "evidence_hash": self.evidence_hash, **self.identity_payload()}


class PostgresRuntimeAuthorityEvidenceRepository:
    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory

    def record(self, evidence: RuntimeAuthorityEvidence) -> RuntimeAuthorityEvidence:
        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO continuous_runtime_authority_evidence(
                    evidence_id, evidence_hash, run_id, tick_id, clock_mode,
                    runtime_origin, clock_source, origin_source, observed_at,
                    recorded_at, code_revision, payload_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, tick_id) DO NOTHING
                """,
                (
                    str(evidence.evidence_id),
                    evidence.evidence_hash,
                    str(evidence.run_id),
                    str(evidence.tick_id),
                    evidence.clock_mode.value,
                    evidence.runtime_origin.value,
                    evidence.clock_source,
                    evidence.origin_source,
                    evidence.observed_at,
                    evidence.recorded_at,
                    evidence.code_revision,
                    Jsonb(evidence.to_canonical_dict()),
                ),
            )
            row = connection.execute(
                "SELECT evidence_hash FROM continuous_runtime_authority_evidence WHERE run_id = %s AND tick_id = %s",
                (str(evidence.run_id), str(evidence.tick_id)),
            ).fetchone()
            if row is None or str(row[0]) != evidence.evidence_hash:
                raise ValueError("Runtime Authority evidence conflict")

        self._factory.run_transaction(operation)
        return self.get(evidence.run_id, evidence.tick_id)

    def get(self, run_id: ArtifactId, tick_id: ArtifactId) -> RuntimeAuthorityEvidence:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT payload_json FROM continuous_runtime_authority_evidence WHERE run_id = %s AND tick_id = %s",
                (str(run_id), str(tick_id)),
            ).fetchone()
        if row is None:
            raise KeyError(f"{run_id}/{tick_id}")
        value = row[0]
        if not isinstance(value, dict):
            raise ValueError("Runtime Authority evidence payload is invalid")
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


def _payload(
    run_id: ArtifactId,
    tick_id: ArtifactId,
    clock_mode: ClockMode,
    runtime_origin: RuntimeOrigin,
    clock_source: str,
    origin_source: str,
    observed_at: datetime,
    recorded_at: datetime,
    code_revision: str,
) -> dict[str, Any]:
    return {
        "schema_version": "runtime-authority-evidence/v1",
        "run_id": str(run_id),
        "tick_id": str(tick_id),
        "clock_mode": clock_mode.value,
        "runtime_origin": runtime_origin.value,
        "clock_source": clock_source,
        "origin_source": origin_source,
        "observed_at": canonical_datetime(observed_at),
        "recorded_at": canonical_datetime(recorded_at),
        "code_revision": code_revision,
    }
