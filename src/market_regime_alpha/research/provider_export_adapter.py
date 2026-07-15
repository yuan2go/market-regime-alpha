"""Strict adapter for a normalized generic provider-export bundle.

This adapter does not guess vendor-specific field meanings. It accepts only an explicit normalized
schema whose availability, finality, adjustment, liquidity, and buyability semantics have already
been declared. Concrete Xuntou/QMT/vendor adapters may translate their native exports into this
schema later.
"""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ProviderId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime, RetrievedAt
from market_regime_alpha.data.contracts import ProviderReference, SourceArtifactReference
from market_regime_alpha.data.rehearsal import (
    RehearsalDailyBar,
    RehearsalDecisionSnapshot,
    RehearsalNextSessionBar,
)
from market_regime_alpha.data.trading_calendar import TradingSession, build_trading_calendar_artifact
from market_regime_alpha.research.provider_rehearsal_market_artifact import (
    ProviderRehearsalMarketArtifact,
    build_provider_rehearsal_market_artifact,
)
from market_regime_alpha.universe.artifacts import (
    HistoricalUniverseMembershipRecord,
    build_historical_pit_universe_artifact,
)
from market_regime_alpha.universe.eligibility_policy import (
    DecisionBuyabilityStatus,
    RawTradingEligibilityObservation,
)


GENERIC_PROVIDER_EXPORT_BUNDLE_SCHEMA_VERSION = "generic-provider-export-bundle-v1"


class GenericProviderExportAdapterError(ValueError):
    """Raised when a normalized provider export cannot be adapted without inventing semantics."""


def load_generic_provider_export_bundle(path: Path) -> ProviderRehearsalMarketArtifact:
    """Load a normalized generic provider-export JSON bundle."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GenericProviderExportAdapterError("PROVIDER_EXPORT_BUNDLE_INVALID") from exc
    if not isinstance(raw, dict):
        raise GenericProviderExportAdapterError("PROVIDER_EXPORT_BUNDLE_INVALID")
    return adapt_generic_provider_export_mapping(raw)


def adapt_generic_provider_export_mapping(raw: dict[str, Any]) -> ProviderRehearsalMarketArtifact:
    """Adapt one explicit normalized mapping into the R5 Provider Rehearsal Market Artifact."""

    required_top_level = {
        "schema_version",
        "provider_references",
        "source_artifacts",
        "conventions",
        "pit_correct_for_scope",
        "calendar",
        "universe",
        "daily_bars",
        "decision_snapshots",
        "next_session_bars",
        "raw_eligibility_observations",
    }
    if not required_top_level <= set(raw):
        raise GenericProviderExportAdapterError("PROVIDER_EXPORT_REQUIRED_SECTION_MISSING")
    if raw["schema_version"] != GENERIC_PROVIDER_EXPORT_BUNDLE_SCHEMA_VERSION:
        raise GenericProviderExportAdapterError("PROVIDER_EXPORT_SCHEMA_UNSUPPORTED")

    try:
        provider_references = _provider_references(raw["provider_references"])
        source_artifacts = _source_artifacts(raw["source_artifacts"])
        conventions = _required_mapping(raw["conventions"], "PROVIDER_EXPORT_CONVENTIONS_INVALID")
        calendar = _calendar(raw["calendar"])
        universe = _universe(raw["universe"])
        daily_bars = _daily_bars(raw["daily_bars"])
        decision_snapshots = _decision_snapshots(raw["decision_snapshots"])
        next_session_bars = _next_session_bars(raw["next_session_bars"])
        raw_eligibility = _raw_eligibility_observations(raw["raw_eligibility_observations"])
        limitations = _string_tuple(raw.get("limitations", []), "PROVIDER_EXPORT_LIMITATIONS_INVALID")
        pit_correct_for_scope = raw["pit_correct_for_scope"]
        if not isinstance(pit_correct_for_scope, bool):
            raise GenericProviderExportAdapterError("PROVIDER_EXPORT_PIT_SCOPE_FLAG_INVALID")

        return build_provider_rehearsal_market_artifact(
            provider_references=provider_references,
            source_artifacts=source_artifacts,
            retrieval_convention=_required_string(conventions, "retrieval_convention"),
            market_availability_convention=_required_string(conventions, "market_availability_convention"),
            raw_eligibility_evidence_convention=_required_string(conventions, "raw_eligibility_evidence_convention"),
            bar_finality_convention=_required_string(conventions, "bar_finality_convention"),
            price_adjustment_basis=_required_string(conventions, "price_adjustment_basis"),
            trading_calendar=calendar,
            universe_artifact=universe,
            daily_bars=daily_bars,
            decision_snapshots=decision_snapshots,
            next_session_bars=next_session_bars,
            raw_eligibility_observations=raw_eligibility,
            pit_correct_for_scope=pit_correct_for_scope,
            limitations=limitations,
        )
    except GenericProviderExportAdapterError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise GenericProviderExportAdapterError("PROVIDER_EXPORT_FIELD_INVALID") from exc


def _provider_references(value: Any) -> tuple[ProviderReference, ...]:
    rows = _required_list(value, "PROVIDER_EXPORT_PROVIDER_REFERENCES_INVALID")
    return tuple(
        ProviderReference(
            provider_id=ProviderId(_required_string(_required_mapping(row, "PROVIDER_EXPORT_PROVIDER_REFERENCE_INVALID"), "provider_id")),
            product=_required_string(row, "product"),
            contract_version=_required_string(row, "contract_version"),
        )
        for row in rows
    )


def _source_artifacts(value: Any) -> tuple[SourceArtifactReference, ...]:
    rows = _required_list(value, "PROVIDER_EXPORT_SOURCE_ARTIFACTS_INVALID")
    result: list[SourceArtifactReference] = []
    for raw_row in rows:
        row = _required_mapping(raw_row, "PROVIDER_EXPORT_SOURCE_ARTIFACT_INVALID")
        result.append(
            SourceArtifactReference(
                artifact_id=ArtifactId(_required_string(row, "artifact_id")),
                provider_id=ProviderId(_required_string(row, "provider_id")),
                retrieved_at=RetrievedAt(_aware_datetime(row, "retrieved_at")),
                content_hash=_required_string(row, "content_hash"),
                locator=_required_string(row, "locator"),
            )
        )
    return tuple(result)


def _calendar(value: Any):
    raw = _required_mapping(value, "PROVIDER_EXPORT_CALENDAR_INVALID")
    sessions = tuple(
        TradingSession(
            trade_date=_date(row, "trade_date"),
            session_close=_aware_datetime(row, "session_close"),
        )
        for row in _mapping_rows(raw, "sessions", "PROVIDER_EXPORT_CALENDAR_SESSIONS_INVALID")
    )
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId(_required_string(raw, "source_dataset_id")),
        market=_required_string(raw, "market"),
        calendar_version=_required_string(raw, "calendar_version"),
        timezone_name=_required_string(raw, "timezone_name"),
        sessions=sessions,
    )


def _universe(value: Any):
    raw = _required_mapping(value, "PROVIDER_EXPORT_UNIVERSE_INVALID")
    records = tuple(
        HistoricalUniverseMembershipRecord(
            as_of_date=_date(row, "as_of_date"),
            symbol=_required_string(row, "symbol"),
            is_member=_required_bool(row, "is_member"),
        )
        for row in _mapping_rows(raw, "records", "PROVIDER_EXPORT_UNIVERSE_RECORDS_INVALID")
    )
    return build_historical_pit_universe_artifact(
        source_dataset_id=DatasetId(_required_string(raw, "source_dataset_id")),
        method_version=_required_string(raw, "method_version"),
        timezone_name=_required_string(raw, "timezone_name"),
        effective_time_convention=_required_string(raw, "effective_time_convention"),
        records=records,
    )


def _daily_bars(value: Any) -> tuple[RehearsalDailyBar, ...]:
    return tuple(
        RehearsalDailyBar(
            symbol=_required_string(row, "symbol"),
            session_date=_date(row, "session_date"),
            close=_number(row, "close"),
            amount=_number(row, "amount", allow_zero=True),
            available_at=AvailabilityTime(_aware_datetime(row, "available_at")),
            finalized=_required_bool(row, "finalized"),
        )
        for row in _mapping_list(value, "PROVIDER_EXPORT_DAILY_BARS_INVALID")
    )


def _decision_snapshots(value: Any) -> tuple[RehearsalDecisionSnapshot, ...]:
    return tuple(
        RehearsalDecisionSnapshot(
            symbol=_required_string(row, "symbol"),
            decision_time=DecisionTime(_aware_datetime(row, "decision_time")),
            reference_price=_number(row, "reference_price"),
            available_at=AvailabilityTime(_aware_datetime(row, "available_at")),
        )
        for row in _mapping_list(value, "PROVIDER_EXPORT_DECISION_SNAPSHOTS_INVALID")
    )


def _next_session_bars(value: Any) -> tuple[RehearsalNextSessionBar, ...]:
    return tuple(
        RehearsalNextSessionBar(
            symbol=_required_string(row, "symbol"),
            session_date=_date(row, "session_date"),
            open=_number(row, "open"),
            high=_number(row, "high"),
            low=_number(row, "low"),
            close=_number(row, "close"),
            available_at=AvailabilityTime(_aware_datetime(row, "available_at")),
        )
        for row in _mapping_list(value, "PROVIDER_EXPORT_NEXT_SESSION_BARS_INVALID")
    )


def _raw_eligibility_observations(value: Any) -> tuple[RawTradingEligibilityObservation, ...]:
    result: list[RawTradingEligibilityObservation] = []
    for row in _mapping_list(value, "PROVIDER_EXPORT_ELIGIBILITY_RECORDS_INVALID"):
        raw_buyability = row.get("decision_buyability")
        if raw_buyability is None:
            buyability = None
        else:
            if not isinstance(raw_buyability, str):
                raise GenericProviderExportAdapterError("PROVIDER_EXPORT_BUYABILITY_INVALID")
            try:
                buyability = DecisionBuyabilityStatus(raw_buyability)
            except ValueError as exc:
                raise GenericProviderExportAdapterError("PROVIDER_EXPORT_BUYABILITY_INVALID") from exc
        result.append(
            RawTradingEligibilityObservation(
                as_of=AsOfTime(_aware_datetime(row, "as_of")),
                available_at=AvailabilityTime(_aware_datetime(row, "available_at")),
                symbol=_required_string(row, "symbol"),
                is_suspended=_optional_bool(row, "is_suspended"),
                is_st=_optional_bool(row, "is_st"),
                prev_close=_optional_number(row, "prev_close"),
                limit_up_price=_optional_number(row, "limit_up_price"),
                limit_down_price=_optional_number(row, "limit_down_price"),
                limit_regime=_optional_string(row, "limit_regime"),
                listing_age_calendar_days=_optional_int(row, "listing_age_calendar_days"),
                liquidity_value=_optional_number(row, "liquidity_value"),
                liquidity_measure_id=_optional_string(row, "liquidity_measure_id"),
                decision_buyability=buyability,
            )
        )
    return tuple(result)


def _required_mapping(value: Any, error_code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GenericProviderExportAdapterError(error_code)
    return value


def _required_list(value: Any, error_code: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise GenericProviderExportAdapterError(error_code)
    return value


def _mapping_list(value: Any, error_code: str) -> tuple[dict[str, Any], ...]:
    rows = _required_list(value, error_code)
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise GenericProviderExportAdapterError(error_code)
        result.append(row)
    return tuple(result)


def _mapping_rows(raw: dict[str, Any], key: str, error_code: str) -> tuple[dict[str, Any], ...]:
    return _mapping_list(raw.get(key), error_code)


def _required_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise GenericProviderExportAdapterError(f"PROVIDER_EXPORT_{key.upper()}_INVALID")
    return value


def _optional_string(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise GenericProviderExportAdapterError(f"PROVIDER_EXPORT_{key.upper()}_INVALID")
    return value


def _required_bool(raw: dict[str, Any], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise GenericProviderExportAdapterError(f"PROVIDER_EXPORT_{key.upper()}_INVALID")
    return value


def _optional_bool(raw: dict[str, Any], key: str) -> bool | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise GenericProviderExportAdapterError(f"PROVIDER_EXPORT_{key.upper()}_INVALID")
    return value


def _date(raw: dict[str, Any], key: str) -> date:
    value = _required_string(raw, key)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise GenericProviderExportAdapterError(f"PROVIDER_EXPORT_{key.upper()}_INVALID") from exc


def _aware_datetime(raw: dict[str, Any], key: str) -> datetime:
    value = _required_string(raw, key)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GenericProviderExportAdapterError(f"PROVIDER_EXPORT_{key.upper()}_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GenericProviderExportAdapterError(f"PROVIDER_EXPORT_{key.upper()}_TIMEZONE_REQUIRED")
    return parsed


def _number(raw: dict[str, Any], key: str, *, allow_zero: bool = False) -> float:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GenericProviderExportAdapterError(f"PROVIDER_EXPORT_{key.upper()}_INVALID")
    number = float(value)
    if not (number >= 0.0 if allow_zero else number > 0.0):
        raise GenericProviderExportAdapterError(f"PROVIDER_EXPORT_{key.upper()}_INVALID")
    return number


def _optional_number(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    if value is None:
        return None
    return _number(raw, key)


def _optional_int(raw: dict[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GenericProviderExportAdapterError(f"PROVIDER_EXPORT_{key.upper()}_INVALID")
    return value


def _string_tuple(value: Any, error_code: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GenericProviderExportAdapterError(error_code)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            raise GenericProviderExportAdapterError(error_code)
        result.append(item)
    return tuple(result)
