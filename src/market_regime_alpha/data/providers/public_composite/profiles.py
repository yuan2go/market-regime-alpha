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
    PublicCompositeProviderResult,
    PublicCompositeRequest,
)
from market_regime_alpha.data.providers.public_composite.replay_archive import (
    AcquiredReplaySource,
    SourceReplayArchiveReader,
)


@dataclass(frozen=True, slots=True)
class PublicCompositeLiveProfile:
    """BaoStock history plus Tencent current data, with no fallback seam."""

    history_client: PublicAcquisitionClient
    current_client: PublicAcquisitionClient
    profile_id: str = PUBLIC_COMPOSITE_LIVE_PROFILE_ID

    def acquire(
        self,
        request: PublicCompositeRequest,
    ) -> PublicCompositeProviderResult:
        history = self.history_client.acquire(request)
        current = self.current_client.acquire(request)
        if any(
            item.provider_id != BAOSTOCK_PUBLIC_PROVIDER_ID
            for item in history.raw_payloads
        ):
            raise ValueError("LIVE history must come only from declared BaoStock")
        if any(
            item.provider_id != TENCENT_PUBLIC_PROVIDER_ID
            for item in current.raw_payloads
        ):
            raise ValueError("LIVE current data must come only from declared Tencent")
        return PublicCompositeProviderResult(
            profile_id=self.profile_id,
            decision_time=request.decision_time,
            raw_payloads=(*history.raw_payloads, *current.raw_payloads),
            bars=(*history.bars, *current.bars),
            quotes=(*history.quotes, *current.quotes),
            source_conflicts=(
                *history.source_conflicts,
                *current.source_conflicts,
            ),
            limitations=(
                *history.limitations,
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
