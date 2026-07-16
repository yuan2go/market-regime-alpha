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


class DecisionBuyabilityStatus(str, Enum):
    """Explicit Candidate-population buyability evidence at the Decision Time.

    BUYABLE is not a guarantee of fill probability or final Execution Feasibility. It only means
    the identified evidence source did not classify the instrument as blocked by the scoped
    Decision-Time buyability rule.
    """

    BUYABLE = "BUYABLE"
    NOT_BUYABLE = "NOT_BUYABLE"
    UNKNOWN = "UNKNOWN"


class TradingEligibilityReason(str, Enum):
    """Canonical reason codes emitted by versioned Trading Eligibility policies."""

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
    LISTING_AGE_MISSING = "LISTING_AGE_MISSING"
    LISTING_AGE_BELOW_MINIMUM = "LISTING_AGE_BELOW_MINIMUM"
    LIQUIDITY_VALUE_MISSING = "LIQUIDITY_VALUE_MISSING"
    LIQUIDITY_MEASURE_MISSING = "LIQUIDITY_MEASURE_MISSING"
    LIQUIDITY_MEASURE_MISMATCH = "LIQUIDITY_MEASURE_MISMATCH"
    LIQUIDITY_BELOW_MINIMUM = "LIQUIDITY_BELOW_MINIMUM"
    DECISION_BUYABILITY_MISSING = "DECISION_BUYABILITY_MISSING"
    DECISION_BUYABILITY_UNKNOWN = "DECISION_BUYABILITY_UNKNOWN"
    DECISION_NOT_BUYABLE = "DECISION_NOT_BUYABLE"


@dataclass(frozen=True, slots=True)
class RawTradingEligibilityObservation:
    """Raw historical eligibility evidence at one exact information-state time.

    ``as_of`` is the state timestamp represented by the raw record. ``available_at`` is when the
    research system may first use that record. The materializer intentionally requires an exact
    observation at the Candidate Decision Time and does not carry older raw states forward.

    The provider-rehearsal v2 fields are optional so Legacy/v1 observations remain readable. A v2
    policy treats missing required v2 evidence as UNKNOWN rather than silently downgrading to v1.
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
    listing_age_calendar_days: int | None = None
    liquidity_value: float | None = None
    liquidity_measure_id: str | None = None
    decision_buyability: DecisionBuyabilityStatus | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.as_of, AsOfTime):
            raise TypeError("as_of must be an AsOfTime")
        if not isinstance(self.available_at, AvailabilityTime):
            raise TypeError("available_at must be an AvailabilityTime")
        if not isinstance(self.symbol, str) or not self.symbol.strip() or self.symbol != self.symbol.strip():
            raise ValueError("symbol must be a non-empty trimmed string")
        for label, boolean_evidence in (
            ("is_suspended", self.is_suspended),
            ("is_st", self.is_st),
        ):
            if boolean_evidence is not None and not isinstance(boolean_evidence, bool):
                raise TypeError(f"{label} must be boolean or None")
        for label, numeric_evidence in (
            ("prev_close", self.prev_close),
            ("limit_up_price", self.limit_up_price),
            ("limit_down_price", self.limit_down_price),
            ("liquidity_value", self.liquidity_value),
        ):
            if isinstance(numeric_evidence, bool):
                raise TypeError(f"{label} must not be boolean")
            if numeric_evidence is not None and (
                not math.isfinite(float(numeric_evidence))
                or float(numeric_evidence) <= 0.0
            ):
                raise ValueError(f"{label} must be positive and finite when present")
        if self.limit_up_price is not None and self.limit_down_price is not None:
            if float(self.limit_down_price) >= float(self.limit_up_price):
                raise ValueError("limit_down_price must be below limit_up_price")
        if self.limit_regime is not None:
            if not isinstance(self.limit_regime, str) or not self.limit_regime.strip() or self.limit_regime != self.limit_regime.strip():
                raise ValueError("limit_regime must be a non-empty trimmed string when present")
        if self.listing_age_calendar_days is not None:
            if isinstance(self.listing_age_calendar_days, bool) or not isinstance(self.listing_age_calendar_days, int):
                raise TypeError("listing_age_calendar_days must be an integer or None")
            if self.listing_age_calendar_days < 0:
                raise ValueError("listing_age_calendar_days must be non-negative")
        if self.liquidity_measure_id is not None:
            if not isinstance(self.liquidity_measure_id, str) or not self.liquidity_measure_id.strip() or self.liquidity_measure_id != self.liquidity_measure_id.strip():
                raise ValueError("liquidity_measure_id must be a non-empty trimmed string when present")
        if (self.liquidity_value is None) != (self.liquidity_measure_id is None):
            raise ValueError("liquidity_value and liquidity_measure_id must be present together")
        if self.decision_buyability is not None and not isinstance(self.decision_buyability, DecisionBuyabilityStatus):
            raise TypeError("decision_buyability must be a DecisionBuyabilityStatus or None")


@dataclass(frozen=True, slots=True)
class TradingEligibilityPolicy:
    """Immutable versioned Candidate-population eligibility policy.

    The v1 configuration uses suspension and optional ST exclusion as hard eligibility rules.
    Provider-rehearsal v2 additionally supports explicit listing-age, PIT-liquidity and
    Decision-Time buyability requirements. BUYABLE remains distinct from final execution/fillability.
    """

    policy_name: str
    version: str
    exclude_st: bool = True
    require_prev_close: bool = True
    require_limit_metadata: bool = True
    minimum_listing_age_calendar_days: int | None = None
    minimum_liquidity_value: float | None = None
    liquidity_measure_id: str | None = None
    require_decision_buyability: bool = False

    def __post_init__(self) -> None:
        for label, text_value in (
            ("policy_name", self.policy_name),
            ("version", self.version),
        ):
            if (
                not isinstance(text_value, str)
                or not text_value.strip()
                or text_value != text_value.strip()
            ):
                raise ValueError(f"{label} must be a non-empty trimmed string")
        for label, boolean_value in (
            ("exclude_st", self.exclude_st),
            ("require_prev_close", self.require_prev_close),
            ("require_limit_metadata", self.require_limit_metadata),
            ("require_decision_buyability", self.require_decision_buyability),
        ):
            if not isinstance(boolean_value, bool):
                raise TypeError(f"{label} must be boolean")
        if self.minimum_listing_age_calendar_days is not None:
            if isinstance(self.minimum_listing_age_calendar_days, bool) or not isinstance(self.minimum_listing_age_calendar_days, int):
                raise TypeError("minimum_listing_age_calendar_days must be an integer or None")
            if self.minimum_listing_age_calendar_days < 0:
                raise ValueError("minimum_listing_age_calendar_days must be non-negative")
        if isinstance(self.minimum_liquidity_value, bool):
            raise TypeError("minimum_liquidity_value must not be boolean")
        if self.minimum_liquidity_value is not None:
            if not math.isfinite(float(self.minimum_liquidity_value)) or float(self.minimum_liquidity_value) <= 0.0:
                raise ValueError("minimum_liquidity_value must be positive and finite when present")
        if self.liquidity_measure_id is not None:
            if not isinstance(self.liquidity_measure_id, str) or not self.liquidity_measure_id.strip() or self.liquidity_measure_id != self.liquidity_measure_id.strip():
                raise ValueError("liquidity_measure_id must be a non-empty trimmed string when present")
        if (self.minimum_liquidity_value is None) != (self.liquidity_measure_id is None):
            raise ValueError("minimum_liquidity_value and liquidity_measure_id must be configured together")

    @property
    def policy_version(self) -> str:
        return f"{self.policy_name}@{self.version}"

    @property
    def uses_provider_rehearsal_v2_evidence(self) -> bool:
        return any(
            (
                self.minimum_listing_age_calendar_days is not None,
                self.minimum_liquidity_value is not None,
                self.liquidity_measure_id is not None,
                self.require_decision_buyability,
            )
        )

    @property
    def policy_artifact_id(self) -> ArtifactId:
        if not self.uses_provider_rehearsal_v2_evidence:
            payload = {
                "schema_version": "trading-eligibility-policy-v1",
                "policy_name": self.policy_name,
                "version": self.version,
                "exclude_st": self.exclude_st,
                "require_prev_close": self.require_prev_close,
                "require_limit_metadata": self.require_limit_metadata,
            }
        else:
            payload = {
                "schema_version": "trading-eligibility-policy-v2",
                "policy_name": self.policy_name,
                "version": self.version,
                "exclude_st": self.exclude_st,
                "require_prev_close": self.require_prev_close,
                "require_limit_metadata": self.require_limit_metadata,
                "minimum_listing_age_calendar_days": self.minimum_listing_age_calendar_days,
                "minimum_liquidity_value": self.minimum_liquidity_value,
                "liquidity_measure_id": self.liquidity_measure_id,
                "require_decision_buyability": self.require_decision_buyability,
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
        if self.minimum_listing_age_calendar_days is not None and observation.listing_age_calendar_days is not None:
            if observation.listing_age_calendar_days < self.minimum_listing_age_calendar_days:
                hard_reasons.append(TradingEligibilityReason.LISTING_AGE_BELOW_MINIMUM.value)
        if self.minimum_liquidity_value is not None and observation.liquidity_value is not None and observation.liquidity_measure_id == self.liquidity_measure_id:
            if float(observation.liquidity_value) < float(self.minimum_liquidity_value):
                hard_reasons.append(TradingEligibilityReason.LIQUIDITY_BELOW_MINIMUM.value)
        if self.require_decision_buyability and observation.decision_buyability is DecisionBuyabilityStatus.NOT_BUYABLE:
            hard_reasons.append(TradingEligibilityReason.DECISION_NOT_BUYABLE.value)
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
        if self.minimum_listing_age_calendar_days is not None and observation.listing_age_calendar_days is None:
            unknown_reasons.append(TradingEligibilityReason.LISTING_AGE_MISSING.value)
        if self.minimum_liquidity_value is not None:
            if observation.liquidity_value is None:
                unknown_reasons.append(TradingEligibilityReason.LIQUIDITY_VALUE_MISSING.value)
            if observation.liquidity_measure_id is None:
                unknown_reasons.append(TradingEligibilityReason.LIQUIDITY_MEASURE_MISSING.value)
            elif observation.liquidity_measure_id != self.liquidity_measure_id:
                unknown_reasons.append(TradingEligibilityReason.LIQUIDITY_MEASURE_MISMATCH.value)
        if self.require_decision_buyability:
            if observation.decision_buyability is None:
                unknown_reasons.append(TradingEligibilityReason.DECISION_BUYABILITY_MISSING.value)
            elif observation.decision_buyability is DecisionBuyabilityStatus.UNKNOWN:
                unknown_reasons.append(TradingEligibilityReason.DECISION_BUYABILITY_UNKNOWN.value)
        if unknown_reasons:
            return TradingEligibilityStatus.UNKNOWN, tuple(unknown_reasons)

        return TradingEligibilityStatus.ELIGIBLE, ()


def r5_rehearsal_trading_eligibility_policy_v1() -> TradingEligibilityPolicy:
    """Return the minimum Legacy-compatible R5 rehearsal eligibility policy."""

    return TradingEligibilityPolicy(
        policy_name="r5-rehearsal-trading-eligibility",
        version="v1",
        exclude_st=True,
        require_prev_close=True,
        require_limit_metadata=True,
    )


def r5_provider_rehearsal_trading_eligibility_policy_v2(
    *,
    minimum_liquidity_value: float,
    liquidity_measure_id: str,
    minimum_listing_age_calendar_days: int = 61,
) -> TradingEligibilityPolicy:
    """Return the provider-rehearsal policy covering the original minimum Candidate-pool scope.

    The default of 61 calendar days implements the preserved original requirement "listed for more
    than 60 days". The liquidity threshold is deliberately required from the caller rather than
    hidden as a global default. Decision-Time buyability must come from an identified provider/
    adapter evidence contract.
    """

    return TradingEligibilityPolicy(
        policy_name="r5-provider-rehearsal-trading-eligibility",
        version="v2",
        exclude_st=True,
        require_prev_close=True,
        require_limit_metadata=True,
        minimum_listing_age_calendar_days=minimum_listing_age_calendar_days,
        minimum_liquidity_value=minimum_liquidity_value,
        liquidity_measure_id=liquidity_measure_id,
        require_decision_buyability=True,
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
            status: TradingEligibilityStatus
            reasons: tuple[str, ...]
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
