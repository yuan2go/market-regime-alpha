"""Strict lineage-preserving input boundary for the Platform V2 Research Layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from math import isfinite
from typing import Any

from market_regime_alpha.core.identity import (
    ArtifactId,
    FeatureDefinitionId,
)
from market_regime_alpha.core.time import AvailabilityTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.daily_decision.snapshot import DecisionPriceSnapshot
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


def _require_unique_by(label: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
