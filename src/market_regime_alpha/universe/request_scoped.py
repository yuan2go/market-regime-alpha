"""Request-scoped Universe view over the existing Operational Universe authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, UniverseId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.market_data import FormalPitStatus
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second
from market_regime_alpha.universe.operational import OperationalUniverseArtifact


REQUEST_SCOPED_UNIVERSE_SCHEMA = "request-scoped-universe-v1"


class UniverseAuthority(str, Enum):
    REQUEST_SCOPED_UNIVERSE = "REQUEST_SCOPED_UNIVERSE"


@dataclass(frozen=True, slots=True)
class RequestScopedUniverseRecord:
    symbol: str
    included: bool
    reason_codes: tuple[str, ...]
    source_record_found: bool
    source_record_included: bool | None
    membership_source: str | None

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if not isinstance(self.included, bool):
            raise TypeError("included must be a bool")
        if not isinstance(self.source_record_found, bool):
            raise TypeError("source_record_found must be a bool")
        if self.source_record_included is not None and not isinstance(
            self.source_record_included, bool
        ):
            raise TypeError("source_record_included must be a bool or None")
        if self.membership_source is not None:
            require_text("membership_source", self.membership_source)
        if self.source_record_found != (self.source_record_included is not None):
            raise ValueError("source record presence fields are inconsistent")
        if self.source_record_found != (self.membership_source is not None):
            raise ValueError("source membership provenance is inconsistent")
        if self.included and self.source_record_included is not True:
            raise ValueError("included request record must be included by its source")
        require_unique_text("request scope reason", self.reason_codes)
        if not self.reason_codes or self.reason_codes != tuple(sorted(self.reason_codes)):
            raise ValueError("request scope reasons must be non-empty and sorted")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "included": self.included,
            "reason_codes": list(self.reason_codes),
            "source_record_found": self.source_record_found,
            "source_record_included": self.source_record_included,
            "membership_source": self.membership_source,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> RequestScopedUniverseRecord:
        _exact(
            payload,
            {
                "symbol",
                "included",
                "reason_codes",
                "source_record_found",
                "source_record_included",
                "membership_source",
            },
            "RequestScopedUniverse record",
        )
        return cls(
            symbol=str(payload["symbol"]),
            included=_boolean(payload["included"], "included"),
            reason_codes=_strings(payload["reason_codes"], "reason_codes"),
            source_record_found=_boolean(
                payload["source_record_found"], "source_record_found"
            ),
            source_record_included=_optional_boolean(
                payload["source_record_included"], "source_record_included"
            ),
            membership_source=(
                None
                if payload["membership_source"] is None
                else str(payload["membership_source"])
            ),
        )


@dataclass(frozen=True, slots=True)
class RequestScopedUniverse:
    schema_version: str
    universe_id: UniverseId
    content_hash: str
    authority: UniverseAuthority
    decision_date: date
    effective_at: datetime
    available_at: datetime
    requested_symbols: tuple[str, ...]
    records: tuple[RequestScopedUniverseRecord, ...]
    source_universe_id: UniverseId
    source_universe_hash: str
    configuration_id: ArtifactId
    configuration_hash: str
    formal_pit_status: FormalPitStatus
    data_eligibility: DataEligibility
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != REQUEST_SCOPED_UNIVERSE_SCHEMA:
            raise ValueError("unsupported RequestScopedUniverse schema")
        if self.authority is not UniverseAuthority.REQUEST_SCOPED_UNIVERSE:
            raise ValueError("RequestScopedUniverse authority cannot be inflated")
        require_sha256("content_hash", self.content_hash)
        require_sha256("source_universe_hash", self.source_universe_hash)
        require_sha256("configuration_hash", self.configuration_hash)
        require_utc_second("effective_at", self.effective_at)
        require_utc_second("available_at", self.available_at)
        if self.available_at < self.effective_at:
            raise ValueError("RequestScopedUniverse cannot precede source effectiveness")
        require_unique_text("requested symbol", self.requested_symbols)
        if not self.requested_symbols or self.requested_symbols != tuple(
            sorted(self.requested_symbols)
        ):
            raise ValueError("requested_symbols must be non-empty and sorted")
        record_symbols = tuple(item.symbol for item in self.records)
        if record_symbols != self.requested_symbols:
            raise ValueError("RequestScopedUniverse records must partition requested_symbols")
        included = set(self.included_symbols)
        excluded = set(self.excluded_symbols)
        if included & excluded or included | excluded != set(self.requested_symbols):
            raise ValueError("RequestScopedUniverse included/excluded partition is invalid")
        require_unique_text("RequestScopedUniverse limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("RequestScopedUniverse limitations must be sorted")
        for required in (
            "COMPLETE_A_SHARE_PIT_UNIVERSE_NOT_ESTABLISHED",
            "REQUEST_SCOPED_UNIVERSE",
        ):
            if required not in self.limitations:
                raise ValueError("RequestScopedUniverse authority ceiling is incomplete")
        if self.formal_pit_status is FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED:
            if "FORMAL_PIT_NOT_ESTABLISHED" not in self.limitations:
                raise ValueError("RequestScopedUniverse lost source PIT limitation")
        self.verify_identity()

    @property
    def included_symbols(self) -> tuple[str, ...]:
        return tuple(item.symbol for item in self.records if item.included)

    @property
    def excluded_symbols(self) -> tuple[str, ...]:
        return tuple(item.symbol for item in self.records if not item.included)

    def record_for(self, symbol: str) -> RequestScopedUniverseRecord:
        for record in self.records:
            if record.symbol == symbol:
                return record
        raise KeyError(symbol)

    def semantic_payload(self) -> dict[str, Any]:
        return _payload(
            authority=self.authority,
            decision_date=self.decision_date,
            effective_at=self.effective_at,
            available_at=self.available_at,
            requested_symbols=self.requested_symbols,
            records=self.records,
            source_universe_id=self.source_universe_id,
            source_universe_hash=self.source_universe_hash,
            configuration_id=self.configuration_id,
            configuration_hash=self.configuration_hash,
            formal_pit_status=self.formal_pit_status,
            data_eligibility=self.data_eligibility,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("RequestScopedUniverse content hash mismatch")
        expected = f"request-scoped-universe-{digest.split(':', 1)[1][:24]}"
        if str(self.universe_id) != expected:
            raise ValueError("RequestScopedUniverse identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "universe_id": str(self.universe_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> RequestScopedUniverse:
        expected = {
            "schema_version",
            "universe_id",
            "content_hash",
            "authority",
            "decision_date",
            "effective_at",
            "available_at",
            "requested_symbols",
            "records",
            "source_universe_id",
            "source_universe_hash",
            "configuration_id",
            "configuration_hash",
            "formal_pit_status",
            "data_eligibility",
            "limitations",
        }
        _exact(payload, expected, "RequestScopedUniverse")
        records = _objects(payload["records"], "records")
        result = cls(
            schema_version=str(payload["schema_version"]),
            universe_id=UniverseId(str(payload["universe_id"])),
            content_hash=str(payload["content_hash"]),
            authority=UniverseAuthority(str(payload["authority"])),
            decision_date=date.fromisoformat(str(payload["decision_date"])),
            effective_at=parse_utc_second("effective_at", payload["effective_at"]),
            available_at=parse_utc_second("available_at", payload["available_at"]),
            requested_symbols=_strings(
                payload["requested_symbols"], "requested_symbols"
            ),
            records=tuple(
                RequestScopedUniverseRecord.from_canonical_dict(item)
                for item in records
            ),
            source_universe_id=UniverseId(str(payload["source_universe_id"])),
            source_universe_hash=str(payload["source_universe_hash"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            formal_pit_status=FormalPitStatus(str(payload["formal_pit_status"])),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            limitations=_strings(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result


def build_request_scoped_universe(
    *,
    source: OperationalUniverseArtifact,
    requested_symbols: tuple[str, ...],
    configuration_id: ArtifactId,
    configuration_hash: str,
) -> RequestScopedUniverse:
    source.verify_identity()
    requested = tuple(sorted(set(requested_symbols)))
    if not requested:
        raise ValueError("requested_symbols must not be empty")
    by_symbol = {item.symbol: item for item in source.records}
    records: list[RequestScopedUniverseRecord] = []
    for symbol in requested:
        require_text("requested symbol", symbol)
        source_record = by_symbol.get(symbol)
        if source_record is None:
            records.append(
                RequestScopedUniverseRecord(
                    symbol=symbol,
                    included=False,
                    reason_codes=("SOURCE_UNIVERSE_RECORD_MISSING",),
                    source_record_found=False,
                    source_record_included=None,
                    membership_source=None,
                )
            )
            continue
        records.append(
            RequestScopedUniverseRecord(
                symbol=symbol,
                included=source_record.included,
                reason_codes=(
                    tuple(sorted(source_record.inclusion_reasons))
                    if source_record.included
                    else tuple(sorted(source_record.exclusion_reasons))
                ),
                source_record_found=True,
                source_record_included=source_record.included,
                membership_source=source_record.membership_source,
            )
        )
    limitations = tuple(
        sorted(
            set(source.limitations)
            | {
                "COMPLETE_A_SHARE_PIT_UNIVERSE_NOT_ESTABLISHED",
                "REQUEST_SCOPED_UNIVERSE",
            }
        )
    )
    values: dict[str, Any] = {
        "authority": UniverseAuthority.REQUEST_SCOPED_UNIVERSE,
        "decision_date": source.decision_date,
        "effective_at": source.effective_at,
        "available_at": source.available_at,
        "requested_symbols": requested,
        "records": tuple(records),
        "source_universe_id": source.universe_id,
        "source_universe_hash": source.content_hash,
        "configuration_id": configuration_id,
        "configuration_hash": configuration_hash,
        "formal_pit_status": source.formal_pit_status,
        "data_eligibility": source.data_eligibility,
        "limitations": limitations,
    }
    digest = canonical_hash(_payload(**values))
    return RequestScopedUniverse(
        schema_version=REQUEST_SCOPED_UNIVERSE_SCHEMA,
        universe_id=UniverseId(
            f"request-scoped-universe-{digest.split(':', 1)[1][:24]}"
        ),
        content_hash=digest,
        **values,
    )


def _payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": REQUEST_SCOPED_UNIVERSE_SCHEMA,
        "authority": values["authority"].value,
        "decision_date": values["decision_date"].isoformat(),
        "effective_at": canonical_datetime(values["effective_at"]),
        "available_at": canonical_datetime(values["available_at"]),
        "requested_symbols": list(values["requested_symbols"]),
        "records": [item.to_canonical_dict() for item in values["records"]],
        "source_universe_id": str(values["source_universe_id"]),
        "source_universe_hash": values["source_universe_hash"],
        "configuration_id": str(values["configuration_id"]),
        "configuration_hash": values["configuration_hash"],
        "formal_pit_status": values["formal_pit_status"].value,
        "data_eligibility": values["data_eligibility"].value,
        "limitations": list(values["limitations"]),
    }


def _exact(
    payload: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _objects(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} must be an object array")
    return tuple(value)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _optional_boolean(value: object, label: str) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean or null")
    return value


__all__ = [
    "REQUEST_SCOPED_UNIVERSE_SCHEMA",
    "RequestScopedUniverse",
    "RequestScopedUniverseRecord",
    "UniverseAuthority",
    "build_request_scoped_universe",
]
