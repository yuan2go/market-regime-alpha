"""PostgreSQL-only bitemporal fact, as-of query and Formal PIT evidence."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_artifact_authority import (
    CanonicalPITArtifactAuthorityResolver,
    PITArtifactAuthorityResolution,
    PITArtifactAuthorityResolver,
    PITArtifactAuthorityUnavailableError,
)
from market_regime_alpha.data.pit_authority import (
    FormalPITEvidenceArtifact,
    FormalPITValidationRequest,
    PITAsOfQuery,
    PITAsOfSnapshot,
    PITArtifactReference,
    PITFactKind,
    PITFactEvidenceMode,
    PITFactRevision,
    PITRequiredFact,
    PITSourceAuthorityStatus,
    PITSourceEvidenceLevel,
    PITSourceQualification,
    PITSelectedFactAuthority,
    PITValidationOutcome,
    RecordedPITFactRevision,
    ProviderQualificationPolicy,
    ProviderQualificationPolicyV2,
    formal_pit_request_rejection_codes,
    require_unique_required_fact_keys,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.native_repository import (
    NativePostgresRepository,
    PostgresConnection,
    acquire_scope_lock,
    aware_datetime,
)


Clock = Callable[[], datetime]


class PITAuthorityConflictError(RuntimeError):
    """A PIT CAS, identity or idempotency boundary was violated."""


class PITAuthorityIntegrityError(RuntimeError):
    """Stored PIT state cannot be reconstructed unambiguously."""


class PostgresPITAuthority(NativePostgresRepository):
    """Sole durable authority for formal temporal facts and validation."""

    def __init__(
        self,
        factory: Any,
        *,
        clock: Clock | None = None,
        artifact_resolver: PITArtifactAuthorityResolver | None = None,
        provider_policy: ProviderQualificationPolicy | ProviderQualificationPolicyV2 | None = None,
    ) -> None:
        super().__init__(factory)
        self._clock = clock
        self._artifact_resolver = artifact_resolver or CanonicalPITArtifactAuthorityResolver(
            artifact_roots={}
        )
        self._provider_policy = provider_policy or ProviderQualificationPolicy.default()

    def _authority_now(self) -> tuple[datetime, str]:
        if self._clock is not None:
            return _whole_second(self._clock()), "ENGINEERING_FIXTURE_CLOCK"
        with self._connect() as connection:
            row = connection.execute(
                "SELECT date_trunc('second', clock_timestamp()) AS authority_now"
            ).fetchone()
        if row is None:
            raise PITAuthorityIntegrityError("PostgreSQL clock returned no row")
        return (
            aware_datetime(row["authority_now"], label="PostgreSQL authority clock"),
            "POSTGRESQL_CLOCK",
        )

    def current_revision(self) -> int:
        with self._connect() as connection:
            return _current_revision(connection)

    def resolve(
        self,
        reference: PITArtifactReference,
        *,
        resolved_at: datetime,
    ) -> PITArtifactAuthorityResolution:
        """Resolve now, or reuse an earlier immutable strict-Reader receipt."""
        try:
            return self._artifact_resolver.resolve(
                reference,
                resolved_at=resolved_at,
            )
        except PITArtifactAuthorityUnavailableError as reader_error:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT payload_json FROM pit_artifact_authority_resolution "
                    "WHERE reference_kind = %s AND artifact_id = %s "
                    "AND artifact_hash = %s AND resolved_at <= %s "
                    "ORDER BY resolved_at DESC LIMIT 1",
                    (
                        reference.reference_kind,
                        str(reference.artifact_id),
                        reference.content_hash,
                        resolved_at,
                    ),
                ).fetchone()
            if row is None:
                raise reader_error
            restored = PITArtifactAuthorityResolution.from_canonical_dict(
                _object(row["payload_json"])
            )
            if restored.reference != reference:
                raise PITAuthorityIntegrityError(
                    "persisted Artifact resolution reference differs"
                )
            return restored

    def resolve_artifact(
        self,
        reference: PITArtifactReference,
        *,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> PITArtifactAuthorityResolution:
        resolved_at, system_time_authority = self._authority_now()
        resolution = self._artifact_resolver.resolve(
            reference,
            resolved_at=resolved_at,
        )
        payload = resolution.to_canonical_dict()
        command_hash = canonical_hash(payload)
        with self._connect() as connection:
            acquire_scope_lock(
                connection,
                namespace="pit-idempotency",
                identity=idempotency_key,
            )
            acquire_scope_lock(
                connection,
                namespace="pit-artifact-resolution",
                identity=(
                    f"{reference.reference_kind}:{reference.artifact_id}:"
                    f"{reference.content_hash}"
                ),
            )
            try:
                duplicate = _idempotent_action(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                )
                if duplicate is not None:
                    if duplicate["action_type"] != "RESOLVE_ARTIFACT":
                        raise PITAuthorityConflictError(
                            "PIT idempotency action mismatch"
                        )
                    restored = _load_resolution(
                        connection,
                        ArtifactId(str(duplicate["aggregate_id"])),
                        resolution.resolution_hash,
                    )
                    connection.commit()
                    return restored
                _persist_resolution(connection, resolution)
                _insert_action(
                    connection,
                    action_type="RESOLVE_ARTIFACT",
                    aggregate_id=str(resolution.resolution_id),
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    payload=payload,
                    actor=actor,
                    reason=reason,
                    created_at=resolved_at,
                    system_time_authority=system_time_authority,
                )
                connection.commit()
                return resolution
            except Exception:
                connection.rollback()
                raise

    def record_source_qualification(
        self,
        qualification: PITSourceQualification,
        *,
        idempotency_key: str,
    ) -> PITSourceQualification:
        payload = qualification.to_canonical_dict()
        command_hash = canonical_hash(payload)
        admitted_at, system_time_authority = self._authority_now()
        if admitted_at < qualification.recorded_at:
            raise PITAuthorityConflictError(
                "source qualification cannot be admitted before it was recorded"
            )
        if qualification.qualification_policy != self._provider_policy.reference:
            raise PITAuthorityConflictError(
                "source qualification does not bind the configured Provider policy"
            )
        try:
            self._provider_policy.require_level(
                qualification.provider_id,
                qualification.evidence_level,
                provider_contract=qualification.provider_contract,
                fact_kinds=qualification.qualified_fact_kinds,
            )
            if (
                qualification.status is PITSourceAuthorityStatus.QUALIFIED
                and qualification.evidence_level
                is PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER
            ):
                self._provider_policy.require_formal_evidence(
                    qualification.provider_evidence
                )
            source_resolution = self.resolve(
                qualification.source_manifest,
                resolved_at=admitted_at,
            )
            evidence_resolutions = tuple(
                self.resolve(
                    item.reference,
                    resolved_at=admitted_at,
                )
                for item in qualification.provider_evidence
            )
        except (PITArtifactAuthorityUnavailableError, ValueError) as exc:
            raise PITAuthorityConflictError(
                "source qualification Artifact authority is not established"
            ) from exc
        if (
            qualification.evidence_level
            is PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER
            and source_resolution.data_eligibility is not DataEligibility.FORMAL_RESEARCH
        ):
            raise PITAuthorityConflictError(
                "formal Provider qualification requires a FORMAL_RESEARCH SourceManifest"
            )
        source_identity = (
            f"{qualification.source_manifest.artifact_id}:"
            f"{qualification.provider_id}:{qualification.provider_contract}"
        )
        with self._connect() as connection:
            acquire_scope_lock(
                connection,
                namespace="pit-idempotency",
                identity=idempotency_key,
            )
            acquire_scope_lock(
                connection,
                namespace="pit-source-qualification",
                identity=source_identity,
            )
            try:
                duplicate = _idempotent_action(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                )
                if duplicate is not None:
                    if duplicate["action_type"] != "SOURCE_QUALIFICATION":
                        raise PITAuthorityConflictError("PIT idempotency action mismatch")
                    restored = _load_source_qualification(
                        connection, ArtifactId(str(duplicate["aggregate_id"]))
                    )
                    connection.commit()
                    return restored
                conflicting_manifest = connection.execute(
                    "SELECT 1 FROM pit_source_qualification "
                    "WHERE source_manifest_id = %s AND source_manifest_hash <> %s "
                    "LIMIT 1",
                    (
                        str(qualification.source_manifest.artifact_id),
                        qualification.source_manifest.content_hash,
                    ),
                ).fetchone()
                if conflicting_manifest is not None:
                    raise PITAuthorityConflictError(
                        "SourceManifest identity already belongs to a different hash"
                    )
                current = connection.execute(
                    "SELECT qualification_id, source_revision "
                    "FROM pit_source_qualification "
                    "WHERE source_manifest_id = %s AND source_manifest_hash = %s "
                    "AND provider_id = %s AND provider_contract = %s "
                    "ORDER BY source_revision DESC LIMIT 1",
                    (
                        str(qualification.source_manifest.artifact_id),
                        qualification.source_manifest.content_hash,
                        qualification.provider_id,
                        qualification.provider_contract,
                    ),
                ).fetchone()
                if current is None:
                    if (
                        qualification.revision != 1
                        or qualification.supersedes_qualification_id is not None
                    ):
                        raise PITAuthorityConflictError(
                            "PIT source qualification revision CAS failed"
                        )
                elif (
                    qualification.revision != int(current["source_revision"]) + 1
                    or qualification.supersedes_qualification_id
                    != ArtifactId(str(current["qualification_id"]))
                ):
                    raise PITAuthorityConflictError(
                        "PIT source qualification revision CAS failed"
                    )
                revision = _insert_action(
                    connection,
                    action_type="SOURCE_QUALIFICATION",
                    aggregate_id=str(qualification.qualification_id),
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    payload=payload,
                    actor=qualification.actor,
                    reason=qualification.reason,
                    created_at=admitted_at,
                    system_time_authority=system_time_authority,
                )
                _persist_resolution(connection, source_resolution)
                for resolution in evidence_resolutions:
                    _persist_resolution(connection, resolution)
                connection.execute(
                    """
                    INSERT INTO pit_source_qualification(
                        qualification_id, qualification_hash,
                        source_manifest_id, source_manifest_hash, provider_id,
                        provider_contract, status, source_revision,
                        supersedes_qualification_id, authority_revision,
                        evidence_level, qualified_fact_kinds,
                        qualification_policy_id,
                        qualification_policy_hash, source_manifest_resolution_id,
                        source_manifest_resolution_hash,
                        effective_at, recorded_at, payload_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        str(qualification.qualification_id),
                        qualification.qualification_hash,
                        str(qualification.source_manifest.artifact_id),
                        qualification.source_manifest.content_hash,
                        qualification.provider_id,
                        qualification.provider_contract,
                        qualification.status.value,
                        qualification.revision,
                        (
                            str(qualification.supersedes_qualification_id)
                            if qualification.supersedes_qualification_id
                            else None
                        ),
                        revision,
                        qualification.evidence_level.value,
                        [item.value for item in qualification.qualified_fact_kinds],
                        str(self._provider_policy.policy_id),
                        self._provider_policy.policy_hash,
                        str(source_resolution.resolution_id),
                        source_resolution.resolution_hash,
                        qualification.effective_at,
                        qualification.recorded_at,
                        _json(payload),
                    ),
                )
                for evidence, resolution in zip(
                    qualification.provider_evidence,
                    evidence_resolutions,
                    strict=True,
                ):
                    connection.execute(
                        "INSERT INTO pit_source_qualification_evidence("
                        "qualification_id, evidence_kind, resolution_id, "
                        "resolution_hash) VALUES (%s, %s, %s, %s)",
                        (
                            str(qualification.qualification_id),
                            evidence.evidence_kind.value,
                            str(resolution.resolution_id),
                            resolution.resolution_hash,
                        ),
                    )
                restored = _load_source_qualification(
                    connection, qualification.qualification_id
                )
                if restored != qualification:
                    raise PITAuthorityIntegrityError(
                        "PIT source qualification identity conflict"
                    )
                connection.commit()
                return restored
            except Exception:
                connection.rollback()
                raise

    def get_source_qualification(
        self, qualification_id: ArtifactId
    ) -> PITSourceQualification:
        with self._connect() as connection:
            return _load_source_qualification(connection, qualification_id)

    def record_fact(
        self,
        fact: PITFactRevision,
        *,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> RecordedPITFactRevision:
        command_payload = {
            "fact": fact.to_canonical_dict(),
            "actor": actor,
            "reason": reason,
        }
        command_hash = canonical_hash(command_payload)
        system_imported_at, system_time_authority = self._authority_now()
        if system_imported_at < fact.recorded_at:
            raise PITAuthorityConflictError(
                "PIT fact cannot be ingested before its recorded time"
            )
        try:
            artifact_resolution = self.resolve(
                fact.artifact,
                resolved_at=system_imported_at,
            )
            source_resolution = self.resolve(
                fact.source_manifest,
                resolved_at=system_imported_at,
            )
            temporal_resolutions = tuple(
                (
                    role,
                    self.resolve(reference, resolved_at=system_imported_at),
                )
                for role, reference in _temporal_authority_references(fact)
            )
        except (PITArtifactAuthorityUnavailableError, ValueError) as exc:
            raise PITAuthorityConflictError(
                "PIT Fact Artifact authority is not established"
            ) from exc
        if fact.data_eligibility is DataEligibility.FORMAL_RESEARCH:
            if source_resolution.data_eligibility is not DataEligibility.FORMAL_RESEARCH:
                raise PITAuthorityConflictError(
                    "FORMAL_RESEARCH fact requires a formal SourceManifest authority"
                )
            if (
                artifact_resolution.data_eligibility is not None
                and artifact_resolution.data_eligibility
                is not DataEligibility.FORMAL_RESEARCH
            ):
                raise PITAuthorityConflictError(
                    "FORMAL_RESEARCH fact Artifact is not FORMAL_RESEARCH eligible"
                )
        with self._connect() as connection:
            acquire_scope_lock(
                connection,
                namespace="pit-idempotency",
                identity=idempotency_key,
            )
            _acquire_shared_source_lock(
                connection,
                source_manifest_id=str(fact.source_manifest.artifact_id),
                provider_id=fact.provider_id,
                provider_contract=fact.provider_contract,
            )
            acquire_scope_lock(
                connection,
                namespace="pit-fact",
                identity=f"{fact.scope_id}:{fact.logical_key}",
            )
            try:
                duplicate = _idempotent_action(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                )
                if duplicate is not None:
                    if duplicate["action_type"] != "RECORD_FACT":
                        raise PITAuthorityConflictError("PIT idempotency action mismatch")
                    restored = _load_fact(connection, ArtifactId(str(duplicate["aggregate_id"])))
                    connection.commit()
                    return restored
                same_identity = connection.execute(
                    "SELECT fact_id FROM pit_fact_revision WHERE fact_id = %s",
                    (str(fact.fact_id),),
                ).fetchone()
                if same_identity is not None:
                    raise PITAuthorityConflictError(
                        "PIT fact identity already belongs to the original idempotency key"
                    )
                current = connection.execute(
                    "SELECT fact_id, fact_revision FROM pit_fact_revision "
                    "WHERE scope_id = %s AND logical_key = %s "
                    "ORDER BY fact_revision DESC LIMIT 1",
                    (fact.scope_id, fact.logical_key),
                ).fetchone()
                if current is None:
                    if fact.revision != 1 or fact.supersedes_fact_id is not None:
                        raise PITAuthorityConflictError("PIT fact revision CAS failed")
                elif (
                    fact.revision != int(current["fact_revision"]) + 1
                    or fact.supersedes_fact_id != ArtifactId(str(current["fact_id"]))
                ):
                    raise PITAuthorityConflictError("PIT fact revision CAS failed")
                qualification = _verify_formal_source_authority(
                    connection,
                    fact=fact,
                    system_imported_at=system_imported_at,
                )
                if fact.fact_kind not in qualification.qualified_fact_kinds:
                    raise PITAuthorityConflictError(
                        "PIT source qualification does not authorize this Fact kind"
                    )
                if fact.data_eligibility is DataEligibility.FORMAL_RESEARCH and (
                    qualification.evidence_level
                    is not PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER
                ):
                    raise PITAuthorityConflictError(
                        "FORMAL_RESEARCH fact requires FORMAL_PIT_PROVIDER source authority"
                    )
                if (
                    fact.temporal_authority.mode
                    is PITFactEvidenceMode.HISTORICAL_PROVIDER_PIT
                    and qualification.evidence_level
                    is not PITSourceEvidenceLevel.FORMAL_PIT_PROVIDER
                ):
                    raise PITAuthorityConflictError(
                        "Historical Provider PIT requires formal Provider qualification"
                    )
                for resolution in (
                    artifact_resolution,
                    source_resolution,
                    *(item[1] for item in temporal_resolutions),
                ):
                    _persist_resolution(connection, resolution)
                authority_revision = _insert_action(
                        connection,
                    action_type="RECORD_FACT",
                    aggregate_id=str(fact.fact_id),
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    payload=command_payload,
                    actor=actor,
                    reason=reason,
                    created_at=system_imported_at,
                    system_time_authority=system_time_authority,
                )
                connection.execute(
                    """
                    INSERT INTO pit_fact_revision(
                        fact_id, content_hash, scope_id, logical_key, fact_kind,
                        subject, fact_revision, supersedes_fact_id,
                        authority_revision, event_time, effective_from,
                        effective_to, available_at, recorded_at, system_imported_at,
                        artifact_id, artifact_hash, source_manifest_id,
                        source_manifest_hash,
                        provider_id, provider_contract, data_eligibility,
                        temporal_mode, system_time_authority,
                        source_qualification_id,
                        source_qualification_hash, artifact_resolution_id,
                        artifact_resolution_hash, source_manifest_resolution_id,
                        source_manifest_resolution_hash, value_json, payload_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        str(fact.fact_id), fact.content_hash, fact.scope_id,
                        fact.logical_key, fact.fact_kind.value, fact.subject,
                        fact.revision,
                        str(fact.supersedes_fact_id) if fact.supersedes_fact_id else None,
                        authority_revision, fact.event_time, fact.effective_from,
                        fact.effective_to, fact.available_at, fact.recorded_at,
                        system_imported_at,
                        str(fact.artifact.artifact_id), fact.artifact.content_hash,
                        str(fact.source_manifest.artifact_id),
                        fact.source_manifest.content_hash, fact.provider_id,
                        fact.provider_contract, fact.data_eligibility.value,
                        fact.temporal_authority.mode.value,
                        system_time_authority,
                        str(qualification.qualification_id),
                        qualification.qualification_hash,
                        str(artifact_resolution.resolution_id),
                        artifact_resolution.resolution_hash,
                        str(source_resolution.resolution_id),
                        source_resolution.resolution_hash,
                        fact.value_json, _json(fact.to_canonical_dict()),
                    ),
                )
                for role, resolution in temporal_resolutions:
                    connection.execute(
                        "INSERT INTO pit_fact_temporal_authority_resolution("
                        "fact_id, authority_role, resolution_id, resolution_hash) "
                        "VALUES (%s, %s, %s, %s)",
                        (
                            str(fact.fact_id),
                            role,
                            str(resolution.resolution_id),
                            resolution.resolution_hash,
                        ),
                    )
                restored = _load_fact(connection, fact.fact_id)
                connection.commit()
                return restored
            except Exception:
                connection.rollback()
                raise

    def get_fact(self, fact_id: ArtifactId) -> RecordedPITFactRevision:
        with self._connect() as connection:
            return _load_fact(connection, fact_id)

    def as_of(self, query: PITAsOfQuery) -> PITAsOfSnapshot:
        require_unique_required_fact_keys(query.required_facts)
        with self._connect() as connection:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            current_revision = _current_revision(connection)
            if current_revision <= 0:
                raise PITAuthorityIntegrityError("PIT authority has no revision")
            return _as_of(connection, query, current_revision)

    def validate(
        self, request: FormalPITValidationRequest
    ) -> FormalPITEvidenceArtifact:
        require_unique_required_fact_keys(request.required_facts)
        command_hash = canonical_hash(
            {"schema_version": "formal-pit-validation-command-v1", "request": request.to_canonical_dict()}
        )
        recorded_at, system_time_authority = self._authority_now()
        lineage_resolutions, artifact_rejections = _resolve_validation_lineage(
            self,
            request=request,
            resolved_at=recorded_at,
        )
        with self._connect() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            try:
                acquire_scope_lock(
                    connection,
                    namespace="pit-idempotency",
                    identity=request.idempotency_key,
                )
                duplicate = _idempotent_action(
                    connection,
                    idempotency_key=request.idempotency_key,
                    command_hash=command_hash,
                )
                if duplicate is not None:
                    if duplicate["action_type"] != "VALIDATE_PIT":
                        raise PITAuthorityConflictError("PIT idempotency action mismatch")
                    evidence = _load_evidence(connection, ArtifactId(str(duplicate["aggregate_id"])))
                    connection.commit()
                    return evidence
                cutoff = max(_current_revision(connection), 1)
                for resolution in lineage_resolutions:
                    _persist_resolution(connection, resolution)
                evidence, snapshot, selected = _evaluate(
                    connection,
                    request=request,
                    authority_revision=cutoff,
                    recorded_at=recorded_at,
                    additional_rejections=artifact_rejections,
                    lineage_resolution_references=tuple(
                        (item.resolution_id, item.resolution_hash)
                        for item in lineage_resolutions
                    ),
                )
                action_revision = _insert_action(
                    connection,
                    action_type="VALIDATE_PIT",
                    aggregate_id=str(evidence.evidence_id),
                    idempotency_key=request.idempotency_key,
                    command_hash=command_hash,
                    payload={
                        "request": request.to_canonical_dict(),
                        "evidence": evidence.to_canonical_dict(),
                    },
                    actor=request.actor,
                    reason=request.reason,
                    created_at=evidence.recorded_at,
                    system_time_authority=system_time_authority,
                )
                connection.execute(
                    """
                    INSERT INTO pit_as_of_snapshot(
                        snapshot_id, snapshot_hash, query_hash, scope_id,
                        decision_time, authority_revision, action_revision,
                        outcome, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(snapshot.snapshot_id), snapshot.snapshot_hash,
                        snapshot.query_hash, snapshot.scope_id,
                        snapshot.decision_time, snapshot.authority_revision,
                        action_revision, snapshot.outcome.value,
                        _json(snapshot.to_canonical_dict()),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO formal_pit_validation_evidence(
                        evidence_id, evidence_hash, request_hash, snapshot_id,
                        authority_revision, action_revision, model_id,
                        definition_hash, model_lineage_id, model_lineage_hash,
                        outcome, request_json, payload_json, available_at,
                        recorded_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    """,
                    (
                        str(evidence.evidence_id), evidence.evidence_hash,
                        evidence.request_hash, str(evidence.snapshot_id),
                        evidence.authority_revision, action_revision,
                        str(evidence.lineage.model_id),
                        evidence.lineage.definition_hash,
                        str(evidence.lineage.model_lineage_id),
                        evidence.lineage.model_lineage_hash,
                        evidence.outcome.value, _json(request.to_canonical_dict()),
                        _json(evidence.to_canonical_dict()), evidence.available_at,
                        evidence.recorded_at,
                    ),
                )
                _verify_selected_facts(selected, evidence)
                restored = _load_evidence(connection, evidence.evidence_id)
                if restored != evidence:
                    raise PITAuthorityIntegrityError("Formal PIT evidence identity conflict")
                connection.commit()
                return restored
            except Exception:
                connection.rollback()
                raise

    def get_evidence(self, evidence_id: ArtifactId) -> FormalPITEvidenceArtifact:
        with self._connect() as connection:
            return _load_evidence(connection, evidence_id)

    def replay_evidence(self, evidence_id: ArtifactId) -> FormalPITEvidenceArtifact:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT request_json, payload_json, snapshot_id "
                "FROM formal_pit_validation_evidence "
                "WHERE evidence_id = %s",
                (str(evidence_id),),
            ).fetchone()
            if row is None:
                raise KeyError(str(evidence_id))
            original = FormalPITEvidenceArtifact.from_canonical_dict(_object(row["payload_json"]))
            request = FormalPITValidationRequest.from_canonical_dict(_object(row["request_json"]))
            if request.request_hash != original.request_hash:
                raise PITAuthorityIntegrityError(
                    "Formal PIT replay request differs from stored evidence"
                )
            snapshot_row = connection.execute(
                "SELECT payload_json FROM pit_as_of_snapshot WHERE snapshot_id = %s",
                (str(original.snapshot_id),),
            ).fetchone()
            if snapshot_row is None:
                raise PITAuthorityIntegrityError("Formal PIT replay snapshot is missing")
            snapshot = PITAsOfSnapshot.from_canonical_dict(
                _object(snapshot_row["payload_json"])
            )
            if (
                snapshot.snapshot_hash != original.snapshot_hash
                or snapshot.selected_fact_authorities
                != original.selected_fact_authorities
            ):
                raise PITAuthorityIntegrityError(
                    "Formal PIT replay snapshot binding differs from evidence"
                )
            _verify_immutable_replay_bindings(connection, original)
            selected = tuple(
                _load_fact(connection, item.fact_id)
                for item in original.selected_fact_authorities
            )
            lineage_resolutions = tuple(
                _load_resolution(connection, resolution_id, resolution_hash)
                for resolution_id, resolution_hash
                in original.lineage_resolution_references
            )
            _verify_replay_projection(
                request=request,
                snapshot=snapshot,
                selected=selected,
                lineage_resolutions=lineage_resolutions,
            )
            replayed_snapshot = PITAsOfSnapshot.create(
                query_hash=snapshot.query_hash,
                scope_id=snapshot.scope_id,
                decision_time=snapshot.decision_time,
                authority_revision=snapshot.authority_revision,
                outcome=snapshot.outcome,
                selected_fact_references=snapshot.selected_fact_references,
                selected_fact_authorities=snapshot.selected_fact_authorities,
                rejection_codes=snapshot.rejection_codes,
            )
            if replayed_snapshot != snapshot:
                raise PITAuthorityIntegrityError(
                    "Formal PIT replay could not reconstruct immutable snapshot"
                )
            replayed = FormalPITEvidenceArtifact.create(
                request_hash=request.request_hash,
                snapshot_id=replayed_snapshot.snapshot_id,
                snapshot_hash=replayed_snapshot.snapshot_hash,
                authority_revision=original.authority_revision,
                lineage=request.lineage,
                outcome=replayed_snapshot.outcome,
                rejection_codes=replayed_snapshot.rejection_codes,
                selected_fact_references=replayed_snapshot.selected_fact_references,
                selected_fact_authorities=replayed_snapshot.selected_fact_authorities,
                lineage_resolution_references=original.lineage_resolution_references,
                available_at=original.available_at,
                recorded_at=original.recorded_at,
                actor=request.actor,
                reason=request.reason,
            )
            if replayed != original:
                raise PITAuthorityIntegrityError(
                    "Formal PIT replay could not reconstruct immutable evidence"
                )
            return replayed


def _evaluate(
    connection: PostgresConnection,
    *,
    request: FormalPITValidationRequest,
    authority_revision: int,
    recorded_at: datetime,
    additional_rejections: tuple[str, ...] = (),
    lineage_resolution_references: tuple[tuple[ArtifactId, str], ...] = (),
) -> tuple[FormalPITEvidenceArtifact, PITAsOfSnapshot, tuple[RecordedPITFactRevision, ...]]:
    query = PITAsOfQuery.create(
        scope_id=request.scope_id,
        decision_time=request.decision_time,
        required_facts=request.required_facts,
    )
    snapshot = _as_of(connection, query, authority_revision)
    selected = tuple(
        _load_fact(connection, fact_id)
        for fact_id, _ in snapshot.selected_fact_references
    )
    reasons = set(snapshot.rejection_codes)
    reasons.update(additional_rejections)
    if recorded_at < request.decision_time:
        reasons.add("VALIDATION_BEFORE_DECISION")
    reasons.update(formal_pit_request_rejection_codes(request))
    reasons.update(_lineage_rejection_codes(request, selected))
    ordered_reasons = tuple(sorted(reasons))
    if ordered_reasons != snapshot.rejection_codes:
        snapshot = PITAsOfSnapshot.create(
            query_hash=query.query_hash,
            scope_id=request.scope_id,
            decision_time=request.decision_time,
            authority_revision=authority_revision,
            outcome=(PITValidationOutcome.REJECTED if ordered_reasons else PITValidationOutcome.SATISFIED),
            selected_fact_references=snapshot.selected_fact_references,
            selected_fact_authorities=snapshot.selected_fact_authorities,
            rejection_codes=ordered_reasons,
        )
    evidence = FormalPITEvidenceArtifact.create(
        request_hash=request.request_hash,
        snapshot_id=snapshot.snapshot_id,
        snapshot_hash=snapshot.snapshot_hash,
        authority_revision=authority_revision,
        lineage=request.lineage,
        outcome=snapshot.outcome,
        rejection_codes=snapshot.rejection_codes,
        selected_fact_references=snapshot.selected_fact_references,
        selected_fact_authorities=snapshot.selected_fact_authorities,
        lineage_resolution_references=lineage_resolution_references,
        available_at=recorded_at,
        recorded_at=recorded_at,
        actor=request.actor,
        reason=request.reason,
    )
    return evidence, snapshot, selected


def _as_of(
    connection: PostgresConnection,
    query: PITAsOfQuery,
    authority_revision: int,
) -> PITAsOfSnapshot:
    require_unique_required_fact_keys(query.required_facts)
    required_by_key = {item.logical_key: item for item in query.required_facts}
    keys = tuple(required_by_key)
    rows: list[dict[str, Any]] = []
    if keys:
        rows = connection.execute(
            """
            SELECT DISTINCT ON (logical_key)
                fact_id, logical_key
            FROM pit_fact_revision
            WHERE scope_id = %s
              AND logical_key = ANY(%s)
              AND event_time <= %s
              AND effective_from <= %s
              AND (effective_to IS NULL OR %s < effective_to)
              AND available_at <= %s
              AND recorded_at <= %s
              AND (
                  temporal_mode = 'HISTORICAL_PROVIDER_PIT'
                  OR system_imported_at <= %s
              )
            ORDER BY logical_key, fact_revision DESC, authority_revision DESC
            """,
            (
                query.scope_id, list(keys),
                query.decision_time, query.decision_time, query.decision_time,
                query.decision_time, query.decision_time, query.decision_time,
            ),
        ).fetchall()
    selected: dict[str, RecordedPITFactRevision] = {}
    for row in rows:
        recorded = _load_fact(connection, ArtifactId(str(row["fact_id"])))
        selected[recorded.fact.logical_key] = recorded
    reasons: set[str] = set()
    for key, required in required_by_key.items():
        found = selected.get(key)
        if found is None:
            reasons.add(_missing_reason(connection, query, required))
        elif found.fact.fact_kind is not required.fact_kind or found.fact.subject != required.subject:
            reasons.add(f"FACT_SCOPE_MISMATCH:{key}")
    references = tuple((item.fact.fact_id, item.fact.content_hash) for item in selected.values())
    authorities = tuple(
        PITSelectedFactAuthority.from_recorded(item) for item in selected.values()
    )
    return PITAsOfSnapshot.create(
        query_hash=query.query_hash,
        scope_id=query.scope_id,
        decision_time=query.decision_time,
        authority_revision=authority_revision,
        outcome=PITValidationOutcome.REJECTED if reasons else PITValidationOutcome.SATISFIED,
        selected_fact_references=references,
        selected_fact_authorities=authorities,
        rejection_codes=tuple(sorted(reasons)),
    )


def _missing_reason(
    connection: PostgresConnection,
    query: PITAsOfQuery,
    required: PITRequiredFact,
) -> str:
    row = connection.execute(
        "SELECT event_time, effective_from, effective_to, available_at, "
        "recorded_at, system_imported_at, temporal_mode, fact_kind, subject "
        "FROM pit_fact_revision "
        "WHERE scope_id = %s AND logical_key = %s "
        "ORDER BY fact_revision DESC LIMIT 1",
        (query.scope_id, required.logical_key),
    ).fetchone()
    suffix = required.logical_key
    if row is None:
        typed_missing = {
            PITFactKind.THEME_MEMBERSHIP: "HISTORICAL_THEME_MEMBERSHIP_UNAVAILABLE",
            PITFactKind.ETF_MEMBERSHIP: "HISTORICAL_ETF_MEMBERSHIP_UNAVAILABLE",
            PITFactKind.ST_STATUS: "HISTORICAL_ST_STATUS_UNAVAILABLE",
            PITFactKind.TRADING_STATUS: "HISTORICAL_SUSPENSION_STATUS_UNAVAILABLE",
            PITFactKind.LISTING_STATUS: "HISTORICAL_LISTING_STATUS_UNAVAILABLE",
            PITFactKind.ADJUSTMENT_FACTOR: "CORPORATE_ACTION_AUTHORITY_UNAVAILABLE",
        }.get(required.fact_kind, "FACT_MISSING")
        return f"{typed_missing}:{suffix}"
    if row["fact_kind"] != required.fact_kind.value or row["subject"] != required.subject:
        return f"FACT_SCOPE_MISMATCH:{suffix}"
    if aware_datetime(row["event_time"], label="event_time") > query.decision_time:
        return f"FUTURE_EVENT_REJECTED:{suffix}"
    if aware_datetime(row["effective_from"], label="effective_from") > query.decision_time:
        return f"FUTURE_EFFECTIVE_STATE_REJECTED:{suffix}"
    if aware_datetime(row["available_at"], label="available_at") > query.decision_time:
        return f"LATE_AVAILABLE_FACT_REJECTED:{suffix}"
    if aware_datetime(row["recorded_at"], label="recorded_at") > query.decision_time:
        return f"LATE_RECORDED_FACT_REJECTED:{suffix}"
    if (
        row["temporal_mode"] == PITFactEvidenceMode.PROSPECTIVE_CAPTURED_PIT.value
        and aware_datetime(row["system_imported_at"], label="system_imported_at")
        > query.decision_time
    ):
        return f"LATE_INGESTED_FACT_REJECTED:{suffix}"
    if row["effective_to"] is not None and query.decision_time >= aware_datetime(row["effective_to"], label="effective_to"):
        return f"EXPIRED_FACT_REJECTED:{suffix}"
    return f"FACT_NOT_VISIBLE:{suffix}"


def _lineage_rejection_codes(
    request: FormalPITValidationRequest,
    facts: tuple[RecordedPITFactRevision, ...],
) -> tuple[str, ...]:
    reasons: set[str] = set()
    allowed_manifests = set(request.lineage.source_manifests)
    for recorded in facts:
        fact = recorded.fact
        if fact.data_eligibility is not DataEligibility.FORMAL_RESEARCH:
            reasons.add(f"INPUT_AUTHORITY_NOT_FORMAL:{fact.logical_key}")
        if fact.source_manifest not in allowed_manifests:
            reasons.add(f"SOURCE_MANIFEST_LINEAGE_MISMATCH:{fact.logical_key}")
        if fact.fact_kind is PITFactKind.MARKET_DATA and fact.artifact != request.lineage.dataset:
            reasons.add(f"DATASET_LINEAGE_MISMATCH:{fact.logical_key}")
        elif fact.fact_kind is PITFactKind.UNIVERSE_MEMBERSHIP and fact.artifact != request.lineage.universe:
            reasons.add(f"UNIVERSE_LINEAGE_MISMATCH:{fact.logical_key}")
        elif fact.fact_kind in {
            PITFactKind.TRADING_STATUS, PITFactKind.ST_STATUS,
            PITFactKind.LISTING_STATUS, PITFactKind.TRADING_ELIGIBILITY,
        } and fact.artifact != request.lineage.eligibility:
            reasons.add(f"ELIGIBILITY_LINEAGE_MISMATCH:{fact.logical_key}")
    selected_features = {
        item.fact.artifact for item in facts
        if item.fact.fact_kind is PITFactKind.FEATURE_MATERIALIZATION
    }
    if selected_features != set(request.lineage.feature_materializations):
        reasons.add("FEATURE_MATERIALIZATION_LINEAGE_MISMATCH")
    return tuple(sorted(reasons))


def _verify_selected_facts(
    facts: tuple[RecordedPITFactRevision, ...],
    evidence: FormalPITEvidenceArtifact,
) -> None:
    actual = tuple(sorted(((item.fact.fact_id, item.fact.content_hash) for item in facts), key=lambda item: str(item[0])))
    if actual != evidence.selected_fact_references:
        raise PITAuthorityIntegrityError("Formal PIT selected fact binding mismatch")


def _verify_replay_projection(
    *,
    request: FormalPITValidationRequest,
    snapshot: PITAsOfSnapshot,
    selected: tuple[RecordedPITFactRevision, ...],
    lineage_resolutions: tuple[PITArtifactAuthorityResolution, ...],
) -> None:
    query = PITAsOfQuery.create(
        scope_id=request.scope_id,
        decision_time=request.decision_time,
        required_facts=request.required_facts,
    )
    if query.query_hash != snapshot.query_hash:
        raise PITAuthorityIntegrityError("Formal PIT replay query identity differs")
    required_by_key = {item.logical_key: item for item in request.required_facts}
    selected_by_key = {item.fact.logical_key: item for item in selected}
    if len(selected_by_key) != len(selected):
        raise PITAuthorityIntegrityError("Formal PIT replay selected keys collide")
    derived_rejections = set(formal_pit_request_rejection_codes(request))
    derived_rejections.update(_lineage_rejection_codes(request, selected))
    derived_rejections.update(
        _validation_lineage_resolution_rejections(request, lineage_resolutions)
    )
    expected_lineage_references = {
        request.lineage.dataset,
        *request.lineage.source_manifests,
        request.lineage.universe,
        request.lineage.eligibility,
        *request.lineage.feature_materializations,
        request.lineage.configuration,
        request.lineage.validation_protocol,
    }
    if (
        snapshot.outcome is PITValidationOutcome.SATISFIED
        and {item.reference for item in lineage_resolutions}
        != expected_lineage_references
    ):
        raise PITAuthorityIntegrityError(
            "Formal PIT replay lineage resolution set is incomplete"
        )
    for key, recorded in selected_by_key.items():
        required = required_by_key.get(key)
        fact = recorded.fact
        if required is None:
            raise PITAuthorityIntegrityError(
                "Formal PIT replay selected an undeclared Fact"
            )
        if fact.fact_kind is not required.fact_kind or fact.subject != required.subject:
            derived_rejections.add(f"FACT_SCOPE_MISMATCH:{key}")
        if fact.scope_id != request.scope_id:
            derived_rejections.add(f"FACT_SCOPE_MISMATCH:{key}")
        if fact.event_time > request.decision_time:
            derived_rejections.add(f"FUTURE_EVENT_REJECTED:{fact.fact_kind.value}:{fact.subject}")
        if fact.effective_from > request.decision_time:
            derived_rejections.add(
                f"FUTURE_EFFECTIVE_STATE_REJECTED:{fact.fact_kind.value}:{fact.subject}"
            )
        if fact.effective_to is not None and request.decision_time >= fact.effective_to:
            derived_rejections.add(f"EXPIRED_FACT_REJECTED:{fact.fact_kind.value}:{fact.subject}")
        if fact.available_at > request.decision_time:
            derived_rejections.add(f"LATE_AVAILABLE_FACT_REJECTED:{fact.fact_kind.value}:{fact.subject}")
        if fact.recorded_at > request.decision_time:
            derived_rejections.add(f"LATE_RECORDED_FACT_REJECTED:{fact.fact_kind.value}:{fact.subject}")
        if (
            fact.temporal_authority.mode
            is PITFactEvidenceMode.PROSPECTIVE_CAPTURED_PIT
            and recorded.system_imported_at > request.decision_time
        ):
            derived_rejections.add(f"LATE_INGESTED_FACT_REJECTED:{fact.fact_kind.value}:{fact.subject}")
    if snapshot.outcome is PITValidationOutcome.SATISFIED and (
        set(required_by_key) != set(selected_by_key) or derived_rejections
    ):
        raise PITAuthorityIntegrityError(
            "satisfied Formal PIT evidence fails replay projection"
        )
    unexplained = derived_rejections.difference(snapshot.rejection_codes)
    if unexplained:
        raise PITAuthorityIntegrityError(
            "Formal PIT replay projection differs: " + ",".join(sorted(unexplained))
        )


def _resolve_validation_lineage(
    resolver: PITArtifactAuthorityResolver,
    *,
    request: FormalPITValidationRequest,
    resolved_at: datetime,
) -> tuple[tuple[PITArtifactAuthorityResolution, ...], tuple[str, ...]]:
    references = (
        request.lineage.dataset,
        *request.lineage.source_manifests,
        request.lineage.universe,
        request.lineage.eligibility,
        *request.lineage.feature_materializations,
        request.lineage.configuration,
        request.lineage.validation_protocol,
    )
    unique = tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.reference_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )
    resolved: list[PITArtifactAuthorityResolution] = []
    reasons: set[str] = set()
    for reference in unique:
        try:
            resolution = resolver.resolve(reference, resolved_at=resolved_at)
        except (PITArtifactAuthorityUnavailableError, ValueError):
            reasons.add(
                "ARTIFACT_AUTHORITY_UNAVAILABLE:"
                f"{reference.reference_kind}:{reference.artifact_id}"
            )
            continue
        if resolution.reference != reference:
            reasons.add(
                "ARTIFACT_AUTHORITY_IDENTITY_MISMATCH:"
                f"{reference.reference_kind}:{reference.artifact_id}"
            )
            continue
        resolved.append(resolution)
    reasons.update(
        _validation_lineage_resolution_rejections(request, tuple(resolved))
    )
    return tuple(resolved), tuple(sorted(reasons))


def _validation_lineage_resolution_rejections(
    request: FormalPITValidationRequest,
    resolved: tuple[PITArtifactAuthorityResolution, ...],
) -> tuple[str, ...]:
    reasons: set[str] = set()
    for resolution in resolved:
        reference = resolution.reference
        if (
            resolution.data_eligibility is not None
            and resolution.data_eligibility is not DataEligibility.FORMAL_RESEARCH
        ):
            reasons.add(
                "ARTIFACT_NOT_FORMAL_RESEARCH:"
                f"{reference.reference_kind}:{reference.artifact_id}"
            )
        if (
            resolution.formal_pit_status is not None
            and resolution.formal_pit_status != "PIT_CORRECT_FOR_DECLARED_SCOPE"
        ):
            reasons.add(
                "ARTIFACT_FORMAL_PIT_NOT_ESTABLISHED:"
                f"{reference.reference_kind}:{reference.artifact_id}"
            )
        for label, instant in (
            ("EFFECTIVE", resolution.effective_at),
            ("AVAILABLE", resolution.available_at),
        ):
            if instant is not None and instant > request.decision_time:
                reasons.add(
                    f"FUTURE_ARTIFACT_{label}:"
                    f"{reference.reference_kind}:{reference.artifact_id}"
                )
    by_reference = {item.reference: item for item in resolved}
    expected_sources = set(request.lineage.source_manifests)
    dataset_resolution = by_reference.get(request.lineage.dataset)
    if dataset_resolution is not None and (
        set(dataset_resolution.bound_references) != expected_sources
    ):
        reasons.add("DATASET_SOURCE_MANIFEST_BINDING_MISMATCH")
    expected_feature_bindings = {request.lineage.dataset, *expected_sources}
    for feature in request.lineage.feature_materializations:
        feature_resolution = by_reference.get(feature)
        if feature_resolution is not None and (
            set(feature_resolution.bound_references) != expected_feature_bindings
        ):
            reasons.add(
                f"FEATURE_DEPENDENCY_BINDING_MISMATCH:{feature.artifact_id}"
            )
    return tuple(sorted(reasons))


def _temporal_authority_references(
    fact: PITFactRevision,
) -> tuple[tuple[str, Any], ...]:
    temporal = fact.temporal_authority
    values = [
        (item.evidence_kind.value, item.reference)
        for item in temporal.provider_evidence
    ]
    if temporal.provider_archive is not None:
        values.append(("PROVIDER_ARCHIVE", temporal.provider_archive))
    return tuple(sorted(values, key=lambda item: item[0]))


def _persist_resolution(
    connection: PostgresConnection,
    resolution: PITArtifactAuthorityResolution,
) -> None:
    connection.execute(
        """
        INSERT INTO pit_artifact_authority_resolution(
            resolution_id, resolution_hash, reference_kind, artifact_id,
            artifact_hash, canonical_schema, reader_contract,
            physical_checksums_hash, payload_json, resolved_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (resolution_id) DO NOTHING
        """,
        (
            str(resolution.resolution_id),
            resolution.resolution_hash,
            resolution.reference.reference_kind,
            str(resolution.reference.artifact_id),
            resolution.reference.content_hash,
            resolution.canonical_schema,
            resolution.reader_contract,
            resolution.physical_checksums_hash,
            _json(resolution.to_canonical_dict()),
            resolution.resolved_at,
        ),
    )
    row = connection.execute(
        "SELECT resolution_hash, reference_kind, artifact_id, artifact_hash "
        "FROM pit_artifact_authority_resolution WHERE resolution_id = %s",
        (str(resolution.resolution_id),),
    ).fetchone()
    if row is None or (
        row["resolution_hash"] != resolution.resolution_hash
        or row["reference_kind"] != resolution.reference.reference_kind
        or row["artifact_id"] != str(resolution.reference.artifact_id)
        or row["artifact_hash"] != resolution.reference.content_hash
    ):
        raise PITAuthorityIntegrityError(
            "PIT Artifact resolution identity conflict"
        )


def _verify_immutable_replay_bindings(
    connection: PostgresConnection,
    evidence: FormalPITEvidenceArtifact,
) -> None:
    for expected in evidence.selected_fact_authorities:
        recorded = _load_fact(connection, expected.fact_id)
        if PITSelectedFactAuthority.from_recorded(recorded) != expected:
            raise PITAuthorityIntegrityError(
                "Formal PIT replay Fact authority binding differs"
            )
        qualification = _load_source_qualification(
            connection, expected.source_qualification_id
        )
        if qualification.qualification_hash != expected.source_qualification_hash:
            raise PITAuthorityIntegrityError(
                "Formal PIT replay source qualification differs"
            )
        artifact_resolution = _load_resolution(
            connection,
            expected.artifact_resolution_id,
            expected.artifact_resolution_hash,
        )
        if artifact_resolution.reference != recorded.fact.artifact:
            raise PITAuthorityIntegrityError(
                "Formal PIT replay Fact Artifact resolution differs"
            )
        source_resolution = _load_resolution(
            connection,
            expected.source_manifest_resolution_id,
            expected.source_manifest_resolution_hash,
        )
        if source_resolution.reference != recorded.fact.source_manifest:
            raise PITAuthorityIntegrityError(
                "Formal PIT replay SourceManifest resolution differs"
            )
        temporal_by_role = dict(_temporal_authority_references(recorded.fact))
        for role, resolution_id, resolution_hash in expected.temporal_resolution_references:
            temporal_resolution = _load_resolution(
                connection,
                resolution_id,
                resolution_hash,
            )
            if temporal_resolution.reference != temporal_by_role.get(role):
                raise PITAuthorityIntegrityError(
                    "Formal PIT replay temporal authority role differs"
                )
        evidence_rows = connection.execute(
            "SELECT evidence_kind, resolution_id, resolution_hash "
            "FROM pit_source_qualification_evidence "
            "WHERE qualification_id = %s ORDER BY evidence_kind",
            (str(qualification.qualification_id),),
        ).fetchall()
        if len(evidence_rows) != len(qualification.provider_evidence):
            raise PITAuthorityIntegrityError(
                "Formal PIT replay Provider qualification evidence is incomplete"
            )
        evidence_by_kind = {
            item.evidence_kind.value: item.reference
            for item in qualification.provider_evidence
        }
        for row in evidence_rows:
            evidence_resolution = _load_resolution(
                connection,
                ArtifactId(str(row["resolution_id"])),
                str(row["resolution_hash"]),
            )
            if evidence_resolution.reference != evidence_by_kind.get(
                str(row["evidence_kind"])
            ):
                raise PITAuthorityIntegrityError(
                    "Formal PIT replay Provider evidence role differs"
                )
    for resolution_id, resolution_hash in evidence.lineage_resolution_references:
        _verify_resolution_reference(connection, resolution_id, resolution_hash)


def _verify_resolution_reference(
    connection: PostgresConnection,
    resolution_id: ArtifactId,
    resolution_hash: str,
) -> None:
    row = connection.execute(
        "SELECT resolution_hash, payload_json "
        "FROM pit_artifact_authority_resolution WHERE resolution_id = %s",
        (str(resolution_id),),
    ).fetchone()
    if row is None or row["resolution_hash"] != resolution_hash:
        raise PITAuthorityIntegrityError(
            "Formal PIT replay Artifact resolution is missing or changed"
        )
    restored = PITArtifactAuthorityResolution.from_canonical_dict(
        _object(row["payload_json"])
    )
    if restored.resolution_hash != resolution_hash:
        raise PITAuthorityIntegrityError(
            "Formal PIT replay Artifact resolution payload differs"
        )


def _load_resolution(
    connection: PostgresConnection,
    resolution_id: ArtifactId,
    resolution_hash: str,
) -> PITArtifactAuthorityResolution:
    _verify_resolution_reference(connection, resolution_id, resolution_hash)
    row = connection.execute(
        "SELECT payload_json FROM pit_artifact_authority_resolution "
        "WHERE resolution_id = %s",
        (str(resolution_id),),
    ).fetchone()
    if row is None:
        raise PITAuthorityIntegrityError("PIT Artifact resolution is missing")
    return PITArtifactAuthorityResolution.from_canonical_dict(
        _object(row["payload_json"])
    )


def _verify_formal_source_authority(
    connection: PostgresConnection,
    *,
    fact: PITFactRevision,
    system_imported_at: datetime,
) -> PITSourceQualification:
    row = connection.execute(
        """
        SELECT qualification.payload_json, action.created_at
        FROM pit_source_qualification AS qualification
        JOIN pit_authority_action AS action
          ON action.authority_revision = qualification.authority_revision
        WHERE qualification.source_manifest_id = %s
          AND qualification.source_manifest_hash = %s
          AND qualification.provider_id = %s
          AND qualification.provider_contract = %s
          AND qualification.effective_at <= %s
          AND qualification.recorded_at <= %s
          AND action.created_at <= %s
        ORDER BY qualification.source_revision DESC
        LIMIT 1
        """,
        (
            str(fact.source_manifest.artifact_id),
            fact.source_manifest.content_hash,
            fact.provider_id,
            fact.provider_contract,
            system_imported_at,
            system_imported_at,
            system_imported_at,
        ),
    ).fetchone()
    if row is None:
        raise PITAuthorityConflictError(
            "FORMAL_RESEARCH fact requires explicit PIT source qualification"
        )
    qualification = PITSourceQualification.from_canonical_dict(
        _object(row["payload_json"])
    )
    action_time = aware_datetime(row["created_at"], label="source authority created_at")
    if (
        qualification.status is not PITSourceAuthorityStatus.QUALIFIED
        or qualification.effective_at > system_imported_at
        or qualification.recorded_at > system_imported_at
        or action_time > system_imported_at
    ):
        raise PITAuthorityConflictError(
            "FORMAL_RESEARCH fact source is not qualified at ingest time"
        )
    return qualification


def _acquire_shared_source_lock(
    connection: PostgresConnection,
    *,
    source_manifest_id: str,
    provider_id: str,
    provider_contract: str,
) -> None:
    identity = f"{source_manifest_id}:{provider_id}:{provider_contract}"
    key = f"market-regime-alpha:pit-source-qualification:{identity}"
    connection.execute(
        "SELECT pg_advisory_xact_lock_shared(hashtextextended(%s, 0))",
        (key,),
    )


def _load_source_qualification(
    connection: PostgresConnection,
    qualification_id: ArtifactId,
) -> PITSourceQualification:
    row = connection.execute(
        "SELECT payload_json FROM pit_source_qualification WHERE qualification_id = %s",
        (str(qualification_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(qualification_id))
    return PITSourceQualification.from_canonical_dict(_object(row["payload_json"]))


def _load_fact(
    connection: PostgresConnection,
    fact_id: ArtifactId,
) -> RecordedPITFactRevision:
    row = connection.execute(
        "SELECT payload_json, authority_revision, system_imported_at, "
        "source_qualification_id, source_qualification_hash, "
        "artifact_resolution_id, artifact_resolution_hash, "
        "source_manifest_resolution_id, source_manifest_resolution_hash, "
        "system_time_authority "
        "FROM pit_fact_revision WHERE fact_id = %s",
        (str(fact_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(fact_id))
    temporal_rows = connection.execute(
        "SELECT authority_role, resolution_id, resolution_hash "
        "FROM pit_fact_temporal_authority_resolution WHERE fact_id = %s "
        "ORDER BY authority_role",
        (str(fact_id),),
    ).fetchall()
    return _recorded_from_row(
        row,
        temporal_resolution_references=tuple(
            (
                str(item["authority_role"]),
                ArtifactId(str(item["resolution_id"])),
                str(item["resolution_hash"]),
            )
            for item in temporal_rows
        ),
    )


def _recorded_from_row(
    row: Mapping[str, Any],
    *,
    temporal_resolution_references: tuple[tuple[str, ArtifactId, str], ...],
) -> RecordedPITFactRevision:
    return RecordedPITFactRevision(
        fact=PITFactRevision.from_canonical_dict(_object(row["payload_json"])),
        authority_revision=int(row["authority_revision"]),
        system_imported_at=aware_datetime(row["system_imported_at"], label="system_imported_at"),
        source_qualification_id=ArtifactId(str(row["source_qualification_id"])),
        source_qualification_hash=str(row["source_qualification_hash"]),
        artifact_resolution_id=ArtifactId(str(row["artifact_resolution_id"])),
        artifact_resolution_hash=str(row["artifact_resolution_hash"]),
        source_manifest_resolution_id=ArtifactId(
            str(row["source_manifest_resolution_id"])
        ),
        source_manifest_resolution_hash=str(
            row["source_manifest_resolution_hash"]
        ),
        temporal_resolution_references=temporal_resolution_references,
        system_time_authority=str(row["system_time_authority"]),
    )


def _load_evidence(
    connection: PostgresConnection,
    evidence_id: ArtifactId,
) -> FormalPITEvidenceArtifact:
    row = connection.execute(
        "SELECT payload_json FROM formal_pit_validation_evidence WHERE evidence_id = %s",
        (str(evidence_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(evidence_id))
    return FormalPITEvidenceArtifact.from_canonical_dict(_object(row["payload_json"]))


def _current_revision(connection: PostgresConnection) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(authority_revision), 0) AS revision FROM pit_authority_action"
    ).fetchone()
    if row is None:
        raise PITAuthorityIntegrityError("PIT authority revision query returned no row")
    return int(row["revision"])


def _idempotent_action(
    connection: PostgresConnection,
    *,
    idempotency_key: str,
    command_hash: str,
) -> Mapping[str, Any] | None:
    row = connection.execute(
        "SELECT action_type, aggregate_id, command_hash FROM pit_authority_action "
        "WHERE idempotency_key = %s",
        (idempotency_key,),
    ).fetchone()
    if row is not None and row["command_hash"] != command_hash:
        raise PITAuthorityConflictError("PIT idempotency key conflict")
    return row


def _insert_action(
    connection: PostgresConnection,
    *,
    action_type: str,
    aggregate_id: str,
    idempotency_key: str,
    command_hash: str,
    payload: Mapping[str, Any],
    actor: str,
    reason: str,
    created_at: datetime,
    system_time_authority: str,
) -> int:
    row = connection.execute(
        "INSERT INTO pit_authority_action(action_type, aggregate_id, "
        "idempotency_key, command_hash, payload_json, actor, reason, created_at, "
        "system_time_authority) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "RETURNING authority_revision",
        (
            action_type, aggregate_id, idempotency_key, command_hash,
            _json(payload), actor, reason, created_at, system_time_authority,
        ),
    ).fetchone()
    if row is None:
        raise PITAuthorityIntegrityError("PIT authority action insert returned no row")
    return int(row["authority_revision"])


def _json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _object(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, Mapping):
            return parsed
    raise PITAuthorityIntegrityError("stored PIT JSON must be an object")


def _whole_second(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("PIT clock must be timezone-aware")
    return value.astimezone(UTC).replace(microsecond=0)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


__all__ = [
    "PITAuthorityConflictError",
    "PITAuthorityIntegrityError",
    "PostgresPITAuthority",
]
