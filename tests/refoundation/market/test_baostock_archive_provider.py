from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

import pytest

from market_regime_alpha.infrastructure.providers.baostock_archive import (
    BaoStockArchiveProvider,
    BaoStockArchiveQuery,
    BaoStockArchiveQueryKind,
    BaoStockSession,
)
from market_regime_alpha.market.domain import SourceAvailabilityStatus
from market_regime_alpha.market.ports import CaptureRequest, MarketProviderError


@dataclass
class _SdkResult:
    fields: list[str]
    rows: list[list[str]]
    error_code: str = "0"
    error_msg: str = "success"
    _index: int = -1

    def next(self) -> bool:
        self._index += 1
        return self._index < len(self.rows)

    def get_row_data(self) -> list[str]:
        return self.rows[self._index]


@dataclass(frozen=True)
class _Status:
    error_code: str
    error_msg: str


class _Sdk:
    def __init__(self, result: _SdkResult, *, login_code: str = "0") -> None:
        self.result = result
        self.login_code = login_code
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def login(self) -> _Status:
        self.calls.append(("login", (), {}))
        return _Status(self.login_code, "login failed" if self.login_code != "0" else "success")

    def logout(self) -> _Status:
        self.calls.append(("logout", (), {}))
        return _Status("0", "success")

    def query_history_k_data_plus(self, *args: Any, **kwargs: Any) -> _SdkResult:
        self.calls.append(("history", args, kwargs))
        return self.result

    def query_trade_dates(self, *args: Any, **kwargs: Any) -> _SdkResult:
        self.calls.append(("calendar", args, kwargs))
        return self.result

    def query_stock_basic(self, *args: Any, **kwargs: Any) -> _SdkResult:
        self.calls.append(("security_master", args, kwargs))
        return self.result

    def query_hs300_stocks(self, *args: Any, **kwargs: Any) -> _SdkResult:
        self.calls.append(("membership", args, kwargs))
        return self.result


def _capture_request(query: BaoStockArchiveQuery) -> CaptureRequest:
    return CaptureRequest(
        provider_product_id=uuid4(),
        capture_key="wp17p:archive:test",
        resource=query.resource,
        request_headers_hash="0" * 64,
    )


def test_history_query_dispatches_exact_typed_arguments_and_preserves_rows() -> None:
    result = _SdkResult(
        fields=["date", "time", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag"],
        rows=[["2026-01-05", "20260105100000000", "sh.600000", "10.0", "10.2", "9.9", "10.1", "100", "1010", "3"]],
    )
    sdk = _Sdk(result)
    query = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.HISTORY_5M_RAW,
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 5),
        code="sh.600000",
    )

    with BaoStockSession(sdk) as session:
        response = BaoStockArchiveProvider(session).capture(_capture_request(query))

    assert sdk.calls == [
        ("login", (), {}),
        (
            "history",
            (
                "sh.600000",
                "date,time,code,open,high,low,close,volume,amount,adjustflag",
            ),
            {"start_date": "2026-01-05", "end_date": "2026-01-05", "frequency": "5", "adjustflag": "3"},
        ),
        ("logout", (), {}),
    ]
    payload = json.loads(response.content)
    assert payload["query"]["kind"] == "HISTORY_5M_RAW"
    assert payload["rows"] == result.rows
    assert response.source_availability_status is SourceAvailabilityStatus.UNKNOWN
    assert response.source_available_at is None
    assert response.provider_time is None
    assert response.limitation_code == "HISTORICAL_AVAILABILITY_AND_FINALITY_UNKNOWN"


def test_query_resource_round_trips_canonically() -> None:
    query = BaoStockArchiveQuery(
        kind=BaoStockArchiveQueryKind.TRADE_DATES,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 9, 3),
    )

    assert BaoStockArchiveQuery.from_resource(query.resource) == query
    assert BaoStockArchiveQuery.from_resource(query.resource).resource == query.resource


def test_login_failure_is_typed_and_still_attempts_logout() -> None:
    sdk = _Sdk(_SdkResult(fields=[], rows=[]), login_code="10001001")

    with pytest.raises(MarketProviderError, match="login failed") as error:
        with BaoStockSession(sdk):
            pass

    assert error.value.code == "BAOSTOCK_LOGIN_FAILED"
    assert [call[0] for call in sdk.calls] == ["login", "logout"]


def test_provider_error_and_malformed_rows_fail_closed() -> None:
    query = BaoStockArchiveQuery(kind=BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    rejected = _Sdk(_SdkResult(fields=["code"], rows=[], error_code="100", error_msg="rejected"))
    with BaoStockSession(rejected) as session, pytest.raises(MarketProviderError) as error:
        BaoStockArchiveProvider(session).capture(_capture_request(query))
    assert error.value.code == "BAOSTOCK_PROVIDER_ERROR"

    malformed = _Sdk(_SdkResult(fields=["code", "name"], rows=[["sh.600000"]]))
    with BaoStockSession(malformed) as session, pytest.raises(MarketProviderError) as error:
        BaoStockArchiveProvider(session).capture(_capture_request(query))
    assert error.value.code == "BAOSTOCK_ROW_SHAPE_INVALID"


def test_unsupported_or_tampered_resource_never_reaches_sdk() -> None:
    sdk = _Sdk(_SdkResult(fields=[], rows=[]))
    request = CaptureRequest(
        provider_product_id=uuid4(),
        capture_key="wp17p:archive:tampered",
        resource='{"kind":"HISTORY_1M_RAW"}',
        request_headers_hash="0" * 64,
    )

    with BaoStockSession(sdk) as session, pytest.raises(MarketProviderError) as error:
        BaoStockArchiveProvider(session).capture(request)

    assert error.value.code == "BAOSTOCK_QUERY_INVALID"
    assert [call[0] for call in sdk.calls] == ["login", "logout"]
