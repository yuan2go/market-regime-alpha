"""Versioned Trading Eligibility policy and exact-time historical materialization.

Trading Eligibility answers whether a PIT Universe member may enter the Candidate Population under
a declared policy. It is not final execution feasibility and does not infer order fillability from
price-limit metadata alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math

from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime
from market_regime_alpha.universe.artifacts import HistoricalPITUniverseArtifact
from market_regime_alpha.universe.contracts import TradingEligibilityStatus
from market_regime_alpha.universe.eligibility_artifacts import (
    HistoricalTradingEligibilityArtifact,
    HistoricalTradingEligibilityRecord,
    build_historical_trading_eligibility_artifact,
)


TRADING_ELIGIBILITY_MATERIALIZER_VERSION = "historical-trading-eligibility-materializer-v1"
EXPLICIT_RAW_ELIGIBILITY_AVAILABILITY_CONVENTION = "EXPLICIT_RAW_OBSERVATION_AVAILABLE_AT"


class TradingEligibilityReason(str, Enum):
    """Canonical reason codes emitted by the minimum versioned eligibility policy."""

    RAW_OBSERVATION_MISSING = "RAW_OBSERVATION_MISSING"
    RAW_OBSERVATION_NOT_AVAILABLE_BY_DECISION_TIME = "RAW_OBSERVATION_NOT_AVAILABLE_BY_DECISION_TIME"
    SUSPENDED = "SUSPENDED"
    ST_EXCLUDED = "ST_EXCLUDED"
    SUSPENSION_STATUS_MISSING = "SUSPENSION_STATUS_MISSING"
    ST_STATUS_MISSING = "ST_STATUS_MISSING"
    PREV_CLOSE_MISSING = "PREV_CLOSE_MISSING"
    LIMIT_UP_PRICE_MISSING = "LIMIT_UP_PRICE_MISSING"
    LIMIT_DOWN_PRICE_MISSING = "LIMIT_DOWN_PRICE_MISSING"
    LIMIT_REGIME_MISSING = "LIMIT_REGIME_MISSING"


@dataclass(frozen=True, slots=True)
class RawTradingEligibilityObservation:
    """Raw historical eligibility evidence at one exact information-state time.

    ``as_of`` is the state timestamp represented by the raw record. ``available_at`` is when the
    research system may first use that record. The materializer intentionally requires an exact
    observation at the Candidate Decision Time and does not carry older raw states forward.
    """

    as_of: AsOfTime
    available_at: AvailabilityTime
    symbol: str
    is_suspended: bool | None
    is_st: bool | None
    prev_close: float | None
    limit_up_price: float | None
    limit_down_price: float | None
    limit_regime: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.as_of, AsOfTime):
            raise TypeError("as_of must be an AsOfTime")
        if not isinstance(self.available_at, AvailabilityTime):
            raise TypeError("available_at must be an AvailabilityTime")
        if not isinstance(self.symbol, str) or not self.symbol.strip() or self.symbol != self.symbol.strip():
            raise ValueError("symbol must be a non-empty trimmed string")
        for label, value in (("is_suspended", self.is_suspended), ("is_st", self.is_st)):
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"{label} must be boolean or None")
        for label, value in (
            ("prev_close", self.prev_close),
            ("limit_up_price", self.limit_up_price),
            ("limit_down_price", self.limit_down_price),
        ):
            if isinstance(value, bool):
                raise TypeError(f"{label} must not be boolean")
            if value is not None and (not math.isfinite(float(value)) or float(value) <= 0.0):
                raise ValueError(f"{label} must be positive and finite when present")
        if self.limit_up_price is not None and self.limit_down_price is not None:
            if float(self.limit_down_price) >= float(self.limit_up_price):
                raise ValueError("limit_down_price must be below limit_up_price")
        if self.limit_regime is not None:
            if not isinstance(self.limit_regime, str) or not self.limit_regime.strip() or self.limit_regime != self.limit_regime.strip():
                raise ValueError("limit_regime must be a non-empty trimmed string when present")


@dataclass(frozen=True, slots=True)
class TradingEligibilityPolicy:
    """Immutable versioned Candidate-population eligibility policy.

    The v1 policy uses suspension and optional ST exclusion as eligibility rules. Previous-close and
    price-limit metadata may be required for raw-evidence completeness, but their presence alone is
    never interpreted as proof of order execution feasibility.
    """

    policy_name: str
    version: str
    exclude_st: bool = True
    require_prev_close: bool = True
    require_limit_metadata: bool = True

    def __post_init__(self) -> None:
        for label, value in (("policy_name", self.policy_name), ("version", self.version)):
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{label} must be a non-empty trimmed string")
        for label, value in (
            ("exclude_st", self.exclude_st),
            ("require_prev_close", self.require_prev_close),
            ("require_limit_metadata", self.require_limit_metadata),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{label} must be boolean")

    @property
    def policy_version(self) -> str:
        return f"{self.policy_name}@{self.version}"

    @property
    def policy_artifact_id(self) -> ArtifactId:
        payload = {
            "schema_version": "trading-eligibility-policy-v1",
            "policy_name": self.policy_name,
            "version": self.version,
            "exclude_st": self.exclude_st,
            "require_prev_close": self.require_prev_close,
            "require_limit_metadata": self.require_limit_metadata,
        }
        canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        digest = sha256(canonical.encode("utf-8")).hexdigest()
        return ArtifactId(f"trading-eligibility-policy-{digest[:24]}")

    def evaluate(
        self,
        observation: RawTradingEligibilityObservation,
    ) -> tuple[TradingEligibilityStatus, tuple[str, ...]]:
        """Evaluate one exact-time raw observation without adding execution assumptions."""

        hard_reasons: list[str] = []
        if observation.is_suspended is True:
            hard_reasons.append(TradingEligibilityReason.SUSPENDED.value)
        if self.exclude_st and observation.is_st is True:
            hard_reasons.append(TradingEligibilityReason.ST_EXCLUDED.value)
        if hard_reasons:
            return TradingEligibilityStatus.INELIGIBLE, tuple(hard_reasons)

        unknown_reasons: list[str] = []
        if observation.is_suspended is None:
            unknown_reasons.append(TradingEligibilityReason.SUSPENSION_STATUS_MISSING.value)
        if self.exclude_st and observation.is_st is None:
            unknown_reasons.append(TradingEligibilityReason.ST_STATUS_MISSING.value)
        if self.require_prev_close and observation.prev_close is None:
            unknown_reasons.append(TradingEligibilityReason.PREV_CLOSE_MISSING.value)
        if self.require_limit_metadata:
            if observation.limit_up_price is None:
                unknown_reasons.append(TradingEligibilityReason.LIMIT_UP_PRICE_MISSING.value)
            if observation.limit_down_price is None:
                unknown_reasons.append(TradingEligibilityReason.LIMIT_DOWN_PRICE_MISSING.value)
            if observation.limit_regime is None:
                unknown_reasons.append(TradingEligibilityReason.LIMIT_REGIME_MISSING.value)
        if unknown_reasons:
            return TradingEligibilityStatus.UNKNOWN, tuple(unknown_reasons)

        return TradingEligibilityStatus.ELIGIBLE, ()


def r5_rehearsal_trading_eligibility_policy_v1() -> TradingEligibilityPolicy:
    """Return the minimum explicit R5 rehearsal eligibility policy."""

    return TradingEligibilityPolicy(
        policy_name="r5-rehearsal-trading-eligibility",
        version="v1",
        exclude_st=True,
        require_prev_close=True,
        require_limit_metadata=True,
    )


def materialize_historical_trading_eligibility(
    *,
    source_dataset_id: DatasetId,
    universe_artifact: HistoricalPITUniverseArtifact,
    policy: TradingEligibilityPolicy,
    decision_times: tuple[DecisionTime, ...],
    observations: tuple[RawTradingEligibilityObservation, ...],
    raw_evidence_convention: str = EXPLICIT_RAW_ELIGIBILITY_AVAILABILITY_CONVENTION,
) -> HistoricalTradingEligibilityArtifact:
    """Materialize exact-Decision-Time eligibility for every historical Universe member.

    Missing raw observations and observations unavailable by Decision Time become explicit UNKNOWN
    records. Older observations are never carried forward implicitly. Explicit Decision Times are
    preserved even when a valid historical Universe has zero members.
    """

    if not isinstance(raw_evidence_convention, str) or not raw_evidence_convention.strip() or raw_evidence_convention != raw_evidence_convention.strip():
        raise ValueError("raw_evidence_convention must be a non-empty trimmed string")
    if not decision_times:
        raise ValueError("decision_times must not be empty")
    if len({decision_time.value for decision_time in decision_times}) != len(decision_times):
        raise ValueError("decision_times must be unique")
    ordered_decision_times = tuple(sorted(decision_times, key=lambda value: value.value))

    observation_keys = tuple((observation.as_of.value, observation.symbol) for observation in observations)
    if len(observation_keys) != len(set(observation_keys)):
        raise ValueError("raw eligibility observations must have unique time-symbol keys")
    observation_by_key = {
        (observation.as_of.value, observation.symbol): observation
        for observation in observations
    }

    records: list[HistoricalTradingEligibilityRecord] = []
    for decision_time in ordered_decision_times:
        universe_snapshot = universe_artifact.snapshot_for_decision_time(decision_time)
        as_of = AsOfTime(decision_time.value)
        for symbol in universe_snapshot.member_symbols:
            observation = observation_by_key.get((decision_time.value, symbol))
            if observation is None:
                status = TradingEligibilityStatus.UNKNOWN
                reasons = (TradingEligibilityReason.RAW_OBSERVATION_MISSING.value,)
            elif observation.available_at.value > decision_time.value:
                status = TradingEligibilityStatus.UNKNOWN
                reasons = (TradingEligibilityReason.RAW_OBSERVATION_NOT_AVAILABLE_BY_DECISION_TIME.value,)
            else:
                status, reasons = policy.evaluate(observation)
            records.append(
                HistoricalTradingEligibilityRecord(
                    as_of=as_of,
                    symbol=symbol,
                    status=status,
                    reasons=reasons,
                )
            )

    return build_historical_trading_eligibility_artifact(
        source_dataset_id=source_dataset_id,
        policy_version=policy.policy_version,
        policy_artifact_id=policy.policy_artifact_id,
        materializer_version=TRADING_ELIGIBILITY_MATERIALIZER_VERSION,
        raw_evidence_convention=raw_evidence_convention,
        records=tuple(records),
        snapshot_as_of_times=tuple(AsOfTime(decision_time.value) for decision_time in ordered_decision_times),
    )
