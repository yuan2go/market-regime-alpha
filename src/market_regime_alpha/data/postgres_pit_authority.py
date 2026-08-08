"""PostgreSQL-only bitemporal fact, as-of query and Formal PIT evidence."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_authority import (
    FormalPITEvidenceArtifact,
    FormalPITValidationRequest,
    PITAsOfQuery,
    PITAsOfSnapshot,
    PITFactKind,
    PITFactRevision,
    PITRequiredFact,
    PITSourceAuthorityStatus,
    PITSourceQualification,
    PITValidationOutcome,
    RecordedPITFactRevision,
    formal_pit_request_rejection_codes,
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

    def __init__(self, factory: Any, *, clock: Clock | None = None) -> None:
        super().__init__(factory)
        self._clock = clock or _utc_now

    def current_revision(self) -> int:
        with self._connect() as connection:
            return _current_revision(connection)

    def record_source_qualification(
        self,
        qualification: PITSourceQualification,
        *,
        idempotency_key: str,
    ) -> PITSourceQualification:
        payload = qualification.to_canonical_dict()
        command_hash = canonical_hash(payload)
        admitted_at = _whole_second(self._clock())
        if admitted_at < qualification.recorded_at:
            raise PITAuthorityConflictError(
                "source qualification cannot be admitted before it was recorded"
            )
        source_identity = (
            f"{qualification.source_manifest.artifact_id}:"
            f"{qualification.provider_id}:{qualification.provider_contract}"
        )
        with self._connect() as connection:
            acquire_scope_lock(
                connection,
                namespace="pit-source-qualification",
                identity=source_identity,
            )
            _acquire_revision_lock(connection)
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
                )
                connection.execute(
                    """
                    INSERT INTO pit_source_qualification(
                        qualification_id, qualification_hash,
                        source_manifest_id, source_manifest_hash, provider_id,
                        provider_contract, status, source_revision,
                        supersedes_qualification_id, authority_revision,
                        effective_at, recorded_at, payload_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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
                        qualification.effective_at,
                        qualification.recorded_at,
                        _json(payload),
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
        ingested_at = _whole_second(self._clock())
        if ingested_at < fact.recorded_at:
            raise PITAuthorityConflictError(
                "PIT fact cannot be ingested before its recorded time"
            )
        with self._connect() as connection:
            acquire_scope_lock(
                connection,
                namespace="pit-fact",
                identity=f"{fact.scope_id}:{fact.logical_key}",
            )
            _acquire_revision_lock(connection)
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
                if fact.data_eligibility is DataEligibility.FORMAL_RESEARCH:
                    _verify_formal_source_authority(
                        connection,
                        fact=fact,
                        ingested_at=ingested_at,
                    )
                authority_revision = _insert_action(
                    connection,
                    action_type="RECORD_FACT",
                    aggregate_id=str(fact.fact_id),
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                    payload=command_payload,
                    actor=actor,
                    reason=reason,
                    created_at=ingested_at,
                )
                connection.execute(
                    """
                    INSERT INTO pit_fact_revision(
                        fact_id, content_hash, scope_id, logical_key, fact_kind,
                        subject, fact_revision, supersedes_fact_id,
                        authority_revision, event_time, effective_from,
                        effective_to, available_at, recorded_at, ingested_at,
                        artifact_id, artifact_hash, source_manifest_id,
                        source_manifest_hash,
                        provider_id, provider_contract, data_eligibility,
                        value_json, payload_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        str(fact.fact_id), fact.content_hash, fact.scope_id,
                        fact.logical_key, fact.fact_kind.value, fact.subject,
                        fact.revision,
                        str(fact.supersedes_fact_id) if fact.supersedes_fact_id else None,
                        authority_revision, fact.event_time, fact.effective_from,
                        fact.effective_to, fact.available_at, fact.recorded_at,
                        ingested_at,
                        str(fact.artifact.artifact_id), fact.artifact.content_hash,
                        str(fact.source_manifest.artifact_id),
                        fact.source_manifest.content_hash, fact.provider_id,
                        fact.provider_contract, fact.data_eligibility.value,
                        fact.value_json, _json(fact.to_canonical_dict()),
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
        with self._connect() as connection:
            current_revision = _current_revision(connection)
            revision = query.authority_revision or current_revision
            if revision <= 0:
                raise PITAuthorityIntegrityError("PIT authority has no revision")
            if revision > current_revision:
                raise PITAuthorityIntegrityError(
                    "PIT authority revision is newer than current authority"
                )
            return _as_of(connection, query, revision)

    def validate(
        self, request: FormalPITValidationRequest
    ) -> FormalPITEvidenceArtifact:
        command_hash = canonical_hash(
            {"schema_version": "formal-pit-validation-command-v1", "request": request.to_canonical_dict()}
        )
        with self._connect() as connection:
            _acquire_revision_lock(connection)
            try:
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
                evidence, snapshot, selected = _evaluate(
                    connection,
                    request=request,
                    authority_revision=cutoff,
                    recorded_at=_whole_second(self._clock()),
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
                "SELECT request_json, payload_json FROM formal_pit_validation_evidence "
                "WHERE evidence_id = %s",
                (str(evidence_id),),
            ).fetchone()
            if row is None:
                raise KeyError(str(evidence_id))
            original = FormalPITEvidenceArtifact.from_canonical_dict(_object(row["payload_json"]))
            request = FormalPITValidationRequest.from_canonical_dict(_object(row["request_json"]))
            replayed, _, _ = _evaluate(
                connection,
                request=request,
                authority_revision=original.authority_revision,
                recorded_at=original.recorded_at,
            )
            if replayed != original:
                raise PITAuthorityIntegrityError("Formal PIT replay differs from stored evidence")
            return replayed


def _evaluate(
    connection: PostgresConnection,
    *,
    request: FormalPITValidationRequest,
    authority_revision: int,
    recorded_at: datetime,
) -> tuple[FormalPITEvidenceArtifact, PITAsOfSnapshot, tuple[RecordedPITFactRevision, ...]]:
    query = PITAsOfQuery.create(
        scope_id=request.scope_id,
        decision_time=request.decision_time,
        required_facts=request.required_facts,
        authority_revision=authority_revision,
    )
    snapshot = _as_of(connection, query, authority_revision)
    selected = tuple(
        _load_fact(connection, fact_id)
        for fact_id, _ in snapshot.selected_fact_references
    )
    reasons = set(snapshot.rejection_codes)
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
    required_by_key = {item.logical_key: item for item in query.required_facts}
    keys = tuple(required_by_key)
    rows: list[dict[str, Any]] = []
    if keys:
        rows = connection.execute(
            """
            SELECT DISTINCT ON (logical_key)
                fact_id, payload_json, authority_revision, ingested_at
            FROM pit_fact_revision
            WHERE scope_id = %s
              AND logical_key = ANY(%s)
              AND authority_revision <= %s
              AND event_time <= %s
              AND effective_from <= %s
              AND (effective_to IS NULL OR %s < effective_to)
              AND available_at <= %s
              AND recorded_at <= %s
              AND ingested_at <= %s
            ORDER BY logical_key, fact_revision DESC, authority_revision DESC
            """,
            (
                query.scope_id, list(keys), authority_revision,
                query.decision_time, query.decision_time, query.decision_time,
                query.decision_time, query.decision_time, query.decision_time,
            ),
        ).fetchall()
    selected: dict[str, RecordedPITFactRevision] = {}
    for row in rows:
        recorded = _recorded_from_row(row)
        selected[recorded.fact.logical_key] = recorded
    reasons: set[str] = set()
    for key, required in required_by_key.items():
        found = selected.get(key)
        if found is None:
            reasons.add(_missing_reason(connection, query, required, authority_revision))
        elif found.fact.fact_kind is not required.fact_kind or found.fact.subject != required.subject:
            reasons.add(f"FACT_SCOPE_MISMATCH:{key}")
    references = tuple((item.fact.fact_id, item.fact.content_hash) for item in selected.values())
    return PITAsOfSnapshot.create(
        query_hash=query.query_hash,
        scope_id=query.scope_id,
        decision_time=query.decision_time,
        authority_revision=authority_revision,
        outcome=PITValidationOutcome.REJECTED if reasons else PITValidationOutcome.SATISFIED,
        selected_fact_references=references,
        rejection_codes=tuple(sorted(reasons)),
    )


def _missing_reason(
    connection: PostgresConnection,
    query: PITAsOfQuery,
    required: PITRequiredFact,
    authority_revision: int,
) -> str:
    row = connection.execute(
        "SELECT event_time, effective_from, effective_to, available_at, "
        "recorded_at, ingested_at, fact_kind, subject FROM pit_fact_revision "
        "WHERE scope_id = %s AND logical_key = %s AND authority_revision <= %s "
        "ORDER BY fact_revision DESC LIMIT 1",
        (query.scope_id, required.logical_key, authority_revision),
    ).fetchone()
    suffix = required.logical_key
    if row is None:
        return f"FACT_MISSING:{suffix}"
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
    if aware_datetime(row["ingested_at"], label="ingested_at") > query.decision_time:
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


def _verify_formal_source_authority(
    connection: PostgresConnection,
    *,
    fact: PITFactRevision,
    ingested_at: datetime,
) -> None:
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
            ingested_at,
            ingested_at,
            ingested_at,
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
        or qualification.effective_at > ingested_at
        or qualification.recorded_at > ingested_at
        or action_time > ingested_at
    ):
        raise PITAuthorityConflictError(
            "FORMAL_RESEARCH fact source is not qualified at ingest time"
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
        "SELECT payload_json, authority_revision, ingested_at "
        "FROM pit_fact_revision WHERE fact_id = %s",
        (str(fact_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(fact_id))
    return _recorded_from_row(row)


def _recorded_from_row(row: Mapping[str, Any]) -> RecordedPITFactRevision:
    return RecordedPITFactRevision(
        fact=PITFactRevision.from_canonical_dict(_object(row["payload_json"])),
        authority_revision=int(row["authority_revision"]),
        ingested_at=aware_datetime(row["ingested_at"], label="ingested_at"),
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


def _acquire_revision_lock(connection: PostgresConnection) -> None:
    acquire_scope_lock(connection, namespace="pit-authority-revision", identity="global")


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
) -> int:
    row = connection.execute(
        "INSERT INTO pit_authority_action(action_type, aggregate_id, "
        "idempotency_key, command_hash, payload_json, actor, reason, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
        "RETURNING authority_revision",
        (
            action_type, aggregate_id, idempotency_key, command_hash,
            _json(payload), actor, reason, created_at,
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
