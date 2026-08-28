"""Target-only Market Provider adapters."""

from market_regime_alpha.infrastructure.providers.baostock import BaoStockHistoryProvider
from market_regime_alpha.infrastructure.providers.tencent import TencentQuoteProvider

__all__ = ["BaoStockHistoryProvider", "TencentQuoteProvider"]
