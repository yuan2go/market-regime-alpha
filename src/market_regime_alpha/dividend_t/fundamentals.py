"""Tushare-backed fundamental scoring for the dividend T model."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from market_regime_alpha.data_sources.tushare_client import (
    TushareConfigError,
    TushareDataError,
    build_tushare_client,
    normalize_ts_code,
)
from market_regime_alpha.dividend_t.cosco_profile import CoscoProfile
from market_regime_alpha.dividend_t.scoring import clamp
from market_regime_alpha.dividend_t.tushare_provider import TushareDividendDataProvider


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FUNDAMENTAL_CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "dividend_t_fundamentals"


@dataclass(frozen=True)
class FundamentalSnapshot:
    symbol: str
    as_of_date: str
    source: str
    f_score: float
    dividend_sustainability_score: float
    valuation_margin_score: float
    cycle_prosperity_score: float
    financial_quality_score: float
    catalyst_stability_score: float
    metrics: dict[str, float | str | None]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TushareFundamentalDataset:
    daily_basic: Any
    dividends: Any
    financial_indicator: Any


class FundamentalProfileResolver:
    """Resolve a profile with fundamental scores as of a given timestamp."""

    def __init__(self, profile: CoscoProfile, scorer: "TushareFundamentalScorer") -> None:
        self.profile = profile
        self.scorer = scorer
        self._cache: dict[str, CoscoProfile] = {}

    def profile_for_timestamp(self, timestamp: Any) -> CoscoProfile:
        as_of_date = _date_text(timestamp)
        cached = self._cache.get(as_of_date)
        if cached is not None:
            return cached
        snapshot = self.scorer.score(self.profile, as_of_date=as_of_date)
        profile = apply_fundamental_snapshot(self.profile, snapshot)
        self._cache[as_of_date] = profile
        return profile


class TushareFundamentalScorer:
    def __init__(
        self,
        *,
        cache_dir: str | Path = DEFAULT_FUNDAMENTAL_CACHE_DIR,
        provider: TushareDividendDataProvider | None = None,
        lookback_days: int = 365 * 3,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.provider = provider
        self.lookback_days = lookback_days
        self._datasets: dict[str, TushareFundamentalDataset] = {}
        self._failures: dict[str, str] = {}

    @classmethod
    def from_env(cls, *, cache_dir: str | Path = DEFAULT_FUNDAMENTAL_CACHE_DIR) -> "TushareFundamentalScorer":
        client = build_tushare_client(cache_dir=PROJECT_ROOT / "data" / "raw" / "tushare")
        return cls(cache_dir=cache_dir, provider=TushareDividendDataProvider(client))

    def score(self, profile: CoscoProfile, *, as_of_date: str | date | datetime | None = None) -> FundamentalSnapshot:
        as_of = _date_text(as_of_date or datetime.now())
        failure = self._failures.get(normalize_ts_code(profile.symbol))
        if failure is not None:
            return fallback_fundamental_snapshot(profile, as_of_date=as_of, reason=failure)
        try:
            dataset = self._dataset(profile.symbol, as_of_date=as_of)
            return score_fundamentals(profile, dataset=dataset, as_of_date=as_of, source="tushare")
        except Exception as exc:  # noqa: BLE001 - third-party SDKs raise requests/proxy errors directly.
            reason = f"{type(exc).__name__}: {exc}"
            self._failures[normalize_ts_code(profile.symbol)] = reason
            return fallback_fundamental_snapshot(profile, as_of_date=as_of, reason=reason)

    def _dataset(self, symbol: str, *, as_of_date: str) -> TushareFundamentalDataset:
        normalized = normalize_ts_code(symbol)
        cached = self._datasets.get(normalized)
        if cached is not None:
            return cached

        daily_basic = self._load_or_fetch_daily_basic(normalized, as_of_date=as_of_date)
        dividends = self._load_or_fetch_table(normalized, "dividend", lambda: self._provider().dividends(normalized))
        financial = self._load_or_fetch_table(
            normalized,
            "fina_indicator",
            lambda: self._provider().financial_indicator(normalized),
        )
        dataset = TushareFundamentalDataset(
            daily_basic=daily_basic,
            dividends=dividends,
            financial_indicator=financial,
        )
        self._datasets[normalized] = dataset
        return dataset

    def _provider(self) -> TushareDividendDataProvider:
        if self.provider is None:
            self.provider = TushareDividendDataProvider(build_tushare_client(cache_dir=PROJECT_ROOT / "data" / "raw" / "tushare"))
        return self.provider

    def _load_or_fetch_daily_basic(self, symbol: str, *, as_of_date: str) -> Any:
        end = _compact_date(as_of_date)
        start = (datetime.strptime(as_of_date, "%Y-%m-%d").date() - timedelta(days=self.lookback_days)).strftime("%Y%m%d")
        return self._load_or_fetch_table(
            symbol,
            f"daily_basic_{start}_{end}",
            lambda: self._provider().daily_basic(symbol, start_date=start, end_date=end),
        )

    def _load_or_fetch_table(self, symbol: str, name: str, fetcher: Any) -> Any:
        import pandas as pd

        safe_symbol = symbol.replace(".", "_")
        path = self.cache_dir / f"{safe_symbol}_{name}.csv"
        if path.exists():
            return pd.read_csv(path)
        frame = fetcher()
        if frame is None:
            raise TushareDataError(f"Tushare {name} returned no data frame")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        return frame


def build_fundamental_resolver(
    profile: CoscoProfile,
    *,
    source: str = "auto",
    cache_dir: str | Path = DEFAULT_FUNDAMENTAL_CACHE_DIR,
) -> FundamentalProfileResolver | None:
    key = source.strip().lower()
    if key in {"", "profile", "none", "off"}:
        return None
    if key not in {"auto", "tushare"}:
        raise ValueError("fundamental source must be one of: auto, tushare, profile")
    try:
        scorer = TushareFundamentalScorer.from_env(cache_dir=cache_dir)
    except (TushareConfigError, ImportError):
        if key == "tushare":
            raise
        scorer = TushareFundamentalScorer(cache_dir=cache_dir, provider=None)
    return FundamentalProfileResolver(profile, scorer)


def apply_fundamental_snapshot(profile: CoscoProfile, snapshot: FundamentalSnapshot) -> CoscoProfile:
    return replace(
        profile,
        base_fundamental_score=snapshot.f_score,
        dividend_sustainability_score=snapshot.dividend_sustainability_score,
        valuation_margin_score=snapshot.valuation_margin_score,
        cycle_prosperity_score=snapshot.cycle_prosperity_score,
        financial_quality_score=snapshot.financial_quality_score,
        catalyst_stability_score=snapshot.catalyst_stability_score,
        fundamental_source=snapshot.source,
        fundamental_as_of=snapshot.as_of_date,
        fundamental_notes=snapshot.notes,
        fundamental_metrics=snapshot.metrics,
    )


def fallback_fundamental_snapshot(profile: CoscoProfile, *, as_of_date: str, reason: str) -> FundamentalSnapshot:
    f_score = _weighted_f_score(
        profile.dividend_sustainability_score,
        profile.valuation_margin_score,
        profile.cycle_prosperity_score,
        profile.financial_quality_score,
        profile.catalyst_stability_score,
    )
    return FundamentalSnapshot(
        symbol=profile.symbol,
        as_of_date=as_of_date,
        source="industry_profile_fallback",
        f_score=round(f_score, 2),
        dividend_sustainability_score=profile.dividend_sustainability_score,
        valuation_margin_score=profile.valuation_margin_score,
        cycle_prosperity_score=profile.cycle_prosperity_score,
        financial_quality_score=profile.financial_quality_score,
        catalyst_stability_score=profile.catalyst_stability_score,
        metrics={},
        notes=(f"Tushare 基本面不可用，回退行业默认 F：{reason}",),
    )


def score_fundamentals(
    profile: CoscoProfile,
    *,
    dataset: TushareFundamentalDataset,
    as_of_date: str,
    source: str = "tushare",
) -> FundamentalSnapshot:
    daily_basic = _filter_daily_basic(dataset.daily_basic, as_of_date=as_of_date)
    financial = _filter_report_frame(dataset.financial_indicator, as_of_date=as_of_date)
    dividends = _filter_report_frame(dataset.dividends, as_of_date=as_of_date)

    latest_basic = _latest_record(daily_basic)
    latest_financial = _latest_record(financial)
    recent_financial = financial.tail(min(4, len(financial))) if len(financial) else financial
    recent_dividends = dividends.tail(min(8, len(dividends))) if len(dividends) else dividends

    dividend_yield = _first_number(latest_basic, ("dv_ttm", "dv_ratio"))
    pe_ttm = _first_number(latest_basic, ("pe_ttm", "pe"))
    pb = _first_number(latest_basic, ("pb",))
    roe = _first_number(latest_financial, ("roe", "roe_dt", "roe_yearly"))
    debt_to_assets = _first_number(latest_financial, ("debt_to_assets", "assets_liab_ratio"))
    ocfps = _first_number(latest_financial, ("ocfps",))
    netprofit_yoy = _first_number(latest_financial, ("netprofit_yoy", "q_netprofit_yoy"))
    revenue_yoy = _first_number(latest_financial, ("or_yoy", "q_sales_yoy", "tr_yoy"))

    valuation_score = _valuation_score(daily_basic, dividend_yield=dividend_yield, pe_ttm=pe_ttm, pb=pb)
    dividend_score = _dividend_score(
        dividend_yield=dividend_yield,
        dividends=recent_dividends,
        roe=roe,
        ocfps=ocfps,
        debt_to_assets=debt_to_assets,
    )
    quality_score = _quality_score(roe=roe, debt_to_assets=debt_to_assets, ocfps=ocfps, revenue_yoy=revenue_yoy)
    cycle_score = _cycle_score(profile, netprofit_yoy=netprofit_yoy, revenue_yoy=revenue_yoy, recent_financial=recent_financial)
    catalyst_score = _catalyst_score(dividends=recent_dividends, financial=financial, profile=profile)
    f_score = _weighted_f_score(dividend_score, valuation_score, cycle_score, quality_score, catalyst_score)

    notes = (
        f"Tushare 基本面 F={f_score:.1f}，D/V/C/Q/E={dividend_score:.0f}/{valuation_score:.0f}/{cycle_score:.0f}/{quality_score:.0f}/{catalyst_score:.0f}。",
        _metric_note(dividend_yield=dividend_yield, pe_ttm=pe_ttm, pb=pb, roe=roe, debt_to_assets=debt_to_assets),
    )
    metrics = {
        "dividend_yield": _round_or_none(dividend_yield),
        "pe_ttm": _round_or_none(pe_ttm),
        "pb": _round_or_none(pb),
        "roe": _round_or_none(roe),
        "debt_to_assets": _round_or_none(debt_to_assets),
        "ocfps": _round_or_none(ocfps),
        "netprofit_yoy": _round_or_none(netprofit_yoy),
        "revenue_yoy": _round_or_none(revenue_yoy),
        "daily_basic_rows": float(len(daily_basic)),
        "financial_rows": float(len(financial)),
        "dividend_rows": float(len(dividends)),
    }
    return FundamentalSnapshot(
        symbol=profile.symbol,
        as_of_date=as_of_date,
        source=source,
        f_score=round(f_score, 2),
        dividend_sustainability_score=round(dividend_score, 2),
        valuation_margin_score=round(valuation_score, 2),
        cycle_prosperity_score=round(cycle_score, 2),
        financial_quality_score=round(quality_score, 2),
        catalyst_stability_score=round(catalyst_score, 2),
        metrics=metrics,
        notes=notes,
    )


def _valuation_score(daily_basic: Any, *, dividend_yield: float | None, pe_ttm: float | None, pb: float | None) -> float:
    score = 55.0
    if dividend_yield is not None:
        if dividend_yield >= 6:
            score += 16
        elif dividend_yield >= 4:
            score += 12
        elif dividend_yield >= 2.5:
            score += 7
        else:
            score -= 5
    if pe_ttm is not None and pe_ttm > 0:
        score += _inverse_percentile_bonus(daily_basic, "pe_ttm", pe_ttm, fallback_column="pe", weight=14)
        if pe_ttm <= 8:
            score += 8
        elif pe_ttm >= 30:
            score -= 8
    if pb is not None and pb > 0:
        score += _inverse_percentile_bonus(daily_basic, "pb", pb, weight=10)
        if pb <= 1:
            score += 7
        elif pb >= 3:
            score -= 6
    return clamp(score, 25.0, 92.0)


def _dividend_score(
    *,
    dividend_yield: float | None,
    dividends: Any,
    roe: float | None,
    ocfps: float | None,
    debt_to_assets: float | None,
) -> float:
    score = 52.0
    if dividend_yield is not None:
        score += clamp(dividend_yield * 3.0, -5.0, 22.0)
    if len(dividends) > 0:
        cash_dividends = _positive_count(dividends, ("cash_div_tax", "cash_div", "base_share"))
        score += min(cash_dividends * 3.0, 12.0)
    else:
        score -= 6.0
    if roe is not None:
        score += 8.0 if roe >= 10 else (-4.0 if roe < 4 else 2.0)
    if ocfps is not None:
        score += 5.0 if ocfps > 0 else -5.0
    if debt_to_assets is not None and debt_to_assets > 75:
        score -= 5.0
    return clamp(score, 20.0, 92.0)


def _quality_score(*, roe: float | None, debt_to_assets: float | None, ocfps: float | None, revenue_yoy: float | None) -> float:
    score = 58.0
    if roe is not None:
        if roe >= 15:
            score += 16
        elif roe >= 10:
            score += 10
        elif roe < 5:
            score -= 8
    if debt_to_assets is not None:
        if debt_to_assets <= 55:
            score += 8
        elif debt_to_assets >= 80:
            score -= 10
    if ocfps is not None:
        score += 6 if ocfps > 0 else -8
    if revenue_yoy is not None:
        score += 5 if revenue_yoy > 0 else -4
    return clamp(score, 20.0, 92.0)


def _cycle_score(profile: CoscoProfile, *, netprofit_yoy: float | None, revenue_yoy: float | None, recent_financial: Any) -> float:
    score = float(profile.cycle_prosperity_score)
    if netprofit_yoy is not None:
        score += clamp(netprofit_yoy / 5.0, -16.0, 16.0)
    if revenue_yoy is not None:
        score += clamp(revenue_yoy / 6.0, -10.0, 10.0)
    if len(recent_financial) >= 2:
        profit_values = _series_numbers(recent_financial, ("netprofit_yoy", "q_netprofit_yoy"))
        if len(profit_values) >= 2 and profit_values[-1] >= profit_values[0]:
            score += 4.0
        elif len(profit_values) >= 2:
            score -= 4.0
    return clamp(score, 20.0, 90.0)


def _catalyst_score(*, dividends: Any, financial: Any, profile: CoscoProfile) -> float:
    score = float(profile.catalyst_stability_score)
    if len(financial) > 0:
        score += 4.0
    else:
        score -= 5.0
    if len(dividends) > 0:
        score += 5.0
    return clamp(score, 20.0, 88.0)


def _weighted_f_score(d: float, v: float, c: float, q: float, e: float) -> float:
    return clamp(0.25 * d + 0.20 * v + 0.20 * c + 0.20 * q + 0.15 * e, 0.0, 100.0)


def _filter_daily_basic(frame: Any, *, as_of_date: str) -> Any:
    data = _copy_frame(frame)
    if data.empty or "trade_date" not in data.columns:
        return data
    data["_date"] = data["trade_date"].astype(str).map(_compact_date)
    return data[data["_date"] <= _compact_date(as_of_date)].sort_values("_date").reset_index(drop=True)


def _filter_report_frame(frame: Any, *, as_of_date: str) -> Any:
    data = _copy_frame(frame)
    if data.empty:
        return data
    date_column = _first_existing_column(data, ("ann_date", "end_date", "record_date", "ex_date", "trade_date"))
    if date_column is None:
        return data.reset_index(drop=True)
    data["_date"] = data[date_column].astype(str).map(_compact_date)
    return data[data["_date"] <= _compact_date(as_of_date)].sort_values("_date").reset_index(drop=True)


def _copy_frame(frame: Any) -> Any:
    import pandas as pd

    if frame is None:
        return pd.DataFrame()
    return frame.copy()


def _latest_record(frame: Any) -> dict[str, Any]:
    if frame is None or getattr(frame, "empty", True):
        return {}
    return dict(frame.iloc[-1])


def _first_number(record: dict[str, Any], columns: tuple[str, ...]) -> float | None:
    for column in columns:
        if column in record:
            value = _to_float(record.get(column))
            if value is not None:
                return value
    return None


def _series_numbers(frame: Any, columns: tuple[str, ...]) -> list[float]:
    column = _first_existing_column(frame, columns)
    if column is None:
        return []
    values: list[float] = []
    for value in frame[column].tolist():
        numeric = _to_float(value)
        if numeric is not None:
            values.append(numeric)
    return values


def _positive_count(frame: Any, columns: tuple[str, ...]) -> int:
    column = _first_existing_column(frame, columns)
    if column is None:
        return 0
    return sum(1 for value in frame[column].tolist() if (_to_float(value) or 0.0) > 0.0)


def _inverse_percentile_bonus(frame: Any, column: str, current: float, *, weight: float, fallback_column: str | None = None) -> float:
    candidates = _series_numbers(frame, (column, fallback_column) if fallback_column else (column,))
    candidates = [value for value in candidates if value > 0]
    if len(candidates) < 20:
        return 0.0
    lower_or_equal = sum(1 for value in candidates if value <= current)
    percentile = lower_or_equal / len(candidates)
    return (0.5 - percentile) * 2.0 * weight


def _first_existing_column(frame: Any, columns: tuple[str | None, ...]) -> str | None:
    if frame is None:
        return None
    existing = set(frame.columns)
    for column in columns:
        if column and column in existing:
            return column
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:  # noqa: BLE001
        pass
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return datetime.now().date().isoformat()
    if " " in text:
        text = text.split(" ", 1)[0]
    if "T" in text:
        text = text.split("T", 1)[0]
    compact = _compact_date(text)
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def _compact_date(value: str) -> str:
    raw = str(value).strip().replace("-", "")
    if len(raw) >= 8 and raw[:8].isdigit():
        return raw[:8]
    return datetime.fromisoformat(str(value).strip()).strftime("%Y%m%d")


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _metric_note(
    *,
    dividend_yield: float | None,
    pe_ttm: float | None,
    pb: float | None,
    roe: float | None,
    debt_to_assets: float | None,
) -> str:
    parts = [
        f"股息率={_fmt_metric(dividend_yield)}",
        f"PE_TTM={_fmt_metric(pe_ttm)}",
        f"PB={_fmt_metric(pb)}",
        f"ROE={_fmt_metric(roe)}",
        f"资产负债率={_fmt_metric(debt_to_assets)}",
    ]
    return "；".join(parts)


def _fmt_metric(value: float | None) -> str:
    return "缺失" if value is None else f"{value:.2f}"
