"""Strategy-scoped path outcome measures over frozen market observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)


class BarrierOrderingOutcome(str, Enum):
    TARGET_BEFORE_STOP = "TARGET_BEFORE_STOP"
    STOP_BEFORE_TARGET = "STOP_BEFORE_TARGET"
    NEITHER = "NEITHER"
    NOT_OBSERVABLE = "NOT_OBSERVABLE"


@dataclass(frozen=True, slots=True)
class PathPriceObservation:
    observed_at: datetime
    session_offset: int
    high: Decimal
    low: Decimal
    close: Decimal

    def __post_init__(self) -> None:
        canonical_datetime(self.observed_at)
        if self.session_offset <= 0:
            raise ValueError("Path session offset must be positive")
        if min(self.high, self.low, self.close) <= 0:
            raise ValueError("Path prices must be positive")
        if not self.low <= self.close <= self.high:
            raise ValueError("Path close must lie inside high/low")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "observed_at": canonical_datetime(self.observed_at),
            "session_offset": self.session_offset,
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
        }


@dataclass(frozen=True, slots=True)
class StrategyPathOutcome:
    outcome_id: ArtifactId
    outcome_hash: str
    strategy_version_reference: RuntimeArtifactReference
    strategy_run_reference: RuntimeArtifactReference
    dataset_reference: RuntimeArtifactReference
    target_reference: RuntimeArtifactReference
    symbol: str
    decision_time: datetime
    horizon_sessions: int
    reference_price: Decimal
    terminal_return: Decimal
    mfe: Decimal
    mae: Decimal
    barrier_ordering: BarrierOrderingOutcome
    time_to_mfe_seconds: int
    trend_continuation: bool
    failure: bool
    exit_time: datetime | None
    exit_price: Decimal | None
    post_exit_opportunity_loss: Decimal | None
    avoided_drawdown: Decimal | None
    measured_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "strategy-path-outcome/v1"

    def __post_init__(self) -> None:
        require_sha256("outcome_hash", self.outcome_hash)
        require_text("symbol", self.symbol)
        canonical_datetime(self.decision_time)
        canonical_datetime(self.measured_at)
        if self.exit_time is not None:
            canonical_datetime(self.exit_time)
        if self.horizon_sessions <= 0 or self.reference_price <= 0:
            raise ValueError("Strategy Path Outcome horizon/reference is invalid")
        if self.mfe < 0 or self.mae > 0 or self.time_to_mfe_seconds < 0:
            raise ValueError("Strategy Path Outcome excursion semantics are invalid")
        if (self.exit_time is None) != (self.exit_price is None):
            raise ValueError("Strategy Path Outcome exit time/price must be paired")
        if (self.post_exit_opportunity_loss is None) != (self.avoided_drawdown is None):
            raise ValueError("Strategy Path Outcome post-exit measures must be paired")
        if self.limitations != tuple(sorted(set(self.limitations))) or not self.limitations:
            raise ValueError("Strategy Path Outcome limitations must be non-empty and sorted")
        digest = canonical_hash(self.identity_payload())
        if digest != self.outcome_hash or str(self.outcome_id) != f"strategy-path-outcome:{digest[7:]}":
            raise ValueError("Strategy Path Outcome identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _outcome_payload(
            strategy_version_reference=self.strategy_version_reference,
            strategy_run_reference=self.strategy_run_reference,
            dataset_reference=self.dataset_reference,
            target_reference=self.target_reference,
            symbol=self.symbol,
            decision_time=self.decision_time,
            horizon_sessions=self.horizon_sessions,
            reference_price=self.reference_price,
            terminal_return=self.terminal_return,
            mfe=self.mfe,
            mae=self.mae,
            barrier_ordering=self.barrier_ordering,
            time_to_mfe_seconds=self.time_to_mfe_seconds,
            trend_continuation=self.trend_continuation,
            failure=self.failure,
            exit_time=self.exit_time,
            exit_price=self.exit_price,
            post_exit_opportunity_loss=self.post_exit_opportunity_loss,
            avoided_drawdown=self.avoided_drawdown,
            measured_at=self.measured_at,
            limitations=self.limitations,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": str(self.outcome_id),
            "outcome_hash": self.outcome_hash,
            **self.identity_payload(),
        }


def measure_strategy_path(
    *,
    strategy_version_reference: RuntimeArtifactReference,
    strategy_run_reference: RuntimeArtifactReference,
    dataset_reference: RuntimeArtifactReference,
    target_reference: RuntimeArtifactReference,
    symbol: str,
    decision_time: datetime,
    reference_price: Decimal,
    target_return: Decimal,
    stop_return: Decimal,
    continuation_return: Decimal,
    failure_return: Decimal,
    observations: tuple[PathPriceObservation, ...],
    exit_time: datetime | None,
    exit_price: Decimal | None,
    measured_at: datetime,
) -> StrategyPathOutcome:
    require_text("symbol", symbol)
    canonical_datetime(decision_time)
    canonical_datetime(measured_at)
    if reference_price <= 0 or target_return <= 0 or stop_return <= 0:
        raise ValueError("Path reference and barrier returns must be positive")
    if not observations:
        raise ValueError("Path outcome requires observations")
    ordered = tuple(sorted(observations, key=lambda item: item.observed_at))
    times = tuple(item.observed_at for item in ordered)
    if ordered != observations or len(times) != len(set(times)):
        raise ValueError("Path observations must be unique and chronological")
    if ordered[0].observed_at <= decision_time or measured_at < ordered[-1].observed_at:
        raise ValueError("Path observations must follow Decision Time and precede measurement")
    if (exit_time is None) != (exit_price is None):
        raise ValueError("Path exit time/price must be paired")
    if exit_time is not None:
        canonical_datetime(exit_time)
        if exit_time <= decision_time or exit_price is None or exit_price <= 0:
            raise ValueError("Path exit semantics are invalid")

    mfe_point = max(ordered, key=lambda item: (item.high, -item.observed_at.timestamp()))
    mfe = mfe_point.high / reference_price - Decimal("1")
    mae = min(item.low for item in ordered) / reference_price - Decimal("1")
    terminal_return = ordered[-1].close / reference_price - Decimal("1")
    target_price = reference_price * (Decimal("1") + target_return)
    stop_price = reference_price * (Decimal("1") - stop_return)
    target_hits = tuple(item for item in ordered if item.high >= target_price)
    stop_hits = tuple(item for item in ordered if item.low <= stop_price)
    ordering = _barrier_ordering(target_hits, stop_hits)
    post_exit = (
        ()
        if exit_time is None
        else tuple(item for item in ordered if item.observed_at > exit_time)
    )
    opportunity_loss = None
    avoided_drawdown = None
    if exit_price is not None:
        opportunity_loss = (
            Decimal("0")
            if not post_exit
            else max(
                Decimal("0"),
                max(item.high for item in post_exit) / exit_price - Decimal("1"),
            )
        )
        avoided_drawdown = (
            Decimal("0")
            if not post_exit
            else max(
                Decimal("0"),
                Decimal("1") - min(item.low for item in post_exit) / exit_price,
            )
        )
    limitations = (
        "CALIBRATED_FALSE",
        "FORMAL_OOS_FALSE",
        "MARKET_OUTCOME_NOT_STRATEGY_PNL",
        "PIT_STATUS_INHERITED_FROM_DATASET",
        "PRODUCTION_AUTHORIZED_FALSE",
    )
    values = {
        "strategy_version_reference": strategy_version_reference,
        "strategy_run_reference": strategy_run_reference,
        "dataset_reference": dataset_reference,
        "target_reference": target_reference,
        "symbol": symbol,
        "decision_time": decision_time,
        "horizon_sessions": max(item.session_offset for item in ordered),
        "reference_price": reference_price,
        "terminal_return": terminal_return,
        "mfe": mfe,
        "mae": mae,
        "barrier_ordering": ordering,
        "time_to_mfe_seconds": int((mfe_point.observed_at - decision_time).total_seconds()),
        "trend_continuation": terminal_return >= continuation_return,
        "failure": ordering is BarrierOrderingOutcome.STOP_BEFORE_TARGET or terminal_return <= failure_return,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "post_exit_opportunity_loss": opportunity_loss,
        "avoided_drawdown": avoided_drawdown,
        "measured_at": measured_at,
        "limitations": limitations,
        "schema_version": "strategy-path-outcome/v1",
    }
    digest = canonical_hash(_outcome_payload(**values))
    return StrategyPathOutcome(
        outcome_id=ArtifactId(f"strategy-path-outcome:{digest[7:]}"),
        outcome_hash=digest,
        **values,
    )


def _barrier_ordering(
    target_hits: tuple[PathPriceObservation, ...],
    stop_hits: tuple[PathPriceObservation, ...],
) -> BarrierOrderingOutcome:
    if not target_hits and not stop_hits:
        return BarrierOrderingOutcome.NEITHER
    if not target_hits:
        return BarrierOrderingOutcome.STOP_BEFORE_TARGET
    if not stop_hits:
        return BarrierOrderingOutcome.TARGET_BEFORE_STOP
    if target_hits[0].observed_at == stop_hits[0].observed_at:
        return BarrierOrderingOutcome.NOT_OBSERVABLE
    return (
        BarrierOrderingOutcome.TARGET_BEFORE_STOP
        if target_hits[0].observed_at < stop_hits[0].observed_at
        else BarrierOrderingOutcome.STOP_BEFORE_TARGET
    )


def _outcome_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": values["schema_version"],
        "strategy_version_reference": values["strategy_version_reference"].to_canonical_dict(),
        "strategy_run_reference": values["strategy_run_reference"].to_canonical_dict(),
        "dataset_reference": values["dataset_reference"].to_canonical_dict(),
        "target_reference": values["target_reference"].to_canonical_dict(),
        "symbol": values["symbol"],
        "decision_time": canonical_datetime(values["decision_time"]),
        "horizon_sessions": values["horizon_sessions"],
        "reference_price": str(values["reference_price"]),
        "terminal_return": str(values["terminal_return"]),
        "mfe": str(values["mfe"]),
        "mae": str(values["mae"]),
        "barrier_ordering": values["barrier_ordering"].value,
        "time_to_mfe_seconds": values["time_to_mfe_seconds"],
        "trend_continuation": values["trend_continuation"],
        "failure": values["failure"],
        "exit_time": None if values["exit_time"] is None else canonical_datetime(values["exit_time"]),
        "exit_price": None if values["exit_price"] is None else str(values["exit_price"]),
        "post_exit_opportunity_loss": (
            None if values["post_exit_opportunity_loss"] is None else str(values["post_exit_opportunity_loss"])
        ),
        "avoided_drawdown": None if values["avoided_drawdown"] is None else str(values["avoided_drawdown"]),
        "measured_at": canonical_datetime(values["measured_at"]),
        "limitations": list(values["limitations"]),
    }


__all__ = [
    "BarrierOrderingOutcome",
    "PathPriceObservation",
    "StrategyPathOutcome",
    "measure_strategy_path",
]
