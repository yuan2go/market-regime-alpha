"""BaoStock exploratory history capture without invented availability semantics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json

from market_regime_alpha.market.domain import SourceAvailabilityStatus
from market_regime_alpha.market.ports import (
    CaptureRequest,
    MarketProviderError,
    ProviderResponse,
)


@dataclass(frozen=True, slots=True)
class BaoStockQueryResult:
    fields: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    error_code: str
    error_message: str


class BaoStockHistoryProvider:
    """Canonicalize a library result while preserving its evidence limitation."""

    def __init__(self, query: Callable[[str], BaoStockQueryResult]) -> None:
        self._query = query

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        try:
            result = self._query(request.resource)
        except Exception as exc:
            raise MarketProviderError(
                "BAOSTOCK_TRANSPORT_FAILED",
                "BaoStock history query failed",
                retryable=True,
            ) from exc
        if result.error_code != "0":
            raise MarketProviderError(
                "BAOSTOCK_PROVIDER_ERROR",
                f"BaoStock returned error {result.error_code}: {result.error_message}",
                retryable=True,
            )
        if any(len(row) != len(result.fields) for row in result.rows):
            raise MarketProviderError(
                "BAOSTOCK_ROW_SHAPE_INVALID",
                "BaoStock row width does not match its field catalog",
                retryable=False,
            )
        content = (
            json.dumps(
                {
                    "error_code": result.error_code,
                    "error_message": result.error_message,
                    "fields": result.fields,
                    "rows": result.rows,
                },
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        return ProviderResponse(
            content=content,
            media_type="application/json",
            payload_encoding="UTF-8",
            provider_time=None,
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            limitation_code="HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED",
        )


__all__ = ["BaoStockHistoryProvider", "BaoStockQueryResult"]
