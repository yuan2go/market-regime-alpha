"""Fail-closed Provider adapter over immutable content-addressed captures."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath

from market_regime_alpha.market.domain import SourceAvailabilityStatus
from market_regime_alpha.market.ports import CaptureRequest, ProviderResponse
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


@dataclass(frozen=True, slots=True)
class ArtifactCaptureReplayEntry:
    """Exact source bytes and request identity for one immutable capture."""

    capture_key: str
    request_sha256: ContentHash | str
    content_sha256: ContentHash | str
    size_bytes: int
    media_type: str
    payload_encoding: str
    locator: str
    limitation_code: str

    def __post_init__(self) -> None:
        if not self.capture_key:
            raise ValueError("replay capture_key is required")
        object.__setattr__(
            self,
            "request_sha256",
            ContentHash(str(self.request_sha256)),
        )
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(str(self.content_sha256)),
        )
        if isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ValueError("replay size_bytes must be non-negative")
        if not self.media_type or not self.payload_encoding:
            raise ValueError("replay media type and payload encoding are required")
        if not self.limitation_code:
            raise ValueError("replay limitation_code is required")
        path = PurePosixPath(self.locator)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("replay locator must be a safe relative path")


class ArtifactCaptureReplayProvider:
    """Serve source Artifact bytes only when request and bytes reconcile exactly."""

    def __init__(
        self,
        artifact_root: Path,
        entries: tuple[ArtifactCaptureReplayEntry, ...],
    ) -> None:
        if not entries or len({item.capture_key for item in entries}) != len(entries):
            raise ValueError("replay capture keys must be non-empty and unique")
        self._artifact_root = artifact_root.resolve()
        self._entries = {item.capture_key: item for item in entries}

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        entry = self._entries.get(request.capture_key)
        if entry is None or str(entry.request_sha256) != canonical_json_sha256(request):
            raise ValueError("replay request differs from the frozen source roster")
        path = (self._artifact_root / entry.locator).resolve()
        if not path.is_relative_to(self._artifact_root):
            raise ValueError("replay locator escapes the Artifact root")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ValueError("replay Artifact bytes are unavailable") from exc
        if (
            len(content) != entry.size_bytes
            or sha256(content).hexdigest() != str(entry.content_sha256)
        ):
            raise ValueError("replay Artifact content differs from the frozen source")
        return ProviderResponse(
            content=content,
            media_type=entry.media_type,
            payload_encoding=entry.payload_encoding,
            provider_time=None,
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            limitation_code=entry.limitation_code,
        )


__all__ = ["ArtifactCaptureReplayEntry", "ArtifactCaptureReplayProvider"]
