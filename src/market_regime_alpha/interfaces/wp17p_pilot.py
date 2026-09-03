"""Deterministic manifests for the isolated WP-17P real-data pilot."""

from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta
import hashlib
import re
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from market_regime_alpha.infrastructure.providers.baostock_archive import (
    BaoStockArchiveQuery,
    BaoStockArchiveQueryKind,
)
from market_regime_alpha.interfaces.archive import (
    ArchiveManifestSlice,
    ArchiveOperatorManifest,
)
from market_regime_alpha.market.application import (
    ArchiveSlicePlan,
    StartMarketArchiveRequest,
)
from market_regime_alpha.market.domain import ArchiveLane, BarTimeframe, PriceBasis
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.shared.hashing import canonical_json_sha256, sha256_bytes
from market_regime_alpha.shared.identity import ContentHash


_SHANGHAI = ZoneInfo("Asia/Shanghai")
_A_SHARE_CODE = re.compile(r"^(?:sh|sz)\.\d{6}$")
_PILOT_SALT = "WP17P_ENGINEERING_PILOT_V1"
_EMPTY_HEADERS_SHA256 = sha256_bytes(b"")


def select_deterministic_pilot(codes: tuple[str, ...]) -> tuple[str, ...]:
    """Select 32 equities by a frozen identity hash, never by a return value."""

    unique = set(codes)
    if len(unique) != len(codes) or any(
        _A_SHARE_CODE.fullmatch(item) is None for item in codes
    ):
        raise ValueError("pilot inputs must be unique BaoStock A-share codes")
    if len(codes) < 32:
        raise ValueError("pilot selection requires at least 32 instruments")
    ranked = sorted(
        codes,
        key=lambda item: (
            hashlib.sha256(f"{_PILOT_SALT}:{item}".encode()).hexdigest(),
            item,
        ),
    )
    return tuple(sorted(ranked[:32]))


def build_retrospective_manifest(
    *,
    provider_product_id: UUID,
    code_artifact_id: UUID,
    config_artifact_id: UUID,
    execution_date: date,
    membership_dates: tuple[date, ...],
    security_master_codes: tuple[str, ...],
    pilot_codes: tuple[str, ...],
    exchange_calendar: str,
    provenance_sha256: str,
    archive_generation: int = 1,
    reserved_free_bytes: int = 2_000_000_000,
    maximum_archive_bytes: int = 2_500_000_000,
    maximum_slice_bytes: int = 50_000_000,
) -> ArchiveOperatorManifest:
    _validate_archive_generation(archive_generation)
    if execution_date < date(2026, 1, 1):
        raise ValueError("retrospective execution date precedes the WP-17P window")
    _validate_codes(security_master_codes)
    exchange_prefix = _exchange_prefix(exchange_calendar)
    selection_population = tuple(
        code for code in security_master_codes if code.startswith(exchange_prefix)
    )
    if select_deterministic_pilot(selection_population) != pilot_codes:
        raise ValueError("pilot roster differs from the frozen stable-hash selection")
    if (
        not membership_dates
        or membership_dates != tuple(sorted(set(membership_dates)))
        or membership_dates[0] < date(2026, 1, 1)
        or membership_dates[-1] > execution_date
    ):
        raise ValueError("membership dates must be unique and inside the archive window")
    archive_code = (
        f"wp17p_retro_2026_{execution_date:%Y%m%d}_g{archive_generation:03d}"
    )
    archive_id = _id(f"archive:{archive_code}")
    window_start = _at(date(2026, 1, 1), time.min)
    window_end = _at(execution_date, time.max)
    inputs: list[tuple[str, datetime, datetime, BaoStockArchiveQuery, str, str]] = [
        (
            "calendar:2026",
            window_start,
            window_end,
            BaoStockArchiveQuery(
                BaoStockArchiveQueryKind.TRADE_DATES,
                date(2026, 1, 1),
                execution_date,
            ),
            "TRADING_SESSION",
            "BACKFILL_CALENDAR",
        )
    ]
    inputs.extend(
        (
            f"security:{code}",
            window_start,
            window_end,
            BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code=code),
            "INSTRUMENT",
            "BACKFILL_SECURITY_MASTER",
        )
        for code in security_master_codes
    )
    inputs.extend(
        (
            f"csi300:{session_date.isoformat()}",
            _at(session_date, time.min),
            _at(session_date, time.max),
            BaoStockArchiveQuery(
                BaoStockArchiveQueryKind.CSI300_MEMBERS,
                session_date,
                session_date,
            ),
            "CLASSIFICATION_MEMBERSHIP",
            "BACKFILL_MEMBERSHIP",
        )
        for session_date in membership_dates
    )
    for code in pilot_codes:
        for month_start, month_end in _months(execution_date):
            start_at = _at(month_start, time.min)
            end_at = _at(month_end, time.max)
            inputs.extend(
                (
                    (
                        f"daily:{code}:{month_start:%Y%m}",
                        start_at,
                        end_at,
                        BaoStockArchiveQuery(
                            BaoStockArchiveQueryKind.HISTORY_DAILY_RAW,
                            month_start,
                            month_end,
                            code,
                        ),
                        "MARKET_BAR_DAILY",
                        "BACKFILL_DAILY",
                    ),
                    (
                        f"5m:{code}:{month_start:%Y%m}",
                        start_at,
                        end_at,
                        BaoStockArchiveQuery(
                            BaoStockArchiveQueryKind.HISTORY_5M_RAW,
                            month_start,
                            month_end,
                            code,
                        ),
                        "MARKET_BAR_5M",
                        "BACKFILL_5M",
                    ),
                )
            )
    return _manifest(
        archive_id=archive_id,
        archive_code=archive_code,
        lane=ArchiveLane.RETROSPECTIVE_BACKFILL,
        provider_product_id=provider_product_id,
        code_artifact_id=code_artifact_id,
        config_artifact_id=config_artifact_id,
        exchange_calendar=exchange_calendar,
        instrument_scope=(
            f"CSI300_{exchange_calendar}_STABLE_HASH_32_ENGINEERING_PILOT"
        ),
        instrument_scope_sha256=canonical_json_sha256(
            {
                "selection": _PILOT_SALT,
                "exchange_calendar": exchange_calendar,
                "codes": pilot_codes,
                "membership_dates": membership_dates,
            }
        ),
        window_start=window_start,
        window_end=window_end,
        inputs=tuple(inputs),
        provenance_sha256=provenance_sha256,
        reserved_free_bytes=reserved_free_bytes,
        maximum_archive_bytes=maximum_archive_bytes,
        maximum_slice_bytes=maximum_slice_bytes,
    )


def build_prospective_manifest(
    *,
    provider_product_id: UUID,
    code_artifact_id: UUID,
    config_artifact_id: UUID,
    archive_not_before: datetime,
    decision_session_date: date,
    outcome_session_date: date,
    later_verification_session_date: date,
    pilot_codes: tuple[str, ...],
    exchange_calendar: str,
    provenance_sha256: str,
    archive_generation: int = 1,
    reserved_free_bytes: int = 2_000_000_000,
    maximum_archive_bytes: int = 1_000_000_000,
    maximum_slice_bytes: int = 50_000_000,
) -> ArchiveOperatorManifest:
    _validate_archive_generation(archive_generation)
    if archive_not_before.tzinfo is None or archive_not_before.utcoffset() is None:
        raise ValueError("archive_not_before must include an offset")
    archive_not_before = archive_not_before.astimezone(UTC)
    _validate_codes(pilot_codes)
    exchange_prefix = _exchange_prefix(exchange_calendar)
    if len(pilot_codes) != 32:
        raise ValueError("prospective archive requires the exact 32-instrument pilot")
    if any(not code.startswith(exchange_prefix) for code in pilot_codes):
        raise ValueError("pilot instrument is outside the explicit exchange calendar")
    archive_code = (
        f"wp17p_prospective_{archive_not_before:%Y%m%d_%H%M%S}"
        f"_g{archive_generation:03d}"
    )
    archive_id = _id(f"archive:{archive_code}")
    first_code = pilot_codes[0]
    smoke_start = archive_not_before + timedelta(minutes=1)
    if not decision_session_date < outcome_session_date < later_verification_session_date:
        raise ValueError("prospective Sessions must be strictly chronological")
    future_slots = (
        ("PRE_DECISION", decision_session_date, time(14, 40), time(14, 48)),
        ("DECISION_NEAR", decision_session_date, time(14, 50), time(14, 56)),
        ("POST_CLOSE", decision_session_date, time(15, 25), time(15, 35)),
        ("EVENING_REVISION", decision_session_date, time(19, 55), time(20, 5)),
        ("OUTCOME_PRE_OPEN", outcome_session_date, time(8, 55), time(9, 5)),
        ("OUTCOME_PATH", outcome_session_date, time(9, 30), time(10, 31)),
        ("OUTCOME_10_30", outcome_session_date, time(10, 25), time(10, 31)),
        ("OUTCOME_POST_CLOSE", outcome_session_date, time(15, 25), time(15, 35)),
        (
            "REVISION_VERIFICATION",
            later_verification_session_date,
            time(15, 25),
            time(15, 35),
        ),
    )
    inputs: list[tuple[str, datetime, datetime, BaoStockArchiveQuery, str, str]] = [
        (
            f"archive-start-smoke:{first_code}",
            smoke_start,
            smoke_start + timedelta(minutes=1),
            BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code=first_code),
            "INSTRUMENT",
            "ARCHIVE_START_SMOKE",
        )
    ]
    for slot, session_date, start, end in future_slots:
        for code in pilot_codes:
            kind = (
                BaoStockArchiveQueryKind.HISTORY_5M_RAW
                if slot in {"PRE_DECISION", "DECISION_NEAR", "OUTCOME_PATH", "OUTCOME_10_30"}
                else BaoStockArchiveQueryKind.HISTORY_DAILY_RAW
            )
            inputs.append(
                (
                    f"{slot.lower()}:{code}:{session_date.isoformat()}",
                    _at(session_date, start),
                    _at(session_date, end),
                    BaoStockArchiveQuery(kind, session_date, session_date, code),
                    "MARKET_BAR_5M" if kind is BaoStockArchiveQueryKind.HISTORY_5M_RAW else "MARKET_BAR_DAILY",
                    slot,
                )
            )
    window_end = max(item[2] for item in inputs)
    return _manifest(
        archive_id=archive_id,
        archive_code=archive_code,
        lane=ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS,
        provider_product_id=provider_product_id,
        code_artifact_id=code_artifact_id,
        config_artifact_id=config_artifact_id,
        exchange_calendar=exchange_calendar,
        instrument_scope=(
            f"CSI300_{exchange_calendar}_STABLE_HASH_32_PROSPECTIVE_ARCHIVE"
        ),
        instrument_scope_sha256=canonical_json_sha256(
            {
                "selection": _PILOT_SALT,
                "exchange_calendar": exchange_calendar,
                "codes": pilot_codes,
            }
        ),
        window_start=smoke_start,
        window_end=window_end,
        inputs=tuple(inputs),
        provenance_sha256=provenance_sha256,
        reserved_free_bytes=reserved_free_bytes,
        maximum_archive_bytes=maximum_archive_bytes,
        maximum_slice_bytes=maximum_slice_bytes,
    )


def _manifest(
    *,
    archive_id: UUID,
    archive_code: str,
    lane: ArchiveLane,
    provider_product_id: UUID,
    code_artifact_id: UUID,
    config_artifact_id: UUID,
    exchange_calendar: str,
    instrument_scope: str,
    instrument_scope_sha256: str,
    window_start: datetime,
    window_end: datetime,
    inputs: tuple[tuple[str, datetime, datetime, BaoStockArchiveQuery, str, str], ...],
    provenance_sha256: str,
    reserved_free_bytes: int,
    maximum_archive_bytes: int,
    maximum_slice_bytes: int,
) -> ArchiveOperatorManifest:
    slices: list[ArchiveManifestSlice] = []
    for ordinal, (scope, start, end, query, fact_kind, schedule_slot) in enumerate(
        inputs, start=1
    ):
        capture = CaptureRequest(
            provider_product_id=provider_product_id,
            capture_key=f"{archive_code}/{ordinal:04d}",
            resource=query.resource,
            request_headers_hash=ContentHash(_EMPTY_HEADERS_SHA256),
        )
        plan = ArchiveSlicePlan(
            market_archive_slice_id=_id(f"{archive_id}:slice:{ordinal}"),
            ordinal=ordinal,
            scope_key=scope,
            event_window_start=start,
            event_window_end=end,
            request_sha256=canonical_json_sha256(capture),
            expected_fact_kind=fact_kind,
        )
        slices.append(ArchiveManifestSlice(plan, capture, schedule_slot))
    request = StartMarketArchiveRequest(
        market_archive_id=archive_id,
        archive_code=archive_code,
        lane=lane,
        provider_product_id=provider_product_id,
        exchange_code=exchange_calendar,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        instrument_scope=instrument_scope,
        instrument_scope_sha256=instrument_scope_sha256,
        event_window_start=window_start,
        event_window_end=window_end,
        reserved_free_bytes=reserved_free_bytes,
        maximum_archive_bytes=maximum_archive_bytes,
        maximum_slice_bytes=maximum_slice_bytes,
        code_artifact_id=code_artifact_id,
        config_artifact_id=config_artifact_id,
        provenance_sha256=provenance_sha256,
        slices=tuple(item.plan for item in slices),
    )
    return ArchiveOperatorManifest(request, tuple(slices))


def _months(execution_date: date) -> tuple[tuple[date, date], ...]:
    cursor = date(2026, 1, 1)
    result: list[tuple[date, date]] = []
    while cursor <= execution_date:
        last = date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1])
        result.append((cursor, min(last, execution_date)))
        cursor = last + timedelta(days=1)
    return tuple(result)


def _validate_codes(codes: tuple[str, ...]) -> None:
    if (
        not codes
        or len(set(codes)) != len(codes)
        or tuple(sorted(codes)) != codes
        or any(_A_SHARE_CODE.fullmatch(item) is None for item in codes)
    ):
        raise ValueError("security roster must be sorted unique BaoStock A-share codes")


def _exchange_prefix(exchange_calendar: str) -> str:
    try:
        return {"XSHG": "sh.", "XSHE": "sz."}[exchange_calendar]
    except KeyError as exc:
        raise ValueError("exchange_calendar must be XSHG or XSHE") from exc


def _validate_archive_generation(archive_generation: int) -> None:
    if isinstance(archive_generation, bool) or archive_generation < 1:
        raise ValueError("archive_generation must be positive")


def _at(value_date: date, value_time: time) -> datetime:
    return datetime.combine(value_date, value_time, tzinfo=_SHANGHAI).astimezone(UTC)


def _id(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"mra:wp17p:{key}")


__all__ = [
    "build_prospective_manifest",
    "build_retrospective_manifest",
    "select_deterministic_pilot",
]
