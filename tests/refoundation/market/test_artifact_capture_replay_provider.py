from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from market_regime_alpha.infrastructure.providers.artifact_capture_replay import (
    ArtifactCaptureReplayEntry,
    ArtifactCaptureReplayProvider,
)
from market_regime_alpha.market.domain import SourceAvailabilityStatus
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


def _request(*, resource: str = '{"kind":"TRADE_DATES"}') -> CaptureRequest:
    return CaptureRequest(
        provider_product_id=uuid4(),
        capture_key="qualification_archive/0001",
        resource=resource,
        request_headers_hash=ContentHash(sha256(b"").hexdigest()),
    )


def _entry(request: CaptureRequest, content: bytes) -> ArtifactCaptureReplayEntry:
    digest = sha256(content).hexdigest()
    return ArtifactCaptureReplayEntry(
        capture_key=request.capture_key,
        request_sha256=canonical_json_sha256(request),
        content_sha256=ContentHash(digest),
        size_bytes=len(content),
        media_type="application/json",
        payload_encoding="UTF-8",
        locator=f"objects/{digest[:2]}/{digest}",
        limitation_code="HISTORICAL_AVAILABILITY_AND_FINALITY_UNKNOWN",
    )


def _write(root: Path, entry: ArtifactCaptureReplayEntry, content: bytes) -> None:
    path = root / entry.locator
    path.parent.mkdir(parents=True)
    path.write_bytes(content)


def test_replays_exact_content_only_for_the_frozen_request(tmp_path: Path) -> None:
    request = _request()
    content = b'{"rows":[]}\n'
    entry = _entry(request, content)
    _write(tmp_path, entry, content)

    response = ArtifactCaptureReplayProvider(tmp_path, (entry,)).capture(request)

    assert response.content == content
    assert response.source_availability_status is SourceAvailabilityStatus.UNKNOWN
    assert response.source_available_at is None
    assert response.provider_time is None
    assert response.limitation_code == "HISTORICAL_AVAILABILITY_AND_FINALITY_UNKNOWN"


def test_replay_rejects_request_or_bytes_mismatch(tmp_path: Path) -> None:
    request = _request()
    content = b'{"rows":[]}\n'
    entry = _entry(request, content)
    _write(tmp_path, entry, b"tampered")
    provider = ArtifactCaptureReplayProvider(tmp_path, (entry,))

    with pytest.raises(ValueError, match="request differs"):
        provider.capture(_request(resource='{"kind":"STOCK_BASIC"}'))
    with pytest.raises(ValueError, match="content differs"):
        provider.capture(request)


def test_replay_roster_rejects_duplicate_keys_and_unsafe_locators(tmp_path: Path) -> None:
    request = _request()
    entry = _entry(request, b"payload")

    with pytest.raises(ValueError, match="unique"):
        ArtifactCaptureReplayProvider(tmp_path, (entry, entry))
    with pytest.raises(ValueError, match="locator"):
        ArtifactCaptureReplayProvider(
            tmp_path,
            (
                ArtifactCaptureReplayEntry(
                    capture_key=entry.capture_key,
                    request_sha256=entry.request_sha256,
                    content_sha256=entry.content_sha256,
                    size_bytes=entry.size_bytes,
                    media_type=entry.media_type,
                    payload_encoding=entry.payload_encoding,
                    locator="../escape",
                    limitation_code=entry.limitation_code,
                ),
            ),
        )
