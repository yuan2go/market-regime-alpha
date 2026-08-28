from __future__ import annotations

import json
from uuid import uuid4

from market_regime_alpha.infrastructure.providers.baostock import (
    BaoStockHistoryProvider,
    BaoStockQueryResult,
)
from market_regime_alpha.infrastructure.providers.tencent import TencentQuoteProvider
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.market.domain import SourceAvailabilityStatus


def _request(resource: str) -> CaptureRequest:
    return CaptureRequest(
        provider_product_id=uuid4(),
        capture_key="capture-2026-08-28-1455",
        resource=resource,
        request_headers_hash="a" * 64,
    )


def test_tencent_adapter_preserves_exact_response_bytes_without_claiming_pit_authority() -> None:
    exact = b'v_sh601919="1~COSCO~601919~15.32~";\n'
    observed: list[str] = []

    def transport(resource: str) -> bytes:
        observed.append(resource)
        return exact

    adapter = TencentQuoteProvider(transport)
    response = adapter.capture(_request("https://qt.gtimg.cn/q=sh601919"))

    assert observed == ["https://qt.gtimg.cn/q=sh601919"]
    assert response.content == exact
    assert response.media_type == "text/plain"
    assert response.payload_encoding == "GB18030"
    assert response.source_availability_status is SourceAvailabilityStatus.UNKNOWN
    assert response.source_available_at is None
    assert response.authority_ceiling == "EXPLORATORY_UNQUALIFIED"


def test_baostock_adapter_canonicalizes_library_rows_but_never_invents_available_time() -> None:
    def query(resource: str) -> BaoStockQueryResult:
        assert resource == "sh.601919?date=2026-08-28"
        return BaoStockQueryResult(
            fields=("date", "code", "open", "high", "low", "close", "volume"),
            rows=(("2026-08-28", "sh.601919", "15.10", "15.40", "15.00", "15.32", "0"),),
            error_code="0",
            error_message="success",
        )

    adapter = BaoStockHistoryProvider(query)
    response = adapter.capture(_request("sh.601919?date=2026-08-28"))
    payload = json.loads(response.content)

    assert payload["fields"] == ["date", "code", "open", "high", "low", "close", "volume"]
    assert payload["rows"][0][5] == "15.32"
    assert response.source_availability_status is SourceAvailabilityStatus.UNKNOWN
    assert response.source_available_at is None
    assert response.limitation_code == "HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED"
    assert response.authority_ceiling == "EXPLORATORY_UNQUALIFIED"


def test_baostock_canonical_bytes_are_deterministic() -> None:
    result = BaoStockQueryResult(
        fields=("code", "close"),
        rows=(("sh.601919", "15.32"),),
        error_code="0",
        error_message="success",
    )
    adapter = BaoStockHistoryProvider(lambda _: result)
    first = adapter.capture(_request("one")).content
    second = adapter.capture(_request("two")).content
    assert first == second
    assert first.endswith(b"\n")
