"""Strict public composite LIVE and offline REPLAY provider profiles."""

from .contracts import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1,
    PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
    PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
    TENCENT_PUBLIC_PROVIDER_ID,
    AcquiredSourcePayload,
    PublicBar,
    PublicCompositeBatch,
    PublicCompositeProviderResult,
    PublicCompositeRequest,
    PublicQuote,
    TradingStatus,
)
from .live_clients import BaoStockHistoryClient, TencentCurrentQuoteClient
from .manifest_builder import (
    DailyControlSourceEvidence,
    build_daily_control_source_evidence,
    build_public_source_manifest,
)
from .profiles import (
    PublicCompositeAcquisitionError,
    PublicCompositeLiveProfile,
    PublicCompositeReplayProfile,
)
from .replay_archive import (
    AcquiredReplaySource,
    SourceReplayArchiveReader,
    publish_source_archive,
    publish_source_replay_archive,
    source_archive_id,
)
from .stage_artifact import (
    PublicSourceAcquisitionStage,
    VerifiedPublicSourceStageArtifact,
    load_verified_public_source_stage_artifact,
    publish_public_source_stage_artifact,
)

__all__ = [
    "BAOSTOCK_PUBLIC_PROVIDER_ID",
    "HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1",
    "PUBLIC_COMPOSITE_LIVE_PROFILE_ID",
    "PUBLIC_COMPOSITE_REPLAY_PROFILE_ID",
    "TENCENT_PUBLIC_PROVIDER_ID",
    "AcquiredReplaySource",
    "AcquiredSourcePayload",
    "BaoStockHistoryClient",
    "PublicBar",
    "PublicCompositeBatch",
    "PublicCompositeAcquisitionError",
    "PublicCompositeLiveProfile",
    "PublicCompositeProviderResult",
    "PublicCompositeReplayProfile",
    "PublicCompositeRequest",
    "PublicQuote",
    "SourceReplayArchiveReader",
    "TencentCurrentQuoteClient",
    "TradingStatus",
    "build_public_source_manifest",
    "build_daily_control_source_evidence",
    "DailyControlSourceEvidence",
    "publish_source_archive",
    "publish_source_replay_archive",
    "source_archive_id",
    "PublicSourceAcquisitionStage",
    "VerifiedPublicSourceStageArtifact",
    "load_verified_public_source_stage_artifact",
    "publish_public_source_stage_artifact",
]
