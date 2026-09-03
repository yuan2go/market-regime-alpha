"""Stable public ports for the Market/PIT bounded context."""

from market_regime_alpha.market.ports.archive import (
    ArchiveRepository,
    ArchiveSliceGapRecord,
    ArchiveUnitOfWork,
    ArchiveUnitOfWorkProvider,
)
from market_regime_alpha.market.ports.provider import (
    CaptureRequest,
    MarketArtifactByteStore,
    MarketDatabaseClock,
    MarketNormalizer,
    MarketProvider,
    MarketProviderError,
    NormalizerContract,
    ProviderResponse,
)
from market_regime_alpha.market.ports.revision_lineage import (
    InstrumentFactRevisionHead,
    MarketBarRevisionHead,
    MarketRevisionLineageReadPort,
)
from market_regime_alpha.market.ports.archive_inspection import (
    ArchiveInspection,
    ArchiveInspectionPort,
    ArchiveSliceInspection,
    ArchiveVerification,
    ArchiveVerificationPort,
)
from market_regime_alpha.market.ports.session_roster import (
    ArchiveTradingSession,
    ArchiveTradingSessionReadPort,
)
from market_regime_alpha.market.ports.archive_operations import (
    ArchiveCaptureDisposition,
    ArchiveOperationsReadPort,
    ArchiveResourceInspector,
    ArchiveSliceOperatingContract,
)
from market_regime_alpha.market.ports.queries import (
    MarketQueries,
    MarketQueryProvider,
)
from market_regime_alpha.market.ports.repository import (
    CaptureSource,
    MarketRepository,
)
from market_regime_alpha.market.ports.uow import (
    MarketArtifactRepository,
    MarketUnitOfWork,
    MarketUnitOfWorkProvider,
)
from market_regime_alpha.market.ports.provider_qualification import (
    ProviderQualificationDecisionRecord,
    ProviderQualificationProtocolRecord,
    ProviderQualificationRepository,
    ProviderQualificationUnitOfWork,
    ProviderQualificationUnitOfWorkProvider,
    QualifiedHistoricalVisibilityRecord,
)
from market_regime_alpha.market.ports.provider_qualification_queries import (
    ProviderQualificationQueryPort,
    ProviderQualificationVerification,
)

__all__ = [
    "ArchiveRepository",
    "ArchiveSliceGapRecord",
    "ArchiveUnitOfWork",
    "ArchiveUnitOfWorkProvider",
    "CaptureRequest",
    "ArchiveCaptureDisposition",
    "ArchiveOperationsReadPort",
    "ArchiveInspection",
    "ArchiveInspectionPort",
    "ArchiveSliceInspection",
    "ArchiveVerification",
    "ArchiveVerificationPort",
    "ArchiveTradingSession",
    "ArchiveTradingSessionReadPort",
    "ArchiveResourceInspector",
    "ArchiveSliceOperatingContract",
    "CaptureSource",
    "MarketArtifactByteStore",
    "MarketArtifactRepository",
    "MarketDatabaseClock",
    "InstrumentFactRevisionHead",
    "MarketBarRevisionHead",
    "MarketRevisionLineageReadPort",
    "MarketNormalizer",
    "MarketProvider",
    "MarketProviderError",
    "MarketQueries",
    "MarketQueryProvider",
    "MarketRepository",
    "MarketUnitOfWork",
    "MarketUnitOfWorkProvider",
    "NormalizerContract",
    "ProviderQualificationDecisionRecord",
    "ProviderQualificationQueryPort",
    "ProviderQualificationProtocolRecord",
    "ProviderQualificationRepository",
    "ProviderQualificationUnitOfWork",
    "ProviderQualificationUnitOfWorkProvider",
    "ProviderQualificationVerification",
    "QualifiedHistoricalVisibilityRecord",
    "ProviderResponse",
]
