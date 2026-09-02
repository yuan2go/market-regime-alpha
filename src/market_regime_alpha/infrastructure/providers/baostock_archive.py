"""Typed BaoStock archive capture with no invented PIT or finality semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import json
from typing import Any, Protocol, Self

from market_regime_alpha.market.domain import SourceAvailabilityStatus
from market_regime_alpha.market.ports import (
    CaptureRequest,
    MarketProviderError,
    ProviderResponse,
)


class BaoStockArchiveQueryKind(str, Enum):
    STOCK_BASIC = "STOCK_BASIC"
    TRADE_DATES = "TRADE_DATES"
    CSI300_MEMBERS = "CSI300_MEMBERS"
    HISTORY_DAILY_RAW = "HISTORY_DAILY_RAW"
    HISTORY_5M_RAW = "HISTORY_5M_RAW"


@dataclass(frozen=True, slots=True)
class BaoStockArchiveQuery:
    """Exact Product request identity accepted by the archive adapter."""

    kind: BaoStockArchiveQueryKind
    start_date: date | None = None
    end_date: date | None = None
    code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BaoStockArchiveQueryKind):
            raise TypeError("kind must be BaoStockArchiveQueryKind")
        if self.start_date is not None and self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date cannot precede start_date")
        if self.kind in {
            BaoStockArchiveQueryKind.HISTORY_DAILY_RAW,
            BaoStockArchiveQueryKind.HISTORY_5M_RAW,
        }:
            if self.code is None or self.start_date is None or self.end_date is None:
                raise ValueError("history query requires code and an exact date interval")
        elif self.kind is BaoStockArchiveQueryKind.TRADE_DATES:
            if self.code is not None or self.start_date is None or self.end_date is None:
                raise ValueError("trade-date query requires only an exact date interval")
        elif self.kind is BaoStockArchiveQueryKind.CSI300_MEMBERS:
            if self.code is not None or self.start_date is None or self.end_date != self.start_date:
                raise ValueError("membership query requires one exact as-of date")
        elif self.kind is BaoStockArchiveQueryKind.STOCK_BASIC:
            if self.start_date is not None or self.end_date is not None:
                raise ValueError("security-master query does not accept a date interval")

    @property
    def resource(self) -> str:
        payload = {
            "code": self.code,
            "end_date": self.end_date.isoformat() if self.end_date is not None else None,
            "kind": self.kind.value,
            "start_date": self.start_date.isoformat() if self.start_date is not None else None,
            "version": 1,
        }
        return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_resource(cls, resource: str) -> Self:
        try:
            payload = json.loads(resource)
            if not isinstance(payload, dict) or set(payload) != {
                "code",
                "end_date",
                "kind",
                "start_date",
                "version",
            }:
                raise ValueError("resource has an unexpected field roster")
            if payload["version"] != 1:
                raise ValueError("resource version is unsupported")
            code = payload["code"]
            if code is not None and not isinstance(code, str):
                raise ValueError("code must be a string")
            start = payload["start_date"]
            end = payload["end_date"]
            query = cls(
                kind=BaoStockArchiveQueryKind(payload["kind"]),
                start_date=date.fromisoformat(start) if isinstance(start, str) else None,
                end_date=date.fromisoformat(end) if isinstance(end, str) else None,
                code=code,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid BaoStock archive query resource") from exc
        if query.resource != resource:
            raise ValueError("BaoStock archive query resource is not canonical")
        return query


class _BaoStockResult(Protocol):
    fields: list[str]
    error_code: str
    error_msg: str

    def next(self) -> bool: ...

    def get_row_data(self) -> list[str]: ...


class _BaoStockSdk(Protocol):
    def login(self) -> Any: ...

    def logout(self) -> Any: ...

    def query_history_k_data_plus(self, *args: Any, **kwargs: Any) -> _BaoStockResult: ...

    def query_trade_dates(self, *args: Any, **kwargs: Any) -> _BaoStockResult: ...

    def query_stock_basic(self, *args: Any, **kwargs: Any) -> _BaoStockResult: ...

    def query_hs300_stocks(self, *args: Any, **kwargs: Any) -> _BaoStockResult: ...


@dataclass(frozen=True, slots=True)
class BaoStockArchiveResult:
    fields: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    error_code: str
    error_message: str


class BaoStockSession:
    """One explicit SDK session; login/query/logout remain outside database UoWs."""

    def __init__(self, sdk: _BaoStockSdk) -> None:
        self._sdk = sdk
        self._active = False

    def __enter__(self) -> Self:
        try:
            status = self._sdk.login()
        except Exception as exc:
            raise MarketProviderError("BAOSTOCK_LOGIN_TRANSPORT_FAILED", "BaoStock login failed") from exc
        if str(status.error_code) != "0":
            try:
                self._sdk.logout()
            finally:
                raise MarketProviderError("BAOSTOCK_LOGIN_FAILED", f"BaoStock login failed: {status.error_msg}")
        self._active = True
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._active:
            self._active = False
            try:
                self._sdk.logout()
            except Exception as logout_error:
                if exc is None:
                    raise MarketProviderError("BAOSTOCK_LOGOUT_FAILED", "BaoStock logout failed") from logout_error

    def execute(self, query: BaoStockArchiveQuery) -> BaoStockArchiveResult:
        if not self._active:
            raise MarketProviderError("BAOSTOCK_SESSION_NOT_ACTIVE", "BaoStock session is not active")
        try:
            result = self._dispatch(query)
            fields = tuple(str(item) for item in result.fields)
            rows: list[tuple[str, ...]] = []
            while result.error_code == "0" and result.next():
                rows.append(tuple(str(item) for item in result.get_row_data()))
        except MarketProviderError:
            raise
        except Exception as exc:
            raise MarketProviderError("BAOSTOCK_TRANSPORT_FAILED", "BaoStock query failed") from exc
        if str(result.error_code) != "0":
            raise MarketProviderError(
                "BAOSTOCK_PROVIDER_ERROR",
                f"BaoStock returned error {result.error_code}: {result.error_msg}",
            )
        if any(len(row) != len(fields) for row in rows):
            raise MarketProviderError("BAOSTOCK_ROW_SHAPE_INVALID", "BaoStock row width differs from its field roster")
        return BaoStockArchiveResult(
            fields=fields,
            rows=tuple(rows),
            error_code=str(result.error_code),
            error_message=str(result.error_msg),
        )

    def _dispatch(self, query: BaoStockArchiveQuery) -> _BaoStockResult:
        if query.kind is BaoStockArchiveQueryKind.STOCK_BASIC:
            return self._sdk.query_stock_basic(code=query.code or "")
        if query.kind is BaoStockArchiveQueryKind.TRADE_DATES:
            assert query.start_date is not None and query.end_date is not None
            return self._sdk.query_trade_dates(
                start_date=query.start_date.isoformat(),
                end_date=query.end_date.isoformat(),
            )
        if query.kind is BaoStockArchiveQueryKind.CSI300_MEMBERS:
            assert query.start_date is not None
            return self._sdk.query_hs300_stocks(date=query.start_date.isoformat())
        assert query.code is not None and query.start_date is not None and query.end_date is not None
        frequency = "d" if query.kind is BaoStockArchiveQueryKind.HISTORY_DAILY_RAW else "5"
        fields = (
            "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST"
            if frequency == "d"
            else "date,time,code,open,high,low,close,volume,amount,adjustflag"
        )
        return self._sdk.query_history_k_data_plus(
            query.code,
            fields,
            start_date=query.start_date.isoformat(),
            end_date=query.end_date.isoformat(),
            frequency=frequency,
            adjustflag="3",
        )


class BaoStockArchiveProvider:
    def __init__(self, session: BaoStockSession) -> None:
        self._session = session

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        try:
            query = BaoStockArchiveQuery.from_resource(request.resource)
        except ValueError as exc:
            raise MarketProviderError("BAOSTOCK_QUERY_INVALID", "BaoStock archive query is invalid") from exc
        result = self._session.execute(query)
        content = (
            json.dumps(
                {
                    "error_code": result.error_code,
                    "error_message": result.error_message,
                    "fields": result.fields,
                    "query": json.loads(query.resource),
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
            limitation_code="HISTORICAL_AVAILABILITY_AND_FINALITY_UNKNOWN",
        )


__all__ = [
    "BaoStockArchiveProvider",
    "BaoStockArchiveQuery",
    "BaoStockArchiveQueryKind",
    "BaoStockArchiveResult",
    "BaoStockSession",
]
