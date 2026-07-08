"""Tushare Pro provider for dividend T-trading research data."""

from __future__ import annotations

from typing import Any

from market_regime_alpha.data_sources.tushare_client import TushareClient, normalize_daily_date, normalize_ts_code


class TushareDividendDataProvider:
    def __init__(self, client: TushareClient) -> None:
        self.client = client

    def daily_bars(self, symbol: str, *, start_date: str | None = None, end_date: str | None = None) -> Any:
        return self.client.daily_bars(symbol, start_date=start_date, end_date=end_date)

    def daily_basic(self, symbol: str, *, start_date: str | None = None, end_date: str | None = None) -> Any:
        pro = self.client._pro  # TushareClient owns the configured SDK object.
        frame = pro.daily_basic(
            ts_code=normalize_ts_code(symbol),
            start_date=normalize_daily_date(start_date),
            end_date=normalize_daily_date(end_date),
            fields="ts_code,trade_date,turnover_rate,pe,pe_ttm,pb,dv_ratio,dv_ttm,total_mv,circ_mv",
        )
        return frame.sort_values("trade_date").reset_index(drop=True)

    def adj_factors(self, symbol: str, *, start_date: str | None = None, end_date: str | None = None) -> Any:
        pro = self.client._pro
        frame = pro.adj_factor(
            ts_code=normalize_ts_code(symbol),
            start_date=normalize_daily_date(start_date),
            end_date=normalize_daily_date(end_date),
        )
        return frame.sort_values("trade_date").reset_index(drop=True)

    def dividends(self, symbol: str) -> Any:
        pro = self.client._pro
        frame = pro.dividend(ts_code=normalize_ts_code(symbol))
        sort_column = "end_date" if "end_date" in frame.columns else frame.columns[0]
        return frame.sort_values(sort_column).reset_index(drop=True)

    def financial_indicator(self, symbol: str) -> Any:
        pro = self.client._pro
        frame = pro.fina_indicator(ts_code=normalize_ts_code(symbol))
        sort_column = "end_date" if "end_date" in frame.columns else frame.columns[0]
        return frame.sort_values(sort_column).reset_index(drop=True)
