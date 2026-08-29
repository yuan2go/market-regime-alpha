"""Row-to-domain mapping for Market write-side reloads."""

from typing import Any
from uuid import UUID

from market_regime_alpha.market.domain import (
    CaptureStatus,
    ProviderCapture,
    SourceAvailabilityStatus,
    TemporalEnvelope,
)
from market_regime_alpha.market.ports import CaptureSource
from market_regime_alpha.runtime.ports import ArtifactRecord
from market_regime_alpha.shared.identity import ContentHash


def _capture_source(row: tuple[Any, ...]) -> CaptureSource:

    capture = ProviderCapture(
        capture_id=UUID(str(row[0])),
        provider_product_id=UUID(str(row[1])),
        capture_key=str(row[2]),
        request_hash=ContentHash(str(row[3])),
        status=CaptureStatus(str(row[4])),
        temporal=TemporalEnvelope(
            provider_time=row[5],
            source_availability_status=SourceAvailabilityStatus(str(row[6])),
            source_available_at=row[7],
            capture_started_at=row[8],
            capture_completed_at=row[9],
            known_at=row[10],
            decision_visible_at=row[11],
        ),
        artifact_id=UUID(str(row[12])) if row[12] is not None else None,
        error_code=str(row[13]) if row[13] is not None else None,
        limitation_code=str(row[14]) if row[14] is not None else None,
        payload_encoding=str(row[15]) if row[15] is not None else None,
    )
    artifact = None
    if row[12] is not None:
        artifact = ArtifactRecord(
            artifact_id=UUID(str(row[12])),
            content_sha256=str(row[16]),
            size_bytes=int(row[17]),
            media_type=str(row[18]),
            locator=str(row[19]),
            integrity_state=str(row[20]),
            retention_until=row[21],
            pin_reason_code=str(row[22]) if row[22] is not None else None,
        )
    return CaptureSource(capture=capture, artifact=artifact)
