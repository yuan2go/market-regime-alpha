"""Typed, content-addressed supplemental evidence for operational research."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_text,
    require_unique_text,
)
from market_regime_alpha.research.platform_v2.inputs import (
    ETFObservation,
    MarketObservation,
    ResearchDailyBar,
    SymbolResearchObservation,
)


SUPPLEMENTAL_RESEARCH_EVIDENCE_SCHEMA = (
    "supplemental-research-evidence-bundle-v1"
)


def _available_by_decision(
    label: str,
    available_at: AvailabilityTime,
    decision_time: DecisionTime,
) -> None:
    if available_at.value > decision_time.value:
        raise ValueError(f"{label} must be available by Decision Time")


def _optional_finite(label: str, value: float | None) -> None:
    if value is not None and not isfinite(value):
        raise ValueError(f"{label} must be finite when present")


@dataclass(frozen=True, slots=True)
class ThemeObservationEvidence:
    """Theme-only observables; capital fields are owned separately."""

    theme_id: str
    theme_name: str
    benchmark_id: str
    proxy_etf_ids: tuple[str, ...]
    available_at: AvailabilityTime
    source_artifact_id: ArtifactId
    relative_strength_1d: float | None
    relative_strength_3d: float | None
    relative_strength_5d: float | None
    relative_strength_10d: float | None
    amount_expansion: float | None
    breadth: float | None
    new_high_breadth: float | None
    leader_strength: float | None
    participation_change: float | None
    rank_persistence: float | None
    confidence: float
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (
            ("theme_id", self.theme_id),
            ("theme_name", self.theme_name),
            ("benchmark_id", self.benchmark_id),
        ):
            require_text(label, value)
        require_unique_text("proxy_etf_id", self.proxy_etf_ids)
        require_unique_text("reason_code", self.reason_codes)
        for name in (
            "relative_strength_1d",
            "relative_strength_3d",
            "relative_strength_5d",
            "relative_strength_10d",
            "amount_expansion",
            "breadth",
            "new_high_breadth",
            "leader_strength",
            "participation_change",
            "rank_persistence",
        ):
            _optional_finite(name, getattr(self, name))
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("theme confidence must be within [0, 1]")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "theme_id": self.theme_id,
            "theme_name": self.theme_name,
            "benchmark_id": self.benchmark_id,
            "proxy_etf_ids": list(self.proxy_etf_ids),
            "available_at": self.available_at.isoformat(),
            "source_artifact_id": str(self.source_artifact_id),
            "relative_strength_1d": self.relative_strength_1d,
            "relative_strength_3d": self.relative_strength_3d,
            "relative_strength_5d": self.relative_strength_5d,
            "relative_strength_10d": self.relative_strength_10d,
            "amount_expansion": self.amount_expansion,
            "breadth": self.breadth,
            "new_high_breadth": self.new_high_breadth,
            "leader_strength": self.leader_strength,
            "participation_change": self.participation_change,
            "rank_persistence": self.rank_persistence,
            "confidence": self.confidence,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ThemeObservationEvidence:
        expected = {
            "theme_id",
            "theme_name",
            "benchmark_id",
            "proxy_etf_ids",
            "available_at",
            "source_artifact_id",
            "relative_strength_1d",
            "relative_strength_3d",
            "relative_strength_5d",
            "relative_strength_10d",
            "amount_expansion",
            "breadth",
            "new_high_breadth",
            "leader_strength",
            "participation_change",
            "rank_persistence",
            "confidence",
            "reason_codes",
        }
        _expect_fields(payload, expected, "ThemeObservationEvidence")
        return cls(
            theme_id=str(payload["theme_id"]),
            theme_name=str(payload["theme_name"]),
            benchmark_id=str(payload["benchmark_id"]),
            proxy_etf_ids=_strings(payload["proxy_etf_ids"]),
            available_at=_availability(payload["available_at"]),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            relative_strength_1d=_optional_float(
                payload["relative_strength_1d"]
            ),
            relative_strength_3d=_optional_float(
                payload["relative_strength_3d"]
            ),
            relative_strength_5d=_optional_float(
                payload["relative_strength_5d"]
            ),
            relative_strength_10d=_optional_float(
                payload["relative_strength_10d"]
            ),
            amount_expansion=_optional_float(payload["amount_expansion"]),
            breadth=_optional_float(payload["breadth"]),
            new_high_breadth=_optional_float(payload["new_high_breadth"]),
            leader_strength=_optional_float(payload["leader_strength"]),
            participation_change=_optional_float(
                payload["participation_change"]
            ),
            rank_persistence=_optional_float(payload["rank_persistence"]),
            confidence=float(payload["confidence"]),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class CapitalObservationEvidence:
    """Observable capital proxies; never an assertion about hidden actors."""

    theme_id: str
    available_at: AvailabilityTime
    source_artifact_id: ArtifactId
    etf_amount_expansion: float | None
    amount_persistence: float | None
    capital_concentration: float | None
    diffusion_score: float | None
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_text("theme_id", self.theme_id)
        require_unique_text("reason_code", self.reason_codes)
        for name in (
            "etf_amount_expansion",
            "amount_persistence",
            "capital_concentration",
            "diffusion_score",
        ):
            _optional_finite(name, getattr(self, name))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "theme_id": self.theme_id,
            "available_at": self.available_at.isoformat(),
            "source_artifact_id": str(self.source_artifact_id),
            "etf_amount_expansion": self.etf_amount_expansion,
            "amount_persistence": self.amount_persistence,
            "capital_concentration": self.capital_concentration,
            "diffusion_score": self.diffusion_score,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CapitalObservationEvidence:
        expected = {
            "theme_id",
            "available_at",
            "source_artifact_id",
            "etf_amount_expansion",
            "amount_persistence",
            "capital_concentration",
            "diffusion_score",
            "reason_codes",
        }
        _expect_fields(payload, expected, "CapitalObservationEvidence")
        return cls(
            theme_id=str(payload["theme_id"]),
            available_at=_availability(payload["available_at"]),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            etf_amount_expansion=_optional_float(
                payload["etf_amount_expansion"]
            ),
            amount_persistence=_optional_float(
                payload["amount_persistence"]
            ),
            capital_concentration=_optional_float(
                payload["capital_concentration"]
            ),
            diffusion_score=_optional_float(payload["diffusion_score"]),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class PITThemeMembershipEvidence:
    symbol: str
    primary_theme_id: str
    supporting_theme_ids: tuple[str, ...]
    available_at: AvailabilityTime
    source_artifact_id: ArtifactId

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_text("primary_theme_id", self.primary_theme_id)
        require_unique_text("supporting_theme_id", self.supporting_theme_ids)
        if self.primary_theme_id in self.supporting_theme_ids:
            raise ValueError("primary theme cannot also be supporting")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "primary_theme_id": self.primary_theme_id,
            "supporting_theme_ids": list(self.supporting_theme_ids),
            "available_at": self.available_at.isoformat(),
            "source_artifact_id": str(self.source_artifact_id),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> PITThemeMembershipEvidence:
        _expect_fields(
            payload,
            {
                "symbol",
                "primary_theme_id",
                "supporting_theme_ids",
                "available_at",
                "source_artifact_id",
            },
            "PITThemeMembershipEvidence",
        )
        return cls(
            symbol=str(payload["symbol"]),
            primary_theme_id=str(payload["primary_theme_id"]),
            supporting_theme_ids=_strings(payload["supporting_theme_ids"]),
            available_at=_availability(payload["available_at"]),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
        )


@dataclass(frozen=True, slots=True)
class ETFThemeMappingEvidence:
    etf_id: str
    theme_id: str
    available_at: AvailabilityTime
    source_artifact_id: ArtifactId

    def __post_init__(self) -> None:
        require_text("etf_id", self.etf_id)
        require_text("theme_id", self.theme_id)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "etf_id": self.etf_id,
            "theme_id": self.theme_id,
            "available_at": self.available_at.isoformat(),
            "source_artifact_id": str(self.source_artifact_id),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ETFThemeMappingEvidence:
        _expect_fields(
            payload,
            {"etf_id", "theme_id", "available_at", "source_artifact_id"},
            "ETFThemeMappingEvidence",
        )
        return cls(
            etf_id=str(payload["etf_id"]),
            theme_id=str(payload["theme_id"]),
            available_at=_availability(payload["available_at"]),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
        )


@dataclass(frozen=True, slots=True)
class MissingEvidence:
    evidence_kind: str
    key: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("evidence_kind", self.evidence_kind)
        require_text("key", self.key)
        require_unique_text("reason_code", self.reason_codes)
        if not self.reason_codes:
            raise ValueError("missing evidence requires reason codes")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "evidence_kind": self.evidence_kind,
            "key": self.key,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> MissingEvidence:
        _expect_fields(
            payload,
            {"evidence_kind", "key", "reason_codes"},
            "MissingEvidence",
        )
        return cls(
            evidence_kind=str(payload["evidence_kind"]),
            key=str(payload["key"]),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class SupplementalResearchEvidenceBundle:
    """Independent evidence package validated before application composition."""

    source_manifest: SourceManifest
    decision_time: DecisionTime
    market_observation: MarketObservation
    theme_observations: tuple[ThemeObservationEvidence, ...]
    capital_observations: tuple[CapitalObservationEvidence, ...]
    symbol_observations: tuple[SymbolResearchObservation, ...]
    theme_memberships: tuple[PITThemeMembershipEvidence, ...]
    etf_theme_mappings: tuple[ETFThemeMappingEvidence, ...]
    etf_observations: tuple[ETFObservation, ...]
    stock_daily_bars: tuple[ResearchDailyBar, ...]
    missing_evidence: tuple[MissingEvidence, ...]
    reason_codes: tuple[str, ...]
    created_at: datetime
    data_eligibility: DataEligibility
    content_hash: str = field(init=False)
    bundle_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        if self.source_manifest.decision_time != self.decision_time:
            raise ValueError("supplemental SourceManifest DecisionTime mismatch")
        if (
            self.data_eligibility is not DataEligibility.EXPLORATORY
            or self.source_manifest.data_eligibility
            is not DataEligibility.EXPLORATORY
        ):
            raise ValueError("supplemental evidence must remain EXPLORATORY")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("supplemental created_at must be timezone-aware")
        if self.created_at < self.decision_time.value:
            raise ValueError("supplemental created_at cannot predate DecisionTime")
        require_unique_text("reason_code", self.reason_codes)
        source_ids = {
            item.artifact_id for item in self.source_manifest.source_artifacts
        }
        timed_sources: list[tuple[str, AvailabilityTime, ArtifactId]] = [
            (
                "market observation",
                self.market_observation.available_at,
                self.market_observation.source_artifact_id,
            )
        ]
        timed_sources.extend(
            ("theme observation", item.available_at, item.source_artifact_id)
            for item in self.theme_observations
        )
        timed_sources.extend(
            ("capital observation", item.available_at, item.source_artifact_id)
            for item in self.capital_observations
        )
        timed_sources.extend(
            ("symbol observation", item.available_at, item.source_artifact_id)
            for item in self.symbol_observations
        )
        timed_sources.extend(
            ("theme membership", item.available_at, item.source_artifact_id)
            for item in self.theme_memberships
        )
        timed_sources.extend(
            ("ETF mapping", item.available_at, item.source_artifact_id)
            for item in self.etf_theme_mappings
        )
        timed_sources.extend(
            ("ETF observation", item.available_at, item.source_artifact_id)
            for item in self.etf_observations
        )
        timed_sources.extend(
            ("stock daily bar", item.available_at, item.source_artifact_id)
            for item in self.stock_daily_bars
        )
        for label, available_at, source_id in timed_sources:
            _available_by_decision(label, available_at, self.decision_time)
            if source_id not in source_ids:
                raise ValueError(
                    f"{label} source is absent from supplemental SourceManifest"
                )
        _require_unique(
            "theme observation",
            tuple(item.theme_id for item in self.theme_observations),
        )
        _require_unique(
            "capital observation",
            tuple(item.theme_id for item in self.capital_observations),
        )
        _require_unique(
            "symbol observation",
            tuple(item.symbol for item in self.symbol_observations),
        )
        _require_unique(
            "theme membership",
            tuple(item.symbol for item in self.theme_memberships),
        )
        _require_unique(
            "ETF mapping",
            tuple(item.etf_id for item in self.etf_theme_mappings),
        )
        _require_unique(
            "ETF observation",
            tuple(item.etf_id for item in self.etf_observations),
        )
        _require_unique(
            "missing evidence",
            tuple(
                f"{item.evidence_kind}:{item.key}"
                for item in self.missing_evidence
            ),
        )
        content_hash = canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "bundle_id",
            ArtifactId(
                "supplemental-research-evidence-"
                f"{content_hash.split(':', 1)[1][:24]}"
            ),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SUPPLEMENTAL_RESEARCH_EVIDENCE_SCHEMA,
            "source_manifest": self.source_manifest.to_canonical_dict(),
            "decision_time": self.decision_time.isoformat(),
            "market_observation": self.market_observation.to_canonical_dict(),
            "theme_observations": [
                item.to_canonical_dict() for item in self.theme_observations
            ],
            "capital_observations": [
                item.to_canonical_dict() for item in self.capital_observations
            ],
            "symbol_observations": [
                item.to_canonical_dict() for item in self.symbol_observations
            ],
            "theme_memberships": [
                item.to_canonical_dict() for item in self.theme_memberships
            ],
            "etf_theme_mappings": [
                item.to_canonical_dict() for item in self.etf_theme_mappings
            ],
            "etf_observations": [
                item.to_canonical_dict() for item in self.etf_observations
            ],
            "stock_daily_bars": [
                item.to_canonical_dict() for item in self.stock_daily_bars
            ],
            "missing_evidence": [
                item.to_canonical_dict() for item in self.missing_evidence
            ],
            "reason_codes": list(self.reason_codes),
            "created_at": self.created_at.isoformat(),
            "data_eligibility": self.data_eligibility.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "bundle_id": str(self.bundle_id),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> SupplementalResearchEvidenceBundle:
        expected = {
            "schema_version",
            "source_manifest",
            "decision_time",
            "market_observation",
            "theme_observations",
            "capital_observations",
            "symbol_observations",
            "theme_memberships",
            "etf_theme_mappings",
            "etf_observations",
            "stock_daily_bars",
            "missing_evidence",
            "reason_codes",
            "created_at",
            "data_eligibility",
            "content_hash",
            "bundle_id",
        }
        _expect_fields(payload, expected, "SupplementalResearchEvidenceBundle")
        if payload["schema_version"] != SUPPLEMENTAL_RESEARCH_EVIDENCE_SCHEMA:
            raise ValueError("unsupported supplemental evidence schema")
        result = cls(
            source_manifest=SourceManifest.from_canonical_dict(
                _mapping(payload["source_manifest"])
            ),
            decision_time=DecisionTime(
                datetime.fromisoformat(str(payload["decision_time"]))
            ),
            market_observation=MarketObservation.from_canonical_dict(
                _dict(payload["market_observation"])
            ),
            theme_observations=tuple(
                ThemeObservationEvidence.from_canonical_dict(_mapping(item))
                for item in _array(payload["theme_observations"])
            ),
            capital_observations=tuple(
                CapitalObservationEvidence.from_canonical_dict(_mapping(item))
                for item in _array(payload["capital_observations"])
            ),
            symbol_observations=tuple(
                SymbolResearchObservation.from_canonical_dict(_dict(item))
                for item in _array(payload["symbol_observations"])
            ),
            theme_memberships=tuple(
                PITThemeMembershipEvidence.from_canonical_dict(_mapping(item))
                for item in _array(payload["theme_memberships"])
            ),
            etf_theme_mappings=tuple(
                ETFThemeMappingEvidence.from_canonical_dict(_mapping(item))
                for item in _array(payload["etf_theme_mappings"])
            ),
            etf_observations=tuple(
                ETFObservation.from_canonical_dict(_dict(item))
                for item in _array(payload["etf_observations"])
            ),
            stock_daily_bars=tuple(
                ResearchDailyBar.from_canonical_dict(_dict(item))
                for item in _array(payload["stock_daily_bars"])
            ),
            missing_evidence=tuple(
                MissingEvidence.from_canonical_dict(_mapping(item))
                for item in _array(payload["missing_evidence"])
            ),
            reason_codes=_strings(payload["reason_codes"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )
        if (
            result.content_hash != payload["content_hash"]
            or str(result.bundle_id) != payload["bundle_id"]
        ):
            raise ValueError("supplemental evidence identity mismatch")
        return result


def _require_unique(label: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} values must be unique")


def _expect_fields(
    payload: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("supplemental evidence value must be an object")
    return value


def _dict(value: object) -> dict[str, Any]:
    return dict(_mapping(value))


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("supplemental evidence value must be an array")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError("supplemental evidence value must be a string array")
    return tuple(value)


def _availability(value: object) -> AvailabilityTime:
    return AvailabilityTime(datetime.fromisoformat(str(value)))


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("supplemental evidence value must be numeric")
    return float(value)
