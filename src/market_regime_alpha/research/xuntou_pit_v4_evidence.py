"""Structural and semantic validation for Xuntou PIT evidence v4 bundles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import math
from typing import Any, Mapping, Sequence

from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash
from market_regime_alpha.research.xuntou_pit_v4_adapter import derive_research_orderability
from market_regime_alpha.research.xuntou_pit_v4_contract import (
    AmountUnitContract,
    FinalizedBarEvidence,
    ResearchOrderabilityStatus,
    XUNTOU_PIT_V4_MAPPING_CONTRACT_ID,
    XuntouPITSourceArtifact,
)
from market_regime_alpha.research.xuntou_pit_v4_qualification import (
    PITEvidenceQualification,
    derive_pit_qualification,
)


PIT_V4_EVIDENCE_SECTIONS = (
    "historical_membership",
    "security_master",
    "st_history",
    "suspension_history",
    "orderability",
    "liquidity_unit",
    "bar_finality",
    "availability",
    "evaluation_path",
)
PIT_V4_EVIDENCE_CONVENTIONS = {
    "decision_bar_convention_id": "completed-1m-end-label-at-1455-v1",
    "decision_bar_label": "END_TIME",
    "decision_bar_freshness_seconds": 60,
    "availability_cutoff": "DECISION_TIME",
    "finality_required": True,
    "evaluation_mark_id": "next-session-1030-minute-close-v1",
    "evaluation_time": "10:30",
    "evaluation_price_rule_id": "exact-completed-1030-minute-close-v1",
    "missing_evaluation_policy": "MISSING_AS_CASH",
    "path_evidence_rule_id": "complete-1m-0930-through-1030-v1",
}
_SHA256_LENGTH = 71
_SHANGHAI_OFFSET = timedelta(hours=8)


@dataclass(frozen=True, slots=True)
class PITV4EvidenceScope:
    decision_times: tuple[datetime, ...]
    symbols: tuple[str, ...]

    @property
    def decision_grid(self) -> frozenset[tuple[datetime, str]]:
        return frozenset(
            (decision_time, symbol)
            for decision_time in self.decision_times
            for symbol in self.symbols
        )


@dataclass(frozen=True, slots=True)
class PITV4EvidenceValidation:
    source: XuntouPITSourceArtifact | None
    qualification: PITEvidenceQualification | None
    reasons: tuple[str, ...]


def validate_pit_v4_evidence(payload: Mapping[str, Any]) -> PITV4EvidenceValidation:
    structural_reasons: list[str] = []
    source = _source_artifact(payload.get("source_artifact"), structural_reasons)
    raw_hashes = _raw_source_hashes(payload.get("raw_source_hashes"), structural_reasons)
    if source is not None and raw_hashes:
        expected_source_hash = canonical_identity_hash(
            {"raw_source_hashes": dict(sorted(raw_hashes.items()))}
        )
        if source.content_hash != expected_source_hash:
            structural_reasons.append("SOURCE_ARTIFACT_RAW_HASH_IDENTITY_MISMATCH")
    if source is not None and source.evidence_classification != "PROVIDER_EXPORT":
        structural_reasons.append("SOURCE_EVIDENCE_CLASSIFICATION_NOT_QUALIFIED")
    if payload.get("mapping_contract_id") != XUNTOU_PIT_V4_MAPPING_CONTRACT_ID:
        structural_reasons.append("V4_MAPPING_CONTRACT_MISMATCH")
    if payload.get("conventions") != PIT_V4_EVIDENCE_CONVENTIONS:
        structural_reasons.append("V4_EVIDENCE_CONVENTION_MISMATCH")
    scope = _scope(payload.get("evidence_scope"), structural_reasons)
    sections_value = payload.get("evidence_sections")
    if not isinstance(sections_value, Mapping):
        structural_reasons.append("EVIDENCE_SECTIONS_MISSING")
        return PITV4EvidenceValidation(source, None, tuple(structural_reasons))
    if set(sections_value) != set(PIT_V4_EVIDENCE_SECTIONS):
        structural_reasons.append("EVIDENCE_SECTION_SET_MISMATCH")
    section_records = {
        name: _section_records(name, sections_value.get(name), structural_reasons)
        for name in PIT_V4_EVIDENCE_SECTIONS
    }
    if source is None or not raw_hashes or scope is None:
        return PITV4EvidenceValidation(
            source, None, tuple(dict.fromkeys(structural_reasons))
        )

    membership_sources = tuple(
        str(row.get("membership_source", ""))
        for row in section_records["historical_membership"]
    )
    checks = {
        "historical_membership_complete": _membership_complete(
            section_records["historical_membership"], scope
        ),
        "security_master_complete": _security_master_complete(
            section_records["security_master"], scope
        ),
        "st_history_complete": _st_history_complete(section_records["st_history"], scope),
        "suspension_history_complete": _suspension_complete(
            section_records["suspension_history"], scope
        ),
        "orderability_complete": _orderability_complete(
            section_records["orderability"], scope
        ),
        "liquidity_unit_verified": _liquidity_unit_verified(
            section_records["liquidity_unit"]
        ),
        "bar_finality_verified": _bar_finality_verified(
            section_records["bar_finality"], scope
        ),
        "availability_verified": _availability_verified(
            section_records["availability"], scope
        ),
        "evaluation_path_complete": _evaluation_path_complete(
            section_records["evaluation_path"], section_records["bar_finality"], scope
        ),
    }
    qualification = derive_pit_qualification(
        **checks,
        membership_sources=membership_sources,
        input_declared_pit_correct=(
            bool(payload["pit_correct_for_scope"])
            if "pit_correct_for_scope" in payload
            else None
        ),
    )
    reasons = tuple(dict.fromkeys((*structural_reasons, *qualification.reasons)))
    return PITV4EvidenceValidation(source, qualification, reasons)


def _source_artifact(
    value: object, reasons: list[str]
) -> XuntouPITSourceArtifact | None:
    if not isinstance(value, Mapping):
        reasons.append("SOURCE_ARTIFACT_EVIDENCE_MISSING")
        return None
    fields = set(XuntouPITSourceArtifact.__dataclass_fields__)
    if set(value) != fields:
        reasons.append("SOURCE_ARTIFACT_FIELDS_MISMATCH")
        return None
    payload = dict(value)
    try:
        for field in ("retrieved_at", "export_started_at", "export_completed_at"):
            payload[field] = _datetime(payload[field])
        return XuntouPITSourceArtifact(**payload)
    except (TypeError, ValueError):
        reasons.append("SOURCE_ARTIFACT_EVIDENCE_INVALID")
        return None


def _raw_source_hashes(value: object, reasons: list[str]) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        reasons.append("RAW_SOURCE_HASH_EVIDENCE_MISSING")
        return {}
    output = {str(key): str(item) for key, item in value.items()}
    if any(not key or not _valid_hash(item) for key, item in output.items()):
        reasons.append("RAW_SOURCE_HASH_EVIDENCE_INVALID")
        return {}
    return output


def _scope(value: object, reasons: list[str]) -> PITV4EvidenceScope | None:
    if not isinstance(value, Mapping) or set(value) != {"decision_times", "symbols"}:
        reasons.append("PIT_EVIDENCE_SCOPE_MISSING")
        return None
    try:
        decision_times = tuple(_datetime(item) for item in _sequence(value["decision_times"]))
        symbols = tuple(str(item) for item in _sequence(value["symbols"]))
    except (TypeError, ValueError):
        reasons.append("PIT_EVIDENCE_SCOPE_INVALID")
        return None
    if (
        not decision_times
        or not symbols
        or len(set(decision_times)) != len(decision_times)
        or len(set(symbols)) != len(symbols)
        or any(not symbol for symbol in symbols)
        or any(
            item.utcoffset() != _SHANGHAI_OFFSET or item.timetz().replace(tzinfo=None) != time(14, 55)
            for item in decision_times
        )
    ):
        reasons.append("PIT_EVIDENCE_SCOPE_INVALID")
        return None
    return PITV4EvidenceScope(decision_times, symbols)


def _section_records(
    name: str, value: object, reasons: list[str]
) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Mapping) or set(value) != {"content_hash", "records"}:
        reasons.append(f"{name.upper()}_EVIDENCE_MISSING")
        return ()
    records_value = value.get("records")
    if not isinstance(records_value, list) or any(
        not isinstance(row, Mapping) for row in records_value
    ):
        reasons.append(f"{name.upper()}_EVIDENCE_INVALID")
        return ()
    records = tuple(row for row in records_value if isinstance(row, Mapping))
    expected_hash = canonical_identity_hash({"records": list(records)})
    if value.get("content_hash") != expected_hash:
        reasons.append(f"{name.upper()}_CONTENT_HASH_MISMATCH")
        return ()
    return records


def _membership_complete(
    rows: tuple[Mapping[str, Any], ...], scope: PITV4EvidenceScope
) -> bool:
    expected = frozenset((item.date(), symbol) for item, symbol in scope.decision_grid)
    actual: set[tuple[date, str]] = set()
    for row in rows:
        try:
            as_of = date.fromisoformat(str(row["as_of_date"]))
            symbol = str(row["symbol"])
            decision_time = _decision_for_date(scope, as_of)
            available_at = _datetime(row["available_at"])
            source = str(row["membership_source"])
            if (
                not isinstance(row["is_member"], bool)
                or row["lookup_complete"] is not True
                or not _nonempty_text(row["membership_source"])
                or source in {"CURRENT_WATCHLIST_BACKFILL", "CURRENT_MEMBERSHIP_BACKFILL"}
                or not _nonempty_text(row["source_artifact_id"])
                or available_at > decision_time
            ):
                return False
            actual.add((as_of, symbol))
        except (KeyError, TypeError, ValueError):
            return False
    return actual == expected and len(rows) == len(expected)


def _security_master_complete(
    rows: tuple[Mapping[str, Any], ...], scope: PITV4EvidenceScope
) -> bool:
    for decision_time, symbol in scope.decision_grid:
        covered = False
        for row in rows:
            try:
                effective_from = _datetime(row["effective_from"])
                effective_to = _optional_datetime(row.get("effective_to"))
                if (
                    str(row["symbol"]) == symbol
                    and row["lookup_complete"] is True
                    and _nonempty_text(row["source_reference"])
                    and _datetime(row["available_at"]) <= decision_time
                    and effective_from <= decision_time
                    and (effective_to is None or decision_time < effective_to)
                ):
                    covered = True
                    break
            except (KeyError, TypeError, ValueError):
                return False
        if not covered:
            return False
    return bool(rows)


def _st_history_complete(
    rows: tuple[Mapping[str, Any], ...], scope: PITV4EvidenceScope
) -> bool:
    earliest = min(scope.decision_times)
    complete_symbols: set[str] = set()
    for row in rows:
        try:
            if (
                row["lookup_complete"] is not True
                or _datetime(row["available_at"]) > earliest
                or not _nonempty_text(row["source_reference"])
            ):
                return False
            complete_symbols.add(str(row["symbol"]))
        except (KeyError, TypeError, ValueError):
            return False
    return complete_symbols == set(scope.symbols)


def _suspension_complete(
    rows: tuple[Mapping[str, Any], ...], scope: PITV4EvidenceScope
) -> bool:
    actual: set[tuple[datetime, str]] = set()
    for row in rows:
        try:
            decision_time = _datetime(row["decision_time"])
            if (
                row["lookup_complete"] is not True
                or _datetime(row["available_at"]) > decision_time
                or not _nonempty_text(row["trading_status"])
                or not _nonempty_text(row["suspension_status"])
                or not _nonempty_text(row["source_reference"])
            ):
                return False
            actual.add((decision_time, str(row["symbol"])))
        except (KeyError, TypeError, ValueError):
            return False
    return actual == scope.decision_grid and len(rows) == len(scope.decision_grid)


def _orderability_complete(
    rows: tuple[Mapping[str, Any], ...], scope: PITV4EvidenceScope
) -> bool:
    actual: set[tuple[datetime, str]] = set()
    for row in rows:
        try:
            decision_time = _datetime(row["decision_time"])
            decision = derive_research_orderability(
                decision_time=decision_time,
                quote_observed_at=_optional_datetime(row.get("quote_observed_at")),
                available_at=_datetime(row["available_at"]),
                snapshot_finalized=row["snapshot_finalized"] is True,
                trading_status=str(row["trading_status"]),
                suspension_status=str(row["suspension_status"]),
                reference_price=_optional_float(row.get("reference_price")),
                best_ask_price=_optional_float(row.get("best_ask_price")),
                best_ask_volume=_optional_float(row.get("best_ask_volume")),
                best_bid_price=_optional_float(row.get("best_bid_price")),
                best_bid_volume=_optional_float(row.get("best_bid_volume")),
                limit_up_price=_optional_float(row.get("limit_up_price")),
                limit_down_price=_optional_float(row.get("limit_down_price")),
            )
            claimed = ResearchOrderabilityStatus(str(row["orderability_status"]))
            if (
                decision.status is ResearchOrderabilityStatus.UNKNOWN
                or decision.status is not claimed
                or decision.reason != row["orderability_reason"]
                or not _nonempty_text(row["source_reference"])
            ):
                return False
            actual.add((decision_time, str(row["symbol"])))
        except (KeyError, TypeError, ValueError):
            return False
    return actual == scope.decision_grid and len(rows) == len(scope.decision_grid)


def _liquidity_unit_verified(rows: tuple[Mapping[str, Any], ...]) -> bool:
    if len(rows) != 1:
        return False
    try:
        contract = AmountUnitContract(**dict(rows[0]))
    except (TypeError, ValueError):
        return False
    return contract.absolute_threshold_qualified


def _bar_finality_verified(
    rows: tuple[Mapping[str, Any], ...], scope: PITV4EvidenceScope
) -> bool:
    seen: set[str] = set()
    decision_bars: set[tuple[datetime, str]] = set()
    for row in rows:
        payload = dict(row)
        try:
            payload["observed_at"] = _datetime(payload["observed_at"])
            payload["session_date"] = date.fromisoformat(str(payload["session_date"]))
            payload["available_at"] = _datetime(payload["available_at"])
            payload["finalized_at"] = _datetime(payload["finalized_at"])
            bar = FinalizedBarEvidence(**payload)
        except (KeyError, TypeError, ValueError):
            return False
        if bar.revision_status != "FINAL" or not bar.revision_id or not bar.source_reference:
            return False
        seen.add(bar.symbol)
        if bar.interval == "1m":
            decision_bars.add((bar.observed_at, bar.symbol))
    return seen == set(scope.symbols) and scope.decision_grid <= decision_bars


def _availability_verified(
    rows: tuple[Mapping[str, Any], ...], scope: PITV4EvidenceScope
) -> bool:
    actual: set[tuple[datetime, str]] = set()
    for row in rows:
        try:
            decision_time = _datetime(row["decision_time"])
            available_at = _datetime(row["available_at"])
            if available_at > decision_time or not _nonempty_text(row["source_reference"]):
                return False
            actual.add((decision_time, str(row["symbol"])))
        except (KeyError, TypeError, ValueError):
            return False
    return actual == scope.decision_grid and len(rows) == len(scope.decision_grid)


def _evaluation_path_complete(
    rows: tuple[Mapping[str, Any], ...],
    bars: tuple[Mapping[str, Any], ...],
    scope: PITV4EvidenceScope,
) -> bool:
    expected = frozenset((item.date(), symbol) for item, symbol in scope.decision_grid)
    actual: set[tuple[date, str]] = set()
    evaluation_bars: set[tuple[date, str, time]] = set()
    for bar in bars:
        try:
            observed_at = _datetime(bar["observed_at"])
            if str(bar["interval"]) == "1m":
                evaluation_bars.add(
                    (
                        date.fromisoformat(str(bar["session_date"])),
                        str(bar["symbol"]),
                        observed_at.timetz().replace(tzinfo=None),
                    )
                )
        except (KeyError, TypeError, ValueError):
            return False
    for row in rows:
        try:
            decision_date = date.fromisoformat(str(row["decision_date"]))
            next_session = date.fromisoformat(str(row["next_session_date"]))
            evaluation_time = _datetime(row["evaluation_time"])
            evaluation_price = float(row["evaluation_price"])
            if (
                next_session <= decision_date
                or evaluation_time.date() != next_session
                or evaluation_time.timetz().replace(tzinfo=None) != time(10, 30)
                or row["minute_path_complete_to_1030"] is not True
                or not math.isfinite(evaluation_price)
                or evaluation_price <= 0
                or _datetime(row["available_at"]) < evaluation_time
                or _datetime(row["finalized_at"]) < evaluation_time
                or row.get("missing_reason") is not None
                or row["evaluation_mark_id"]
                != PIT_V4_EVIDENCE_CONVENTIONS["evaluation_mark_id"]
                or row["price_rule_id"]
                != PIT_V4_EVIDENCE_CONVENTIONS["evaluation_price_rule_id"]
                or not _complete_0930_1030_path(
                    evaluation_bars,
                    next_session=next_session,
                    symbol=str(row["symbol"]),
                )
            ):
                return False
            actual.add((decision_date, str(row["symbol"])))
        except (KeyError, TypeError, ValueError):
            return False
    return actual == expected and len(rows) == len(expected)


def _decision_for_date(scope: PITV4EvidenceScope, value: date) -> datetime:
    matches = [item for item in scope.decision_times if item.date() == value]
    if len(matches) != 1:
        raise ValueError("decision date is not unique in PIT scope")
    return matches[0]


def _datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() != _SHANGHAI_OFFSET:
        raise ValueError("Asia/Shanghai-aware datetime required")
    return parsed


def _optional_datetime(value: object) -> datetime | None:
    return None if value is None else _datetime(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("numeric evidence required")
    return float(value)


def _sequence(value: object) -> Sequence[object]:
    if not isinstance(value, list):
        raise TypeError("array required")
    return value


def _valid_hash(value: str) -> bool:
    return (
        len(value) == _SHA256_LENGTH
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _complete_0930_1030_path(
    bars: set[tuple[date, str, time]], *, next_session: date, symbol: str
) -> bool:
    required = {
        (next_session, symbol, time(total_minutes // 60, total_minutes % 60))
        for total_minutes in range(9 * 60 + 30, 10 * 60 + 31)
    }
    return required <= bars


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value)
