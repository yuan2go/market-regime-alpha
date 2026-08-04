"""Versioned factor-requirement and trading-session freshness policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data import Timeframe
from market_regime_alpha.market_data.contracts import require_utc_second
from market_regime_alpha.signals.input_assembly import SignalFactorName


SIGNAL_FACTOR_REQUIREMENT_POLICY_SCHEMA = "signal-factor-requirement-policy-v1"
SIGNAL_FACTOR_FRESHNESS_POLICY_SCHEMA = "signal-factor-freshness-policy-v1"


class SignalFactorRequirementMode(str, Enum):
    ALL_FACTORS_REQUIRED = "ALL_FACTORS_REQUIRED"
    DECLARED_REQUIRED_FACTORS = "DECLARED_REQUIRED_FACTORS"
    REQUIRED_PLUS_MINIMUM_TOTAL = "REQUIRED_PLUS_MINIMUM_TOTAL"


@dataclass(frozen=True, slots=True)
class SignalFactorRequirementAssessment:
    sufficient: bool
    missing_required_factors: tuple[SignalFactorName, ...]
    available_factor_count: int
    minimum_factor_count: int
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SignalFactorRequirementPolicy:
    schema_version: str
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    mode: SignalFactorRequirementMode
    required_factors: tuple[SignalFactorName, ...]
    minimum_factor_count: int

    @property
    def configuration_id(self) -> ArtifactId:
        return self.policy_id

    @property
    def configuration_hash(self) -> str:
        return self.policy_hash

    def __post_init__(self) -> None:
        if self.schema_version != SIGNAL_FACTOR_REQUIREMENT_POLICY_SCHEMA:
            raise ValueError("unsupported Signal Factor Requirement Policy schema")
        require_sha256("policy_hash", self.policy_hash)
        require_text("policy_version", self.policy_version)
        expected = tuple(sorted(set(self.required_factors), key=lambda item: item.value))
        if self.required_factors != expected:
            raise ValueError("required factors must be unique and sorted")
        factor_count = len(SignalFactorName)
        if isinstance(self.minimum_factor_count, bool) or not (
            0 <= self.minimum_factor_count <= factor_count
        ):
            raise ValueError("minimum_factor_count is outside the factor count")
        all_factors = tuple(sorted(SignalFactorName, key=lambda item: item.value))
        if self.mode is SignalFactorRequirementMode.ALL_FACTORS_REQUIRED:
            if self.required_factors != all_factors or self.minimum_factor_count != factor_count:
                raise ValueError("ALL_FACTORS_REQUIRED must require the complete factor set")
        elif self.mode is SignalFactorRequirementMode.DECLARED_REQUIRED_FACTORS:
            if self.minimum_factor_count != len(self.required_factors):
                raise ValueError(
                    "DECLARED_REQUIRED_FACTORS minimum must equal required factor count"
                )
        elif self.minimum_factor_count < len(self.required_factors):
            raise ValueError("minimum_factor_count cannot be below required factor count")

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        mode: SignalFactorRequirementMode,
        required_factors: tuple[SignalFactorName, ...],
        minimum_factor_count: int,
    ) -> SignalFactorRequirementPolicy:
        ordered = tuple(sorted(required_factors, key=lambda item: item.value))
        semantic = _requirement_payload(
            policy_version=policy_version,
            mode=mode,
            required_factors=ordered,
            minimum_factor_count=minimum_factor_count,
        )
        policy_hash = canonical_hash(semantic)
        result = cls(
            schema_version=SIGNAL_FACTOR_REQUIREMENT_POLICY_SCHEMA,
            policy_id=ArtifactId(
                f"signal-factor-requirement-{policy_hash.split(':', 1)[1][:24]}"
            ),
            policy_hash=policy_hash,
            policy_version=policy_version,
            mode=mode,
            required_factors=ordered,
            minimum_factor_count=minimum_factor_count,
        )
        result.verify_identity()
        return result

    def validate_mapping_requirements(
        self, required_by_factor: Mapping[SignalFactorName, bool]
    ) -> None:
        if set(required_by_factor) != set(SignalFactorName):
            raise ValueError("Signal mapping must declare required for every factor")
        declared = tuple(
            sorted(
                (factor for factor, required in required_by_factor.items() if required),
                key=lambda item: item.value,
            )
        )
        if declared != self.required_factors:
            raise ValueError("Signal mapping required flags conflict with Requirement Policy")

    def assess(
        self, values: Mapping[SignalFactorName, object | None]
    ) -> SignalFactorRequirementAssessment:
        if set(values) != set(SignalFactorName):
            raise ValueError("Requirement assessment must cover every Signal factor")
        missing_required = tuple(
            factor for factor in self.required_factors if values[factor] is None
        )
        available = sum(value is not None for value in values.values())
        reasons = {
            *(f"REQUIRED_FACTOR_{item.value}_MISSING" for item in missing_required)
        }
        if available < self.minimum_factor_count:
            reasons.add("MINIMUM_SIGNAL_FACTOR_COUNT_NOT_MET")
        sufficient = not reasons
        if sufficient:
            reasons.add("SIGNAL_FACTOR_REQUIREMENTS_SATISFIED")
        return SignalFactorRequirementAssessment(
            sufficient=sufficient,
            missing_required_factors=missing_required,
            available_factor_count=available,
            minimum_factor_count=self.minimum_factor_count,
            reason_codes=tuple(sorted(reasons)),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _requirement_payload(
            policy_version=self.policy_version,
            mode=self.mode,
            required_factors=self.required_factors,
            minimum_factor_count=self.minimum_factor_count,
        )

    def verify_identity(self) -> None:
        expected = canonical_hash(self.semantic_payload())
        if self.policy_hash != expected:
            raise ValueError("Signal Factor Requirement Policy hash mismatch")
        if str(self.policy_id) != (
            f"signal-factor-requirement-{expected.split(':', 1)[1][:24]}"
        ):
            raise ValueError("Signal Factor Requirement Policy identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> SignalFactorRequirementPolicy:
        expected = {
            "schema_version",
            "policy_id",
            "policy_hash",
            "policy_version",
            "mode",
            "required_factors",
            "minimum_factor_count",
        }
        if set(payload) != expected:
            raise ValueError("Signal Factor Requirement Policy fields mismatch")
        raw_factors = payload["required_factors"]
        if not isinstance(raw_factors, list):
            raise ValueError("required_factors must be an array")
        result = cls(
            schema_version=str(payload["schema_version"]),
            policy_id=ArtifactId(str(payload["policy_id"])),
            policy_hash=str(payload["policy_hash"]),
            policy_version=str(payload["policy_version"]),
            mode=SignalFactorRequirementMode(str(payload["mode"])),
            required_factors=tuple(SignalFactorName(str(item)) for item in raw_factors),
            minimum_factor_count=_integer(payload["minimum_factor_count"], "minimum_factor_count"),
        )
        result.verify_identity()
        return result


class SignalFactorFreshnessMode(str, Enum):
    TRADING_SESSION_DISTANCE = "TRADING_SESSION_DISTANCE"
    ELAPSED_SECONDS = "ELAPSED_SECONDS"
    SAME_TRADING_SESSION = "SAME_TRADING_SESSION"


class FactorFreshnessState(str, Enum):
    FRESH = "FRESH"
    FUTURE = "FUTURE"
    STALE = "STALE"
    CALENDAR_INSUFFICIENT = "CALENDAR_INSUFFICIENT"
    OUTSIDE_TRADING_SESSION = "OUTSIDE_TRADING_SESSION"


@dataclass(frozen=True, slots=True)
class SignalFactorFreshnessRule:
    factor_name: SignalFactorName
    modes: tuple[SignalFactorFreshnessMode, ...]
    maximum_session_lag: int | None
    maximum_elapsed_seconds: int | None

    def __post_init__(self) -> None:
        if not self.modes or self.modes != tuple(sorted(set(self.modes), key=lambda item: item.value)):
            raise ValueError("freshness modes must be non-empty, unique, and sorted")
        session_mode = SignalFactorFreshnessMode.TRADING_SESSION_DISTANCE in self.modes
        elapsed_mode = SignalFactorFreshnessMode.ELAPSED_SECONDS in self.modes
        if session_mode != (self.maximum_session_lag is not None):
            raise ValueError("maximum_session_lag must exactly match session-distance mode")
        if elapsed_mode != (self.maximum_elapsed_seconds is not None):
            raise ValueError("maximum_elapsed_seconds must exactly match elapsed mode")
        if self.maximum_session_lag is not None and self.maximum_session_lag < 0:
            raise ValueError("maximum_session_lag must be non-negative")
        if self.maximum_elapsed_seconds is not None and self.maximum_elapsed_seconds <= 0:
            raise ValueError("maximum_elapsed_seconds must be positive")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "factor_name": self.factor_name.value,
            "modes": [item.value for item in self.modes],
            "maximum_session_lag": self.maximum_session_lag,
            "maximum_elapsed_seconds": self.maximum_elapsed_seconds,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> SignalFactorFreshnessRule:
        if set(payload) != {
            "factor_name",
            "modes",
            "maximum_session_lag",
            "maximum_elapsed_seconds",
        }:
            raise ValueError("Signal Factor Freshness Rule fields mismatch")
        raw_modes = payload["modes"]
        if not isinstance(raw_modes, list):
            raise ValueError("freshness modes must be an array")
        return cls(
            factor_name=SignalFactorName(str(payload["factor_name"])),
            modes=tuple(SignalFactorFreshnessMode(str(item)) for item in raw_modes),
            maximum_session_lag=_optional_integer(payload["maximum_session_lag"]),
            maximum_elapsed_seconds=_optional_integer(payload["maximum_elapsed_seconds"]),
        )


@dataclass(frozen=True, slots=True)
class SignalFactorFreshnessAssessment:
    state: FactorFreshnessState
    session_date: str | None
    session_lag: int | None
    elapsed_seconds: int | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SignalFactorFreshnessPolicy:
    schema_version: str
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    trading_calendar_id: ArtifactId
    trading_calendar_hash: str
    rules: tuple[SignalFactorFreshnessRule, ...]

    @property
    def configuration_id(self) -> ArtifactId:
        return self.policy_id

    @property
    def configuration_hash(self) -> str:
        return self.policy_hash

    def __post_init__(self) -> None:
        if self.schema_version != SIGNAL_FACTOR_FRESHNESS_POLICY_SCHEMA:
            raise ValueError("unsupported Signal Factor Freshness Policy schema")
        require_sha256("policy_hash", self.policy_hash)
        require_sha256("trading_calendar_hash", self.trading_calendar_hash)
        require_text("policy_version", self.policy_version)
        factors = tuple(item.factor_name.value for item in self.rules)
        if factors != tuple(sorted(item.value for item in SignalFactorName)):
            raise ValueError("freshness rules must exactly cover Signal factors")

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        trading_calendar: TradingCalendarArtifact,
        rules: tuple[SignalFactorFreshnessRule, ...],
    ) -> SignalFactorFreshnessPolicy:
        ordered = tuple(sorted(rules, key=lambda item: item.factor_name.value))
        semantic = _freshness_payload(
            policy_version=policy_version,
            trading_calendar_id=trading_calendar.artifact_id,
            trading_calendar_hash=trading_calendar.content_hash,
            rules=ordered,
        )
        policy_hash = canonical_hash(semantic)
        result = cls(
            schema_version=SIGNAL_FACTOR_FRESHNESS_POLICY_SCHEMA,
            policy_id=ArtifactId(
                f"signal-factor-freshness-{policy_hash.split(':', 1)[1][:24]}"
            ),
            policy_hash=policy_hash,
            policy_version=policy_version,
            trading_calendar_id=trading_calendar.artifact_id,
            trading_calendar_hash=trading_calendar.content_hash,
            rules=ordered,
        )
        result.verify_identity()
        return result

    def assess(
        self,
        *,
        factor_name: SignalFactorName,
        source_available_at: datetime,
        decision_time: datetime,
        timeframe: Timeframe,
        trading_calendar: TradingCalendarArtifact,
    ) -> SignalFactorFreshnessAssessment:
        require_utc_second("source_available_at", source_available_at)
        require_utc_second("decision_time", decision_time)
        if (
            trading_calendar.artifact_id != self.trading_calendar_id
            or trading_calendar.content_hash != self.trading_calendar_hash
        ):
            raise ValueError("TradingCalendar identity does not match Freshness Policy")
        rule = next(item for item in self.rules if item.factor_name is factor_name)
        if source_available_at > decision_time:
            return SignalFactorFreshnessAssessment(
                FactorFreshnessState.FUTURE,
                None,
                None,
                None,
                ("FACTOR_EVIDENCE_FROM_FUTURE",),
            )
        zone = ZoneInfo(trading_calendar.timezone_name)
        source_local = source_available_at.astimezone(zone)
        decision_local = decision_time.astimezone(zone)
        source_date = source_local.date()
        decision_date = decision_local.date()
        session_lag: int | None = None
        elapsed_seconds: int | None = None
        reasons: set[str] = set()
        if SignalFactorFreshnessMode.TRADING_SESSION_DISTANCE in rule.modes:
            completed_dates = tuple(
                item.trade_date
                for item in trading_calendar.sessions
                if item.session_close.astimezone(zone) <= decision_local
            )
            if not completed_dates or source_date not in trading_calendar.trading_dates:
                reasons.add("TRADING_CALENDAR_COVERAGE_INSUFFICIENT")
            else:
                latest = completed_dates[-1]
                dates = trading_calendar.trading_dates
                source_index = dates.index(source_date)
                latest_index = dates.index(latest)
                session_lag = latest_index - source_index
                if session_lag < 0:
                    reasons.add("FACTOR_EVIDENCE_FROM_FUTURE_SESSION")
                elif rule.maximum_session_lag is not None and session_lag > rule.maximum_session_lag:
                    reasons.add("FACTOR_EVIDENCE_STALE_SESSION_DISTANCE")
        if SignalFactorFreshnessMode.SAME_TRADING_SESSION in rule.modes:
            if source_date != decision_date or not trading_calendar.contains(decision_date):
                reasons.add("FACTOR_NOT_FROM_DECISION_TRADING_SESSION")
            elif not _inside_session(source_local.time(), decision_local.time(), trading_calendar, decision_date):
                reasons.add("FACTOR_TIME_OUTSIDE_TRADING_SESSION")
        if SignalFactorFreshnessMode.ELAPSED_SECONDS in rule.modes:
            elapsed_seconds = int((decision_time - source_available_at).total_seconds())
            if rule.maximum_elapsed_seconds is not None and elapsed_seconds > rule.maximum_elapsed_seconds:
                reasons.add("FACTOR_EVIDENCE_STALE_ELAPSED_SECONDS")
        state = (
            FactorFreshnessState.CALENDAR_INSUFFICIENT
            if "TRADING_CALENDAR_COVERAGE_INSUFFICIENT" in reasons
            else FactorFreshnessState.OUTSIDE_TRADING_SESSION
            if any("TRADING_SESSION" in item and item != "FACTOR_EVIDENCE_STALE_SESSION_DISTANCE" for item in reasons)
            else FactorFreshnessState.FUTURE
            if any("FUTURE" in item for item in reasons)
            else FactorFreshnessState.STALE
            if reasons
            else FactorFreshnessState.FRESH
        )
        return SignalFactorFreshnessAssessment(
            state=state,
            session_date=source_date.isoformat(),
            session_lag=session_lag,
            elapsed_seconds=elapsed_seconds,
            reason_codes=tuple(sorted(reasons or {"FACTOR_FRESH"})),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _freshness_payload(
            policy_version=self.policy_version,
            trading_calendar_id=self.trading_calendar_id,
            trading_calendar_hash=self.trading_calendar_hash,
            rules=self.rules,
        )

    def verify_identity(self) -> None:
        expected = canonical_hash(self.semantic_payload())
        if self.policy_hash != expected:
            raise ValueError("Signal Factor Freshness Policy hash mismatch")
        if str(self.policy_id) != f"signal-factor-freshness-{expected.split(':', 1)[1][:24]}":
            raise ValueError("Signal Factor Freshness Policy identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> SignalFactorFreshnessPolicy:
        if set(payload) != {
            "schema_version",
            "policy_id",
            "policy_hash",
            "policy_version",
            "trading_calendar_id",
            "trading_calendar_hash",
            "rules",
        }:
            raise ValueError("Signal Factor Freshness Policy fields mismatch")
        raw_rules = payload["rules"]
        if not isinstance(raw_rules, list):
            raise ValueError("freshness rules must be an array")
        result = cls(
            schema_version=str(payload["schema_version"]),
            policy_id=ArtifactId(str(payload["policy_id"])),
            policy_hash=str(payload["policy_hash"]),
            policy_version=str(payload["policy_version"]),
            trading_calendar_id=ArtifactId(str(payload["trading_calendar_id"])),
            trading_calendar_hash=str(payload["trading_calendar_hash"]),
            rules=tuple(SignalFactorFreshnessRule.from_canonical_dict(item) for item in raw_rules if isinstance(item, dict)),
        )
        if len(result.rules) != len(raw_rules):
            raise ValueError("freshness rule fields mismatch")
        result.verify_identity()
        return result


def canonical_all_factors_required_policy() -> SignalFactorRequirementPolicy:
    return SignalFactorRequirementPolicy.create(
        policy_version="canonical-five-factor-all-required-v1",
        mode=SignalFactorRequirementMode.ALL_FACTORS_REQUIRED,
        required_factors=tuple(sorted(SignalFactorName, key=lambda item: item.value)),
        minimum_factor_count=len(SignalFactorName),
    )


def canonical_signal_freshness_policy(
    *, trading_calendar: TradingCalendarArtifact
) -> SignalFactorFreshnessPolicy:
    daily_modes = (SignalFactorFreshnessMode.TRADING_SESSION_DISTANCE,)
    intraday_modes = tuple(
        sorted(
            (
                SignalFactorFreshnessMode.ELAPSED_SECONDS,
                SignalFactorFreshnessMode.SAME_TRADING_SESSION,
            ),
            key=lambda item: item.value,
        )
    )
    rules = tuple(
        SignalFactorFreshnessRule(
            factor_name=factor,
            modes=(intraday_modes if factor is SignalFactorName.PRICE_VS_VWAP_RETURN else daily_modes),
            maximum_session_lag=(None if factor is SignalFactorName.PRICE_VS_VWAP_RETURN else 1),
            maximum_elapsed_seconds=(900 if factor is SignalFactorName.PRICE_VS_VWAP_RETURN else None),
        )
        for factor in sorted(SignalFactorName, key=lambda item: item.value)
    )
    return SignalFactorFreshnessPolicy.create(
        policy_version="canonical-a-share-session-freshness-v1",
        trading_calendar=trading_calendar,
        rules=rules,
    )


def _inside_session(
    source_time: time,
    decision_time: time,
    calendar: TradingCalendarArtifact,
    decision_date: object,
) -> bool:
    session = next(
        (item for item in calendar.sessions if item.trade_date == decision_date), None
    )
    if session is None:
        return False
    close_time = session.session_close.astimezone(ZoneInfo(calendar.timezone_name)).time()
    regular_source = (
        time(9, 30) <= source_time <= time(11, 30)
        or time(13, 0) <= source_time <= close_time
    )
    regular_decision = (
        time(9, 30) <= decision_time <= time(11, 30)
        or time(13, 0) <= decision_time <= close_time
    )
    return regular_source and regular_decision


def _requirement_payload(
    *,
    policy_version: str,
    mode: SignalFactorRequirementMode,
    required_factors: tuple[SignalFactorName, ...],
    minimum_factor_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_FACTOR_REQUIREMENT_POLICY_SCHEMA,
        "policy_version": policy_version,
        "mode": mode.value,
        "required_factors": [item.value for item in required_factors],
        "minimum_factor_count": minimum_factor_count,
    }


def _freshness_payload(
    *,
    policy_version: str,
    trading_calendar_id: ArtifactId,
    trading_calendar_hash: str,
    rules: tuple[SignalFactorFreshnessRule, ...],
) -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_FACTOR_FRESHNESS_POLICY_SCHEMA,
        "policy_version": policy_version,
        "trading_calendar_id": str(trading_calendar_id),
        "trading_calendar_hash": trading_calendar_hash,
        "rules": [item.to_canonical_dict() for item in rules],
    }


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _optional_integer(value: object) -> int | None:
    return None if value is None else _integer(value, "optional integer")


__all__ = [
    "FactorFreshnessState",
    "SignalFactorFreshnessAssessment",
    "SignalFactorFreshnessMode",
    "SignalFactorFreshnessPolicy",
    "SignalFactorFreshnessRule",
    "SignalFactorRequirementAssessment",
    "SignalFactorRequirementMode",
    "SignalFactorRequirementPolicy",
    "canonical_all_factors_required_policy",
    "canonical_signal_freshness_policy",
]
