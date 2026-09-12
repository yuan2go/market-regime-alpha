"""Reload recorded protocol and raw bytes from the original Capture Artifact."""

from typing import Any
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.recorded_professional_provider import replay_professional_capture
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


def replay_recorded_capture(pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore, capture_id: UUID) -> dict[str,Any]:
    with pool.connection(read_only=True) as connection:
        row=connection.execute("""SELECT capture.provider_product_id,capture.request_hash,capture.capture_started_at,
            capture.capture_completed_at,capture.source_available_at,capture.source_availability_status,
            artifact.artifact_id,artifact.content_sha256,artifact.size_bytes,
            mra.market_artifact_is_readable(artifact.integrity_state,artifact.last_verified_at),capture.capture_key
            FROM mra.data_capture capture JOIN mra.artifact artifact USING(artifact_id)
            WHERE capture.capture_id=%s AND capture.status='CAPTURED'""",(capture_id,)).fetchone()
    if row is None or not row[9] or row[4] is not None or row[5]!="UNKNOWN":
        raise ArtifactIntegrityError("recorded Capture owner or availability contract differs")
    if row[8]>134_000_000 or byte_store.verify(row[7],expected_size=row[8]).result!="VERIFIED":
        raise ArtifactIntegrityError("recorded Capture physical bytes are not exact")
    contract,recording,verification=replay_professional_capture(byte_store.read_bytes(row[7],expected_size=row[8]))
    request=verification.get("capture_request",{})
    if (verification.get("capture_request_sha256")!=row[1] or request.get("provider_product_id")!=str(row[0])
            or request.get("capture_key")!=row[10]):
        raise ArtifactIntegrityError("recorded Capture original request identity differs or is unverified")
    verification["capture_request_identity"]="MATCHED_ORIGINAL_CAPTURE_OWNER"
    from dataclasses import asdict
    from hashlib import sha256
    return {"capture_id":capture_id,"provider_product_id":row[0],"request_sha256":row[1],
        "capture_started_at":row[2],"capture_completed_at":row[3],"source_available_at":None,
        "artifact_id":row[6],"capture_content_sha256":row[7],"recording_sha256":sha256(recording).hexdigest(),
        "contract":asdict(contract),"verification":verification,"business_writes":0}
