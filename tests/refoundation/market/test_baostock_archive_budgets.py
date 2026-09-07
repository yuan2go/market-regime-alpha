from __future__ import annotations

from time import monotonic, sleep

import pytest

from market_regime_alpha.infrastructure.providers.baostock_archive import (
    BaoStockArchiveQuery,
    BaoStockArchiveQueryKind,
    BaoStockSession,
)
from market_regime_alpha.market.ports import MarketProviderError
from tests.refoundation.market.test_baostock_archive_provider import _Sdk, _SdkResult


def test_complete_execute_has_one_deadline_despite_progressing_rows() -> None:
    class SlowRows(_SdkResult):
        def next(self) -> bool:
            sleep(0.01)
            return super().next()

    result = SlowRows(["code"], [["sh.600000"] for _ in range(60)])
    sdk = _Sdk(result)
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    with BaoStockSession(sdk, timeout_seconds=0.15, maximum_attempts=1) as session:
        started = monotonic()
        with pytest.raises(MarketProviderError) as error:
            session.execute(query)
        elapsed = monotonic() - started

    assert error.value.code == "BAOSTOCK_EXECUTE_DEADLINE_EXCEEDED"
    assert elapsed < 0.5
    assert result._index < 60
    assert [call[0] for call in sdk.calls] == ["login", "security_master", "logout"]


def test_row_budget_stops_before_reading_overflow_without_retry() -> None:
    class CountedRows(_SdkResult):
        reads = 0

        def get_row_data(self) -> list[str]:
            self.reads += 1
            return super().get_row_data()

    rows = CountedRows(["code"], [["sh.600000"] for _ in range(4)])
    sdk = _Sdk(rows)
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    with BaoStockSession(sdk, maximum_rows=2) as session, pytest.raises(MarketProviderError) as error:
        session.execute(query)
    assert error.value.code == "BAOSTOCK_RESPONSE_ROW_BUDGET_EXCEEDED"
    assert rows.reads == 2
    assert rows._index == 2
    assert [call[0] for call in sdk.calls] == ["login", "security_master", "logout"]


def test_response_byte_budget_is_exact_utf8_envelope_and_preserves_success_bytes() -> None:
    from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveProvider
    from tests.refoundation.market.test_baostock_archive_provider import _capture_request

    expected = (
        '{"error_code":"0","error_message":"success","fields":["name"],'
        '"query":{"code":"sh.600000","end_date":null,"kind":"STOCK_BASIC",'
        '"start_date":null,"version":1},"rows":[["浦发\\\"银行"],["乙"]]}\n'
    ).encode("utf-8")
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    sdk = _Sdk(_SdkResult(["name"], [['浦发"银行'], ["乙"]]))
    with BaoStockSession(sdk, maximum_response_bytes=len(expected), maximum_rows=2) as session:
        response = BaoStockArchiveProvider(session).capture(_capture_request(query))
    assert response.content == expected

    overflow_sdk = _Sdk(_SdkResult(["name"], [['浦发"银行'], ["乙"]]))
    with BaoStockSession(overflow_sdk, maximum_response_bytes=len(expected) - 1) as session:
        with pytest.raises(MarketProviderError) as error:
            BaoStockArchiveProvider(session).capture(_capture_request(query))
    assert error.value.code == "BAOSTOCK_RESPONSE_BYTE_BUDGET_EXCEEDED"
    assert [call[0] for call in overflow_sdk.calls] == ["login", "security_master", "logout"]


def test_response_metadata_alone_can_exceed_byte_budget() -> None:
    rows = _SdkResult(["name"], [])
    sdk = _Sdk(rows)
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    with BaoStockSession(sdk, maximum_response_bytes=1) as session, pytest.raises(MarketProviderError) as error:
        session.execute(query)
    assert error.value.code == "BAOSTOCK_RESPONSE_BYTE_BUDGET_EXCEEDED"
    assert rows._index == -1


@pytest.mark.parametrize("option", [
    {"timeout_seconds": True}, {"timeout_seconds": float("nan")},
    {"timeout_seconds": float("inf")}, {"timeout_seconds": "1"},
    {"timeout_seconds": 0}, {"timeout_seconds": -1},
    {"maximum_attempts": True}, {"maximum_attempts": 1.5},
    {"maximum_attempts": 0}, {"maximum_attempts": 4},
    {"maximum_rows": True}, {"maximum_rows": 1.5},
    {"maximum_rows": 0}, {"maximum_rows": -1},
    {"maximum_response_bytes": True}, {"maximum_response_bytes": 1.5},
    {"maximum_response_bytes": 0}, {"maximum_response_bytes": -1},
    {"defer_login": 1},
])
def test_resource_budgets_reject_invalid_values_before_provider_effect(option: dict) -> None:
    sdk = _Sdk(_SdkResult([], []))
    with pytest.raises((TypeError, ValueError)):
        BaoStockSession(sdk, **option)
    assert sdk.calls == []


@pytest.mark.parametrize("unsupported", ["worker-thread", "missing-timer"])
def test_unsupported_timeout_environment_fails_closed_before_provider_effect(monkeypatch, unsupported) -> None:
    import market_regime_alpha.infrastructure.providers.baostock_archive as module

    sdk = _Sdk(_SdkResult([], []))
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    if unsupported == "worker-thread":
        monkeypatch.setattr(module.threading, "current_thread", lambda: object())
    else:
        monkeypatch.delattr(module.signal, "setitimer")
    with BaoStockSession(sdk, defer_login=True) as session, pytest.raises(MarketProviderError) as error:
        session.execute(query)
    assert error.value.code == "BAOSTOCK_TIMEOUT_ENVIRONMENT_UNSUPPORTED"
    assert sdk.calls == []


def test_existing_alarm_is_preserved_and_prevents_provider_effect() -> None:
    import signal

    sdk = _Sdk(_SdkResult([], []))
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    original_handler = signal.getsignal(signal.SIGALRM)
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    signal.setitimer(signal.ITIMER_REAL, 60.0)
    try:
        with BaoStockSession(sdk, defer_login=True) as session, pytest.raises(MarketProviderError) as error:
            session.execute(query)
        assert error.value.code == "BAOSTOCK_TIMEOUT_TIMER_ALREADY_OWNED"
        assert 50 < signal.getitimer(signal.ITIMER_REAL)[0] <= 60
        assert signal.getsignal(signal.SIGALRM) == original_handler
        assert sdk.calls == []
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def test_deferred_login_and_query_share_execute_deadline_and_do_not_retry_expiry() -> None:
    class SlowLoginAndQuery(_Sdk):
        def login(self):
            sleep(0.08)
            return super().login()

        def query_stock_basic(self, *args, **kwargs):
            self.calls.append(("security_master", args, kwargs))
            sleep(0.08)
            return self.result

    sdk = SlowLoginAndQuery(_SdkResult([], []))
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    with BaoStockSession(sdk, defer_login=True, timeout_seconds=0.12, maximum_attempts=3) as session:
        with pytest.raises(MarketProviderError) as error:
            session.execute(query)
    assert error.value.code == "BAOSTOCK_EXECUTE_DEADLINE_EXCEEDED"
    assert [call[0] for call in sdk.calls] == ["login", "security_master", "logout"]


def test_deadline_covers_row_conversion_and_is_released_for_next_capture() -> None:
    class SlowString:
        def __str__(self) -> str:
            sleep(0.2)
            return "sh.600000"

    sdk = _Sdk(_SdkResult(["code"], [[SlowString()]]))
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    with BaoStockSession(sdk, timeout_seconds=0.1) as session:
        with pytest.raises(MarketProviderError) as error:
            session.execute(query)
        assert error.value.code == "BAOSTOCK_EXECUTE_DEADLINE_EXCEEDED"
        sdk.result = _SdkResult(["code"], [["sh.600000"]])
        assert session.execute(query).rows == (("sh.600000",),)


def test_query_retry_consumes_remaining_deadline_instead_of_resetting_it() -> None:
    class RetrySdk(_Sdk):
        def query_stock_basic(self, *args, **kwargs):
            self.calls.append(("security_master", args, kwargs))
            sleep(0.08)
            raise ConnectionError("fixture incomplete query")

    sdk = RetrySdk(_SdkResult([], []))
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    with BaoStockSession(sdk, timeout_seconds=0.12, maximum_attempts=3) as session:
        with pytest.raises(MarketProviderError) as error:
            session.execute(query)
    assert error.value.code == "BAOSTOCK_EXECUTE_DEADLINE_EXCEEDED"
    assert [call[0] for call in sdk.calls] == ["login", "security_master", "security_master", "logout"]


@pytest.mark.parametrize("stage", ["query", "next", "row"])
def test_capture_does_not_retry_unknown_query_or_row_effect(stage: str) -> None:
    effects: list[str] = []

    class UnknownRows(_SdkResult):
        def next(self) -> bool:
            effects.append("next")
            if stage == "next":
                raise ConnectionError("secret=unknown-provider-effect")
            return super().next()

        def get_row_data(self) -> list[str]:
            effects.append("row")
            raise ConnectionError("secret=unknown-provider-effect")

    class UnknownSdk(_Sdk):
        def query_stock_basic(self, *args, **kwargs):
            effects.append("query")
            if stage == "query":
                raise ConnectionError("secret=unknown-provider-effect")
            return super().query_stock_basic(*args, **kwargs)

    sdk = UnknownSdk(UnknownRows(["code"], [["sh.600000"]]))
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    with BaoStockSession(sdk, maximum_attempts=1) as session, pytest.raises(MarketProviderError) as error:
        session.execute(query)
    assert error.value.code == "BAOSTOCK_TRANSPORT_FAILED"
    assert "secret" not in str(error.value)
    assert effects == {"query": ["query"], "next": ["query", "next"], "row": ["query", "next", "row"]}[stage]
