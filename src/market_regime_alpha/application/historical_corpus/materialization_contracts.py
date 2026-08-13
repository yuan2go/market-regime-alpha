"""Content-addressed Phase E session components owned by PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
)
from market_regime_alpha.market_data.contracts import parse_utc_second, require_utc_second


HISTORICAL_SESSION_COMPONENT_SCHEMA = "historical-session-component/v1"


class HistoricalComponentKind(str, Enum):
    FEATURE = "FEATURE"
    MARKET_REGIME = "MARKET_REGIME"
    ETF = "ETF"
    THEME = "THEME"
    CAPITAL = "CAPITAL"
    DYNAMIC_POOL = "DYNAMIC_POOL"
    CANDIDATE = "CANDIDATE"
    SIGNAL = "SIGNAL"
    FORECAST = "FORECAST"
    STRATEGY = "STRATEGY"
    PORTFOLIO = "PORTFOLIO"
    OUTCOME = "OUTCOME"
    RESEARCH_PANEL = "RESEARCH_PANEL"


@dataclass(frozen=True, slots=True)
class HistoricalSessionComponent:
    component_id: ArtifactId
    component_hash: str
    run_id: ArtifactId
    session_id: ArtifactId
    trading_date: date
    component_kind: HistoricalComponentKind
    source_max_event_time: datetime
    materialized_at: datetime
    source_references: tuple[ValidationArtifactReference, ...]
    payload: Mapping[str, Any]
    limitations: tuple[str, ...]
    schema_version: str = HISTORICAL_SESSION_COMPONENT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != HISTORICAL_SESSION_COMPONENT_SCHEMA:
            raise ValueError("unsupported Historical session component schema")
        require_sha256("component_hash", self.component_hash)
        require_utc_second("source_max_event_time", self.source_max_event_time)
        require_utc_second("materialized_at", self.materialized_at)
        if self.materialized_at < self.source_max_event_time:
            raise ValueError("Historical component predates its source events")
        if self.source_references != _references(self.source_references):
            raise ValueError("Historical component sources must be unique and sorted")
        if not self.source_references:
            raise ValueError("Historical component requires exact source lineage")
        if not isinstance(self.payload, Mapping):
            raise TypeError("Historical component payload must be an object")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Historical component limitations must be sorted and unique")
        for required in (
            "EXPLORATORY",
            "FORMAL_OOS_FALSE",
            "PIT_INCOMPLETE",
            "RETROSPECTIVE_EVENT_TIME",
        ):
            if required not in self.limitations:
                raise ValueError("Historical component evidence ceiling is incomplete")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        run_id: ArtifactId,
        session_id: ArtifactId,
        trading_date: date,
        component_kind: HistoricalComponentKind,
        source_max_event_time: datetime,
        materialized_at: datetime,
        source_references: tuple[ValidationArtifactReference, ...],
        payload: Mapping[str, Any],
        limitations: tuple[str, ...] = (),
    ) -> HistoricalSessionComponent:
        ordered_sources = _references(source_references)
        canonical_payload = dict(payload)
        ordered_limitations = tuple(
            sorted(
                {
                    *limitations,
                    "EXPLORATORY",
                    "FORMAL_OOS_FALSE",
                    "PIT_INCOMPLETE",
                    "RETROSPECTIVE_EVENT_TIME",
                }
            )
        )
        values = {
            "run_id": run_id,
            "session_id": session_id,
            "trading_date": trading_date,
            "component_kind": component_kind,
            "source_max_event_time": source_max_event_time,
            "materialized_at": materialized_at,
            "source_references": ordered_sources,
            "payload": canonical_payload,
            "limitations": ordered_limitations,
        }
        digest = canonical_hash(_payload(**values))
        return cls(
            component_id=ArtifactId(
                f"historical-{component_kind.value.lower()}-{digest[7:31]}"
            ),
            component_hash=digest,
            run_id=run_id,
            session_id=session_id,
            trading_date=trading_date,
            component_kind=component_kind,
            source_max_event_time=source_max_event_time,
            materialized_at=materialized_at,
            source_references=ordered_sources,
            payload=canonical_payload,
            limitations=ordered_limitations,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            f"HISTORICAL_{self.component_kind.value}",
            self.component_id,
            self.component_hash,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _payload(
            run_id=self.run_id,
            session_id=self.session_id,
            trading_date=self.trading_date,
            component_kind=self.component_kind,
            source_max_event_time=self.source_max_event_time,
            materialized_at=self.materialized_at,
            source_references=self.source_references,
            payload=self.payload,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.component_hash:
            raise ValueError("Historical component hash mismatch")
        expected = f"historical-{self.component_kind.value.lower()}-{digest[7:31]}"
        if str(self.component_id) != expected:
            raise ValueError("Historical component identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "component_id": str(self.component_id),
            "component_hash": self.component_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> HistoricalSessionComponent:
        raw_payload = payload["payload"]
        if not isinstance(raw_payload, Mapping):
            raise ValueError("Historical component payload must be an object")
        return cls(
            component_id=ArtifactId(str(payload["component_id"])),
            component_hash=str(payload["component_hash"]),
            run_id=ArtifactId(str(payload["run_id"])),
            session_id=ArtifactId(str(payload["session_id"])),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            component_kind=HistoricalComponentKind(str(payload["component_kind"])),
            source_max_event_time=parse_utc_second(
                "source_max_event_time", payload["source_max_event_time"]
            ),
            materialized_at=parse_utc_second(
                "materialized_at", payload["materialized_at"]
            ),
            source_references=tuple(
                ValidationArtifactReference.from_canonical_dict(item)
                for item in _objects(payload["source_references"])
            ),
            payload=dict(raw_payload),
            limitations=_strings(payload["limitations"]),
            schema_version=str(payload["schema_version"]),
        )


def _payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": HISTORICAL_SESSION_COMPONENT_SCHEMA,
        "run_id": str(values["run_id"]),
        "session_id": str(values["session_id"]),
        "trading_date": values["trading_date"].isoformat(),
        "component_kind": values["component_kind"].value,
        "source_max_event_time": canonical_datetime(values["source_max_event_time"]),
        "materialized_at": canonical_datetime(values["materialized_at"]),
        "source_references": [
            item.to_canonical_dict() for item in values["source_references"]
        ],
        "payload": dict(values["payload"]),
        "limitations": list(values["limitations"]),
    }


def _references(
    values: tuple[ValidationArtifactReference, ...],
) -> tuple[ValidationArtifactReference, ...]:
    keyed = {
        (item.artifact_kind, str(item.artifact_id), item.content_hash): item
        for item in values
    }
    return tuple(keyed[key] for key in sorted(keyed))


def _objects(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError("Historical component sources must be object array")
    return tuple(value)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("Historical component limitations must be string array")
    return tuple(value)


__all__ = [
    "HISTORICAL_SESSION_COMPONENT_SCHEMA",
    "HistoricalComponentKind",
    "HistoricalSessionComponent",
]
