from __future__ import annotations

from datetime import UTC, date, datetime
import json
from types import SimpleNamespace

import pytest

from market_regime_alpha.data.providers.public_composite.historical_security_facts import (
    _build_acquisition,
    _checkpointed_fact_query,
)
from market_regime_alpha.data_sources.a_share_bars import AShareDataError
from market_regime_alpha.universe.historical_facts import (
    HistoricalSecurityFactKind,
)


NOW = datetime(2026, 8, 13, tzinfo=UTC)


def _response(fields: tuple[str, ...], rows: tuple[tuple[str, ...], ...]):
    return {
        "error_code": "0",
        "error_message": "success",
        "fields": list(fields),
        "rows": [list(item) for item in rows],
    }


def _item(product: str, response, ordinal: int):
    return (
        product,
        f"baostock://historical-fact-test/{ordinal}",
        (("ordinal", str(ordinal)),),
        ("600000.SH",),
        NOW,
        NOW,
        response,
    )


def test_historical_fact_provider_preserves_real_facts_and_missing_rows() -> None:
    responses = (
        _item(
            "query_stock_industry:effective-date:v1",
            _response(
                (
                    "updateDate",
                    "code",
                    "code_name",
                    "industry",
                    "industryClassification",
                ),
                (
                    ("2024-12-30", "sh.600000", "浦发银行", "J66货币金融服务", "证监会行业分类"),
                    ("2024-12-30", "sh.600001", "邯郸钢铁", "", "证监会行业分类"),
                ),
            ),
            1,
        ),
        _item(
            "query_profit_data:quarter:v1",
            _response(
                (
                    "code",
                    "pubDate",
                    "statDate",
                    "totalShare",
                    "liqaShare",
                ),
                (("sh.600000", "2025-03-29", "2024-12-31", "29352178302.00", "29352178302.00"),),
            ),
            2,
        ),
        _item(
            "query_adjust_factor:range:v1",
            _response(
                (
                    "code",
                    "dividOperateDate",
                    "foreAdjustFactor",
                    "backAdjustFactor",
                    "adjustFactor",
                ),
                (("sh.600000", "2025-07-16", "0.95", "12.76", "12.76"),),
            ),
            3,
        ),
        _item(
            "query_dividend_data:report-year:v1",
            _response(
                (
                    "code",
                    "dividPreNoticeDate",
                    "dividAgmPumDate",
                    "dividPlanAnnounceDate",
                    "dividPlanDate",
                    "dividRegistDate",
                    "dividOperateDate",
                    "dividPayDate",
                    "dividStockMarketDate",
                    "dividCashPsBeforeTax",
                    "dividCashPsAfterTax",
                    "dividStocksPs",
                    "dividCashStock",
                    "dividReserveToStockPs",
                ),
                (
                    (
                        "sh.600000",
                        "",
                        "2025-06-28",
                        "2025-03-29",
                        "2025-07-10",
                        "2025-07-15",
                        "2025-07-16",
                        "2025-07-16",
                        "",
                        "0.41",
                        "0.41",
                        "0",
                        "10派4.1元",
                        "",
                    ),
                ),
            ),
            4,
        ),
    )

    acquired = _build_acquisition(
        symbols=("600000.SH",),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 7, 31),
        responses=responses,
    )

    assert acquired.query_count == 4
    assert acquired.rejected_row_count == 0
    assert dict(acquired.fact_counts) == {
        HistoricalSecurityFactKind.ADJUSTMENT_EVENT.value: 1,
        HistoricalSecurityFactKind.DIVIDEND_EVENT.value: 1,
        HistoricalSecurityFactKind.INDUSTRY.value: 1,
        HistoricalSecurityFactKind.SHARE_CAPITAL.value: 1,
    }
    assert all(item.symbol == "600000.SH" for item in acquired.owner.facts)
    assert acquired.owner.formal_pit is False


def test_historical_fact_provider_rejects_same_effective_fact_drift() -> None:
    fields = (
        "updateDate",
        "code",
        "code_name",
        "industry",
        "industryClassification",
    )
    responses = (
        _item(
            "query_stock_industry:effective-date:v1",
            _response(fields, (("2024-12-30", "sh.600000", "浦发银行", "银行", "证监会行业分类"),)),
            1,
        ),
        _item(
            "query_stock_industry:effective-date:v1",
            _response(fields, (("2024-12-30", "sh.600000", "浦发银行", "金融", "证监会行业分类"),)),
            2,
        ),
    )

    with pytest.raises(Exception, match="drifted"):
        _build_acquisition(
            symbols=("600000.SH",),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 7, 31),
            responses=responses,
        )


def test_historical_fact_provider_persists_unresolved_corporate_action_gap() -> None:
    responses = (
        _item(
            "query_stock_industry:effective-date:v1",
            _response(
                ("updateDate", "code", "code_name", "industry", "industryClassification"),
                (("2024-12-30", "sh.600000", "浦发银行", "银行", "证监会行业分类"),),
            ),
            1,
        ),
        (
            "query_dividend_data:report-year:v1",
            "baostock://query-dividend-data/sh.600000/2025/report",
            (("code", "sh.600000"), ("year", "2025"), ("year_type", "report")),
            ("600000.SH",),
            NOW,
            NOW,
            _response(
                ("code", "dividOperateDate"),
                (("sh.600000", ""),),
            ),
        ),
    )

    acquired = _build_acquisition(
        symbols=("600000.SH",),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 7, 31),
        responses=responses,
    )

    assert acquired.coverage_gap_count == 1
    gap = acquired.owner.coverage_gaps[0]
    assert gap.symbol == "600000.SH"
    assert gap.coverage_start == date(2025, 1, 1)
    assert gap.coverage_end == date(2025, 7, 31)


def test_historical_fact_provider_preserves_multiple_real_dividends_on_one_day() -> None:
    fields = (
        "code",
        "dividOperateDate",
        "dividPreNoticeDate",
        "dividPlanAnnounceDate",
        "dividAgmPumDate",
        "dividPlanDate",
        "dividCashPsBeforeTax",
        "dividStocksPs",
        "dividReserveToStockPs",
    )
    responses = (
        _item(
            "query_stock_industry:effective-date:v1",
            _response(
                ("updateDate", "code", "code_name", "industry", "industryClassification"),
                (("2024-12-30", "sh.600000", "浦发银行", "银行", "证监会行业分类"),),
            ),
            1,
        ),
        _item(
            "query_dividend_data:report-year:v1",
            _response(
                fields,
                (
                    ("sh.600000", "2025-05-29", "2025-01-01", "", "", "", "0.56", "0", ""),
                    ("sh.600000", "2025-05-29", "2025-03-01", "", "", "", "1.41", "0", ""),
                ),
            ),
            2,
        ),
    )

    acquired = _build_acquisition(
        symbols=("600000.SH",),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 7, 31),
        responses=responses,
    )

    dividends = tuple(
        item
        for item in acquired.owner.facts
        if item.fact_kind is HistoricalSecurityFactKind.DIVIDEND_EVENT
    )
    assert len(dividends) == 2
    assert {dict(item.values)["cash_dividend_per_share_before_tax"] for item in dividends} == {
        "0.56",
        "1.41",
    }


class _QueryResult:
    error_code = "0"
    error_msg = "success"
    fields = ["code"]

    def __init__(self) -> None:
        self._consumed = False

    def next(self) -> bool:
        if self._consumed:
            return False
        self._consumed = True
        return True

    def get_row_data(self) -> list[str]:
        return ["sh.600000"]


def test_historical_fact_query_checkpoint_resumes_and_detects_corruption(
    tmp_path,
) -> None:
    values = {
        "checkpoint_root": tmp_path,
        "product": "query_profit_data:quarter:v1",
        "locator": "baostock://query-profit-data/sh.600000/2025/1",
        "parameters": (("code", "sh.600000"),),
        "scope": ("600000.SH",),
        "clock": lambda: NOW,
    }
    first = _checkpointed_fact_query(
        **values,
        query=_QueryResult,
    )
    second = _checkpointed_fact_query(
        **values,
        query=lambda: SimpleNamespace(error_code="9", error_msg="must not run"),
    )

    assert second == first
    checkpoint = next(tmp_path.glob("*.json"))
    checkpoint.write_text("{}\n", encoding="utf-8")
    with pytest.raises(AShareDataError, match="identity drift"):
        _checkpointed_fact_query(
            **values,
            query=_QueryResult,
        )


def test_historical_fact_query_checkpoint_hash_covers_retrieval_times(tmp_path) -> None:
    values = {
        "checkpoint_root": tmp_path,
        "product": "query_profit_data:quarter:v1",
        "locator": "baostock://query-profit-data/sh.600000/2025/1",
        "parameters": (("code", "sh.600000"),),
        "scope": ("600000.SH",),
        "clock": lambda: NOW,
    }
    _checkpointed_fact_query(**values, query=_QueryResult)
    checkpoint = next(tmp_path.glob("*.json"))
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["retrieved_at"] = datetime(2026, 8, 14, tzinfo=UTC).isoformat()
    checkpoint.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AShareDataError, match="content drift"):
        _checkpointed_fact_query(**values, query=_QueryResult)
