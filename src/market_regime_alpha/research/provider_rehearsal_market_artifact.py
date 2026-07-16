"""Identified provider-backed/provider-export-backed rehearsal input bundle for R5 research.

The bundle lives in the downstream research context because it composes independently owned Data,
Trading Calendar, Universe, and Eligibility evidence. It does not make Data depend on Universe and
it grants REHEARSAL authority only.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.contracts import (
    DataEligibility,
    DatasetContract,
    ProviderReference,
    SourceArtifactReference,
)
from market_regime_alpha.data.rehearsal import (
    RehearsalDailyBar,
    RehearsalDecisionSnapshot,
    RehearsalNextSessionBar,
)
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.universe.artifacts import HistoricalPITUniverseArtifact
from market_regime_alpha.universe.eligibility_artifacts import HistoricalTradingEligibilityArtifact
from market_regime_alpha.universe.eligibility_policy import (
    RawTradingEligibilityObservation,
    TradingEligibilityPolicy,
    materialize_historical_trading_eligibility,
)


PROVIDER_REHEARSAL_MARKET_ARTIFACT_SCHEMA_VERSION = "provider-rehearsal-market-artifact-v1"


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


@dataclass(frozen=True, slots=True)
class ProviderRehearsalMarketArtifact:
    """Immutable identified R5 rehearsal input bundle composed from upstream evidence."""

    artifact_id: ArtifactId
    dataset_contract: DatasetContract
    schema_version: str
    source_artifacts: tuple[SourceArtifactReference, ...]
    retrieval_convention: str
    market_availability_convention: str
    raw_eligibility_evidence_convention: str
    bar_finality_convention: str
    price_adjustment_basis: str
    trading_calendar: TradingCalendarArtifact
    universe_artifact: HistoricalPITUniverseArtifact
    daily_bars: tuple[RehearsalDailyBar, ...]
    decision_snapshots: tuple[RehearsalDecisionSnapshot, ...]
    next_session_bars: tuple[RehearsalNextSessionBar, ...]
    raw_eligibility_observations: tuple[RawTradingEligibilityObservation, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("schema_version", self.schema_version),
            ("retrieval_convention", self.retrieval_convention),
            ("market_availability_convention", self.market_availability_convention),
            ("raw_eligibility_evidence_convention", self.raw_eligibility_evidence_convention),
            ("bar_finality_convention", self.bar_finality_convention),
            ("price_adjustment_basis", self.price_adjustment_basis),
        ):
            _require_non_empty(label, value)
        if self.schema_version != PROVIDER_REHEARSAL_MARKET_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("unsupported provider rehearsal market artifact schema_version")
        if self.dataset_contract.eligibility is not DataEligibility.REHEARSAL:
            raise ValueError("provider rehearsal market artifact requires REHEARSAL Data Eligibility")
        if self.dataset_contract.manifest_artifact_id != self.artifact_id:
            raise ValueError("dataset manifest Artifact identity must match provider rehearsal artifact")
        if not self.source_artifacts:
            raise ValueError("provider rehearsal market artifact requires source artifacts")
        source_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source artifact identities must be unique")
        declared_provider_ids = {reference.provider_id for reference in self.dataset_contract.provider_references}
        if any(item.provider_id not in declared_provider_ids for item in self.source_artifacts):
            raise ValueError("source artifact provider must be declared by Dataset provider references")
        if not self.daily_bars:
            raise ValueError("provider rehearsal market artifact requires daily bars")
        if not self.decision_snapshots:
            raise ValueError("provider rehearsal market artifact requires Decision-Time snapshots")
        if not self.next_session_bars:
            raise ValueError("provider rehearsal market artifact requires next-session OHLC bars")
        if not self.raw_eligibility_observations:
            raise ValueError("provider rehearsal market artifact requires raw eligibility observations")
        _require_unique_keys(
            "daily bars",
            tuple((item.session_date, item.symbol) for item in self.daily_bars),
        )
        _require_unique_keys(
            "Decision-Time snapshots",
            tuple((item.decision_time.value, item.symbol) for item in self.decision_snapshots),
        )
        _require_unique_keys(
            "next-session bars",
            tuple((item.session_date, item.symbol) for item in self.next_session_bars),
        )
        _require_unique_keys(
            "raw eligibility observations",
            tuple((item.as_of.value, item.symbol) for item in self.raw_eligibility_observations),
        )
        zone = ZoneInfo(self.trading_calendar.timezone_name)
        for daily_bar in self.daily_bars:
            if not self.trading_calendar.contains(daily_bar.session_date):
                raise ValueError("daily bar session date is absent from identified Trading Calendar")
        for snapshot in self.decision_snapshots:
            local_date = snapshot.decision_time.value.astimezone(zone).date()
            if not self.trading_calendar.contains(local_date):
                raise ValueError("Decision-Time snapshot date is absent from identified Trading Calendar")
        for next_session_bar in self.next_session_bars:
            if not self.trading_calendar.contains(next_session_bar.session_date):
                raise ValueError("next-session bar date is absent from identified Trading Calendar")
        for observation in self.raw_eligibility_observations:
            local_date = observation.as_of.value.astimezone(zone).date()
            if not self.trading_calendar.contains(local_date):
                raise ValueError("raw eligibility observation date is absent from identified Trading Calendar")

    @property
    def decision_times(self) -> tuple:
        return tuple(
            sorted(
                {snapshot.decision_time for snapshot in self.decision_snapshots},
                key=lambda value: value.value,
            )
        )

    def materialize_trading_eligibility(
        self,
        *,
        policy: TradingEligibilityPolicy,
    ) -> HistoricalTradingEligibilityArtifact:
        """Materialize exact-time eligibility under the supplied identified Policy."""

        return materialize_historical_trading_eligibility(
            source_dataset_id=self.dataset_contract.dataset_id,
            universe_artifact=self.universe_artifact,
            policy=policy,
            decision_times=self.decision_times,
            observations=self.raw_eligibility_observations,
            raw_evidence_convention=self.raw_eligibility_evidence_convention,
        )


def build_provider_rehearsal_market_artifact(
    *,
    provider_references: tuple[ProviderReference, ...],
    source_artifacts: tuple[SourceArtifactReference, ...],
    retrieval_convention: str,
    market_availability_convention: str,
    raw_eligibility_evidence_convention: str,
    bar_finality_convention: str,
    price_adjustment_basis: str,
    trading_calendar: TradingCalendarArtifact,
    universe_artifact: HistoricalPITUniverseArtifact,
    daily_bars: tuple[RehearsalDailyBar, ...],
    decision_snapshots: tuple[RehearsalDecisionSnapshot, ...],
    next_session_bars: tuple[RehearsalNextSessionBar, ...],
    raw_eligibility_observations: tuple[RawTradingEligibilityObservation, ...],
    pit_correct_for_scope: bool,
    limitations: tuple[str, ...] = (),
) -> ProviderRehearsalMarketArtifact:
    """Build a deterministic REHEARSAL input artifact from identified provider evidence."""

    if not isinstance(pit_correct_for_scope, bool):
        raise TypeError("pit_correct_for_scope must be boolean")
    for label, value in (
        ("retrieval_convention", retrieval_convention),
        ("market_availability_convention", market_availability_convention),
        ("raw_eligibility_evidence_convention", raw_eligibility_evidence_convention),
        ("bar_finality_convention", bar_finality_convention),
        ("price_adjustment_basis", price_adjustment_basis),
    ):
        _require_non_empty(label, value)
    if not provider_references:
        raise ValueError("provider_references must not be empty")
    if not source_artifacts:
        raise ValueError("source_artifacts must not be empty")

    ordered_provider_references = tuple(
        sorted(
            provider_references,
            key=lambda item: (str(item.provider_id), item.product, item.contract_version),
        )
    )
    ordered_source_artifacts = tuple(sorted(source_artifacts, key=lambda item: str(item.artifact_id)))
    ordered_daily_bars = tuple(sorted(daily_bars, key=lambda item: (item.session_date, item.symbol)))
    ordered_decision_snapshots = tuple(
        sorted(decision_snapshots, key=lambda item: (item.decision_time.value, item.symbol))
    )
    ordered_next_session_bars = tuple(
        sorted(next_session_bars, key=lambda item: (item.session_date, item.symbol))
    )
    ordered_raw_eligibility = tuple(
        sorted(raw_eligibility_observations, key=lambda item: (item.as_of.value, item.symbol))
    )

    payload = {
        "schema_version": PROVIDER_REHEARSAL_MARKET_ARTIFACT_SCHEMA_VERSION,
        "provider_references": [
            {
                "provider_id": str(item.provider_id),
                "product": item.product,
                "contract_version": item.contract_version,
            }
            for item in ordered_provider_references
        ],
        "source_artifacts": [
            {
                "artifact_id": str(item.artifact_id),
                "provider_id": str(item.provider_id),
                "retrieved_at": item.retrieved_at.isoformat(),
                "content_hash": item.content_hash,
                "locator": item.locator,
            }
            for item in ordered_source_artifacts
        ],
        "retrieval_convention": retrieval_convention,
        "market_availability_convention": market_availability_convention,
        "raw_eligibility_evidence_convention": raw_eligibility_evidence_convention,
        "bar_finality_convention": bar_finality_convention,
        "price_adjustment_basis": price_adjustment_basis,
        "trading_calendar_artifact_id": str(trading_calendar.artifact_id),
        "trading_calendar_source_dataset_id": str(trading_calendar.source_dataset_id),
        "universe_artifact_id": str(universe_artifact.artifact_id),
        "universe_source_dataset_id": str(universe_artifact.source_dataset_id),
        "daily_bars": [
            {
                "symbol": item.symbol,
                "session_date": item.session_date.isoformat(),
                "close": item.close,
                "amount": item.amount,
                "available_at": item.available_at.isoformat(),
                "finalized": item.finalized,
            }
            for item in ordered_daily_bars
        ],
        "decision_snapshots": [
            {
                "symbol": item.symbol,
                "decision_time": item.decision_time.isoformat(),
                "reference_price": item.reference_price,
                "available_at": item.available_at.isoformat(),
            }
            for item in ordered_decision_snapshots
        ],
        "next_session_bars": [
            {
                "symbol": item.symbol,
                "session_date": item.session_date.isoformat(),
                "open": item.open,
                "high": item.high,
                "low": item.low,
                "close": item.close,
                "available_at": item.available_at.isoformat(),
            }
            for item in ordered_next_session_bars
        ],
        "raw_eligibility_observations": [
            {
                "as_of": item.as_of.isoformat(),
                "available_at": item.available_at.isoformat(),
                "symbol": item.symbol,
                "is_suspended": item.is_suspended,
                "is_st": item.is_st,
                "prev_close": item.prev_close,
                "limit_up_price": item.limit_up_price,
                "limit_down_price": item.limit_down_price,
                "limit_regime": item.limit_regime,
                "listing_age_calendar_days": item.listing_age_calendar_days,
                "liquidity_value": item.liquidity_value,
                "liquidity_measure_id": item.liquidity_measure_id,
                "decision_buyability": (
                    item.decision_buyability.value if item.decision_buyability is not None else None
                ),
            }
            for item in ordered_raw_eligibility
        ],
        "pit_correct_for_scope": pit_correct_for_scope,
        "limitations": list(limitations),
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    artifact_id = ArtifactId(f"provider-rehearsal-market-artifact-{digest[:24]}")
    dataset_id = DatasetId(f"provider-rehearsal-market-dataset-{digest[:24]}")
    dataset_contract = DatasetContract(
        dataset_id=dataset_id,
        schema_version=PROVIDER_REHEARSAL_MARKET_ARTIFACT_SCHEMA_VERSION,
        eligibility=DataEligibility.REHEARSAL,
        manifest_artifact_id=artifact_id,
        provider_references=ordered_provider_references,
        pit_correct_for_scope=pit_correct_for_scope,
        scope="R5 provider-backed/provider-export-backed rehearsal market input bundle",
        limitations=limitations,
    )
    return ProviderRehearsalMarketArtifact(
        artifact_id=artifact_id,
        dataset_contract=dataset_contract,
        schema_version=PROVIDER_REHEARSAL_MARKET_ARTIFACT_SCHEMA_VERSION,
        source_artifacts=ordered_source_artifacts,
        retrieval_convention=retrieval_convention,
        market_availability_convention=market_availability_convention,
        raw_eligibility_evidence_convention=raw_eligibility_evidence_convention,
        bar_finality_convention=bar_finality_convention,
        price_adjustment_basis=price_adjustment_basis,
        trading_calendar=trading_calendar,
        universe_artifact=universe_artifact,
        daily_bars=ordered_daily_bars,
        decision_snapshots=ordered_decision_snapshots,
        next_session_bars=ordered_next_session_bars,
        raw_eligibility_observations=ordered_raw_eligibility,
    )


def _require_unique_keys(label: str, keys: tuple[tuple[object, ...], ...]) -> None:
    if len(keys) != len(set(keys)):
        raise ValueError(f"{label} must have unique keys")
