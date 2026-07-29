"""Strict LIVE and REPLAY public composite profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.providers.public_composite.contracts import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
    PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
    TENCENT_PUBLIC_PROVIDER_ID,
    PublicAcquisitionClient,
    PublicCompositeBatch,
    PublicCompositeProviderResult,
    PublicCompositeRequest,
)
from market_regime_alpha.data.providers.public_composite.replay_archive import (
    AcquiredReplaySource,
    SourceReplayArchiveReader,
)
from market_regime_alpha.data_sources.a_share_bars import AShareDataError


class PublicCompositeAcquisitionError(AShareDataError):
    """Expected LIVE failure carrying every successfully acquired partial byte."""

    def __init__(
        self,
        message: str,
        *,
        partial_batch: PublicCompositeBatch,
    ) -> None:
        super().__init__(message)
        self.partial_batch = partial_batch


@dataclass(frozen=True, slots=True)
class PublicCompositeLiveProfile:
    """BaoStock history plus Tencent current data, with no fallback seam."""

    history_client: PublicAcquisitionClient
    current_client: PublicAcquisitionClient
    security_status_client: PublicAcquisitionClient | None = None
    profile_id: str = PUBLIC_COMPOSITE_LIVE_PROFILE_ID

    def acquire(
        self,
        request: PublicCompositeRequest,
    ) -> PublicCompositeProviderResult:
        history = self.acquire_history(request)
        try:
            status = self.acquire_security_status(request)
            current = self.acquire_current(request)
        except AShareDataError as exc:
            raise PublicCompositeAcquisitionError(
                f"decision acquisition failed after history freeze: {exc}",
                partial_batch=history,
            ) from exc
        return self.compose(
            history=history,
            security_status=status,
            current=current,
            request=request,
        )

    def acquire_history(
        self,
        request: PublicCompositeRequest,
    ) -> PublicCompositeBatch:
        """Acquire only declared BaoStock history."""

        history = self.history_client.acquire(request)
        if any(
            item.provider_id != BAOSTOCK_PUBLIC_PROVIDER_ID
            for item in history.raw_payloads
        ):
            raise ValueError("LIVE history must come only from declared BaoStock")
        return history

    def acquire_current(
        self,
        request: PublicCompositeRequest,
    ) -> PublicCompositeBatch:
        """Acquire only declared Tencent decision quotes."""

        current = self.current_client.acquire(request)
        if any(
            item.provider_id != TENCENT_PUBLIC_PROVIDER_ID
            for item in current.raw_payloads
        ):
            raise ValueError("LIVE current data must come only from declared Tencent")
        return current

    def acquire_security_status(
        self,
        request: PublicCompositeRequest,
    ) -> PublicCompositeBatch:
        """Acquire exact-date BaoStock status without prior-session promotion."""

        if self.security_status_client is None:
            raise AShareDataError("LIVE security status client is not configured")
        status = self.security_status_client.acquire(request)
        if any(
            item.provider_id != BAOSTOCK_PUBLIC_PROVIDER_ID
            for item in status.raw_payloads
        ):
            raise ValueError(
                "LIVE security status must come only from declared BaoStock"
            )
        return status

    def compose(
        self,
        *,
        history: PublicCompositeBatch,
        current: PublicCompositeBatch,
        request: PublicCompositeRequest,
        security_status: PublicCompositeBatch | None = None,
    ) -> PublicCompositeProviderResult:
        """Compose already-frozen stages without invoking either client."""

        status = security_status
        return PublicCompositeProviderResult(
            profile_id=self.profile_id,
            decision_time=request.decision_time,
            raw_payloads=(
                *history.raw_payloads,
                *(status.raw_payloads if status is not None else ()),
                *current.raw_payloads,
            ),
            bars=(*history.bars, *current.bars),
            quotes=(*history.quotes, *current.quotes),
            source_conflicts=(
                *history.source_conflicts,
                *(status.source_conflicts if status is not None else ()),
                *current.source_conflicts,
            ),
            limitations=(
                *history.limitations,
                *(status.limitations if status is not None else ()),
                *current.limitations,
                "PUBLIC_DATA_EXPLORATORY_ONLY",
                "NO_LOCAL_ARCHIVE_FALLBACK",
            ),
        )


@dataclass(frozen=True, slots=True)
class PublicCompositeReplayProfile:
    """Offline profile that has no acquisition/network client dependency."""

    archive_reader: SourceReplayArchiveReader = SourceReplayArchiveReader()
    profile_id: str = PUBLIC_COMPOSITE_REPLAY_PROFILE_ID

    def acquire(
        self,
        *,
        archive_path: Path,
        expected_source_manifest_id: ArtifactId,
    ) -> AcquiredReplaySource:
        acquired = self.archive_reader.read(archive_path)
        if acquired.source_manifest.source_manifest_id != expected_source_manifest_id:
            raise ValueError("SourceManifest identity does not match replay request")
        return acquired
