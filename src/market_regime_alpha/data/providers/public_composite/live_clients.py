"""Raw-preserving BaoStock and Tencent clients for the LIVE profile."""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, time, timedelta, timezone
from io import StringIO
import json
import socket
from typing import Any, Callable
from urllib.request import Request, urlopen

from market_regime_alpha.core.time import AvailabilityTime, RetrievedAt
from market_regime_alpha.data.providers.public_composite.contracts import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1,
    TENCENT_PUBLIC_PROVIDER_ID,
    AcquiredSourcePayload,
    PublicBar,
    PublicCompositeBatch,
    PublicCompositeRequest,
    PublicQuote,
    PublicSecurityStatusObservation,
    STStatus,
    ListingStatus,
    SecurityStatusEvidenceScope,
    SecurityStatusFactType,
    TradingStatus,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.source_manifest import (
    SourceAuthorityKind,
    SourceFieldFinality,
    SourceFieldQualityStatus,
)
from market_regime_alpha.data_sources.a_share_bars import (
    AShareDataError,
    TENCENT_QUOTE_URL,
    TENCENT_USER_AGENT,
    baostock_credentials,
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
    """Acquire prior-session BaoStock daily rows without cache substitution."""

    def __init__(self, *, clock: Clock = _utc_now) -> None:
        self._clock = clock

    def acquire(self, request: PublicCompositeRequest) -> PublicCompositeBatch:
        try:
            import baostock as bs
        except ImportError as exc:
            raise AShareDataError("baostock is not installed") from exc
        user_id, password = baostock_credentials()
        with redirect_stdout(StringIO()):
            login = bs.login(user_id=user_id, password=password)
        payloads: list[AcquiredSourcePayload] = []
        bars: list[PublicBar] = []
        status_observations: list[PublicSecurityStatusObservation] = []
        try:
            if getattr(login, "error_code", "0") != "0":
                raise AShareDataError(f"BaoStock login failed: {login.error_msg}")
            for symbol in request.symbols:
                history_end = (
                    request.decision_time.value.date() - timedelta(days=1)
                )
                result = bs.query_history_k_data_plus(
                    to_baostock_code(symbol),
                    (
                        "date,code,open,high,low,close,volume,amount,"
                        "adjustflag,tradestatus,isST"
                    ),
                    start_date=request.history_start.isoformat(),
                    end_date=history_end.isoformat(),
                    frequency="d",
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
                            "end_date": history_end.isoformat(),
                            "frequency": "d",
                            "adjustflag": "3",
                        },
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                source = AcquiredSourcePayload(
                    provider_id=BAOSTOCK_PUBLIC_PROVIDER_ID,
                    product="query_history_k_data_plus:daily:adjustflag=3",
                    locator=f"baostock://history/{to_baostock_code(symbol)}",
                    raw_payload=raw,
                    retrieved_time=_retrieved_at(self._clock),
                    limitations=(
                        "HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED",
                        HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1,
                        "PUBLIC_DATA_EXPLORATORY_ONLY",
                    ),
                )
                payloads.append(source)
                if not rows:
                    continue
                latest_prior_record: dict[str, str] | None = None
                for raw_row in rows:
                    record = dict(zip(result.fields, raw_row, strict=True))
                    try:
                        event_time = datetime.combine(
                            datetime.strptime(
                                str(record["date"]),
                                "%Y-%m-%d",
                            ).date(),
                            time(15, 0),
                            tzinfo=request.decision_time.value.tzinfo,
                        )
                        open_price = float(record["open"])
                        high_price = float(record["high"])
                        low_price = float(record["low"])
                        close_price = float(record["close"])
                        volume = float(record["volume"])
                        amount = float(record["amount"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if (
                        event_time.date()
                        >= request.decision_time.value.date()
                        or event_time > request.decision_time.value
                    ):
                        continue
                    bars.append(
                        PublicBar(
                            symbol=symbol,
                            event_time=event_time,
                            available_time=None,
                            source_artifact_id=source.source_artifact_id,
                            open=open_price,
                            high=high_price,
                            low=low_price,
                            close=close_price,
                            volume=volume,
                            amount=amount,
                            unit="CNY",
                            adjustment_basis="BAOSTOCK_ADJUSTFLAG_3",
                            finality=SourceFieldFinality.UNKNOWN,
                        )
                    )
                    if (
                        latest_prior_record is None
                        or record["date"] > latest_prior_record["date"]
                    ):
                        latest_prior_record = record
                if latest_prior_record is not None:
                    status_observations.extend(
                        _prior_session_status_observations(
                            symbol=symbol,
                            record=latest_prior_record,
                            source=source,
                            request=request,
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
                HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1,
            ),
            security_status_observations=tuple(status_observations),
        )


class BaoStockSecurityStatusClient:
    """Observe exact decision-date security status without prior-day promotion."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        clock: Clock = _utc_now,
    ) -> None:
        if timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        self._clock = clock

    def acquire(self, request: PublicCompositeRequest) -> PublicCompositeBatch:
        try:
            import baostock as bs
        except ImportError as exc:
            raise AShareDataError("baostock is not installed") from exc

        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.timeout_seconds)
        payloads: list[AcquiredSourcePayload] = []
        observations: list[PublicSecurityStatusObservation] = []
        provider_errors = 0
        try:
            user_id, password = baostock_credentials()
            with redirect_stdout(StringIO()):
                login = bs.login(user_id=user_id, password=password)
            if getattr(login, "error_code", "0") != "0":
                raise AShareDataError(f"BaoStock login failed: {login.error_msg}")
            try:
                for symbol in request.symbols:
                    history_response = _query_baostock_status_history(
                        bs=bs,
                        symbol=symbol,
                        request=request,
                    )
                    basic_response = _query_baostock_stock_basic(
                        bs=bs,
                        symbol=symbol,
                    )
                    if (
                        history_response["error_code"] != "0"
                        or basic_response["error_code"] != "0"
                    ):
                        provider_errors += 1
                    raw = json.dumps(
                        {
                            "decision_date": (
                                request.decision_time.value.date().isoformat()
                            ),
                            "symbol": symbol,
                            "history_status": history_response,
                            "stock_basic": basic_response,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    retrieved = _retrieved_at(self._clock)
                    source = AcquiredSourcePayload(
                        provider_id=BAOSTOCK_PUBLIC_PROVIDER_ID,
                        product=(
                            "decision-security-status:"
                            "query_history_k_data_plus+query_stock_basic:v1"
                        ),
                        locator=(
                            "baostock://security-status/"
                            f"{to_baostock_code(symbol)}/"
                            f"{request.decision_time.value.date().isoformat()}"
                        ),
                        raw_payload=raw,
                        retrieved_time=retrieved,
                        limitations=(
                            "CURRENT_OBSERVATION_AVAILABLE_TIME_IS_RETRIEVAL_TIME",
                            "PROVIDER_DOES_NOT_DECLARE_HISTORICAL_PUBLICATION_TIME",
                            "PUBLIC_DATA_EXPLORATORY_ONLY",
                            "FORMAL_PIT_NOT_ESTABLISHED",
                        ),
                    )
                    payloads.append(source)
                    observations.extend(
                        _current_security_status_observations(
                            symbol=symbol,
                            history_response=history_response,
                            basic_response=basic_response,
                            source=source,
                            request=request,
                        )
                    )
            finally:
                with redirect_stdout(StringIO()):
                    bs.logout()
        finally:
            socket.setdefaulttimeout(previous_timeout)

        limitations = [
            "BAOSTOCK_CURRENT_SECURITY_STATUS_ONLY",
            "CURRENT_OBSERVATION_AVAILABLE_TIME_IS_RETRIEVAL_TIME",
            "PUBLIC_DATA_EXPLORATORY_ONLY",
            "FORMAL_PIT_NOT_ESTABLISHED",
        ]
        if provider_errors == len(request.symbols):
            limitations.append("SECURITY_STATUS_PROVIDER_UNUSABLE")
        if not any(
            item.value.value != "UNKNOWN"
            and item.quality_status is SourceFieldQualityStatus.COMPLETE
            for item in observations
        ):
            limitations.append("SECURITY_STATUS_PROVIDER_UNUSABLE")
        return PublicCompositeBatch(
            raw_payloads=tuple(payloads),
            bars=(),
            quotes=(),
            source_conflicts=(),
            limitations=tuple(dict.fromkeys(limitations)),
            security_status_observations=tuple(observations),
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


def _prior_session_status_observations(
    *,
    symbol: str,
    record: dict[str, str],
    source: AcquiredSourcePayload,
    request: PublicCompositeRequest,
) -> tuple[PublicSecurityStatusObservation, ...]:
    """Retain BaoStock status columns without promoting them to current facts."""

    raw_date = record.get("date")
    event_time: datetime | None = None
    if raw_date:
        try:
            event_time = datetime.combine(
                datetime.strptime(raw_date, "%Y-%m-%d").date(),
                time(15, 0),
                tzinfo=request.decision_time.value.tzinfo,
            )
        except ValueError:
            event_time = None
    trading = {
        "1": TradingStatus.TRADING,
        "0": TradingStatus.SUSPENDED,
    }.get(record.get("tradestatus", ""), TradingStatus.UNKNOWN)
    st_status = {
        "1": STStatus.ST,
        "0": STStatus.NOT_ST,
    }.get(record.get("isST", ""), STStatus.UNKNOWN)

    def observation(
        fact_type: SecurityStatusFactType,
        value: TradingStatus | STStatus,
    ) -> PublicSecurityStatusObservation:
        reasons = (
            "PRIOR_SESSION_STATUS_NOT_CURRENT",
            *(
                ("PROVIDER_STATUS_VALUE_UNKNOWN",)
                if value.value == "UNKNOWN"
                else ()
            ),
        )
        return PublicSecurityStatusObservation(
            symbol=symbol,
            fact_type=fact_type,
            value=value,
            scope=SecurityStatusEvidenceScope.PRIOR_SESSION_STATUS,
            event_time=event_time,
            available_time=None,
            retrieved_time=source.retrieved_time,
            decision_time=request.decision_time,
            policy_effective_time=None,
            provider_id=source.provider_id,
            source_artifact_id=source.source_artifact_id,
            authority_kind=SourceAuthorityKind.PROVIDER,
            quality_status=SourceFieldQualityStatus.DEGRADED,
            reason_codes=reasons,
            finality=SourceFieldFinality.UNKNOWN,
            data_eligibility=DataEligibility.EXPLORATORY,
        )

    return (
        observation(SecurityStatusFactType.TRADING_STATUS, trading),
        observation(SecurityStatusFactType.ST_STATUS, st_status),
    )


def _query_baostock_status_history(
    *,
    bs: Any,
    symbol: str,
    request: PublicCompositeRequest,
) -> dict[str, Any]:
    decision_date = request.decision_time.value.date().isoformat()
    try:
        result = bs.query_history_k_data_plus(
            to_baostock_code(symbol),
            "date,code,tradestatus,isST",
            start_date=decision_date,
            end_date=decision_date,
            frequency="d",
            adjustflag="3",
        )
        return _consume_baostock_result(result)
    except Exception as exc:  # noqa: BLE001 - preserve isolated Provider failure.
        return {
            "error_code": "CLIENT_EXCEPTION",
            "error_message": f"{type(exc).__name__}: {exc}",
            "fields": [],
            "rows": [],
        }


def _query_baostock_stock_basic(
    *,
    bs: Any,
    symbol: str,
) -> dict[str, Any]:
    try:
        result = bs.query_stock_basic(code=to_baostock_code(symbol))
        return _consume_baostock_result(result)
    except Exception as exc:  # noqa: BLE001 - preserve isolated Provider failure.
        return {
            "error_code": "CLIENT_EXCEPTION",
            "error_message": f"{type(exc).__name__}: {exc}",
            "fields": [],
            "rows": [],
        }


def _consume_baostock_result(result: Any) -> dict[str, Any]:
    fields = [str(value) for value in getattr(result, "fields", ())]
    rows: list[list[str]] = []
    if getattr(result, "error_code", "0") == "0":
        while result.next():
            rows.append([str(value) for value in result.get_row_data()])
    return {
        "error_code": str(getattr(result, "error_code", "UNKNOWN")),
        "error_message": str(getattr(result, "error_msg", "")),
        "fields": fields,
        "rows": rows,
    }


def _current_security_status_observations(
    *,
    symbol: str,
    history_response: dict[str, Any],
    basic_response: dict[str, Any],
    source: AcquiredSourcePayload,
    request: PublicCompositeRequest,
) -> tuple[PublicSecurityStatusObservation, ...]:
    decision_date = request.decision_time.value.date().isoformat()
    history_records = [
        dict(zip(history_response["fields"], row, strict=True))
        for row in history_response["rows"]
        if len(history_response["fields"]) == len(row)
    ]
    exact_history = [
        record for record in history_records if record.get("date") == decision_date
    ]
    history_record = exact_history[-1] if exact_history else {}
    basic_records = [
        dict(zip(basic_response["fields"], row, strict=True))
        for row in basic_response["rows"]
        if len(basic_response["fields"]) == len(row)
    ]
    basic_record = basic_records[-1] if basic_records else {}

    trading = {
        "1": TradingStatus.TRADING,
        "0": TradingStatus.SUSPENDED,
    }.get(str(history_record.get("tradestatus", "")), TradingStatus.UNKNOWN)
    st_status = {
        "1": STStatus.ST,
        "0": STStatus.NOT_ST,
    }.get(str(history_record.get("isST", "")), STStatus.UNKNOWN)
    listing_status = {
        "1": ListingStatus.LISTED,
        "0": ListingStatus.DELISTED,
    }.get(str(basic_record.get("status", "")), ListingStatus.UNKNOWN)
    retrieved_late = source.retrieved_time.as_utc() > request.decision_time.as_utc()

    def observation(
        fact_type: SecurityStatusFactType,
        value: TradingStatus | STStatus | ListingStatus,
        *,
        missing_reason: str,
    ) -> PublicSecurityStatusObservation:
        reasons: tuple[str, ...]
        quality: SourceFieldQualityStatus
        finality: SourceFieldFinality
        if value.value == "UNKNOWN":
            reasons = (missing_reason,)
            quality = SourceFieldQualityStatus.INSUFFICIENT
            finality = SourceFieldFinality.UNKNOWN
        elif retrieved_late:
            reasons = ("STATUS_RETRIEVED_AFTER_DECISION",)
            quality = SourceFieldQualityStatus.INSUFFICIENT
            finality = SourceFieldFinality.PRELIMINARY
        else:
            reasons = ()
            quality = SourceFieldQualityStatus.COMPLETE
            finality = SourceFieldFinality.PRELIMINARY
        return PublicSecurityStatusObservation(
            symbol=symbol,
            fact_type=fact_type,
            value=value,
            scope=SecurityStatusEvidenceScope.CURRENT_DECISION_SESSION,
            event_time=None,
            available_time=AvailabilityTime(source.retrieved_time.value),
            retrieved_time=source.retrieved_time,
            decision_time=request.decision_time,
            policy_effective_time=None,
            provider_id=source.provider_id,
            source_artifact_id=source.source_artifact_id,
            authority_kind=SourceAuthorityKind.PROVIDER,
            quality_status=quality,
            reason_codes=reasons,
            finality=finality,
            data_eligibility=DataEligibility.EXPLORATORY,
        )

    return (
        observation(
            SecurityStatusFactType.TRADING_STATUS,
            trading,
            missing_reason="CURRENT_TRADING_STATUS_UNKNOWN",
        ),
        observation(
            SecurityStatusFactType.ST_STATUS,
            st_status,
            missing_reason="CURRENT_ST_STATUS_UNKNOWN",
        ),
        observation(
            SecurityStatusFactType.LISTING_STATUS,
            listing_status,
            missing_reason="CURRENT_LISTING_STATUS_UNKNOWN",
        ),
    )
