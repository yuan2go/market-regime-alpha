"""Raw-preserving BaoStock and Tencent clients for the LIVE profile."""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from typing import Any, Callable
from urllib.request import Request, urlopen

from market_regime_alpha.core.time import AvailabilityTime, RetrievedAt
from market_regime_alpha.data.providers.public_composite.contracts import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    TENCENT_PUBLIC_PROVIDER_ID,
    AcquiredSourcePayload,
    PublicBar,
    PublicCompositeBatch,
    PublicCompositeRequest,
    PublicQuote,
    TradingStatus,
)
from market_regime_alpha.data.source_manifest import SourceFieldFinality
from market_regime_alpha.data_sources.a_share_bars import (
    AShareDataError,
    TENCENT_QUOTE_URL,
    TENCENT_USER_AGENT,
    baostock_credentials,
    normalize_baostock_minute_frame,
    parse_tencent_quote_text,
    to_baostock_code,
    to_tencent_code,
)


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _retrieved_at(clock: Clock) -> RetrievedAt:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("LIVE acquisition clock must return timezone-aware time")
    return RetrievedAt(value)


class BaoStockHistoryClient:
    """Acquire exact BaoStock response rows without local cache substitution."""

    def __init__(self, *, clock: Clock = _utc_now) -> None:
        self._clock = clock

    def acquire(self, request: PublicCompositeRequest) -> PublicCompositeBatch:
        try:
            import baostock as bs
            import pandas as pd
        except ImportError as exc:
            raise AShareDataError("baostock is not installed") from exc
        user_id, password = baostock_credentials()
        with redirect_stdout(StringIO()):
            login = bs.login(user_id=user_id, password=password)
        payloads: list[AcquiredSourcePayload] = []
        bars: list[PublicBar] = []
        try:
            if getattr(login, "error_code", "0") != "0":
                raise AShareDataError(f"BaoStock login failed: {login.error_msg}")
            for symbol in request.symbols:
                result = bs.query_history_k_data_plus(
                    to_baostock_code(symbol),
                    "date,time,code,open,high,low,close,volume,amount",
                    start_date=request.history_start.isoformat(),
                    end_date=request.decision_time.value.date().isoformat(),
                    frequency="5",
                    adjustflag="3",
                )
                if getattr(result, "error_code", "0") != "0":
                    raise AShareDataError(
                        f"BaoStock minute query failed: {result.error_msg}"
                    )
                rows: list[list[str]] = []
                while result.next():
                    rows.append(result.get_row_data())
                raw = json.dumps(
                    {
                        "fields": list(result.fields),
                        "rows": rows,
                        "request": {
                            "symbol": symbol,
                            "start_date": request.history_start.isoformat(),
                            "end_date": request.decision_time.value.date().isoformat(),
                            "frequency": "5",
                            "adjustflag": "3",
                        },
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                source = AcquiredSourcePayload(
                    provider_id=BAOSTOCK_PUBLIC_PROVIDER_ID,
                    product="query_history_k_data_plus:5min:adjustflag=3",
                    locator=f"baostock://history/{to_baostock_code(symbol)}",
                    raw_payload=raw,
                    retrieved_time=_retrieved_at(self._clock),
                    limitations=(
                        "HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED",
                        "PUBLIC_DATA_EXPLORATORY_ONLY",
                    ),
                )
                payloads.append(source)
                if not rows:
                    continue
                frame = normalize_baostock_minute_frame(
                    pd.DataFrame(rows, columns=result.fields),
                    symbol=symbol,
                    source_freq="5min",
                )
                for record in frame.to_dict(orient="records"):
                    event_time = _as_aware_datetime(
                        record["timestamp"],
                        request.decision_time,
                    )
                    if event_time > request.decision_time.value:
                        continue
                    bars.append(
                        PublicBar(
                            symbol=symbol,
                            event_time=event_time,
                            available_time=None,
                            source_artifact_id=source.source_artifact_id,
                            open=float(record["open"]),
                            high=float(record["high"]),
                            low=float(record["low"]),
                            close=float(record["close"]),
                            volume=float(record["volume"]),
                            amount=float(record.get("amount") or 0.0),
                            unit="CNY",
                            adjustment_basis="BAOSTOCK_ADJUSTFLAG_3",
                            finality=SourceFieldFinality.UNKNOWN,
                        )
                    )
        finally:
            with redirect_stdout(StringIO()):
                bs.logout()
        return PublicCompositeBatch(
            raw_payloads=tuple(payloads),
            bars=tuple(sorted(bars, key=lambda item: (item.symbol, item.event_time))),
            quotes=(),
            source_conflicts=(),
            limitations=(
                "BAOSTOCK_HISTORY_ONLY",
                "HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED",
            ),
        )


class TencentCurrentQuoteClient:
    """Acquire and retain the exact Tencent quote response bytes."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        clock: Clock = _utc_now,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._clock = clock

    def acquire(self, request: PublicCompositeRequest) -> PublicCompositeBatch:
        query = ",".join(to_tencent_code(symbol) for symbol in request.symbols)
        url = f"{TENCENT_QUOTE_URL}{query}"
        http_request = Request(
            url,
            headers={
                "User-Agent": TENCENT_USER_AGENT,
                "Referer": "https://gu.qq.com/",
            },
        )
        try:
            with urlopen(  # noqa: S310 - fixed Tencent public quote endpoint.
                http_request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read()
        except Exception as exc:  # noqa: BLE001
            raise AShareDataError(f"Tencent quote query failed: {exc}") from exc
        retrieved = _retrieved_at(self._clock)
        source = AcquiredSourcePayload(
            provider_id=TENCENT_PUBLIC_PROVIDER_ID,
            product="qt.gtimg.cn:current-quote",
            locator=url,
            raw_payload=raw,
            retrieved_time=retrieved,
            limitations=(
                "TRADING_STATUS_NOT_QUALIFIED",
                "PUBLIC_DATA_EXPLORATORY_ONLY",
            ),
        )
        parsed = parse_tencent_quote_text(
            raw.decode("gb18030", errors="ignore")
        )
        quotes: list[PublicQuote] = []
        for symbol in request.symbols:
            quote = parsed.get(symbol)
            if quote is None:
                continue
            event_time = _parse_tencent_time(
                quote.quote_time,
                request.decision_time,
            )
            quotes.append(
                PublicQuote(
                    symbol=symbol,
                    event_time=event_time,
                    available_time=AvailabilityTime(retrieved.value),
                    source_artifact_id=source.source_artifact_id,
                    price=quote.current_price,
                    trading_status=TradingStatus.UNKNOWN,
                    unit="CNY",
                    finality=SourceFieldFinality.PRELIMINARY,
                )
            )
        return PublicCompositeBatch(
            raw_payloads=(source,),
            bars=(),
            quotes=tuple(quotes),
            source_conflicts=(),
            limitations=("TENCENT_CURRENT_QUOTE_ONLY",),
        )


def _as_aware_datetime(value: Any, decision_time: Any) -> datetime:
    parsed = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    if not isinstance(parsed, datetime):
        parsed = datetime.fromisoformat(str(parsed))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=decision_time.value.tzinfo)
    return parsed


def _parse_tencent_time(
    value: str | None,
    decision_time: Any,
) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    for pattern in ("%Y%m%d%H%M%S", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(raw, pattern).replace(
                tzinfo=decision_time.value.tzinfo
            )
        except ValueError:
            continue
    return None
