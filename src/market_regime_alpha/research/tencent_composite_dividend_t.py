"""Compatibility facade for the isolated Tencent/dividend-T Legacy adapter."""

from market_regime_alpha.migration.legacy.adapters.tencent_dividend_t import (
    COMPOSITE_DATA_SOURCE,
    DIFF_FIELDS,
    CompositeFrameProvider,
    DividendTRefreshResult,
    compare_dividend_snapshots,
    refresh_dividend_t_from_composite,
)


__all__ = [
    "COMPOSITE_DATA_SOURCE",
    "DIFF_FIELDS",
    "CompositeFrameProvider",
    "DividendTRefreshResult",
    "compare_dividend_snapshots",
    "refresh_dividend_t_from_composite",
]
