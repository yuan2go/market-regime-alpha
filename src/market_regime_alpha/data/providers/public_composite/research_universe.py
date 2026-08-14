"""BaoStock full Security Master acquisition for exploratory Research Universe."""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import StringIO
import json
import socket
from typing import Any, Callable

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.time import DecisionTime, RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite.contracts import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
    AcquiredSourcePayload,
    PublicCompositeProviderResult,
    RawSourceRequestMetadata,
)
from market_regime_alpha.data.providers.public_composite.replay_archive import (
    source_archive_id,
)
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.data_sources.a_share_bars import (
    AShareDataError,
    baostock_credentials,
)
from market_regime_alpha.universe.research import (
    FreeDataEvidenceOrigin,
    FreeResearchUniverseSnapshot,
    build_free_research_universe_snapshot,
    build_historical_constituent_universe_snapshot,
)


Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class FreeResearchUniverseAcquisition:
    provider_result: PublicCompositeProviderResult
    source_manifest: SourceManifest
    snapshot: FreeResearchUniverseSnapshot


@dataclass(frozen=True, slots=True)
class FreeResearchUniverseHistoryAcquisition:
    acquisitions: tuple[FreeResearchUniverseAcquisition, ...]
    queried_trading_dates: tuple[date, ...]
    query_effective_dates: tuple[tuple[date, date], ...]
    scan_provider_result: PublicCompositeProviderResult
    scan_source_manifest: SourceManifest
    scan_raw_archive_id: str
    start_date: date
    end_date: date
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if not self.acquisitions:
            raise ValueError("Historical constituent history requires cohorts")
        effective_dates = tuple(
            item.snapshot.constituent_effective_date for item in self.acquisitions if item.snapshot.constituent_effective_date is not None
        )
        if len(effective_dates) != len(self.acquisitions) or effective_dates != tuple(sorted(set(effective_dates))):
            raise ValueError("Historical constituent history cohorts must have unique effective dates")
        if not self.queried_trading_dates or self.queried_trading_dates != tuple(sorted(set(self.queried_trading_dates))):
            raise ValueError("Historical constituent query dates must be non-empty and ordered")
        if (
            tuple(item[0] for item in self.query_effective_dates) != self.queried_trading_dates
            or any(effective > query for query, effective in self.query_effective_dates)
            or {item[1] for item in self.query_effective_dates} != set(effective_dates)
        ):
            raise ValueError("Historical constituent query/effective mapping is invalid")
        if self.start_date > self.end_date or (
            self.queried_trading_dates[0] < self.start_date or self.queried_trading_dates[-1] > self.end_date
        ):
            raise ValueError("Historical constituent scan range is inconsistent")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("Historical constituent scan retrieval time must be aware")
        if (
            source_archive_id(
                provider_result=self.scan_provider_result,
                source_manifest=self.scan_source_manifest,
            )
            != self.scan_raw_archive_id
        ):
            raise ValueError("Historical constituent scan archive identity mismatch")
        constituent_sources = tuple(
            item for item in self.scan_provider_result.raw_payloads if item.product == "query_hs300_stocks:session-history:v1"
        )
        if len(constituent_sources) != len(self.queried_trading_dates):
            raise ValueError("Historical constituent scan omitted raw session responses")


class BaoStockResearchUniverseClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Research Universe timeout must be positive")
        self._timeout_seconds = timeout_seconds
        self._clock = clock

    def acquire(self, *, as_of_date: date) -> FreeResearchUniverseAcquisition:
        try:
            import baostock as bs
        except ImportError as exc:
            raise AShareDataError("baostock is not installed") from exc
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self._timeout_seconds)
        try:
            requested_at = self._clock()
            user_id, password = baostock_credentials()
            with redirect_stdout(StringIO()):
                login = bs.login(user_id=user_id, password=password)
            if getattr(login, "error_code", "0") != "0":
                raise AShareDataError(f"BaoStock login failed: {login.error_msg}")
            try:
                response = _consume_result(bs.query_stock_basic())
            finally:
                with redirect_stdout(StringIO()):
                    bs.logout()
            if response["error_code"] != "0" or not response["rows"]:
                raise AShareDataError("BaoStock full Security Master query returned no usable rows")
            retrieved_at = self._clock()
        finally:
            socket.setdefaulttimeout(previous_timeout)
        if requested_at.tzinfo is None or retrieved_at.tzinfo is None:
            raise ValueError("Research Universe client clock must be timezone-aware")
        raw = json.dumps(
            response,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        decision_time = DecisionTime(retrieved_at)
        source = AcquiredSourcePayload(
            provider_id=BAOSTOCK_PUBLIC_PROVIDER_ID,
            product="query_stock_basic:all:v1",
            locator=f"baostock://query-stock-basic/all/{as_of_date.isoformat()}",
            raw_payload=raw,
            retrieved_time=RetrievedAt(retrieved_at),
            limitations=(
                "BAOSTOCK_LIBRARY_RESULT_REENCODED_NOT_TRANSPORT_BYTES",
                "CURRENT_RETRIEVAL_TIME_ONLY",
                "FORMAL_PIT_NOT_ESTABLISHED",
                "PUBLIC_DATA_EXPLORATORY_ONLY",
            ),
            request_metadata=RawSourceRequestMetadata(
                provider_profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
                endpoint="query_stock_basic",
                request_parameters=(("scope", "ALL_SECURITIES"),),
                requested_at=requested_at,
                provider_timestamp=None,
                event_time=None,
                available_at=retrieved_at,
                decision_time=retrieved_at,
                http_status=None,
                content_type="application/json",
                response_size=len(raw),
                encoding="utf-8",
                symbol_scope=("ALL_SECURITIES",),
                field_scope=tuple(sorted(str(item) for item in response["fields"])),
            ),
        )
        provider_result = PublicCompositeProviderResult(
            profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
            decision_time=decision_time,
            raw_payloads=(source,),
            bars=(),
            quotes=(),
            source_conflicts=(),
            limitations=(
                "FREE_DATA_EXPLORATORY",
                "FORMAL_PIT_NOT_ESTABLISHED",
                "NO_PROVIDER_FALLBACK",
                "SECURITY_MASTER_CURRENT_RETRIEVAL_ONLY",
            ),
        )
        manifest = SourceManifest(
            provider_profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
            decision_time=decision_time,
            source_artifacts=provider_result.source_artifact_references,
            fields=(),
            source_conflicts=(),
            limitations=provider_result.limitations,
            data_eligibility=DataEligibility.EXPLORATORY,
        )
        archive_id = source_archive_id(
            provider_result=provider_result,
            source_manifest=manifest,
        )
        rows = _normalize_security_master_rows(
            fields=tuple(str(item) for item in response["fields"]),
            rows=tuple(tuple(str(item) for item in row) for row in response["rows"]),
        )
        snapshot = build_free_research_universe_snapshot(
            as_of_date=as_of_date,
            known_at=retrieved_at,
            provider_id=str(BAOSTOCK_PUBLIC_PROVIDER_ID),
            provider_contract="baostock-query-stock-basic-all/v1",
            source_manifest_reference=ValidationArtifactReference(
                "SOURCE_MANIFEST",
                manifest.source_manifest_id,
                manifest.content_hash,
            ),
            raw_archive_id=archive_id,
            evidence_origin=FreeDataEvidenceOrigin.REAL_FREE_PROVIDER_OBSERVATION,
            rows=rows,
        )
        return FreeResearchUniverseAcquisition(provider_result, manifest, snapshot)

    def acquire_historical_constituents(
        self,
        *,
        effective_date: date,
    ) -> FreeResearchUniverseAcquisition:
        """Acquire an effective-dated CSI 300 member set plus lifecycle facts."""

        try:
            import baostock as bs
        except ImportError as exc:
            raise AShareDataError("baostock is not installed") from exc
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self._timeout_seconds)
        try:
            user_id, password = baostock_credentials()
            with redirect_stdout(StringIO()):
                login = bs.login(user_id=user_id, password=password)
            if getattr(login, "error_code", "0") != "0":
                raise AShareDataError(f"BaoStock login failed: {login.error_msg}")
            try:
                constituent_requested_at = self._clock()
                constituents = _consume_result(bs.query_hs300_stocks(effective_date.isoformat()))
                constituent_retrieved_at = self._clock()
                basic_requested_at = self._clock()
                security_master = _consume_result(bs.query_stock_basic())
                security_master_retrieved_at = self._clock()
            finally:
                with redirect_stdout(StringIO()):
                    bs.logout()
        finally:
            socket.setdefaulttimeout(previous_timeout)
        return _build_historical_acquisition(
            query_date=effective_date,
            constituent_response=constituents,
            constituent_requested_at=constituent_requested_at,
            constituent_retrieved_at=constituent_retrieved_at,
            security_master_response=security_master,
            security_master_requested_at=basic_requested_at,
            security_master_retrieved_at=security_master_retrieved_at,
            retrieved_at=security_master_retrieved_at,
        )

    def acquire_historical_constituent_history(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> FreeResearchUniverseHistoryAcquisition:
        """Scan every real trading session and retain distinct Provider cohorts."""

        if start_date > end_date:
            raise ValueError("Historical constituent history range is reversed")
        try:
            import baostock as bs
        except ImportError as exc:
            raise AShareDataError("baostock is not installed") from exc
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self._timeout_seconds)
        try:
            user_id, password = baostock_credentials()
            with redirect_stdout(StringIO()):
                login = bs.login(user_id=user_id, password=password)
            if getattr(login, "error_code", "0") != "0":
                raise AShareDataError(f"BaoStock login failed: {login.error_msg}")
            try:
                calendar_requested_at = self._clock()
                calendar = _consume_result(
                    bs.query_trade_dates(
                        start_date=start_date.isoformat(),
                        end_date=end_date.isoformat(),
                    )
                )
                calendar_retrieved_at = self._clock()
                trading_dates = _trading_dates(calendar)
                distinct: dict[
                    date,
                    tuple[date, dict[str, Any], datetime, datetime],
                ] = {}
                normalized_by_effective: dict[date, tuple[dict[str, Any], ...]] = {}
                query_responses: list[
                    tuple[date, dict[str, Any], datetime, datetime]
                ] = []
                query_effective_dates: list[tuple[date, date]] = []
                for query_date in trading_dates:
                    requested_at = self._clock()
                    response = _consume_result(bs.query_hs300_stocks(query_date.isoformat()))
                    response_retrieved_at = self._clock()
                    query_responses.append(
                        (query_date, response, requested_at, response_retrieved_at)
                    )
                    rows = _validated_constituent_rows(response)
                    effective_dates = {date.fromisoformat(str(item["updateDate"])) for item in rows}
                    if len(effective_dates) != 1:
                        raise AShareDataError("BaoStock CSI 300 response has mixed effective dates")
                    provider_effective_date = next(iter(effective_dates))
                    query_effective_dates.append((query_date, provider_effective_date))
                    prior = normalized_by_effective.get(provider_effective_date)
                    if prior is not None and prior != rows:
                        raise AShareDataError("BaoStock CSI 300 membership drifted for one effective date")
                    normalized_by_effective[provider_effective_date] = rows
                    distinct.setdefault(
                        provider_effective_date,
                        (
                            query_date,
                            response,
                            requested_at,
                            response_retrieved_at,
                        ),
                    )
                basic_requested_at = self._clock()
                security_master = _consume_result(bs.query_stock_basic())
                security_master_retrieved_at = self._clock()
            finally:
                with redirect_stdout(StringIO()):
                    bs.logout()
        finally:
            socket.setdefaulttimeout(previous_timeout)
        _validate_nonempty_response("trading calendar", calendar)
        acquisitions = tuple(
            _build_historical_acquisition(
                query_date=query_date,
                constituent_response=response,
                constituent_requested_at=requested_at,
                constituent_retrieved_at=response_retrieved_at,
                security_master_response=security_master,
                security_master_requested_at=basic_requested_at,
                security_master_retrieved_at=security_master_retrieved_at,
                retrieved_at=security_master_retrieved_at,
                calendar_response=calendar,
                calendar_requested_at=calendar_requested_at,
                calendar_retrieved_at=calendar_retrieved_at,
                calendar_range=(start_date, end_date),
            )
            for _effective_date, (
                query_date,
                response,
                requested_at,
                response_retrieved_at,
            ) in sorted(distinct.items())
        )
        scan_result, scan_manifest, scan_archive_id = _build_history_scan_archive(
            start_date=start_date,
            end_date=end_date,
            constituent_responses=tuple(query_responses),
            calendar_response=calendar,
            calendar_requested_at=calendar_requested_at,
            calendar_retrieved_at=calendar_retrieved_at,
            security_master_response=security_master,
            security_master_requested_at=basic_requested_at,
            security_master_retrieved_at=security_master_retrieved_at,
            retrieved_at=security_master_retrieved_at,
        )
        return FreeResearchUniverseHistoryAcquisition(
            acquisitions=acquisitions,
            queried_trading_dates=trading_dates,
            query_effective_dates=tuple(query_effective_dates),
            scan_provider_result=scan_result,
            scan_source_manifest=scan_manifest,
            scan_raw_archive_id=scan_archive_id,
            start_date=start_date,
            end_date=end_date,
            retrieved_at=security_master_retrieved_at,
        )


def _build_historical_acquisition(
    *,
    query_date: date,
    constituent_response: dict[str, Any],
    constituent_requested_at: datetime,
    constituent_retrieved_at: datetime,
    security_master_response: dict[str, Any],
    security_master_requested_at: datetime,
    security_master_retrieved_at: datetime,
    retrieved_at: datetime,
    calendar_response: dict[str, Any] | None = None,
    calendar_requested_at: datetime | None = None,
    calendar_retrieved_at: datetime | None = None,
    calendar_range: tuple[date, date] | None = None,
) -> FreeResearchUniverseAcquisition:
    _validate_nonempty_response("historical CSI 300 constituents", constituent_response)
    _validate_nonempty_response("Security Master lifecycle", security_master_response)
    instants = [
        constituent_requested_at,
        constituent_retrieved_at,
        security_master_requested_at,
        security_master_retrieved_at,
        retrieved_at,
    ]
    if calendar_requested_at is not None:
        instants.append(calendar_requested_at)
    if calendar_retrieved_at is not None:
        instants.append(calendar_retrieved_at)
    if any(item.tzinfo is None or item.utcoffset() is None for item in instants):
        raise ValueError("Research Universe client clock must be timezone-aware")
    constituents = constituent_response
    security_master = security_master_response
    constituent_source = _historical_source_payload(
        response=constituents,
        product="query_hs300_stocks:effective-date:v1",
        locator=f"baostock://query-hs300-stocks/{query_date.isoformat()}",
        requested_at=constituent_requested_at,
        retrieved_at=constituent_retrieved_at,
        request_parameters=(("date", query_date.isoformat()),),
        symbol_scope=("CSI_300_CONSTITUENTS",),
    )
    security_master_source = _historical_source_payload(
        response=security_master,
        product="query_stock_basic:all:v1",
        locator=(f"baostock://query-stock-basic/all-for-historical-constituents/{query_date.isoformat()}"),
        requested_at=security_master_requested_at,
        retrieved_at=security_master_retrieved_at,
        request_parameters=(("scope", "ALL_SECURITIES"),),
        symbol_scope=("ALL_SECURITIES",),
    )
    raw_payloads = [constituent_source, security_master_source]
    if calendar_response is not None:
        if (
            calendar_requested_at is None
            or calendar_retrieved_at is None
            or calendar_range is None
        ):
            raise ValueError("Historical constituent calendar lineage is incomplete")
        raw_payloads.append(
            _historical_source_payload(
                response=calendar_response,
                product="query_trade_dates:range:v1",
                locator=(f"baostock://query-trade-dates/{calendar_range[0].isoformat()}/{calendar_range[1].isoformat()}"),
                requested_at=calendar_requested_at,
                retrieved_at=calendar_retrieved_at,
                request_parameters=(
                    ("end_date", calendar_range[1].isoformat()),
                    ("start_date", calendar_range[0].isoformat()),
                ),
                symbol_scope=("A_SHARE_TRADING_CALENDAR",),
            )
        )
    decision_time = DecisionTime(retrieved_at)
    provider_result = PublicCompositeProviderResult(
        profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
        decision_time=decision_time,
        raw_payloads=tuple(raw_payloads),
        bars=(),
        quotes=(),
        source_conflicts=(),
        limitations=(
            "CURRENT_CLASSIFICATION_NOT_BACKFILLED",
            "FREE_DATA_EXPLORATORY",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_PROVIDER_FALLBACK",
            "RETRIEVED_AFTER_CONSTITUENT_EFFECTIVE_DATE",
        ),
    )
    manifest = SourceManifest(
        provider_profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
        decision_time=decision_time,
        source_artifacts=provider_result.source_artifact_references,
        fields=(),
        source_conflicts=(),
        limitations=provider_result.limitations,
        data_eligibility=DataEligibility.EXPLORATORY,
    )
    archive_id = source_archive_id(
        provider_result=provider_result,
        source_manifest=manifest,
    )
    constituent_rows = _normalize_security_master_rows(
        fields=tuple(str(item) for item in constituents["fields"]),
        rows=tuple(tuple(str(item) for item in row) for row in constituents["rows"]),
    )
    basic_rows = _normalize_security_master_rows(
        fields=tuple(str(item) for item in security_master["fields"]),
        rows=tuple(tuple(str(item) for item in row) for row in security_master["rows"]),
    )
    snapshot = build_historical_constituent_universe_snapshot(
        effective_date=query_date,
        known_at=retrieved_at,
        provider_id=str(BAOSTOCK_PUBLIC_PROVIDER_ID),
        provider_contract="baostock-query-hs300-stocks/v1",
        source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            manifest.source_manifest_id,
            manifest.content_hash,
        ),
        constituent_source_reference=ValidationArtifactReference(
            "HISTORICAL_CONSTITUENT_SNAPSHOT",
            constituent_source.source_artifact_id,
            constituent_source.raw_hash,
        ),
        raw_archive_id=archive_id,
        evidence_origin=FreeDataEvidenceOrigin.REAL_FREE_PROVIDER_OBSERVATION,
        constituent_rows=constituent_rows,
        security_master_rows=basic_rows,
    )
    return FreeResearchUniverseAcquisition(provider_result, manifest, snapshot)


def _build_history_scan_archive(
    *,
    start_date: date,
    end_date: date,
    constituent_responses: tuple[
        tuple[date, dict[str, Any], datetime, datetime], ...
    ],
    calendar_response: dict[str, Any],
    calendar_requested_at: datetime,
    calendar_retrieved_at: datetime,
    security_master_response: dict[str, Any],
    security_master_requested_at: datetime,
    security_master_retrieved_at: datetime,
    retrieved_at: datetime,
) -> tuple[PublicCompositeProviderResult, SourceManifest, str]:
    """Bind every range-scan response into one immutable replay archive."""

    raw_payloads = tuple(
        _historical_source_payload(
            response=response,
            product="query_hs300_stocks:session-history:v1",
            locator=f"baostock://query-hs300-stocks/history/{query_date.isoformat()}",
            requested_at=requested_at,
            retrieved_at=response_retrieved_at,
            request_parameters=(("date", query_date.isoformat()),),
            symbol_scope=("CSI_300_CONSTITUENTS",),
        )
        for query_date, response, requested_at, response_retrieved_at in constituent_responses
    ) + (
        _historical_source_payload(
            response=calendar_response,
            product="query_trade_dates:history-range:v1",
            locator=(f"baostock://query-trade-dates/history/{start_date.isoformat()}/{end_date.isoformat()}"),
            requested_at=calendar_requested_at,
            retrieved_at=calendar_retrieved_at,
            request_parameters=(
                ("end_date", end_date.isoformat()),
                ("start_date", start_date.isoformat()),
            ),
            symbol_scope=("A_SHARE_TRADING_CALENDAR",),
        ),
        _historical_source_payload(
            response=security_master_response,
            product="query_stock_basic:history-range:v1",
            locator=(f"baostock://query-stock-basic/history/{start_date.isoformat()}/{end_date.isoformat()}"),
            requested_at=security_master_requested_at,
            retrieved_at=security_master_retrieved_at,
            request_parameters=(("scope", "ALL_SECURITIES"),),
            symbol_scope=("ALL_SECURITIES",),
        ),
    )
    decision_time = DecisionTime(retrieved_at)
    result = PublicCompositeProviderResult(
        profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
        decision_time=decision_time,
        raw_payloads=raw_payloads,
        bars=(),
        quotes=(),
        source_conflicts=(),
        limitations=(
            "CURRENT_CLASSIFICATION_NOT_BACKFILLED",
            "EVERY_TRADING_SESSION_RESPONSE_ARCHIVED",
            "FREE_DATA_EXPLORATORY",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_PROVIDER_FALLBACK",
            "RETRIEVED_AFTER_CONSTITUENT_EFFECTIVE_DATE",
        ),
    )
    manifest = SourceManifest(
        provider_profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
        decision_time=decision_time,
        source_artifacts=result.source_artifact_references,
        fields=(),
        source_conflicts=(),
        limitations=result.limitations,
        data_eligibility=DataEligibility.EXPLORATORY,
    )
    return (
        result,
        manifest,
        source_archive_id(provider_result=result, source_manifest=manifest),
    )


def _validate_nonempty_response(label: str, response: dict[str, Any]) -> None:
    if response["error_code"] != "0" or not response["rows"]:
        raise AShareDataError(f"BaoStock {label} query returned no usable rows")


def _validated_constituent_rows(
    response: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    _validate_nonempty_response("historical CSI 300 constituents", response)
    rows = _normalize_security_master_rows(
        fields=tuple(str(item) for item in response["fields"]),
        rows=tuple(tuple(str(item) for item in row) for row in response["rows"]),
    )
    if any(not str(item.get("updateDate", "")).strip() for item in rows):
        raise AShareDataError("BaoStock CSI 300 response lacks updateDate")
    return rows


def _trading_dates(response: dict[str, Any]) -> tuple[date, ...]:
    _validate_nonempty_response("trading calendar", response)
    fields = tuple(str(item) for item in response["fields"])
    if set(fields) != {"calendar_date", "is_trading_day"}:
        raise AShareDataError("BaoStock trading calendar fields are unusable")
    date_index = fields.index("calendar_date")
    trading_index = fields.index("is_trading_day")
    result = tuple(date.fromisoformat(str(row[date_index])) for row in response["rows"] if str(row[trading_index]) == "1")
    if not result or result != tuple(sorted(set(result))):
        raise AShareDataError("BaoStock trading calendar has no ordered sessions")
    return result


def _historical_source_payload(
    *,
    response: dict[str, Any],
    product: str,
    locator: str,
    requested_at: datetime,
    retrieved_at: datetime,
    request_parameters: tuple[tuple[str, str], ...],
    symbol_scope: tuple[str, ...],
) -> AcquiredSourcePayload:
    raw = json.dumps(
        response,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return AcquiredSourcePayload(
        provider_id=BAOSTOCK_PUBLIC_PROVIDER_ID,
        product=product,
        locator=locator,
        raw_payload=raw,
        retrieved_time=RetrievedAt(retrieved_at),
        limitations=(
            "BAOSTOCK_LIBRARY_RESULT_REENCODED_NOT_TRANSPORT_BYTES",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "PUBLIC_DATA_EXPLORATORY_ONLY",
            "RETRIEVED_AFTER_HISTORICAL_EFFECTIVE_DATE",
        ),
        request_metadata=RawSourceRequestMetadata(
            provider_profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
            endpoint=product.split(":", 1)[0],
            request_parameters=request_parameters,
            requested_at=requested_at,
            provider_timestamp=None,
            event_time=None,
            available_at=retrieved_at,
            decision_time=retrieved_at,
            http_status=None,
            content_type="application/json",
            response_size=len(raw),
            encoding="utf-8",
            symbol_scope=symbol_scope,
            field_scope=tuple(sorted(str(item) for item in response["fields"])),
        ),
    )


def _consume_result(result: Any) -> dict[str, Any]:
    fields = [str(item) for item in getattr(result, "fields", ())]
    rows: list[list[str]] = []
    if getattr(result, "error_code", "0") == "0":
        while result.next():
            rows.append([str(item) for item in result.get_row_data()])
    return {
        "error_code": str(getattr(result, "error_code", "UNKNOWN")),
        "error_message": str(getattr(result, "error_msg", "")),
        "fields": fields,
        "rows": rows,
    }


def _normalize_security_master_rows(
    *,
    fields: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
) -> tuple[dict[str, Any], ...]:
    if not fields or len(fields) != len(set(fields)) or "code" not in fields:
        raise AShareDataError("BaoStock Security Master fields are unusable")
    normalized: list[dict[str, Any]] = []
    code_index = fields.index("code")
    for index, row in enumerate(rows):
        if code_index >= len(row) or not row[code_index].strip():
            raise AShareDataError(f"BaoStock malformed Security Master row has no security code: row {index}")
        malformed = len(row) != len(fields)
        values: dict[str, Any] = {field: (row[field_index] if field_index < len(row) else "") for field_index, field in enumerate(fields)}
        if malformed:
            values["_provider_row_malformed"] = True
            values["_provider_row_field_count"] = len(row)
        normalized.append(values)
    return tuple(normalized)


__all__ = [
    "BaoStockResearchUniverseClient",
    "FreeResearchUniverseAcquisition",
    "FreeResearchUniverseHistoryAcquisition",
]
