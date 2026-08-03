"""Strict lineage-preserving input boundary for the Platform V2 Research Layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from math import isfinite
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from market_regime_alpha.application.operational_research.composite_manifest import (
        CompositeOperationalCompositionPolicy,
        CompositeOperationalInputManifest,
    )

from market_regime_alpha.core.identity import (
    ArtifactId,
    FeatureDefinitionId,
)
from market_regime_alpha.core.time import AvailabilityTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.daily_decision.snapshot import DecisionPriceSnapshot
from market_regime_alpha.daily_decision.serialization import (
    eligibility_snapshot_from_dict,
    eligibility_snapshot_to_dict,
    universe_snapshot_from_dict,
    universe_snapshot_to_dict,
)
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.platform.prediction_run import PredictionRun
from market_regime_alpha.universe.contracts import (
    PITUniverseSnapshot,
    TradingEligibilitySnapshot,
)


class ResearchEvidenceKind(str, Enum):
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    HISTORICAL_IMMUTABLE_ARCHIVE = "HISTORICAL_IMMUTABLE_ARCHIVE"
    OPERATIONAL_EXPLORATORY_ARCHIVE = "OPERATIONAL_EXPLORATORY_ARCHIVE"


def _finite_optional(label: str, value: float | None) -> None:
    if value is not None and not isfinite(value):
        raise ValueError(f"{label} must be finite when present")


def _validate_available(
    available_at: AvailabilityTime, decision_time: datetime
) -> None:
    if available_at.value > decision_time:
        raise ValueError("research input must be available by Decision Time")


@dataclass(frozen=True, slots=True)
class MarketObservation:
    """Observable MR2A-compatible market context available at Decision Time."""

    available_at: AvailabilityTime
    source_artifact_id: ArtifactId
    market_direction_return: float | None
    market_intraday_range_to_cutoff: float | None
    market_amount_change_same_cutoff: float | None
    candidate_breadth_at_cutoff: float | None
    limit_structure_score: float | None
    coverage: float
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (
            ("market_direction_return", self.market_direction_return),
            (
                "market_intraday_range_to_cutoff",
                self.market_intraday_range_to_cutoff,
            ),
            (
                "market_amount_change_same_cutoff",
                self.market_amount_change_same_cutoff,
            ),
            (
                "candidate_breadth_at_cutoff",
                self.candidate_breadth_at_cutoff,
            ),
            ("limit_structure_score", self.limit_structure_score),
        ):
            _finite_optional(label, value)
        if not 0.0 <= self.coverage <= 1.0:
            raise ValueError("market observation coverage must be within [0, 1]")
        require_unique_text("reason_code", self.reason_codes)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "available_at": self.available_at.isoformat(),
            "source_artifact_id": str(self.source_artifact_id),
            "market_direction_return": self.market_direction_return,
            "market_intraday_range_to_cutoff": self.market_intraday_range_to_cutoff,
            "market_amount_change_same_cutoff": self.market_amount_change_same_cutoff,
            "candidate_breadth_at_cutoff": self.candidate_breadth_at_cutoff,
            "limit_structure_score": self.limit_structure_score,
            "coverage": self.coverage,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> MarketObservation:
        expected = {
            "available_at",
            "source_artifact_id",
            "market_direction_return",
            "market_intraday_range_to_cutoff",
            "market_amount_change_same_cutoff",
            "candidate_breadth_at_cutoff",
            "limit_structure_score",
            "coverage",
            "reason_codes",
        }
        _expect_fields(payload, expected, "MarketObservation")
        return cls(
            available_at=AvailabilityTime(
                datetime.fromisoformat(str(payload["available_at"]))
            ),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            market_direction_return=_optional_float(
                payload["market_direction_return"]
            ),
            market_intraday_range_to_cutoff=_optional_float(
                payload["market_intraday_range_to_cutoff"]
            ),
            market_amount_change_same_cutoff=_optional_float(
                payload["market_amount_change_same_cutoff"]
            ),
            candidate_breadth_at_cutoff=_optional_float(
                payload["candidate_breadth_at_cutoff"]
            ),
            limit_structure_score=_optional_float(
                payload["limit_structure_score"]
            ),
            coverage=float(payload["coverage"]),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class ThemeResearchObservation:
    """Decision-time observable proxies for one theme."""

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
    etf_amount_expansion: float | None
    breadth: float | None
    new_high_breadth: float | None
    leader_strength: float | None
    participation_change: float | None
    rank_persistence: float | None
    amount_persistence: float | None
    capital_concentration: float | None
    diffusion_score: float | None
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
        for label in (
            "relative_strength_1d",
            "relative_strength_3d",
            "relative_strength_5d",
            "relative_strength_10d",
            "amount_expansion",
            "etf_amount_expansion",
            "breadth",
            "new_high_breadth",
            "leader_strength",
            "participation_change",
            "rank_persistence",
            "amount_persistence",
            "capital_concentration",
            "diffusion_score",
        ):
            _finite_optional(label, getattr(self, label))
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("theme observation confidence must be within [0, 1]")
        require_unique_text("reason_code", self.reason_codes)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "theme_id": self.theme_id,
            "theme_name": self.theme_name,
            "benchmark_id": self.benchmark_id,
            "proxy_etf_ids": list(self.proxy_etf_ids),
            "available_at": self.available_at.isoformat(),
            "source_artifact_id": str(self.source_artifact_id),
            **{
                name: getattr(self, name)
                for name in (
                    "relative_strength_1d",
                    "relative_strength_3d",
                    "relative_strength_5d",
                    "relative_strength_10d",
                    "amount_expansion",
                    "etf_amount_expansion",
                    "breadth",
                    "new_high_breadth",
                    "leader_strength",
                    "participation_change",
                    "rank_persistence",
                    "amount_persistence",
                    "capital_concentration",
                    "diffusion_score",
                    "confidence",
                )
            },
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> ThemeResearchObservation:
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
            "etf_amount_expansion",
            "breadth",
            "new_high_breadth",
            "leader_strength",
            "participation_change",
            "rank_persistence",
            "amount_persistence",
            "capital_concentration",
            "diffusion_score",
            "confidence",
            "reason_codes",
        }
        _expect_fields(payload, expected, "ThemeResearchObservation")
        numeric = {
            name: _optional_float(payload[name])
            for name in expected
            if name
            in {
                "relative_strength_1d",
                "relative_strength_3d",
                "relative_strength_5d",
                "relative_strength_10d",
                "amount_expansion",
                "etf_amount_expansion",
                "breadth",
                "new_high_breadth",
                "leader_strength",
                "participation_change",
                "rank_persistence",
                "amount_persistence",
                "capital_concentration",
                "diffusion_score",
            }
        }
        return cls(
            theme_id=str(payload["theme_id"]),
            theme_name=str(payload["theme_name"]),
            benchmark_id=str(payload["benchmark_id"]),
            proxy_etf_ids=_strings(payload["proxy_etf_ids"]),
            available_at=AvailabilityTime(
                datetime.fromisoformat(str(payload["available_at"]))
            ),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            confidence=float(payload["confidence"]),
            reason_codes=_strings(payload["reason_codes"]),
            **numeric,
        )


@dataclass(frozen=True, slots=True)
class SymbolResearchObservation:
    """Observable symbol-level capital proxies and non-model gates."""

    symbol: str
    available_at: AvailabilityTime
    source_artifact_id: ArtifactId
    symbol_relative_strength: float | None
    symbol_amount_expansion: float | None
    theme_participation_contribution: float | None
    leader_correlation: float | None
    leader_lag: float | None
    rank_persistence: float | None
    amount_persistence: float | None
    liquidity_eligible: bool
    history_complete: bool
    status_known: bool
    source_feature_ids: tuple[FeatureDefinitionId, ...]
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        for label in (
            "symbol_relative_strength",
            "symbol_amount_expansion",
            "theme_participation_contribution",
            "leader_correlation",
            "leader_lag",
            "rank_persistence",
            "amount_persistence",
        ):
            _finite_optional(label, getattr(self, label))
        if len(self.source_feature_ids) != len(set(self.source_feature_ids)):
            raise ValueError("source_feature_ids must be unique")
        require_unique_text("reason_code", self.reason_codes)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "available_at": self.available_at.isoformat(),
            "source_artifact_id": str(self.source_artifact_id),
            **{
                name: getattr(self, name)
                for name in (
                    "symbol_relative_strength",
                    "symbol_amount_expansion",
                    "theme_participation_contribution",
                    "leader_correlation",
                    "leader_lag",
                    "rank_persistence",
                    "amount_persistence",
                    "liquidity_eligible",
                    "history_complete",
                    "status_known",
                )
            },
            "source_feature_ids": [
                str(item) for item in self.source_feature_ids
            ],
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> SymbolResearchObservation:
        expected = {
            "symbol",
            "available_at",
            "source_artifact_id",
            "symbol_relative_strength",
            "symbol_amount_expansion",
            "theme_participation_contribution",
            "leader_correlation",
            "leader_lag",
            "rank_persistence",
            "amount_persistence",
            "liquidity_eligible",
            "history_complete",
            "status_known",
            "source_feature_ids",
            "reason_codes",
        }
        _expect_fields(payload, expected, "SymbolResearchObservation")
        return cls(
            symbol=str(payload["symbol"]),
            available_at=AvailabilityTime(
                datetime.fromisoformat(str(payload["available_at"]))
            ),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            symbol_relative_strength=_optional_float(
                payload["symbol_relative_strength"]
            ),
            symbol_amount_expansion=_optional_float(
                payload["symbol_amount_expansion"]
            ),
            theme_participation_contribution=_optional_float(
                payload["theme_participation_contribution"]
            ),
            leader_correlation=_optional_float(payload["leader_correlation"]),
            leader_lag=_optional_float(payload["leader_lag"]),
            rank_persistence=_optional_float(payload["rank_persistence"]),
            amount_persistence=_optional_float(payload["amount_persistence"]),
            liquidity_eligible=_boolean(payload["liquidity_eligible"]),
            history_complete=_boolean(payload["history_complete"]),
            status_known=_boolean(payload["status_known"]),
            source_feature_ids=tuple(
                FeatureDefinitionId(value)
                for value in _strings(payload["source_feature_ids"])
            ),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class ThemeMembership:
    symbol: str
    primary_theme_id: str
    supporting_theme_ids: tuple[str, ...] = ()

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
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> ThemeMembership:
        _expect_fields(
            payload,
            {"symbol", "primary_theme_id", "supporting_theme_ids"},
            "ThemeMembership",
        )
        return cls(
            symbol=str(payload["symbol"]),
            primary_theme_id=str(payload["primary_theme_id"]),
            supporting_theme_ids=_strings(payload["supporting_theme_ids"]),
        )


@dataclass(frozen=True, slots=True)
class ETFObservation:
    etf_id: str
    theme_id: str
    available_at: AvailabilityTime
    source_artifact_id: ArtifactId
    relative_strength: float
    amount_expansion: float

    def __post_init__(self) -> None:
        require_text("etf_id", self.etf_id)
        require_text("theme_id", self.theme_id)
        _finite_optional("relative_strength", self.relative_strength)
        _finite_optional("amount_expansion", self.amount_expansion)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "etf_id": self.etf_id,
            "theme_id": self.theme_id,
            "available_at": self.available_at.isoformat(),
            "source_artifact_id": str(self.source_artifact_id),
            "relative_strength": self.relative_strength,
            "amount_expansion": self.amount_expansion,
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> ETFObservation:
        _expect_fields(
            payload,
            {
                "etf_id",
                "theme_id",
                "available_at",
                "source_artifact_id",
                "relative_strength",
                "amount_expansion",
            },
            "ETFObservation",
        )
        return cls(
            etf_id=str(payload["etf_id"]),
            theme_id=str(payload["theme_id"]),
            available_at=AvailabilityTime(
                datetime.fromisoformat(str(payload["available_at"]))
            ),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            relative_strength=float(payload["relative_strength"]),
            amount_expansion=float(payload["amount_expansion"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchDailyBar:
    symbol: str
    session_date: date
    available_at: AvailabilityTime
    source_artifact_id: ArtifactId
    close: float
    amount: float

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if not isfinite(self.close) or self.close <= 0.0:
            raise ValueError("Research Daily Bar close must be positive")
        if not isfinite(self.amount) or self.amount < 0.0:
            raise ValueError("Research Daily Bar amount must be non-negative")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "session_date": self.session_date.isoformat(),
            "available_at": self.available_at.isoformat(),
            "source_artifact_id": str(self.source_artifact_id),
            "close": self.close,
            "amount": self.amount,
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> ResearchDailyBar:
        _expect_fields(
            payload,
            {
                "symbol",
                "session_date",
                "available_at",
                "source_artifact_id",
                "close",
                "amount",
            },
            "ResearchDailyBar",
        )
        return cls(
            symbol=str(payload["symbol"]),
            session_date=date.fromisoformat(str(payload["session_date"])),
            available_at=AvailabilityTime(
                datetime.fromisoformat(str(payload["available_at"]))
            ),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            close=float(payload["close"]),
            amount=float(payload["amount"]),
        )


class ResearchInputView(Protocol):
    """Read-only model seam shared by exact V1 and V2 input schemas."""

    @property
    def evidence_kind(self) -> ResearchEvidenceKind: ...

    @property
    def source_manifest(self) -> SourceManifest: ...

    @property
    def universe_snapshot(self) -> PITUniverseSnapshot: ...

    @property
    def eligibility_snapshot(self) -> TradingEligibilitySnapshot: ...

    @property
    def decision_price_snapshot(self) -> DecisionPriceSnapshot: ...

    @property
    def market_observation(self) -> MarketObservation | None: ...

    @property
    def theme_observations(self) -> tuple[ThemeResearchObservation, ...]: ...

    @property
    def symbol_observations(self) -> tuple[SymbolResearchObservation, ...]: ...

    @property
    def theme_memberships(self) -> tuple[ThemeMembership, ...]: ...

    @property
    def etf_observations(self) -> tuple[ETFObservation, ...]: ...

    @property
    def stock_daily_bars(self) -> tuple[ResearchDailyBar, ...]: ...

    @property
    def prediction_runs(self) -> tuple[PredictionRun, ...]: ...

    @property
    def input_artifact_ids(self) -> tuple[ArtifactId, ...]: ...

    @property
    def input_content_hashes(self) -> tuple[str, ...]: ...

    @property
    def created_at(self) -> datetime: ...

    @property
    def data_eligibility(self) -> DataEligibility: ...

    @property
    def content_hash(self) -> str: ...

    @property
    def input_bundle_id(self) -> ArtifactId: ...

    def to_canonical_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ResearchInputBundle:
    """Self-contained typed Research Layer input with exact evidence lineage."""

    SCHEMA_VERSION = "research-input-bundle-v1"

    evidence_kind: ResearchEvidenceKind
    source_manifest: SourceManifest
    universe_snapshot: PITUniverseSnapshot
    eligibility_snapshot: TradingEligibilitySnapshot
    decision_price_snapshot: DecisionPriceSnapshot
    market_observation: MarketObservation | None
    theme_observations: tuple[ThemeResearchObservation, ...]
    symbol_observations: tuple[SymbolResearchObservation, ...]
    theme_memberships: tuple[ThemeMembership, ...]
    etf_observations: tuple[ETFObservation, ...]
    stock_daily_bars: tuple[ResearchDailyBar, ...]
    prediction_runs: tuple[PredictionRun, ...]
    input_artifact_ids: tuple[ArtifactId, ...]
    input_content_hashes: tuple[str, ...]
    created_at: datetime
    data_eligibility: DataEligibility
    content_hash: str = field(init=False)
    input_bundle_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_kind, ResearchEvidenceKind):
            raise TypeError("evidence_kind must be ResearchEvidenceKind")
        decision = self.source_manifest.decision_time
        if (
            self.universe_snapshot.as_of.value > decision.value
            or self.eligibility_snapshot.as_of.value > decision.value
            or self.decision_price_snapshot.decision_time != decision
            or self.decision_price_snapshot.source_manifest_id
            != self.source_manifest.source_manifest_id
        ):
            raise ValueError("Research Input Bundle scope mismatch")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("Research Input Bundle created_at must be aware")
        if self.created_at < decision.value:
            raise ValueError("Research Input Bundle cannot predate Decision Time")
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("Research Input Bundle must remain EXPLORATORY")
        if len(self.input_artifact_ids) != len(self.input_content_hashes):
            raise ValueError("Research input identities and hashes must align")
        if (
            tuple(sorted(self.input_artifact_ids, key=str))
            != self.input_artifact_ids
            or len(self.input_artifact_ids) != len(set(self.input_artifact_ids))
        ):
            raise ValueError("Research input Artifact identities must be sorted and unique")
        for input_hash in self.input_content_hashes:
            require_sha256("input_content_hash", input_hash)
        required_ids = {
            self.universe_snapshot.evidence_artifact_id,
            self.eligibility_snapshot.evidence_artifact_id,
            self.decision_price_snapshot.decision_snapshot_id,
        }
        if not required_ids.issubset(set(self.input_artifact_ids)):
            raise ValueError("Research input lineage omits required snapshots")
        for theme_observation in self.theme_observations:
            _validate_available(theme_observation.available_at, decision.value)
        for symbol_observation in self.symbol_observations:
            _validate_available(symbol_observation.available_at, decision.value)
        for etf_observation in self.etf_observations:
            _validate_available(etf_observation.available_at, decision.value)
        for daily_bar in self.stock_daily_bars:
            _validate_available(daily_bar.available_at, decision.value)
        if self.market_observation is not None:
            _validate_available(
                self.market_observation.available_at, decision.value
            )
        _require_unique_by(
            "theme observations",
            tuple(item.theme_id for item in self.theme_observations),
        )
        _require_unique_by(
            "symbol observations",
            tuple(item.symbol for item in self.symbol_observations),
        )
        _require_unique_by(
            "theme memberships",
            tuple(item.symbol for item in self.theme_memberships),
        )
        for run in self.prediction_runs:
            if run.decision_time != decision:
                raise ValueError("PredictionRun Decision Time mismatch")
        content_hash = canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "input_bundle_id",
            ArtifactId(
                f"research-input-{content_hash.split(':', 1)[1][:24]}"
            ),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "evidence_kind": self.evidence_kind.value,
            "source_manifest": self.source_manifest.to_canonical_dict(),
            "universe_snapshot_id": str(
                self.universe_snapshot.evidence_artifact_id
            ),
            "eligibility_snapshot_id": str(
                self.eligibility_snapshot.evidence_artifact_id
            ),
            "decision_price_snapshot_id": str(
                self.decision_price_snapshot.decision_snapshot_id
            ),
            "market_observation": (
                self.market_observation.to_canonical_dict()
                if self.market_observation is not None
                else None
            ),
            "theme_observations": [
                item.to_canonical_dict() for item in self.theme_observations
            ],
            "symbol_observations": [
                item.to_canonical_dict() for item in self.symbol_observations
            ],
            "theme_memberships": [
                item.to_canonical_dict() for item in self.theme_memberships
            ],
            "etf_observations": [
                item.to_canonical_dict() for item in self.etf_observations
            ],
            "stock_daily_bars": [
                item.to_canonical_dict() for item in self.stock_daily_bars
            ],
            "prediction_runs": [
                item.to_canonical_dict() for item in self.prediction_runs
            ],
            "input_artifact_ids": [
                str(item) for item in self.input_artifact_ids
            ],
            "input_content_hashes": list(self.input_content_hashes),
            "created_at": self.created_at.isoformat(),
            "data_eligibility": self.data_eligibility.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "universe_snapshot": universe_snapshot_to_dict(
                self.universe_snapshot
            ),
            "eligibility_snapshot": eligibility_snapshot_to_dict(
                self.eligibility_snapshot
            ),
            "decision_price_snapshot": (
                self.decision_price_snapshot.to_canonical_dict()
            ),
            "content_hash": self.content_hash,
            "input_bundle_id": str(self.input_bundle_id),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> ResearchInputBundle:
        expected = {
            *{
                "schema_version",
                "evidence_kind",
                "source_manifest",
                "universe_snapshot_id",
                "eligibility_snapshot_id",
                "decision_price_snapshot_id",
                "market_observation",
                "theme_observations",
                "symbol_observations",
                "theme_memberships",
                "etf_observations",
                "stock_daily_bars",
                "prediction_runs",
                "input_artifact_ids",
                "input_content_hashes",
                "created_at",
                "data_eligibility",
            },
            "universe_snapshot",
            "eligibility_snapshot",
            "decision_price_snapshot",
            "content_hash",
            "input_bundle_id",
        }
        _expect_fields(payload, expected, "ResearchInputBundle")
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported ResearchInputBundle schema")
        market = payload["market_observation"]
        result = cls(
            evidence_kind=ResearchEvidenceKind(str(payload["evidence_kind"])),
            source_manifest=SourceManifest.from_canonical_dict(
                _object(payload["source_manifest"])
            ),
            universe_snapshot=universe_snapshot_from_dict(
                _object(payload["universe_snapshot"])
            ),
            eligibility_snapshot=eligibility_snapshot_from_dict(
                _object(payload["eligibility_snapshot"])
            ),
            decision_price_snapshot=DecisionPriceSnapshot.from_canonical_dict(
                _object(payload["decision_price_snapshot"])
            ),
            market_observation=(
                MarketObservation.from_canonical_dict(_object(market))
                if market is not None
                else None
            ),
            theme_observations=tuple(
                ThemeResearchObservation.from_canonical_dict(_object(item))
                for item in _array(payload["theme_observations"])
            ),
            symbol_observations=tuple(
                SymbolResearchObservation.from_canonical_dict(_object(item))
                for item in _array(payload["symbol_observations"])
            ),
            theme_memberships=tuple(
                ThemeMembership.from_canonical_dict(_object(item))
                for item in _array(payload["theme_memberships"])
            ),
            etf_observations=tuple(
                ETFObservation.from_canonical_dict(_object(item))
                for item in _array(payload["etf_observations"])
            ),
            stock_daily_bars=tuple(
                ResearchDailyBar.from_canonical_dict(_object(item))
                for item in _array(payload["stock_daily_bars"])
            ),
            prediction_runs=tuple(
                PredictionRun.from_canonical_dict(_object(item))
                for item in _array(payload["prediction_runs"])
            ),
            input_artifact_ids=tuple(
                ArtifactId(value)
                for value in _strings(payload["input_artifact_ids"])
            ),
            input_content_hashes=_strings(payload["input_content_hashes"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )
        if (
            str(result.universe_snapshot.evidence_artifact_id)
            != payload["universe_snapshot_id"]
            or str(result.eligibility_snapshot.evidence_artifact_id)
            != payload["eligibility_snapshot_id"]
            or str(result.decision_price_snapshot.decision_snapshot_id)
            != payload["decision_price_snapshot_id"]
            or result.content_hash != payload["content_hash"]
            or str(result.input_bundle_id) != payload["input_bundle_id"]
        ):
            raise ValueError("ResearchInputBundle identity mismatch")
        return result


@dataclass(frozen=True, slots=True)
class ResearchInputBundleV2(ResearchInputBundle):
    """Operational V2 input bound to one verified H6 composite manifest."""

    SCHEMA_VERSION = "research-input-bundle-v2"

    composite_manifest: CompositeOperationalInputManifest
    composition_policy: CompositeOperationalCompositionPolicy

    def __post_init__(self) -> None:
        from market_regime_alpha.application.operational_research.composite_manifest import (
            CompositeOperationalCompositionPolicy,
            CompositeOperationalCompositionStatus,
            CompositeOperationalInputManifest,
        )

        if not isinstance(
            self.composite_manifest, CompositeOperationalInputManifest
        ):
            raise TypeError(
                "composite_manifest must be CompositeOperationalInputManifest"
            )
        if not isinstance(
            self.composition_policy, CompositeOperationalCompositionPolicy
        ):
            raise TypeError(
                "composition_policy must be CompositeOperationalCompositionPolicy"
            )
        if (
            self.composite_manifest.composition_policy_id
            != self.composition_policy.policy_id
            or self.composite_manifest.composition_policy_hash
            != self.composition_policy.policy_hash
            or self.composite_manifest.builder_revision
            != self.composition_policy.builder_revision
        ):
            raise ValueError("ResearchInputBundleV2 composition policy mismatch")
        if (
            self.composite_manifest.status
            is not CompositeOperationalCompositionStatus.VERIFIED
        ):
            raise ValueError("ResearchInputBundleV2 requires a VERIFIED manifest")
        if (
            self.evidence_kind
            is not ResearchEvidenceKind.OPERATIONAL_EXPLORATORY_ARCHIVE
        ):
            raise ValueError(
                "ResearchInputBundleV2 requires operational exploratory evidence"
            )
        if (
            self.source_manifest.source_manifest_id
            != self.composite_manifest.daily_source_manifest_id
            or self.source_manifest.content_hash
            != self.composite_manifest.daily_source_manifest_hash
        ):
            raise ValueError("ResearchInputBundleV2 primary SourceManifest mismatch")
        lineage = dict(
            zip(
                self.input_artifact_ids,
                self.input_content_hashes,
                strict=True,
            )
        )
        required = {
            self.composite_manifest.manifest_id: (
                self.composite_manifest.content_hash
            ),
            self.composite_manifest.daily_artifact_id: (
                self.composite_manifest.daily_artifact_hash
            ),
            self.composite_manifest.supplemental_bundle_id: (
                self.composite_manifest.supplemental_bundle_hash
            ),
            self.composite_manifest.daily_source_manifest_id: (
                self.composite_manifest.daily_source_manifest_hash
            ),
            self.composite_manifest.supplemental_source_manifest_id: (
                self.composite_manifest.supplemental_source_manifest_hash
            ),
        }
        if any(lineage.get(key) != value for key, value in required.items()):
            raise ValueError("ResearchInputBundleV2 omits H6 composite lineage")
        ResearchInputBundle.__post_init__(self)

    @property
    def primary_source_manifest(self) -> SourceManifest:
        return self.source_manifest

    @property
    def composite_manifest_id(self) -> ArtifactId:
        return self.composite_manifest.manifest_id

    @property
    def composite_manifest_hash(self) -> str:
        return str(self.composite_manifest.content_hash)

    def semantic_payload(self) -> dict[str, Any]:
        payload = ResearchInputBundle.semantic_payload(self)
        source = payload.pop("source_manifest")
        payload["primary_source_manifest"] = source
        payload["composite_manifest"] = self.composite_manifest.to_canonical_dict()
        payload["composition_policy"] = self.composition_policy.to_canonical_dict()
        payload["composite_manifest_id"] = str(self.composite_manifest_id)
        payload["composite_manifest_hash"] = self.composite_manifest_hash
        return payload

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> ResearchInputBundleV2:
        from market_regime_alpha.application.operational_research.composite_manifest import (
            CompositeOperationalCompositionPolicy,
            CompositeOperationalInputManifest,
        )

        expected = {
            "schema_version",
            "evidence_kind",
            "primary_source_manifest",
            "universe_snapshot_id",
            "eligibility_snapshot_id",
            "decision_price_snapshot_id",
            "market_observation",
            "theme_observations",
            "symbol_observations",
            "theme_memberships",
            "etf_observations",
            "stock_daily_bars",
            "prediction_runs",
            "input_artifact_ids",
            "input_content_hashes",
            "created_at",
            "data_eligibility",
            "composite_manifest",
            "composition_policy",
            "composite_manifest_id",
            "composite_manifest_hash",
            "universe_snapshot",
            "eligibility_snapshot",
            "decision_price_snapshot",
            "content_hash",
            "input_bundle_id",
        }
        _expect_fields(payload, expected, "ResearchInputBundleV2")
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported ResearchInputBundleV2 schema")
        composite_payload = _object(payload["composite_manifest"])
        policy = CompositeOperationalCompositionPolicy.from_canonical_dict(
            _object(payload["composition_policy"])
        )
        manifest = CompositeOperationalInputManifest.from_canonical_dict(
            composite_payload,
            composition_policy=policy,
        )
        market = payload["market_observation"]
        result = cls(
            evidence_kind=ResearchEvidenceKind(str(payload["evidence_kind"])),
            source_manifest=SourceManifest.from_canonical_dict(
                _object(payload["primary_source_manifest"])
            ),
            universe_snapshot=universe_snapshot_from_dict(
                _object(payload["universe_snapshot"])
            ),
            eligibility_snapshot=eligibility_snapshot_from_dict(
                _object(payload["eligibility_snapshot"])
            ),
            decision_price_snapshot=DecisionPriceSnapshot.from_canonical_dict(
                _object(payload["decision_price_snapshot"])
            ),
            market_observation=(
                MarketObservation.from_canonical_dict(_object(market))
                if market is not None
                else None
            ),
            theme_observations=tuple(
                ThemeResearchObservation.from_canonical_dict(_object(item))
                for item in _array(payload["theme_observations"])
            ),
            symbol_observations=tuple(
                SymbolResearchObservation.from_canonical_dict(_object(item))
                for item in _array(payload["symbol_observations"])
            ),
            theme_memberships=tuple(
                ThemeMembership.from_canonical_dict(_object(item))
                for item in _array(payload["theme_memberships"])
            ),
            etf_observations=tuple(
                ETFObservation.from_canonical_dict(_object(item))
                for item in _array(payload["etf_observations"])
            ),
            stock_daily_bars=tuple(
                ResearchDailyBar.from_canonical_dict(_object(item))
                for item in _array(payload["stock_daily_bars"])
            ),
            prediction_runs=tuple(
                PredictionRun.from_canonical_dict(_object(item))
                for item in _array(payload["prediction_runs"])
            ),
            input_artifact_ids=tuple(
                ArtifactId(value)
                for value in _strings(payload["input_artifact_ids"])
            ),
            input_content_hashes=_strings(payload["input_content_hashes"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            composite_manifest=manifest,
            composition_policy=policy,
        )
        if (
            str(result.universe_snapshot.evidence_artifact_id)
            != payload["universe_snapshot_id"]
            or str(result.eligibility_snapshot.evidence_artifact_id)
            != payload["eligibility_snapshot_id"]
            or str(result.decision_price_snapshot.decision_snapshot_id)
            != payload["decision_price_snapshot_id"]
            or str(result.composite_manifest_id)
            != payload["composite_manifest_id"]
            or result.composite_manifest_hash
            != payload["composite_manifest_hash"]
            or result.content_hash != payload["content_hash"]
            or str(result.input_bundle_id) != payload["input_bundle_id"]
        ):
            raise ValueError("ResearchInputBundleV2 identity mismatch")
        return result


ResearchInputBundleAny = ResearchInputBundle | ResearchInputBundleV2


def research_input_bundle_from_canonical_dict(
    payload: dict[str, Any],
) -> ResearchInputBundleAny:
    schema = payload.get("schema_version")
    if schema == ResearchInputBundle.SCHEMA_VERSION:
        return ResearchInputBundle.from_canonical_dict(payload)
    if schema == ResearchInputBundleV2.SCHEMA_VERSION:
        return ResearchInputBundleV2.from_canonical_dict(payload)
    raise ValueError("unsupported Research Input Bundle schema")


def _require_unique_by(label: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _expect_fields(
    payload: dict[str, Any], expected: set[str], label: str
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Research input value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Research input value must be an array")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError("Research input value must be a string array")
    return tuple(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Research input value must be numeric")
    return float(value)


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Research input value must be boolean")
    return value
