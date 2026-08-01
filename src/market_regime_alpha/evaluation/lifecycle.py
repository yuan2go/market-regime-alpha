"""Closed-trade outcome, diagnostic attribution and rolling scorecards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any

from market_regime_alpha.core.identity import (
    ArtifactId,
    FillId,
    PositionSnapshotId,
    RollingScorecardId,
    ThesisId,
    TradeOutcomeId,
)
from market_regime_alpha.decision.opportunity import DecisionEvidenceReference
from market_regime_alpha.decision.thesis import TradingThesis
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.execution.manual import (
    ExecutionDeviation,
    Fill,
    FillKind,
    TradeSide,
)
from market_regime_alpha.position.authority import PositionSnapshot, PositionState


TRADE_EVALUATION_CONFIG_SCHEMA = "trade-evaluation-config-v1"
TRADE_OUTCOME_SCHEMA = "trade-outcome-v1"
ROLLING_SCORECARD_SCHEMA = "rolling-scorecard-v1"


class AttributionComponent(str, Enum):
    SELECTION = "SELECTION"
    ENTRY = "ENTRY"
    HOLDING = "HOLDING"
    EXIT = "EXIT"


class ScorecardStatus(str, Enum):
    AVAILABLE_FOR_REVIEW = "AVAILABLE_FOR_REVIEW"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class TradeEvaluationConfig:
    profile_id: str
    configuration_id: ArtifactId
    configuration_hash: str
    rolling_window_size: int
    minimum_sample_count: int
    capture_denominator_floor: float
    schema_version: str

    def __post_init__(self) -> None:
        if self.schema_version != TRADE_EVALUATION_CONFIG_SCHEMA:
            raise ValueError("unsupported TradeEvaluationConfig schema")
        _text("profile_id", self.profile_id)
        if self.rolling_window_size <= 0 or not (
            0 < self.minimum_sample_count <= self.rolling_window_size
        ):
            raise ValueError("evaluation rolling sample configuration is invalid")
        if (
            not isfinite(self.capture_denominator_floor)
            or self.capture_denominator_floor <= 0.0
        ):
            raise ValueError("capture denominator floor must be positive")
        require_sha256("configuration_hash", self.configuration_hash)
        if canonical_hash(self.semantic_payload()) != self.configuration_hash:
            raise ValueError("TradeEvaluationConfig hash mismatch")
        digest = self.configuration_hash.split(":", 1)[1]
        if self.configuration_id != ArtifactId(
            f"trade-evaluation-config-{digest[:24]}"
        ):
            raise ValueError("TradeEvaluationConfig identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "rolling_window_size": self.rolling_window_size,
            "minimum_sample_count": self.minimum_sample_count,
            "capture_denominator_floor": self.capture_denominator_floor,
            "schema_version": self.schema_version,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
        }

    @classmethod
    def create(
        cls,
        *,
        profile_id: str,
        rolling_window_size: int,
        minimum_sample_count: int,
        capture_denominator_floor: float,
        schema_version: str,
    ) -> TradeEvaluationConfig:
        semantic = {
            "profile_id": profile_id,
            "rolling_window_size": rolling_window_size,
            "minimum_sample_count": minimum_sample_count,
            "capture_denominator_floor": capture_denominator_floor,
            "schema_version": schema_version,
        }
        digest = canonical_hash(semantic)
        return cls(
            profile_id=profile_id,
            configuration_id=ArtifactId(
                f"trade-evaluation-config-{digest.split(':', 1)[1][:24]}"
            ),
            configuration_hash=digest,
            rolling_window_size=rolling_window_size,
            minimum_sample_count=minimum_sample_count,
            capture_denominator_floor=capture_denominator_floor,
            schema_version=schema_version,
        )

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> TradeEvaluationConfig:
        expected = {
            "profile_id",
            "configuration_id",
            "configuration_hash",
            "rolling_window_size",
            "minimum_sample_count",
            "capture_denominator_floor",
            "schema_version",
        }
        if set(payload) != expected:
            raise ValueError("TradeEvaluationConfig fields mismatch")
        return cls(
            profile_id=str(payload["profile_id"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            rolling_window_size=int(payload["rolling_window_size"]),
            minimum_sample_count=int(payload["minimum_sample_count"]),
            capture_denominator_floor=float(
                payload["capture_denominator_floor"]
            ),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class TradePathObservation:
    symbol: str
    path_started_at: datetime
    path_ended_at: datetime
    availability_time: datetime
    maximum_price: float
    minimum_price: float
    entry_reference_price: float
    entry_fill_ids: tuple[FillId, ...]
    evidence: DecisionEvidenceReference

    def __post_init__(self) -> None:
        _text("symbol", self.symbol)
        for timestamp in (
            self.path_started_at,
            self.path_ended_at,
            self.availability_time,
        ):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("trade path times must be timezone-aware")
        if not self.path_started_at < self.path_ended_at <= self.availability_time:
            raise ValueError("trade path temporal order is invalid")
        values = (
            self.maximum_price,
            self.minimum_price,
            self.entry_reference_price,
        )
        if any(not isfinite(value) or value <= 0.0 for value in values):
            raise ValueError("trade path prices must be positive and finite")
        if self.minimum_price > self.maximum_price:
            raise ValueError("trade path price range is invalid")
        if self.entry_fill_ids != tuple(sorted(set(self.entry_fill_ids), key=str)):
            raise ValueError("entry Fill IDs must be sorted and unique")
        if self.evidence.status not in {
            "AVAILABLE_FOR_RESEARCH",
            "RESEARCH_READY",
            "VERIFIED_EXPLORATORY",
        }:
            raise ValueError("TradePathObservation requires verified evidence")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "path_started_at": self.path_started_at.isoformat(),
            "path_ended_at": self.path_ended_at.isoformat(),
            "availability_time": self.availability_time.isoformat(),
            "maximum_price": self.maximum_price,
            "minimum_price": self.minimum_price,
            "entry_reference_price": self.entry_reference_price,
            "entry_fill_ids": [str(item) for item in self.entry_fill_ids],
            "evidence": self.evidence.to_canonical_dict(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> TradePathObservation:
        expected = {
            "symbol",
            "path_started_at",
            "path_ended_at",
            "availability_time",
            "maximum_price",
            "minimum_price",
            "entry_reference_price",
            "entry_fill_ids",
            "evidence",
        }
        if set(payload) != expected:
            raise ValueError("TradePathObservation fields mismatch")
        fill_ids = payload["entry_fill_ids"]
        evidence = payload["evidence"]
        if not isinstance(fill_ids, list) or not isinstance(evidence, dict):
            raise ValueError("TradePathObservation value type mismatch")
        return cls(
            symbol=str(payload["symbol"]),
            path_started_at=datetime.fromisoformat(str(payload["path_started_at"])),
            path_ended_at=datetime.fromisoformat(str(payload["path_ended_at"])),
            availability_time=datetime.fromisoformat(
                str(payload["availability_time"])
            ),
            maximum_price=float(payload["maximum_price"]),
            minimum_price=float(payload["minimum_price"]),
            entry_reference_price=float(payload["entry_reference_price"]),
            entry_fill_ids=tuple(FillId(str(item)) for item in fill_ids),
            evidence=DecisionEvidenceReference.from_canonical_dict(evidence),
        )


@dataclass(frozen=True, slots=True)
class AttributionRecord:
    component: AttributionComponent
    metric_name: str
    metric_value: float | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _text("metric_name", self.metric_name)
        if self.metric_value is not None and not isfinite(self.metric_value):
            raise ValueError("attribution metric must be finite")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("attribution reason codes must be sorted and unique")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "component": self.component.value,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> AttributionRecord:
        expected = {"component", "metric_name", "metric_value", "reason_codes"}
        reasons = payload.get("reason_codes")
        if set(payload) != expected or not isinstance(reasons, list):
            raise ValueError("AttributionRecord fields mismatch")
        value = payload["metric_value"]
        return cls(
            component=AttributionComponent(str(payload["component"])),
            metric_name=str(payload["metric_name"]),
            metric_value=float(value) if value is not None else None,
            reason_codes=tuple(str(item) for item in reasons),
        )


@dataclass(frozen=True, slots=True)
class TradeOutcome:
    schema_version: str
    outcome_id: TradeOutcomeId
    thesis_id: ThesisId
    thesis_version: int
    symbol: str
    final_position_snapshot_id: PositionSnapshotId
    final_position_version: int
    source_fill_ids: tuple[FillId, ...]
    entry_vwap: float
    exit_vwap: float
    realized_pnl: float
    realized_return: float
    mfe: float
    mae: float
    capture_ratio: float | None
    execution_deviations: tuple[ExecutionDeviation, ...]
    attributions: tuple[AttributionRecord, ...]
    path_evidence: DecisionEvidenceReference
    configuration_id: ArtifactId
    configuration_hash: str
    closed_at: datetime
    evaluated_at: datetime
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != TRADE_OUTCOME_SCHEMA:
            raise ValueError("unsupported TradeOutcome schema")
        require_sha256("configuration_hash", self.configuration_hash)
        values = (
            self.entry_vwap,
            self.exit_vwap,
            self.realized_pnl,
            self.realized_return,
            self.mfe,
            self.mae,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("TradeOutcome metrics must be finite")
        if self.entry_vwap <= 0.0 or self.exit_vwap <= 0.0:
            raise ValueError("TradeOutcome prices must be positive")
        if self.mfe < 0.0 or self.mae > 0.0:
            raise ValueError("TradeOutcome MFE/MAE signs are invalid")
        if self.capture_ratio is not None and not isfinite(self.capture_ratio):
            raise ValueError("capture ratio must be finite")
        if self.source_fill_ids != tuple(sorted(set(self.source_fill_ids), key=str)):
            raise ValueError("TradeOutcome Fill IDs must be sorted and unique")
        components = tuple(item.component for item in self.attributions)
        if components != tuple(AttributionComponent):
            raise ValueError("TradeOutcome requires ordered four-part attribution")
        if self.closed_at > self.evaluated_at:
            raise ValueError("TradeOutcome cannot be evaluated before close")
        expected = _outcome_id(self.semantic_payload())
        if self.outcome_id != expected:
            raise ValueError("TradeOutcome content identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "thesis_id": str(self.thesis_id),
            "thesis_version": self.thesis_version,
            "symbol": self.symbol,
            "final_position_snapshot_id": str(self.final_position_snapshot_id),
            "final_position_version": self.final_position_version,
            "source_fill_ids": [str(item) for item in self.source_fill_ids],
            "entry_vwap": self.entry_vwap,
            "exit_vwap": self.exit_vwap,
            "realized_pnl": self.realized_pnl,
            "realized_return": self.realized_return,
            "mfe": self.mfe,
            "mae": self.mae,
            "capture_ratio": self.capture_ratio,
            "execution_deviations": [
                item.to_canonical_dict() for item in self.execution_deviations
            ],
            "attributions": [item.to_canonical_dict() for item in self.attributions],
            "path_evidence": self.path_evidence.to_canonical_dict(),
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            "closed_at": self.closed_at.isoformat(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"outcome_id": str(self.outcome_id), **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> TradeOutcome:
        expected = {
            "outcome_id",
            "schema_version",
            "thesis_id",
            "thesis_version",
            "symbol",
            "final_position_snapshot_id",
            "final_position_version",
            "source_fill_ids",
            "entry_vwap",
            "exit_vwap",
            "realized_pnl",
            "realized_return",
            "mfe",
            "mae",
            "capture_ratio",
            "execution_deviations",
            "attributions",
            "path_evidence",
            "configuration_id",
            "configuration_hash",
            "closed_at",
            "evaluated_at",
            "reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("TradeOutcome fields mismatch")
        source_ids = _array(payload["source_fill_ids"])
        deviations = _array(payload["execution_deviations"])
        attributions = _array(payload["attributions"])
        evidence = _object(payload["path_evidence"])
        reasons = _array(payload["reason_codes"])
        capture = payload["capture_ratio"]
        return cls(
            schema_version=str(payload["schema_version"]),
            outcome_id=TradeOutcomeId(str(payload["outcome_id"])),
            thesis_id=ThesisId(str(payload["thesis_id"])),
            thesis_version=int(payload["thesis_version"]),
            symbol=str(payload["symbol"]),
            final_position_snapshot_id=PositionSnapshotId(
                str(payload["final_position_snapshot_id"])
            ),
            final_position_version=int(payload["final_position_version"]),
            source_fill_ids=tuple(FillId(str(item)) for item in source_ids),
            entry_vwap=float(payload["entry_vwap"]),
            exit_vwap=float(payload["exit_vwap"]),
            realized_pnl=float(payload["realized_pnl"]),
            realized_return=float(payload["realized_return"]),
            mfe=float(payload["mfe"]),
            mae=float(payload["mae"]),
            capture_ratio=float(capture) if capture is not None else None,
            execution_deviations=tuple(
                ExecutionDeviation.from_canonical_dict(_object(item))
                for item in deviations
            ),
            attributions=tuple(
                AttributionRecord.from_canonical_dict(_object(item))
                for item in attributions
            ),
            path_evidence=DecisionEvidenceReference.from_canonical_dict(evidence),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            closed_at=datetime.fromisoformat(str(payload["closed_at"])),
            evaluated_at=datetime.fromisoformat(str(payload["evaluated_at"])),
            reason_codes=tuple(str(item) for item in reasons),
        )


@dataclass(frozen=True, slots=True)
class RollingScorecard:
    schema_version: str
    scorecard_id: RollingScorecardId
    configuration_id: ArtifactId
    configuration_hash: str
    status: ScorecardStatus
    outcome_ids: tuple[TradeOutcomeId, ...]
    sample_count: int
    mean_realized_return: float | None
    mean_mfe: float | None
    mean_mae: float | None
    mean_capture_ratio: float | None
    evaluated_at: datetime
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != ROLLING_SCORECARD_SCHEMA:
            raise ValueError("unsupported RollingScorecard schema")
        require_sha256("configuration_hash", self.configuration_hash)
        if self.sample_count != len(self.outcome_ids):
            raise ValueError("RollingScorecard sample count mismatch")
        metrics = (
            self.mean_realized_return,
            self.mean_mfe,
            self.mean_mae,
            self.mean_capture_ratio,
        )
        if any(value is not None and not isfinite(value) for value in metrics):
            raise ValueError("RollingScorecard metrics must be finite")
        if self.status is ScorecardStatus.DATA_INSUFFICIENT and any(
            value is not None for value in metrics
        ):
            raise ValueError("insufficient scorecard cannot publish aggregate metrics")
        expected = _scorecard_id(self.semantic_payload())
        if self.scorecard_id != expected:
            raise ValueError("RollingScorecard content identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            "status": self.status.value,
            "outcome_ids": [str(item) for item in self.outcome_ids],
            "sample_count": self.sample_count,
            "mean_realized_return": self.mean_realized_return,
            "mean_mfe": self.mean_mfe,
            "mean_mae": self.mean_mae,
            "mean_capture_ratio": self.mean_capture_ratio,
            "evaluated_at": self.evaluated_at.isoformat(),
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"scorecard_id": str(self.scorecard_id), **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> RollingScorecard:
        expected = {
            "scorecard_id",
            "schema_version",
            "configuration_id",
            "configuration_hash",
            "status",
            "outcome_ids",
            "sample_count",
            "mean_realized_return",
            "mean_mfe",
            "mean_mae",
            "mean_capture_ratio",
            "evaluated_at",
            "reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("RollingScorecard fields mismatch")
        outcome_ids = _array(payload["outcome_ids"])
        reasons = _array(payload["reason_codes"])
        return cls(
            schema_version=str(payload["schema_version"]),
            scorecard_id=RollingScorecardId(str(payload["scorecard_id"])),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            status=ScorecardStatus(str(payload["status"])),
            outcome_ids=tuple(TradeOutcomeId(str(item)) for item in outcome_ids),
            sample_count=int(payload["sample_count"]),
            mean_realized_return=_optional_float(payload["mean_realized_return"]),
            mean_mfe=_optional_float(payload["mean_mfe"]),
            mean_mae=_optional_float(payload["mean_mae"]),
            mean_capture_ratio=_optional_float(payload["mean_capture_ratio"]),
            evaluated_at=datetime.fromisoformat(str(payload["evaluated_at"])),
            reason_codes=tuple(str(item) for item in reasons),
        )


class TradeOutcomeEvaluator:
    def evaluate(
        self,
        *,
        thesis: TradingThesis,
        final_position: PositionSnapshot,
        fills: tuple[Fill, ...],
        path: TradePathObservation,
        execution_deviations: tuple[ExecutionDeviation, ...],
        configuration: TradeEvaluationConfig,
        evaluated_at: datetime,
    ) -> TradeOutcome:
        if final_position.state is not PositionState.CLOSED:
            raise ValueError("TradeOutcome requires a closed authoritative Position")
        if thesis.symbol != final_position.symbol or path.symbol != thesis.symbol:
            raise ValueError("TradeOutcome symbol scope mismatch")
        ordered = tuple(sorted(fills, key=lambda item: (item.recorded_at, str(item.fill_id))))
        if tuple(item.fill_id for item in ordered) != final_position.source_fill_ids:
            raise ValueError("TradeOutcome Fill ledger differs from Position authority")
        if path.availability_time > evaluated_at:
            raise ValueError("TradeOutcome cannot consume unavailable path evidence")
        effective = _effective_fills(ordered)
        buys = tuple(item for item in effective if item.side is TradeSide.BUY)
        sells = tuple(item for item in effective if item.side is TradeSide.SELL)
        buy_quantity = sum(item.quantity for item in buys)
        sell_quantity = sum(item.quantity for item in sells)
        if not buys or not sells or buy_quantity != sell_quantity:
            raise ValueError("closed long-only TradeOutcome requires balanced buy/sell Fills")
        entry_ids = tuple(sorted((item.fill_id for item in buys), key=str))
        if entry_ids != path.entry_fill_ids:
            raise ValueError("trade path entry evidence does not bind effective entry Fills")
        entry_vwap = sum(item.price * item.quantity for item in buys) / buy_quantity
        exit_vwap = sum(item.price * item.quantity for item in sells) / sell_quantity
        if (
            path.path_started_at > min(item.occurred_at for item in buys)
            or path.path_ended_at < max(item.occurred_at for item in sells)
        ):
            raise ValueError("trade path does not cover authoritative entry and exit Fills")
        if abs(entry_vwap - path.entry_reference_price) > 1e-12:
            raise ValueError("trade path entry price differs from authoritative Fill VWAP")
        entry_capital = sum(
            item.price * item.quantity + item.fees for item in buys
        )
        realized_return = final_position.realized_pnl / entry_capital
        mfe = max(0.0, path.maximum_price / entry_vwap - 1.0)
        mae = min(0.0, path.minimum_price / entry_vwap - 1.0)
        capture = (
            realized_return / mfe
            if mfe >= configuration.capture_denominator_floor
            else None
        )
        deviations = tuple(
            sorted(execution_deviations, key=lambda item: str(item.manual_trade_id))
        )
        entry_deviation = _entry_deviation(deviations, buys)
        attributions = (
            AttributionRecord(
                AttributionComponent.SELECTION,
                "realized_return",
                realized_return,
                ("DIAGNOSTIC_NOT_CAUSAL_ATTRIBUTION",),
            ),
            AttributionRecord(
                AttributionComponent.ENTRY,
                "entry_price_deviation_return",
                entry_deviation,
                ("MANUAL_EXECUTION_DEVIATION",),
            ),
            AttributionRecord(
                AttributionComponent.HOLDING,
                "mfe_capture_ratio",
                capture,
                (
                    "CAPTURE_DENOMINATOR_INSUFFICIENT"
                    if capture is None
                    else "PATH_CAPTURE_DIAGNOSTIC"
                ,),
            ),
            AttributionRecord(
                AttributionComponent.EXIT,
                "return_giveback_from_mfe",
                realized_return - mfe,
                ("PATH_GIVEBACK_DIAGNOSTIC",),
            ),
        )
        reason_codes = (
            ("CLOSED_TRADE_REBUILT_FROM_FILLS", "CAPTURE_RATIO_AVAILABLE")
            if capture is not None
            else (
                "CAPTURE_DENOMINATOR_INSUFFICIENT",
                "CLOSED_TRADE_REBUILT_FROM_FILLS",
            )
        )
        semantic = {
            "schema_version": TRADE_OUTCOME_SCHEMA,
            "thesis_id": str(thesis.thesis_id),
            "thesis_version": thesis.version,
            "symbol": thesis.symbol,
            "final_position_snapshot_id": str(final_position.snapshot_id),
            "final_position_version": final_position.version,
            "source_fill_ids": [str(item.fill_id) for item in sorted(effective, key=lambda item: str(item.fill_id))],
            "entry_vwap": entry_vwap,
            "exit_vwap": exit_vwap,
            "realized_pnl": final_position.realized_pnl,
            "realized_return": realized_return,
            "mfe": mfe,
            "mae": mae,
            "capture_ratio": capture,
            "execution_deviations": [item.to_canonical_dict() for item in deviations],
            "attributions": [item.to_canonical_dict() for item in attributions],
            "path_evidence": path.evidence.to_canonical_dict(),
            "configuration_id": str(configuration.configuration_id),
            "configuration_hash": configuration.configuration_hash,
            "closed_at": path.path_ended_at.isoformat(),
            "evaluated_at": evaluated_at.isoformat(),
            "reason_codes": list(reason_codes),
        }
        return TradeOutcome(
            schema_version=TRADE_OUTCOME_SCHEMA,
            outcome_id=_outcome_id(semantic),
            thesis_id=thesis.thesis_id,
            thesis_version=thesis.version,
            symbol=thesis.symbol,
            final_position_snapshot_id=final_position.snapshot_id,
            final_position_version=final_position.version,
            source_fill_ids=tuple(
                sorted((item.fill_id for item in effective), key=str)
            ),
            entry_vwap=entry_vwap,
            exit_vwap=exit_vwap,
            realized_pnl=final_position.realized_pnl,
            realized_return=realized_return,
            mfe=mfe,
            mae=mae,
            capture_ratio=capture,
            execution_deviations=deviations,
            attributions=attributions,
            path_evidence=path.evidence,
            configuration_id=configuration.configuration_id,
            configuration_hash=configuration.configuration_hash,
            closed_at=path.path_ended_at,
            evaluated_at=evaluated_at,
            reason_codes=reason_codes,
        )


class RollingScorecardBuilder:
    """Pure diagnostic aggregation; deliberately has no Model Registry access."""

    def build(
        self,
        outcomes: tuple[TradeOutcome, ...],
        configuration: TradeEvaluationConfig,
        *,
        evaluated_at: datetime,
    ) -> RollingScorecard:
        ordered = tuple(
            sorted(outcomes, key=lambda item: (item.closed_at, str(item.outcome_id)))
        )[-configuration.rolling_window_size :]
        if len({item.outcome_id for item in ordered}) != len(ordered):
            raise ValueError("RollingScorecard cannot consume duplicate outcomes")
        if any(
            item.configuration_id != configuration.configuration_id
            or item.configuration_hash != configuration.configuration_hash
            for item in ordered
        ):
            raise ValueError("RollingScorecard outcomes use a different protocol")
        outcome_ids = tuple(item.outcome_id for item in ordered)
        sufficient = len(ordered) >= configuration.minimum_sample_count
        captures = tuple(
            item.capture_ratio for item in ordered if item.capture_ratio is not None
        )
        status = (
            ScorecardStatus.AVAILABLE_FOR_REVIEW
            if sufficient
            else ScorecardStatus.DATA_INSUFFICIENT
        )
        means: tuple[float | None, float | None, float | None, float | None]
        if sufficient:
            means = (
                _mean(tuple(item.realized_return for item in ordered)),
                _mean(tuple(item.mfe for item in ordered)),
                _mean(tuple(item.mae for item in ordered)),
                _mean(captures) if captures else None,
            )
            reasons = ("ROLLING_SCORECARD_AVAILABLE_FOR_REVIEW",)
        else:
            means = (None, None, None, None)
            reasons = ("MINIMUM_SCORECARD_SAMPLE_NOT_MET",)
        semantic = {
            "schema_version": ROLLING_SCORECARD_SCHEMA,
            "configuration_id": str(configuration.configuration_id),
            "configuration_hash": configuration.configuration_hash,
            "status": status.value,
            "outcome_ids": [str(item) for item in outcome_ids],
            "sample_count": len(ordered),
            "mean_realized_return": means[0],
            "mean_mfe": means[1],
            "mean_mae": means[2],
            "mean_capture_ratio": means[3],
            "evaluated_at": evaluated_at.isoformat(),
            "reason_codes": list(reasons),
        }
        return RollingScorecard(
            schema_version=ROLLING_SCORECARD_SCHEMA,
            scorecard_id=_scorecard_id(semantic),
            configuration_id=configuration.configuration_id,
            configuration_hash=configuration.configuration_hash,
            status=status,
            outcome_ids=outcome_ids,
            sample_count=len(ordered),
            mean_realized_return=means[0],
            mean_mfe=means[1],
            mean_mae=means[2],
            mean_capture_ratio=means[3],
            evaluated_at=evaluated_at,
            reason_codes=reasons,
        )


def _effective_fills(fills: tuple[Fill, ...]) -> tuple[Fill, ...]:
    executions = {
        item.fill_id: item for item in fills if item.fill_kind is FillKind.EXECUTION
    }
    corrections: dict[FillId, Fill] = {}
    for item in fills:
        if item.fill_kind is FillKind.CORRECTION:
            assert item.correction_of_fill_id is not None
            if item.correction_of_fill_id not in executions:
                raise ValueError("TradeOutcome correction references unknown Fill")
            if item.correction_of_fill_id in corrections:
                raise ValueError("TradeOutcome Fill has multiple corrections")
            corrections[item.correction_of_fill_id] = item
    return tuple(
        corrections.get(fill_id, fill) for fill_id, fill in executions.items()
    )


def _entry_deviation(
    deviations: tuple[ExecutionDeviation, ...], buys: tuple[Fill, ...]
) -> float | None:
    buy_trade_ids = {item.manual_trade_id for item in buys}
    selected = tuple(
        item for item in deviations if item.manual_trade_id in buy_trade_ids
    )
    priced = tuple(
        item
        for item in selected
        if item.price_deviation is not None and item.volume_weighted_price is not None
    )
    if not priced:
        return None
    return -_mean(
        tuple(
            (item.price_deviation or 0.0) / item.expected_mid_price
            for item in priced
        )
    )


def _mean(values: tuple[float, ...]) -> float:
    if not values:
        raise ValueError("mean requires values")
    return sum(values) / len(values)


def _outcome_id(payload: dict[str, Any]) -> TradeOutcomeId:
    digest = canonical_hash(payload).split(":", 1)[1]
    return TradeOutcomeId(f"trade-outcome-{digest[:24]}")


def _scorecard_id(payload: dict[str, Any]) -> RollingScorecardId:
    digest = canonical_hash(payload).split(":", 1)[1]
    return RollingScorecardId(f"rolling-scorecard-{digest[:24]}")


def _text(label: str, value: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("evaluation value must be an array")
    return value


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("evaluation value must be an object")
    return value


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None
