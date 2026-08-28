"""Tencent exploratory quote capture preserving the exact HTTP response bytes."""

from __future__ import annotations

from collections.abc import Callable

from market_regime_alpha.market.domain import SourceAvailabilityStatus
from market_regime_alpha.market.ports import (
    CaptureRequest,
    MarketProviderError,
    ProviderResponse,
)


class TencentQuoteProvider:
    """Network adapter with an injectable byte transport and no PIT promotion."""

    def __init__(self, transport: Callable[[str], bytes]) -> None:
        self._transport = transport

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        try:
            content = self._transport(request.resource)
        except Exception as exc:
            raise MarketProviderError(
                "TENCENT_TRANSPORT_FAILED",
                "Tencent quote transport failed",
                retryable=True,
            ) from exc
        if not isinstance(content, bytes) or not content:
            raise MarketProviderError(
                "TENCENT_EMPTY_RESPONSE",
                "Tencent quote response was not non-empty exact bytes",
                retryable=True,
            )
        try:
            content.decode("gb18030")
        except UnicodeDecodeError as exc:
            raise MarketProviderError(
                "TENCENT_INVALID_GB18030",
                "Tencent quote bytes are not valid GB18030",
                retryable=False,
            ) from exc
        return ProviderResponse(
            content=content,
            media_type="text/plain",
            payload_encoding="GB18030",
            provider_time=None,
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            limitation_code=None,
        )


__all__ = ["TencentQuoteProvider"]
