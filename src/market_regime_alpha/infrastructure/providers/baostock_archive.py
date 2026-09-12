"""Typed BaoStock archive capture with no invented PIT or finality semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import json
import math
from contextlib import contextmanager, nullcontext
import signal
import threading
from time import monotonic, sleep
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
    HISTORY_DAILY_BACK_ADJUSTED = "HISTORY_DAILY_BACK_ADJUSTED"
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
            BaoStockArchiveQueryKind.HISTORY_DAILY_BACK_ADJUSTED,
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
            "version": 2 if self.kind is BaoStockArchiveQueryKind.HISTORY_DAILY_BACK_ADJUSTED else 1,
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
            if payload["version"] not in (1, 2):
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


class BaoStockResult(Protocol):
    fields: list[str]
    error_code: str
    error_msg: str

    def next(self) -> bool: ...

    def get_row_data(self) -> list[str]: ...


class BaoStockSdk(Protocol):
    def login(self) -> Any: ...

    def logout(self) -> Any: ...

    def query_history_k_data_plus(self, *args: Any, **kwargs: Any) -> BaoStockResult: ...

    def query_trade_dates(self, *args: Any, **kwargs: Any) -> BaoStockResult: ...

    def query_stock_basic(self, *args: Any, **kwargs: Any) -> BaoStockResult: ...

    def query_hs300_stocks(self, *args: Any, **kwargs: Any) -> BaoStockResult: ...


@dataclass(frozen=True, slots=True)
class BaoStockArchiveResult:
    fields: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    error_code: str
    error_message: str


class BaoStockSession:
    """One explicit SDK session; login/query/logout remain outside database UoWs."""

    def __init__(
        self,
        sdk: BaoStockSdk,
        *,
        timeout_seconds: float = 30.0,
        maximum_attempts: int = 2,
        defer_login: bool = False,
        maximum_rows: int = 100_000,
        maximum_response_bytes: int = 33_554_432,
        retry_interval_seconds: float = 0,
    ) -> None:
        if type(timeout_seconds) not in (int, float):
            raise TypeError("BaoStock timeout_seconds must be numeric, excluding bool")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("BaoStock timeout_seconds must be finite and positive")
        if type(maximum_attempts) is not int:
            raise TypeError("BaoStock maximum_attempts must be an integer, excluding bool")
        if maximum_attempts < 1 or maximum_attempts > 3:
            raise ValueError("BaoStock maximum_attempts must be between 1 and 3")
        for name, value in (("maximum_rows", maximum_rows), ("maximum_response_bytes", maximum_response_bytes)):
            if type(value) is not int:
                raise TypeError(f"BaoStock {name} must be an integer, excluding bool")
            if value < 1:
                raise ValueError(f"BaoStock {name} must be positive")
        if type(defer_login) is not bool:
            raise TypeError("BaoStock defer_login must be boolean")
        if isinstance(retry_interval_seconds, bool) or not math.isfinite(retry_interval_seconds) or not 0 <= retry_interval_seconds <= 30:
            raise ValueError("BaoStock retry_interval_seconds must be finite and between 0 and 30")
        self._retry_interval_seconds = retry_interval_seconds
        self._sdk = sdk
        self._timeout_seconds = timeout_seconds
        self._maximum_attempts = maximum_attempts
        self._maximum_rows = maximum_rows
        self._maximum_response_bytes = maximum_response_bytes
        self._active = False
        self._defer_login = defer_login
        self._entered = False
        self._execute_deadline: float | None = None

    def __enter__(self) -> Self:
        self._entered = True
        if not self._defer_login:
            self._connect()
        return self

    def _connect(self) -> None:
        try:
            status = self._transport_call("login", self._sdk.login)
        except _DeadlineExceeded:
            raise
        except Exception as exc:
            raise MarketProviderError("BAOSTOCK_LOGIN_TRANSPORT_FAILED", "BaoStock login failed") from exc
        if str(status.error_code) != "0":
            try:
                self._transport_call("logout", self._sdk.logout)
            finally:
                raise MarketProviderError("BAOSTOCK_LOGIN_FAILED", f"BaoStock login failed: {status.error_msg}")
        self._active = True

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._entered = False
        if self._active:
            self._active = False
            try:
                self._transport_call("logout", self._sdk.logout)
            except Exception as logout_error:
                if exc is None:
                    raise MarketProviderError("BAOSTOCK_LOGOUT_FAILED", "BaoStock logout failed") from logout_error

    def execute(self, query: BaoStockArchiveQuery) -> BaoStockArchiveResult:
        deadline = monotonic() + self._timeout_seconds
        try:
            with _timeout_guard("execute", self._timeout_seconds):
                self._execute_deadline = deadline
                try:
                    return self._execute(query)
                finally:
                    self._execute_deadline = None
        except _DeadlineExceeded as exc:
            raise MarketProviderError(
                "BAOSTOCK_EXECUTE_DEADLINE_EXCEEDED",
                "BaoStock complete execute deadline exceeded",
            ) from exc

    def _execute(self, query: BaoStockArchiveQuery) -> BaoStockArchiveResult:
        if self._defer_login and self._entered and not self._active:
            self._connect()
        if not self._active:
            raise MarketProviderError("BAOSTOCK_SESSION_NOT_ACTIVE", "BaoStock session is not active")
        result = self._transport_call("query", self._dispatch, query)
        if str(result.error_code) != "0":
            raise MarketProviderError(
                "BAOSTOCK_PROVIDER_ERROR",
                f"BaoStock returned error {result.error_code}: {result.error_msg}",
            )
        fields = tuple(str(item) for item in result.fields)
        rows: list[tuple[str, ...]] = []
        error_code, error_message = str(result.error_code), str(result.error_msg)
        # Include the exact UTF-8 envelope, escaping, commas and final newline.
        # Count each row once before retaining it; no quadratic re-serialization.
        response_bytes = len(
            _result_content(query, BaoStockArchiveResult(fields, (), error_code, error_message))
        )
        self._check_response_bytes(response_bytes)
        while self._transport_call("row-iteration", result.next, retry=False):
            if len(rows) >= self._maximum_rows:
                raise MarketProviderError(
                    "BAOSTOCK_RESPONSE_ROW_BUDGET_EXCEEDED",
                    "BaoStock response exceeds the declared row budget",
                )
            row = tuple(
                str(item)
                for item in self._transport_call("row-read", result.get_row_data, retry=False)
            )
            if len(row) != len(fields):
                raise MarketProviderError("BAOSTOCK_ROW_SHAPE_INVALID", "BaoStock row width differs from its field roster")
            response_bytes += len(_json_bytes(row)) + (1 if rows else 0)
            self._check_response_bytes(response_bytes)
            rows.append(row)
        return BaoStockArchiveResult(
            fields=fields,
            rows=tuple(rows),
            error_code=error_code,
            error_message=error_message,
        )

    def _check_response_bytes(self, byte_count: int) -> None:
        if byte_count > self._maximum_response_bytes:
            raise MarketProviderError(
                "BAOSTOCK_RESPONSE_BYTE_BUDGET_EXCEEDED",
                "BaoStock response exceeds the declared UTF-8 byte budget",
            )

    def _transport_call(
        self,
        label: str,
        operation: Any,
        *args: Any,
        retry: bool = True,
    ) -> Any:
        last_error: Exception | None = None
        attempts = self._maximum_attempts if retry else 1
        for attempt_index in range(attempts):
            try:
                if attempt_index and self._retry_interval_seconds:
                    sleep(self._retry_interval_seconds)

                # Execute owns one unreset alarm: each transport consumes its
                # remaining deadline, including retries and deferred login.
                if self._execute_deadline is not None and monotonic() >= self._execute_deadline:
                    raise _DeadlineExceeded("BaoStock execute deadline exceeded")
                guard = (
                    nullcontext()
                    if self._execute_deadline is not None
                    else _timeout_guard(label, self._timeout_seconds)
                )
                with guard:
                    result = operation(*args)
                if self._execute_deadline is not None and monotonic() >= self._execute_deadline:
                    raise _DeadlineExceeded("BaoStock execute deadline exceeded")
                return result
            except _DeadlineExceeded:
                if self._execute_deadline is not None:
                    raise
                last_error = TimeoutError(f"BaoStock {label} timed out")
            except MarketProviderError:
                raise
            except Exception as exc:
                last_error = exc
        raise MarketProviderError(
            "BAOSTOCK_TRANSPORT_FAILED",
            f"BaoStock {label} failed after {attempts} bounded attempt(s)",
        ) from last_error

    def _dispatch(self, query: BaoStockArchiveQuery) -> BaoStockResult:
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
        frequency = "5" if query.kind is BaoStockArchiveQueryKind.HISTORY_5M_RAW else "d"
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
            adjustflag="1" if query.kind is BaoStockArchiveQueryKind.HISTORY_DAILY_BACK_ADJUSTED else "3",
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
        content = _result_content(query, result)
        return ProviderResponse(
            content=content,
            media_type="application/json",
            payload_encoding="UTF-8",
            provider_time=None,
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            limitation_code="HISTORICAL_AVAILABILITY_AND_FINALITY_UNKNOWN",
        )


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def _result_content(query: BaoStockArchiveQuery, result: BaoStockArchiveResult) -> bytes:
    return _json_bytes({
        "error_code": result.error_code,
        "error_message": result.error_message,
        "fields": result.fields,
        "query": json.loads(query.resource),
        "rows": result.rows,
    }) + b"\n"


class _DeadlineExceeded(TimeoutError):
    """Distinguish the owned deadline from an SDK-reported timeout."""


@contextmanager
def _timeout_guard(label: str, timeout_seconds: float):
    if (
        threading.current_thread() is not threading.main_thread()
        or any(not hasattr(signal, name) for name in ("setitimer", "getitimer", "SIGALRM", "ITIMER_REAL"))
    ):
        raise MarketProviderError(
            "BAOSTOCK_TIMEOUT_ENVIRONMENT_UNSUPPORTED",
            "BaoStock requires the main thread and a POSIX real-time timer",
        )
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise MarketProviderError(
            "BAOSTOCK_TIMEOUT_TIMER_ALREADY_OWNED",
            "BaoStock cannot replace an existing real-time timer",
        )

    def _raise_timeout(_signum: int, _frame: object) -> None:
        raise _DeadlineExceeded(f"BaoStock {label} timed out")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


__all__ = [
    "BaoStockArchiveProvider",
    "BaoStockArchiveQuery",
    "BaoStockArchiveQueryKind",
    "BaoStockArchiveResult",
    "BaoStockResult",
    "BaoStockSdk",
    "BaoStockSession",
]
