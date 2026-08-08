"""Contracts for recoverable Feature Materialization runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from market_regime_alpha.features.v2_contracts import FeatureMaterializationReceipt
from market_regime_alpha.market_data import Timeframe


DEFAULT_FEATURE_TASK_LEASE = timedelta(minutes=5)


class FeatureMaterializationExecutionMode(str, Enum):
    START_NEW = "START_NEW"
    RESUME_EXISTING = "RESUME_EXISTING"
    RETURN_IF_COMPLETE = "RETURN_IF_COMPLETE"


class FeatureMaterializationRunStatus(str, Enum):
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    COMPLETE = "COMPLETE"


class FeatureMaterializationTaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True, slots=True)
class FeatureMaterializationTaskSpec:
    symbol: str
    feature_id: str
    timeframe: Timeframe

    @property
    def task_key(self) -> str:
        return f"{self.symbol}|{self.feature_id}|{self.timeframe.value}"


@dataclass(frozen=True, slots=True)
class ClaimedFeatureMaterializationTask:
    run_id: int
    task_key: str
    symbol: str
    feature_id: str
    timeframe: Timeframe
    claim_token: str
    claim_epoch: int
    task_version: int
    attempt_number: int
    lease_acquired_at: datetime
    lease_expires_at: datetime
    heartbeat_at: datetime


@dataclass(frozen=True, slots=True)
class FeatureMaterializationRunSnapshot:
    run_id: int
    idempotency_key: str
    command_hash: str
    status: FeatureMaterializationRunStatus
    version: int
    tasks: tuple[
        tuple[str, FeatureMaterializationTaskStatus, str | None, str | None], ...
    ]
    receipt: FeatureMaterializationReceipt | None
    events: tuple[tuple[int, str, str | None, str], ...]


__all__ = [
    "ClaimedFeatureMaterializationTask",
    "DEFAULT_FEATURE_TASK_LEASE",
    "FeatureMaterializationExecutionMode",
    "FeatureMaterializationRunSnapshot",
    "FeatureMaterializationRunStatus",
    "FeatureMaterializationTaskSpec",
    "FeatureMaterializationTaskStatus",
]
