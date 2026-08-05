"""T+1 factual observations for future validation, never validation itself."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.application.controlled_operation.evidence_package import (
    ControlledOperationalEvidencePackage,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
)
from market_regime_alpha.forecasting.artifact import VerifiedPathForecastArtifact
from market_regime_alpha.market_data import VerifiedMarketDataDataset
from market_regime_alpha.market_data.contracts import (
    CanonicalMarketBar,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    canonical_decimal,
    parse_canonical_decimal,
    parse_utc_second,
    require_utc_second,
)
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals.v3 import VerifiedSignalRunArtifactV3


TRADE_HORIZON_DEFINITION_SCHEMA = "trade-horizon-definition-v1"
TRADE_HORIZON_OUTCOME_SCHEMA = "trade-horizon-outcome-observation-v1"
TRADE_HORIZON_OUTCOME_PACKAGE_SCHEMA = "trade-horizon-outcome-package-v1"
TRADE_HORIZON_OUTCOME_PACKAGE_FILES = (
    "SHA256SUMS.json",
    "artifact.json",
    "manifest.json",
)


class OutcomeCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    DATA_INCOMPLETE = "DATA_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class TradeHorizonDefinition:
    schema_version: str
    horizon_id: ArtifactId
    content_hash: str
    timezone_name: str
    observation_time: time
    morning_start: time
    morning_end: time
    include_session_close: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != TRADE_HORIZON_DEFINITION_SCHEMA:
            raise ValueError("unsupported Trade Horizon definition schema")
        require_sha256("content_hash", self.content_hash)
        ZoneInfo(self.timezone_name)
        if not self.morning_start < self.observation_time <= self.morning_end:
            raise ValueError("Trade Horizon observation time is outside morning interval")
        if not self.limitations or self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Trade Horizon limitations must be non-empty and sorted")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        timezone_name: str = "Asia/Shanghai",
        observation_time: time = time(10, 30),
        morning_start: time = time(9, 30),
        morning_end: time = time(11, 30),
        include_session_close: bool = True,
        limitations: tuple[str, ...] = (
            "FACTUAL_OBSERVATION_ONLY",
            "NOT_A_FORMAL_H9_LABEL",
        ),
    ) -> TradeHorizonDefinition:
        values = {
            "timezone_name": timezone_name,
            "observation_time": observation_time,
            "morning_start": morning_start,
            "morning_end": morning_end,
            "include_session_close": include_session_close,
            "limitations": tuple(sorted(set(limitations))),
        }
        digest = canonical_hash(_horizon_payload(**values))
        return cls(
            schema_version=TRADE_HORIZON_DEFINITION_SCHEMA,
            horizon_id=ArtifactId(f"trade-horizon-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _horizon_payload(**_horizon_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Trade Horizon definition hash mismatch")
        if str(self.horizon_id) != f"trade-horizon-{digest.split(':', 1)[1][:24]}":
            raise ValueError("Trade Horizon definition identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "horizon_id": str(self.horizon_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> TradeHorizonDefinition:
        expected = {
            "schema_version", "horizon_id", "content_hash", "timezone_name",
            "observation_time", "morning_start", "morning_end",
            "include_session_close", "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Trade Horizon definition fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            horizon_id=ArtifactId(str(payload["horizon_id"])),
            content_hash=str(payload["content_hash"]),
            timezone_name=str(payload["timezone_name"]),
            observation_time=time.fromisoformat(str(payload["observation_time"])),
            morning_start=time.fromisoformat(str(payload["morning_start"])),
            morning_end=time.fromisoformat(str(payload["morning_end"])),
            include_session_close=bool(payload["include_session_close"]),
            limitations=_strings(payload["limitations"], "limitations"),
        )


@dataclass(frozen=True, slots=True)
class TradeHorizonOutcomeObservation:
    schema_version: str
    observation_id: ArtifactId
    content_hash: str
    symbol: str
    candidate_set_id: ArtifactId
    candidate_set_hash: str
    signal_snapshot_id: ArtifactId
    signal_snapshot_hash: str
    path_forecast_id: ArtifactId
    path_forecast_hash: str
    operation_package_id: ArtifactId
    operation_package_hash: str
    source_dataset_id: ArtifactId
    source_dataset_hash: str
    source_artifact_references: tuple[tuple[ArtifactId, str], ...]
    horizon: TradeHorizonDefinition
    decision_time: datetime
    next_session_date: date
    decision_reference_price: Decimal
    next_open: Decimal | None
    next_1030_price: Decimal | None
    morning_high: Decimal | None
    morning_low: Decimal | None
    session_close: Decimal | None
    gross_return: Decimal | None
    mfe: Decimal | None
    mae: Decimal | None
    suspended: bool | None
    price_limit_observations: tuple[str, ...]
    availability_time: datetime | None
    completeness: OutcomeCompleteness
    feasibility_observations: tuple[str, ...]
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != TRADE_HORIZON_OUTCOME_SCHEMA:
            raise ValueError("unsupported Trade Horizon Outcome schema")
        for label, value in (
            ("content_hash", self.content_hash),
            ("candidate_set_hash", self.candidate_set_hash),
            ("signal_snapshot_hash", self.signal_snapshot_hash),
            ("path_forecast_hash", self.path_forecast_hash),
            ("operation_package_hash", self.operation_package_hash),
            ("source_dataset_hash", self.source_dataset_hash),
        ):
            require_sha256(label, value)
        require_utc_second("decision_time", self.decision_time)
        if self.availability_time is not None:
            require_utc_second("availability_time", self.availability_time)
            if self.availability_time <= self.decision_time:
                raise ValueError("Outcome evidence must become available after DecisionTime")
        if self.decision_reference_price <= 0:
            raise ValueError("Outcome decision reference price must be positive")
        references = tuple((str(item), digest) for item, digest in self.source_artifact_references)
        if references != tuple(sorted(set(references))):
            raise ValueError("Outcome source references must be unique and sorted")
        for _, digest in self.source_artifact_references:
            require_sha256("source artifact hash", digest)
        values = (
            self.next_open,
            self.next_1030_price,
            self.morning_high,
            self.morning_low,
            self.session_close,
            self.gross_return,
            self.mfe,
            self.mae,
        )
        if self.completeness is OutcomeCompleteness.COMPLETE:
            if any(item is None for item in values) or self.availability_time is None:
                raise ValueError("complete Outcome observation has missing values")
        elif any(item is not None for item in (self.gross_return, self.mfe, self.mae)):
            raise ValueError("incomplete Outcome cannot carry derived metrics")
        for label, items in (
            ("price_limit_observations", self.price_limit_observations),
            ("feasibility_observations", self.feasibility_observations),
            ("reason_codes", self.reason_codes),
            ("limitations", self.limitations),
        ):
            if not items or items != tuple(sorted(set(items))):
                raise ValueError(f"Outcome {label} must be non-empty and sorted")
        for required in ("FACTUAL_OBSERVATION_ONLY", "NOT_A_FORMAL_H9_LABEL"):
            if required not in self.limitations:
                raise ValueError("Outcome authority ceiling is incomplete")
        self.verify_identity()

    def semantic_payload(self) -> dict[str, Any]:
        return _outcome_payload(**_outcome_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Trade Horizon Outcome hash mismatch")
        expected = f"trade-horizon-outcome-{digest.split(':', 1)[1][:24]}"
        if str(self.observation_id) != expected:
            raise ValueError("Trade Horizon Outcome identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "observation_id": str(self.observation_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> TradeHorizonOutcomeObservation:
        expected = {"observation_id", "content_hash", *_outcome_payload_keys()}
        if set(payload) != expected:
            raise ValueError("Trade Horizon Outcome fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            observation_id=ArtifactId(str(payload["observation_id"])),
            content_hash=str(payload["content_hash"]),
            symbol=str(payload["symbol"]),
            candidate_set_id=ArtifactId(str(payload["candidate_set_id"])),
            candidate_set_hash=str(payload["candidate_set_hash"]),
            signal_snapshot_id=ArtifactId(str(payload["signal_snapshot_id"])),
            signal_snapshot_hash=str(payload["signal_snapshot_hash"]),
            path_forecast_id=ArtifactId(str(payload["path_forecast_id"])),
            path_forecast_hash=str(payload["path_forecast_hash"]),
            operation_package_id=ArtifactId(str(payload["operation_package_id"])),
            operation_package_hash=str(payload["operation_package_hash"]),
            source_dataset_id=ArtifactId(str(payload["source_dataset_id"])),
            source_dataset_hash=str(payload["source_dataset_hash"]),
            source_artifact_references=tuple(
                (ArtifactId(str(item["artifact_id"])), str(item["content_hash"]))
                for item in _objects(payload["source_artifact_references"], "source references")
            ),
            horizon=TradeHorizonDefinition.from_canonical_dict(
                _object(payload["horizon"], "horizon")
            ),
            decision_time=parse_utc_second("decision_time", payload["decision_time"]),
            next_session_date=date.fromisoformat(str(payload["next_session_date"])),
            decision_reference_price=_decimal(payload["decision_reference_price"]),
            next_open=_optional_decimal(payload["next_open"]),
            next_1030_price=_optional_decimal(payload["next_1030_price"]),
            morning_high=_optional_decimal(payload["morning_high"]),
            morning_low=_optional_decimal(payload["morning_low"]),
            session_close=_optional_decimal(payload["session_close"]),
            gross_return=_optional_decimal(payload["gross_return"]),
            mfe=_optional_decimal(payload["mfe"]),
            mae=_optional_decimal(payload["mae"]),
            suspended=(
                bool(payload["suspended"]) if payload["suspended"] is not None else None
            ),
            price_limit_observations=_strings(
                payload["price_limit_observations"], "price limit observations"
            ),
            availability_time=(
                parse_utc_second("availability_time", payload["availability_time"])
                if payload["availability_time"] is not None else None
            ),
            completeness=OutcomeCompleteness(str(payload["completeness"])),
            feasibility_observations=_strings(
                payload["feasibility_observations"], "feasibility observations"
            ),
            reason_codes=_strings(payload["reason_codes"], "reason codes"),
            limitations=_strings(payload["limitations"], "limitations"),
        )


@dataclass(frozen=True, slots=True)
class TradeHorizonOutcomeEvidence:
    artifact_id: ArtifactId
    content_hash: str
    operation_package_id: ArtifactId
    operation_package_hash: str
    source_dataset_id: ArtifactId
    source_dataset_hash: str
    horizon: TradeHorizonDefinition
    observations: tuple[TradeHorizonOutcomeObservation, ...]
    created_at: datetime
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("content_hash", self.content_hash)
        require_sha256("operation_package_hash", self.operation_package_hash)
        require_sha256("source_dataset_hash", self.source_dataset_hash)
        require_utc_second("created_at", self.created_at)
        symbols = tuple(item.symbol for item in self.observations)
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("Outcome evidence symbols must be unique and sorted")
        if any(
            item.operation_package_id != self.operation_package_id
            or item.operation_package_hash != self.operation_package_hash
            or item.source_dataset_id != self.source_dataset_id
            or item.source_dataset_hash != self.source_dataset_hash
            or item.horizon != self.horizon
            for item in self.observations
        ):
            raise ValueError("Outcome evidence child binding mismatch")
        if not self.limitations or self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Outcome evidence limitations must be non-empty and sorted")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        operation_package: ControlledOperationalEvidencePackage,
        source_dataset: VerifiedMarketDataDataset,
        observations: tuple[TradeHorizonOutcomeObservation, ...],
        horizon: TradeHorizonDefinition,
        created_at: datetime,
    ) -> TradeHorizonOutcomeEvidence:
        ordered = tuple(sorted(observations, key=lambda item: item.symbol))
        values = {
            "operation_package_id": operation_package.package_id,
            "operation_package_hash": operation_package.content_hash,
            "source_dataset_id": ArtifactId(str(source_dataset.artifact.dataset_id)),
            "source_dataset_hash": source_dataset.artifact.content_hash,
            "horizon": horizon,
            "observations": ordered,
            "created_at": created_at,
            "limitations": (
                "FACTUAL_OBSERVATION_ONLY",
                "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                "NOT_A_FORMAL_H9_LABEL",
            ),
        }
        digest = canonical_hash(_evidence_payload(**values))
        return cls(
            artifact_id=ArtifactId(f"outcome-evidence-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _evidence_payload(**_evidence_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Outcome evidence hash mismatch")
        if str(self.artifact_id) != f"outcome-evidence-{digest.split(':', 1)[1][:24]}":
            raise ValueError("Outcome evidence identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> TradeHorizonOutcomeEvidence:
        expected = {"artifact_id", "content_hash", *_evidence_payload_keys()}
        if set(payload) != expected:
            raise ValueError("Outcome evidence fields mismatch")
        return cls(
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            operation_package_id=ArtifactId(str(payload["operation_package_id"])),
            operation_package_hash=str(payload["operation_package_hash"]),
            source_dataset_id=ArtifactId(str(payload["source_dataset_id"])),
            source_dataset_hash=str(payload["source_dataset_hash"]),
            horizon=TradeHorizonDefinition.from_canonical_dict(
                _object(payload["horizon"], "horizon")
            ),
            observations=tuple(
                TradeHorizonOutcomeObservation.from_canonical_dict(item)
                for item in _objects(payload["observations"], "observations")
            ),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            limitations=_strings(payload["limitations"], "limitations"),
        )


def build_trade_horizon_outcome_evidence(
    *,
    operation_package: ControlledOperationalEvidencePackage,
    candidate_set: CandidateSet,
    signal: VerifiedSignalRunArtifactV3,
    forecasts: tuple[VerifiedPathForecastArtifact, ...],
    decision_dataset: VerifiedMarketDataDataset,
    settlement_dataset: VerifiedMarketDataDataset,
    next_session_date: date,
    horizon: TradeHorizonDefinition,
    created_at: datetime,
) -> TradeHorizonOutcomeEvidence:
    """Derive factual observations only from verified immutable datasets."""

    candidates = {item.symbol for item in candidate_set.selected}
    signals = {item.symbol: item for item in signal.artifact.snapshots}
    if (
        candidate_set.envelope.decision_time.value
        != operation_package.command.decision_time
        or signal.artifact.envelope.decision_time.value
        != operation_package.command.decision_time
    ):
        raise ValueError("Outcome Operation, CandidateSet, and Signal DecisionTime mismatch")
    daily_references = {
        (item.object_id, item.content_hash)
        for item in operation_package.evidence_references
        if item.reference_type == "DAILY_DATASET"
    }
    if daily_references != {
        (
            ArtifactId(str(decision_dataset.artifact.dataset_id)),
            decision_dataset.artifact.content_hash,
        )
    }:
        raise ValueError("Outcome decision Dataset package binding mismatch")
    if next_session_date <= operation_package.command.decision_date:
        raise ValueError("Outcome next session must follow the operation DecisionDate")
    if not candidates.issubset(set(settlement_dataset.artifact.coverage.expected_symbols)):
        raise ValueError("Outcome settlement Dataset does not cover all Candidates")
    by_signal_id = {
        item.artifact.signal_snapshot.envelope.artifact_id: item for item in forecasts
    }
    if set(signals) != candidates:
        raise ValueError("Outcome CandidateSet and Signal scope mismatch")
    if set(by_signal_id) != {item.envelope.artifact_id for item in signals.values()}:
        raise ValueError("Outcome PathForecast scope mismatch")
    decision_bars = tuple(decision_dataset.artifact.iter_bars())
    settlement_bars = tuple(settlement_dataset.artifact.iter_bars())
    observations = tuple(
        _build_observation(
            symbol=symbol,
            candidate_set=candidate_set,
            signal_snapshot=signals[symbol],
            forecast=by_signal_id[signals[symbol].envelope.artifact_id],
            operation_package=operation_package,
            settlement_dataset=settlement_dataset,
            decision_bars=decision_bars,
            settlement_bars=settlement_bars,
            next_session_date=next_session_date,
            horizon=horizon,
        )
        for symbol in sorted(candidates)
    )
    return TradeHorizonOutcomeEvidence.create(
        operation_package=operation_package,
        source_dataset=settlement_dataset,
        observations=observations,
        horizon=horizon,
        created_at=created_at,
    )


def _build_observation(
    *,
    symbol: str,
    candidate_set: CandidateSet,
    signal_snapshot: Any,
    forecast: VerifiedPathForecastArtifact,
    operation_package: ControlledOperationalEvidencePackage,
    settlement_dataset: VerifiedMarketDataDataset,
    decision_bars: tuple[CanonicalMarketBar, ...],
    settlement_bars: tuple[CanonicalMarketBar, ...],
    next_session_date: date,
    horizon: TradeHorizonDefinition,
) -> TradeHorizonOutcomeObservation:
    reference_candidates = [
        item for item in decision_bars
        if item.symbol == symbol
        and item.timeframe is Timeframe.DAILY
        and item.market_date <= operation_package.command.decision_date
    ]
    if not reference_candidates:
        raise ValueError(f"Outcome decision reference missing for {symbol}")
    reference = max(reference_candidates, key=lambda item: item.market_date).close
    bars = [
        item for item in settlement_bars
        if item.symbol == symbol and item.market_date == next_session_date
    ]
    zone = ZoneInfo(horizon.timezone_name)
    minutes = sorted(
        (item for item in bars if item.timeframe is Timeframe.MINUTE_1),
        key=lambda item: item.event_start,
    )
    morning = [
        item for item in minutes
        if horizon.morning_start
        <= item.event_start.astimezone(zone).time().replace(tzinfo=None)
        < horizon.observation_time
        and item.event_end.astimezone(zone).time().replace(tzinfo=None)
        <= horizon.observation_time
    ]
    daily = next((item for item in bars if item.timeframe is Timeframe.DAILY), None)
    next_open = morning[0].open if morning else None
    price_1030 = morning[-1].close if morning else None
    high = max((item.high for item in morning), default=None)
    low = min((item.low for item in morning), default=None)
    close = daily.close if daily is not None else None
    complete = all(item is not None for item in (next_open, price_1030, high, low, close))
    completeness = OutcomeCompleteness.COMPLETE if complete else OutcomeCompleteness.DATA_INCOMPLETE
    availability = (
        max(item.available_at for item in (*morning, *((daily,) if daily is not None else ())))
        if morning or daily is not None else None
    )
    suspended = (
        any(item.trading_status is TradingStatus.SUSPENDED for item in bars)
        if bars else None
    )
    limits = tuple(
        sorted({item.price_limit_state.value for item in bars if item.price_limit_state is not PriceLimitState.UNKNOWN})
    ) or ("PRICE_LIMIT_STATE_UNAVAILABLE",)
    feasibility = {
        "NO_EXECUTION_ASSUMED",
        "SUSPENSION_OBSERVED" if suspended else "SUSPENSION_NOT_OBSERVED" if suspended is False else "SUSPENSION_UNKNOWN",
        *(f"PRICE_LIMIT_{item}" for item in limits),
    }
    reasons = {
        "OUTCOME_COMPLETE" if complete else "OUTCOME_DATA_INCOMPLETE",
        *(("MORNING_MINUTE_DATA_MISSING",) if not morning else ()),
        *(("SESSION_CLOSE_MISSING",) if daily is None else ()),
    }
    values: dict[str, Any] = {
        "symbol": symbol,
        "candidate_set_id": candidate_set.envelope.artifact_id,
        "candidate_set_hash": candidate_set.envelope.content_hash,
        "signal_snapshot_id": signal_snapshot.envelope.artifact_id,
        "signal_snapshot_hash": signal_snapshot.envelope.content_hash,
        "path_forecast_id": forecast.artifact.artifact_id,
        "path_forecast_hash": forecast.artifact.forecast.envelope.content_hash,
        "operation_package_id": operation_package.package_id,
        "operation_package_hash": operation_package.content_hash,
        "source_dataset_id": ArtifactId(str(settlement_dataset.artifact.dataset_id)),
        "source_dataset_hash": settlement_dataset.artifact.content_hash,
        "source_artifact_references": tuple(
            sorted(set(settlement_dataset.artifact.source_manifest_references), key=lambda item: str(item[0]))
        ),
        "horizon": horizon,
        "decision_time": operation_package.command.decision_time,
        "next_session_date": next_session_date,
        "decision_reference_price": reference,
        "next_open": next_open,
        "next_1030_price": price_1030,
        "morning_high": high,
        "morning_low": low,
        "session_close": close,
        "gross_return": ((price_1030 - reference) / reference if complete and price_1030 is not None else None),
        "mfe": ((high - reference) / reference if complete and high is not None else None),
        "mae": ((low - reference) / reference if complete and low is not None else None),
        "suspended": suspended,
        "price_limit_observations": limits,
        "availability_time": availability,
        "completeness": completeness,
        "feasibility_observations": tuple(sorted(feasibility)),
        "reason_codes": tuple(sorted(reasons)),
        "limitations": ("FACTUAL_OBSERVATION_ONLY", "NOT_A_FORMAL_H9_LABEL"),
    }
    digest = canonical_hash(_outcome_payload(**values))
    return TradeHorizonOutcomeObservation(
        schema_version=TRADE_HORIZON_OUTCOME_SCHEMA,
        observation_id=ArtifactId(f"trade-horizon-outcome-{digest.split(':', 1)[1][:24]}"),
        content_hash=digest,
        **values,
    )


def publish_trade_horizon_outcome_evidence(
    *, root: Path, artifact: TradeHorizonOutcomeEvidence
) -> Path:
    artifact.verify_identity()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / str(artifact.artifact_id)
    if destination.exists():
        if load_trade_horizon_outcome_evidence(destination) != artifact:
            raise ValueError("Outcome evidence identity conflict")
        return destination
    staging = Path(tempfile.mkdtemp(prefix=f".{artifact.artifact_id}.", dir=root))
    try:
        _write_json(staging / "artifact.json", artifact.to_canonical_dict())
        _write_json(staging / "SHA256SUMS.json", {"artifact.json": _file_hash(staging / "artifact.json")})
        _write_json(staging / "manifest.json", {
            "schema_version": TRADE_HORIZON_OUTCOME_PACKAGE_SCHEMA,
            "artifact_id": str(artifact.artifact_id),
            "content_hash": artifact.content_hash,
            "exact_file_set": list(TRADE_HORIZON_OUTCOME_PACKAGE_FILES),
            "checksums_sha256": _file_hash(staging / "SHA256SUMS.json"),
        })
        _fsync_directory(staging)
        staging.rename(destination)
        _fsync_directory(root)
    except FileExistsError:
        shutil.rmtree(staging, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if load_trade_horizon_outcome_evidence(destination) != artifact:
        raise ValueError("published Outcome evidence semantic mismatch")
    return destination


def load_trade_horizon_outcome_evidence(path: Path) -> TradeHorizonOutcomeEvidence:
    actual = {item.name for item in path.iterdir() if item.is_file()}
    if actual != set(TRADE_HORIZON_OUTCOME_PACKAGE_FILES):
        raise ValueError("Outcome evidence exact file set mismatch")
    manifest = _read_json(path / "manifest.json")
    if (
        manifest.get("schema_version") != TRADE_HORIZON_OUTCOME_PACKAGE_SCHEMA
        or manifest.get("exact_file_set") != list(TRADE_HORIZON_OUTCOME_PACKAGE_FILES)
        or manifest.get("checksums_sha256") != _file_hash(path / "SHA256SUMS.json")
    ):
        raise ValueError("Outcome evidence manifest mismatch")
    checksums = _read_json(path / "SHA256SUMS.json")
    if checksums != {"artifact.json": _file_hash(path / "artifact.json")}:
        raise ValueError("Outcome evidence checksum mismatch")
    artifact = TradeHorizonOutcomeEvidence.from_canonical_dict(_read_json(path / "artifact.json"))
    if manifest.get("artifact_id") != str(artifact.artifact_id) or manifest.get("content_hash") != artifact.content_hash:
        raise ValueError("Outcome evidence manifest identity mismatch")
    return artifact


def replay_trade_horizon_outcome_evidence(path: Path) -> TradeHorizonOutcomeEvidence:
    artifact = load_trade_horizon_outcome_evidence(path)
    replayed = TradeHorizonOutcomeEvidence.create(
        operation_package=_OperationPackageView(artifact.operation_package_id, artifact.operation_package_hash),
        source_dataset=_DatasetView(artifact.source_dataset_id, artifact.source_dataset_hash),
        observations=artifact.observations,
        horizon=artifact.horizon,
        created_at=artifact.created_at,
    )
    if replayed != artifact:
        raise ValueError("Outcome evidence replay divergence")
    return replayed


@dataclass(frozen=True)
class _OperationPackageView:
    package_id: ArtifactId
    content_hash: str


@dataclass(frozen=True)
class _DatasetArtifactView:
    dataset_id: ArtifactId
    content_hash: str


@dataclass(frozen=True)
class _DatasetView:
    dataset_id: ArtifactId
    content_hash: str

    @property
    def artifact(self) -> _DatasetArtifactView:
        return _DatasetArtifactView(self.dataset_id, self.content_hash)


def _horizon_values(item: TradeHorizonDefinition) -> dict[str, Any]:
    return {name: getattr(item, name) for name in ("timezone_name", "observation_time", "morning_start", "morning_end", "include_session_close", "limitations")}


def _horizon_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": TRADE_HORIZON_DEFINITION_SCHEMA,
        "timezone_name": values["timezone_name"],
        "observation_time": values["observation_time"].isoformat(),
        "morning_start": values["morning_start"].isoformat(),
        "morning_end": values["morning_end"].isoformat(),
        "include_session_close": values["include_session_close"],
        "limitations": list(values["limitations"]),
    }


def _outcome_values(item: TradeHorizonOutcomeObservation) -> dict[str, Any]:
    return {name: getattr(item, name) for name in _outcome_value_names()}


def _outcome_value_names() -> tuple[str, ...]:
    return (
        "symbol", "candidate_set_id", "candidate_set_hash", "signal_snapshot_id",
        "signal_snapshot_hash", "path_forecast_id", "path_forecast_hash",
        "operation_package_id", "operation_package_hash", "source_dataset_id",
        "source_dataset_hash", "source_artifact_references", "horizon", "decision_time",
        "next_session_date", "decision_reference_price", "next_open", "next_1030_price",
        "morning_high", "morning_low", "session_close", "gross_return", "mfe", "mae",
        "suspended", "price_limit_observations", "availability_time", "completeness",
        "feasibility_observations", "reason_codes", "limitations",
    )


def _outcome_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": TRADE_HORIZON_OUTCOME_SCHEMA,
        **{
            name: str(values[name])
            for name in (
                "candidate_set_id", "signal_snapshot_id", "path_forecast_id",
                "operation_package_id", "source_dataset_id",
            )
        },
        "symbol": values["symbol"],
        "candidate_set_hash": values["candidate_set_hash"],
        "signal_snapshot_hash": values["signal_snapshot_hash"],
        "path_forecast_hash": values["path_forecast_hash"],
        "operation_package_hash": values["operation_package_hash"],
        "source_dataset_hash": values["source_dataset_hash"],
        "source_artifact_references": [
            {"artifact_id": str(item), "content_hash": digest}
            for item, digest in values["source_artifact_references"]
        ],
        "horizon": values["horizon"].to_canonical_dict(),
        "decision_time": canonical_datetime(values["decision_time"]),
        "next_session_date": values["next_session_date"].isoformat(),
        **{
            name: canonical_decimal(values[name]) if values[name] is not None else None
            for name in (
                "decision_reference_price", "next_open", "next_1030_price",
                "morning_high", "morning_low", "session_close", "gross_return", "mfe", "mae",
            )
        },
        "suspended": values["suspended"],
        "price_limit_observations": list(values["price_limit_observations"]),
        "availability_time": canonical_datetime(values["availability_time"]) if values["availability_time"] is not None else None,
        "completeness": values["completeness"].value,
        "feasibility_observations": list(values["feasibility_observations"]),
        "reason_codes": list(values["reason_codes"]),
        "limitations": list(values["limitations"]),
    }


def _outcome_payload_keys() -> set[str]:
    return {
        "schema_version", *_outcome_value_names(),
    } - {"source_artifact_references", "horizon"} | {"source_artifact_references", "horizon"}


def _evidence_values(item: TradeHorizonOutcomeEvidence) -> dict[str, Any]:
    return {name: getattr(item, name) for name in ("operation_package_id", "operation_package_hash", "source_dataset_id", "source_dataset_hash", "horizon", "observations", "created_at", "limitations")}


def _evidence_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": TRADE_HORIZON_OUTCOME_PACKAGE_SCHEMA,
        "operation_package_id": str(values["operation_package_id"]),
        "operation_package_hash": values["operation_package_hash"],
        "source_dataset_id": str(values["source_dataset_id"]),
        "source_dataset_hash": values["source_dataset_hash"],
        "horizon": values["horizon"].to_canonical_dict(),
        "observations": [item.to_canonical_dict() for item in values["observations"]],
        "created_at": canonical_datetime(values["created_at"]),
        "limitations": list(values["limitations"]),
    }


def _evidence_payload_keys() -> set[str]:
    return {"schema_version", "operation_package_id", "operation_package_hash", "source_dataset_id", "source_dataset_hash", "horizon", "observations", "created_at", "limitations"}


def _decimal(value: object) -> Decimal:
    return parse_canonical_decimal("Outcome decimal", value)


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _decimal(value)


def _file_hash(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("Outcome evidence JSON must be an object")
    return payload


def _objects(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} must be an object array")
    return tuple(value)


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _fsync_directory(root: Path) -> None:
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "OutcomeCompleteness",
    "TradeHorizonDefinition",
    "TradeHorizonOutcomeEvidence",
    "TradeHorizonOutcomeObservation",
    "build_trade_horizon_outcome_evidence",
    "load_trade_horizon_outcome_evidence",
    "publish_trade_horizon_outcome_evidence",
    "replay_trade_horizon_outcome_evidence",
]
